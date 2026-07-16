from __future__ import annotations

import base64
import mimetypes
import re
import unicodedata
from collections.abc import Iterator
from email import policy
from email.header import decode_header, make_header
from email.message import Message
from email.parser import BytesParser
from email.utils import collapse_rfc2231_value, getaddresses, parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import PurePath
from urllib.parse import urlsplit

from mailbox_manager.domain.models import MailAttachment, MailMessage

MAX_RAW_MESSAGE_SIZE = 25 * 1024 * 1024
MAX_BODY_LENGTH = 500_000
MAX_HTML_SOURCE_LENGTH = 2_000_000
MAX_STORED_HTML_LENGTH = 12 * 1024 * 1024
MAX_INLINE_IMAGE_SIZE = 4 * 1024 * 1024
MAX_ATTACHMENT_COUNT = 100
MAX_ATTACHMENT_SIZE = MAX_RAW_MESSAGE_SIZE
MAX_TOTAL_ATTACHMENT_SIZE = MAX_RAW_MESSAGE_SIZE
MAX_ATTACHMENT_FILENAME_LENGTH = 180
MATCH_TEXT_LIMIT = 50_000
CODE_PATTERN = re.compile(r"(?<![\w-])\d{4,8}(?!\d)")
UNSAFE_PATTERN = re.compile(r"\([^)]*[+*][^)]*\)[+*{]|\\[1-9]")
_HTML_TAG_PATTERN = re.compile(
    r"(?is)<\s*(?:html|body|div|p|span|table|tr|td|br|h[1-6]|img|a)\b"
)
_ENCODED_TAG_PATTERN = re.compile(
    r"(?is)&lt;\s*/?\s*(?:html|body|head|style|div|p|span|table|tr|td|br|img|a)\b"
)
_CSS_BLOCK_PATTERN = re.compile(
    r"(?is)<(?:style|script|head|svg|noscript|template)\b[^>]*>.*?"
    r"</(?:style|script|head|svg|noscript|template)>"
)
_HTML_COMMENT_PATTERN = re.compile(r"(?is)<!--.*?-->")
_DATA_IMAGE_PATTERN = re.compile(
    r"(?is)^data:(image/(?:png|jpeg|jpg|gif|webp));base64,([a-z0-9+/=\s]+)$"
)
_CSS_BACKGROUND_URL_PATTERN = re.compile(
    r"(?is)background(?:-image)?\s*:[^;{}]*?url\(\s*"
    r"(?:\"([^\"]*)\"|'([^']*)'|([^)'\"]*?))\s*\)"
)
_SRCSET_SEPARATOR = re.compile(
    r"(?i)\s*,\s*(?=(?:https?:)?//|cid:|data:image/(?:png|jpeg|jpg|gif|webp))"
)
_SRCSET_DESCRIPTOR = re.compile(r"(?i)\s+\d+(?:\.\d+)?[wx]\s*$")
_LAZY_IMAGE_ATTRIBUTES = (
    "data-src",
    "data-original",
    "data-lazy-src",
    "data-url",
)
_SRCSET_ATTRIBUTES = ("data-srcset", "srcset")
MAX_IMAGE_REFERENCE_LENGTH = 4096
_WINDOWS_RESERVED_NAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def repair_mojibake(value: str) -> str:
    """Repair common UTF-8 decoding mistakes only when the candidate is clearly better."""

    def score(text: str) -> int:
        latin_markers = ("Ã", "Â", "â€", "â€™", "â€œ", "â€\x9d", "ðŸ", "ï»¿")
        chinese_markers = ("浣犲", "鐨勶", "銆傛", "锛屾", "鏄")
        return text.count("\ufffd") * 20 + sum(
            text.count(marker) * 3 for marker in (*latin_markers, *chinese_markers)
        )

    original_score = score(value)
    if original_score == 0:
        return value
    candidates = [value]
    for source_encoding in ("latin1", "cp1252", "gb18030"):
        try:
            candidates.append(value.encode(source_encoding).decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    best = min(candidates, key=score)
    return best if score(best) + 2 <= original_score else value


def normalize_email_html(value: str) -> str:
    """Normalize provider HTML, including Outlook bodies containing escaped markup."""

    normalized = repair_mojibake(value[:MAX_HTML_SOURCE_LENGTH]).replace("\x00", "")
    for _ in range(3):
        if not _ENCODED_TAG_PATTERN.search(normalized):
            break
        decoded = unescape(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    return normalized


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in {"style", "script", "head", "svg", "noscript", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in {"br", "p", "div", "li", "tr", "table", "td", "th", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"style", "script", "head", "svg", "noscript", "template"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag in {"p", "div", "li", "tr", "table", "td", "th", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


_SAFE_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "del",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}
_VOID_TAGS = {"br", "hr", "img"}
_BLOCKED_CONTAINER_TAGS = {
    "applet",
    "form",
    "frameset",
    "head",
    "iframe",
    "noscript",
    "object",
    "script",
    "style",
    "svg",
    "template",
}
_BLOCKED_VOID_TAGS = {"embed", "frame", "input", "meta"}
_BLOCKED_TAGS = _BLOCKED_CONTAINER_TAGS | _BLOCKED_VOID_TAGS
_SAFE_IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}


def _data_image_uri(content_type: str, payload: bytes) -> str:
    mime = content_type.casefold().split(";", 1)[0].strip()
    if mime not in _SAFE_IMAGE_MIMES or not payload or len(payload) > MAX_INLINE_IMAGE_SIZE:
        return ""
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _normalize_image_reference(value: str) -> str:
    source = unescape(value).strip()
    if (
        not source
        or len(source) > MAX_IMAGE_REFERENCE_LENGTH
        or any(ord(character) < 32 for character in source)
    ):
        return ""
    if source.startswith("//"):
        source = "https:" + source
    lowered = source.casefold()
    if lowered.startswith("cid:"):
        return source if source[4:].strip().strip("<>") else ""
    if lowered.startswith("data:"):
        match = _DATA_IMAGE_PATTERN.fullmatch(source)
        if match and len(match.group(2)) <= MAX_INLINE_IMAGE_SIZE * 2:
            return source
        return ""
    if lowered.startswith(("http://", "https://")):
        parsed = urlsplit(source)
        if parsed.hostname and parsed.username is None and parsed.password is None:
            return source
    return ""


def _normalize_link_reference(value: str) -> str:
    target = unescape(value).strip()
    if (
        not target
        or len(target) > MAX_IMAGE_REFERENCE_LENGTH
        or any(ord(character) < 32 for character in target)
    ):
        return ""
    if target.startswith("//"):
        target = "https:" + target
    parsed = urlsplit(target)
    scheme = parsed.scheme.casefold()
    if scheme == "mailto":
        return target
    if (
        scheme in {"http", "https"}
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    ):
        return target
    return ""


def _srcset_references(value: str) -> tuple[str, ...]:
    references: list[str] = []
    for candidate in _SRCSET_SEPARATOR.split(value[: MAX_IMAGE_REFERENCE_LENGTH * 4]):
        normalized = _normalize_image_reference(
            _SRCSET_DESCRIPTOR.sub("", candidate.strip())
        )
        if normalized:
            references.append(normalized)
    return tuple(dict.fromkeys(references))


def _preferred_image_reference(values: dict[str, str]) -> str:
    for name in _LAZY_IMAGE_ATTRIBUTES:
        normalized = _normalize_image_reference(values.get(name, ""))
        if normalized:
            return normalized
    normalized = _normalize_image_reference(values.get("src", ""))
    if normalized:
        return normalized
    for name in _SRCSET_ATTRIBUTES:
        references = _srcset_references(values.get(name, ""))
        if references:
            return references[0]
    return ""


def _background_image_references(values: dict[str, str]) -> tuple[str, ...]:
    references: list[str] = []
    background = _normalize_image_reference(values.get("background", ""))
    if background:
        references.append(background)
    style = values.get("style", "")[:20_000]
    for match in _CSS_BACKGROUND_URL_PATTERN.finditer(style):
        source = next((group for group in match.groups() if group is not None), "")
        normalized = _normalize_image_reference(source)
        if normalized:
            references.append(normalized)
    return tuple(dict.fromkeys(references))


class _SafeHtmlSanitizer(HTMLParser):
    def __init__(
        self,
        *,
        inline_images: dict[str, tuple[str, bytes]],
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0
        self._inline_images = {
            key.strip().strip("<>").casefold(): value for key, value in inline_images.items()
        }
        self._picture_sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if self._ignored_depth:
            if tag in _BLOCKED_CONTAINER_TAGS:
                self._ignored_depth += 1
            return
        if tag in _BLOCKED_VOID_TAGS:
            return
        if tag in _BLOCKED_CONTAINER_TAGS:
            self._ignored_depth = 1
            return
        values = {name.casefold(): (value or "") for name, value in attrs}
        if tag == "picture":
            self._picture_sources.append("")
            return
        if tag == "source":
            if self._picture_sources and not self._picture_sources[-1]:
                self._picture_sources[-1] = _preferred_image_reference(values)
            return
        if tag in {"img", "v:imagedata"}:
            source = _preferred_image_reference(values)
            picture_source = self._picture_sources[-1] if self._picture_sources else ""
            if picture_source and (not source or source.casefold().startswith("data:")):
                source = picture_source
            values["src"] = source
            self._append_image(values)
            return
        rendered_tag = tag in _SAFE_TAGS
        safe_attrs: list[tuple[str, str]] = []
        if tag == "a":
            href = _normalize_link_reference(values.get("href", ""))
            if href:
                safe_attrs.append(("href", href))
            if values.get("title"):
                safe_attrs.append(("title", values["title"][:300]))
        if tag in {"td", "th"}:
            for name in ("colspan", "rowspan"):
                value = values.get(name, "")
                if value.isdigit() and 1 <= int(value) <= 100:
                    safe_attrs.append((name, value))
            align = values.get("align", "").casefold()
            if align in {"left", "center", "right"}:
                safe_attrs.append(("align", align))
        if rendered_tag:
            rendered_attrs = "".join(
                f' {name}="{escape(value, quote=True)}"' for name, value in safe_attrs
            )
            self.parts.append(f"<{tag}{rendered_attrs}>")
        for source in _background_image_references(values):
            self._append_image({"src": source, "alt": "背景图片"})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in _BLOCKED_TAGS:
            return
        self.handle_starttag(tag, attrs)
        if normalized_tag == "picture" or (
            normalized_tag in _SAFE_TAGS and normalized_tag not in _VOID_TAGS
        ):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._ignored_depth:
            if tag in _BLOCKED_CONTAINER_TAGS:
                self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if tag == "picture":
            if self._picture_sources:
                self._picture_sources.pop()
            return
        if tag in _SAFE_TAGS and tag not in _VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(escape(repair_mojibake(data)))

    def _append_image(self, values: dict[str, str]) -> None:
        source = _normalize_image_reference(values.get("src", ""))
        alt = repair_mojibake(values.get("alt", "").strip())[:300]
        rendered_source = ""
        if source.casefold().startswith("cid:"):
            content_id = source[4:].strip().strip("<>").casefold()
            image = self._inline_images.get(content_id)
            if image:
                rendered_source = _data_image_uri(*image)
        elif source.casefold().startswith(("http://", "https://", "data:")):
            rendered_source = source
        if not rendered_source:
            if alt:
                self.parts.append(f"<span>[图片：{escape(alt)}]</span>")
            return
        safe_attrs = [("src", rendered_source)]
        if alt:
            safe_attrs.append(("alt", alt))
        for name in ("width", "height"):
            value = values.get(name, "").strip()
            if value.isdigit() and 1 <= int(value) <= 4096:
                safe_attrs.append((name, value))
        rendered_attrs = "".join(
            f' {name}="{escape(value, quote=True)}"' for name, value in safe_attrs
        )
        self.parts.append(f"<img{rendered_attrs}>")


def sanitize_email_html(
    value: str,
    *,
    inline_images: dict[str, tuple[str, bytes]] | None = None,
) -> str:
    """Return a safe HTML fragment while retaining the extracted image sources."""

    parser = _SafeHtmlSanitizer(
        inline_images=inline_images or {},
    )
    parser.feed(normalize_email_html(value))
    parser.close()
    return "".join(parser.parts)[:MAX_STORED_HTML_LENGTH]


class _VisibleHtmlDetector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if self._ignored_depth:
            if tag in _BLOCKED_CONTAINER_TAGS:
                self._ignored_depth += 1
            return
        if tag in _BLOCKED_VOID_TAGS:
            return
        if tag in _BLOCKED_CONTAINER_TAGS:
            self._ignored_depth = 1
            return
        values = {name.casefold(): (value or "") for name, value in attrs}
        if _background_image_references(values):
            self.visible = True
        if tag in {"img", "source", "v:imagedata"}:
            self.visible = self.visible or bool(_preferred_image_reference(values))
        elif tag == "hr":
            self.visible = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() not in _BLOCKED_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._ignored_depth and tag in _BLOCKED_CONTAINER_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.visible = True


def has_visible_email_html(value: str) -> bool:
    """Return whether HTML contains renderable text or a supported image reference."""

    if not value.strip():
        return False
    detector = _VisibleHtmlDetector()
    detector.feed(normalize_email_html(value))
    detector.close()
    return detector.visible


def _looks_like_template_noise(line: str) -> bool:
    lowered = line.casefold().strip()
    if not lowered:
        return False
    if lowered in {"<!--", "-->", "<![endif]-->", "table", "tbody", "html", "body"}:
        return True
    if any(
        marker in lowered
        for marker in (
            "@font-face",
            "@media",
            "font-family:",
            "mso-",
            "-webkit-",
            "#outlook",
            ".externalclass",
        )
    ):
        return True
    return "{" in lowered and ("}" in lowered or ":" in lowered)


def _clean_plain_text(value: str) -> str:
    text = repair_mojibake(unescape(value)).replace("\N{NO-BREAK SPACE}", " ")
    text = text.replace("\u200b", "").replace("\ufeff", "").replace("\x00", "")
    text = _HTML_COMMENT_PATTERN.sub(" ", text)
    cleaned: list[str] = []
    previous_blank = False
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[\t\f\v ]+", " ", raw_line).strip()
        if _looks_like_template_noise(line):
            continue
        if not line:
            if cleaned and not previous_blank:
                cleaned.append("")
            previous_blank = True
            continue
        cleaned.append(line)
        previous_blank = False
    return "\n".join(cleaned).strip()[:MAX_BODY_LENGTH]


def clean_message_text(value: str) -> str:
    normalized = normalize_email_html(value)
    if _HTML_TAG_PATTERN.search(normalized):
        return html_to_text(normalized)
    return _clean_plain_text(normalized)


def html_to_text(value: str) -> str:
    normalized = normalize_email_html(value)
    normalized = _CSS_BLOCK_PATTERN.sub(" ", normalized)
    normalized = _HTML_COMMENT_PATTERN.sub(" ", normalized)
    parser = _HtmlTextExtractor()
    parser.feed(normalized)
    parser.close()
    return _clean_plain_text("".join(parser.parts))


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return repair_mojibake(str(make_header(decode_header(value))))
    except (LookupError, UnicodeError):
        return repair_mojibake(value[:1000])


def safe_attachment_filename(value: object, *, fallback_index: int = 1) -> str:
    """Return a display/save-safe Windows filename without accepting sender paths."""

    if isinstance(value, tuple):
        try:
            value = collapse_rfc2231_value(value)
        except (LookupError, TypeError, UnicodeError):
            value = ""
    decoded = _decode_header(str(value or ""))
    # Some senders put a full Windows or POSIX path in filename=. Never retain path segments.
    basename = re.split(r"[/\\]+", decoded)[-1]
    normalized = unicodedata.normalize("NFKC", basename)
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) not in {"Cc", "Cf"}
    )
    normalized = _UNSAFE_FILENAME_CHARS.sub("_", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    if not normalized or normalized in {".", ".."}:
        normalized = f"attachment-{max(1, fallback_index)}"
    stem, suffix = _split_filename(normalized)
    if stem.casefold() in _WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"
    suffix = suffix[:32]
    max_stem_length = max(1, MAX_ATTACHMENT_FILENAME_LENGTH - len(suffix))
    return f"{stem[:max_stem_length].rstrip(' .') or 'attachment'}{suffix}"


def _split_filename(filename: str) -> tuple[str, str]:
    suffixes = PurePath(filename).suffixes
    suffix = "".join(suffixes[-2:]) if suffixes else ""
    if len(suffix) >= len(filename):
        return filename, ""
    return filename[: -len(suffix)] if suffix else filename, suffix


def _fallback_attachment_name(content_type: str, index: int) -> str:
    suffix = mimetypes.guess_extension(content_type, strict=False) or ""
    if suffix == ".jpe":
        suffix = ".jpg"
    return f"attachment-{index}{suffix}"


def _attachment_payload(part: Message) -> bytes:
    decoded = part.get_payload(decode=True)
    if isinstance(decoded, bytes):
        return decoded
    payload = part.get_payload()
    if isinstance(payload, list):
        return b"\r\n".join(
            item.as_bytes(policy=policy.default)
            for item in payload
            if isinstance(item, Message)
        )
    if isinstance(payload, Message):
        return payload.as_bytes(policy=policy.default)
    if isinstance(payload, str):
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.encode(charset)
        except (LookupError, UnicodeError):
            return payload.encode("utf-8", errors="replace")
    return b""


def _iter_mime_parts(message: Message) -> Iterator[Message]:
    payload = message.get_payload()
    if not isinstance(payload, list):
        return
    for part in payload:
        if not isinstance(part, Message):
            continue
        yield part
        # An attached message is one downloadable file. Its internal MIME tree must not leak
        # into the parent message's attachment list or CID image map.
        if part.get_content_type().casefold() == "message/rfc822":
            continue
        if part.is_multipart():
            yield from _iter_mime_parts(part)


def _message_attachments(message: Message) -> tuple[MailAttachment, ...]:
    attachments: list[MailAttachment] = []
    used_names: set[str] = set()
    retained_bytes = 0
    for part in _iter_mime_parts(message):
        if part.is_multipart() and part.get_content_type().casefold() != "message/rfc822":
            continue
        disposition = (part.get_content_disposition() or "").casefold()
        raw_filename = part.get_filename()
        if raw_filename is None:
            raw_filename = part.get_param("name", header="content-type")
        # CID-only related images are rendered in the HTML body and should not clutter the
        # download list. A named inline file remains visible as an inline attachment.
        if disposition != "attachment" and raw_filename is None:
            continue
        if len(attachments) >= MAX_ATTACHMENT_COUNT:
            break
        content_type = part.get_content_type().casefold()[:255]
        index = len(attachments) + 1
        filename = safe_attachment_filename(
            raw_filename or _fallback_attachment_name(content_type, index),
            fallback_index=index,
        )
        filename = _unique_attachment_filename(filename, used_names)
        payload = _attachment_payload(part)
        size = len(payload)
        is_truncated = (
            size > MAX_ATTACHMENT_SIZE or retained_bytes + size > MAX_TOTAL_ATTACHMENT_SIZE
        )
        content = None if is_truncated else payload
        if content is not None:
            retained_bytes += size
        attachments.append(
            MailAttachment(
                filename=filename,
                content_type=content_type or "application/octet-stream",
                size=size,
                content_id=str(part.get("Content-ID") or "").strip().strip("<>")[:500],
                disposition="inline" if disposition == "inline" else "attachment",
                content=content,
                is_truncated=is_truncated,
            )
        )
    return tuple(attachments)


def _unique_attachment_filename(filename: str, used_names: set[str]) -> str:
    candidate = filename
    stem, suffix = _split_filename(filename)
    counter = 2
    while candidate.casefold() in used_names:
        addition = f" ({counter})"
        max_stem_length = max(
            1, MAX_ATTACHMENT_FILENAME_LENGTH - len(suffix) - len(addition)
        )
        candidate = f"{stem[:max_stem_length].rstrip(' .')}{addition}{suffix}"
        counter += 1
    used_names.add(candidate.casefold())
    return candidate


def _decode_part(part: Message) -> str:
    try:
        content = part.get_content()
    except (LookupError, UnicodeError):
        payload = part.get_payload(decode=True) or b""
        charsets = [part.get_content_charset(), "utf-8", "gb18030", "cp1252"]
        content = ""
        for charset in charsets:
            if not charset:
                continue
            try:
                content = payload.decode(charset)
                break
            except (LookupError, UnicodeError):
                continue
        if not content:
            content = payload.decode("utf-8", errors="replace")
    return repair_mojibake(content) if isinstance(content, str) else ""


def _message_bodies(message: Message) -> tuple[str, str, str]:
    plain_part = message.get_body(preferencelist=("plain",))
    html_part = message.get_body(preferencelist=("html",))
    plain_source = _decode_part(plain_part) if plain_part is not None else ""
    html_source = _decode_part(html_part) if html_part is not None else ""
    inline_images: dict[str, tuple[str, bytes]] = {}
    for part in _iter_mime_parts(message):
        if part.get_content_maintype().casefold() != "image":
            continue
        content_id = str(part.get("Content-ID") or "").strip().strip("<>").casefold()
        payload = part.get_payload(decode=True) or b""
        if content_id and payload and len(payload) <= MAX_INLINE_IMAGE_SIZE:
            inline_images[content_id] = (part.get_content_type(), payload)
    html_body = (
        sanitize_email_html(
            html_source,
            inline_images=inline_images,
        )
        if html_source
        else ""
    )
    web_html_body = ""
    if html_source:
        from mailbox_manager.mail.web_document import sanitize_email_web_source

        web_html_body = sanitize_email_web_source(
            html_source,
            inline_images=inline_images,
        )
    text_body = clean_message_text(plain_source) if plain_source else html_to_text(html_source)
    return text_body, html_body, web_html_body


def extract_matches(
    text: str,
    *,
    keywords: tuple[str, ...] = ("verification code", "验证码", "reset password"),
    custom_pattern: str = "",
) -> tuple[str, ...]:
    sample = text[:MATCH_TEXT_LIMIT]
    values: list[str] = []
    values.extend(CODE_PATTERN.findall(sample))
    lowered = sample.casefold()
    values.extend(keyword for keyword in keywords if keyword.casefold() in lowered)
    if custom_pattern:
        if len(custom_pattern) > 500 or UNSAFE_PATTERN.search(custom_pattern):
            raise ValueError("自定义正则包含高风险结构")
        try:
            values.extend(match.group(0) for match in re.finditer(custom_pattern, sample))
        except re.error as exc:
            raise ValueError("自定义正则格式不正确") from exc
    return tuple(dict.fromkeys(value for value in values if value))


def parse_email_message(
    raw: bytes,
    *,
    folder: str,
    keywords: tuple[str, ...] = ("verification code", "验证码", "reset password"),
    custom_pattern: str = "",
) -> MailMessage:
    if len(raw) > MAX_RAW_MESSAGE_SIZE:
        raise ValueError("单封邮件原件不能超过 25 MiB")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    subject = _decode_header(message.get("Subject"))
    sender_addresses = getaddresses(message.get_all("From", []))
    recipient_addresses = getaddresses(message.get_all("To", []) + message.get_all("Cc", []))
    recipients = tuple(address.casefold() for _, address in recipient_addresses if address)
    original = (
        message.get("X-Original-To")
        or message.get("Delivered-To")
        or (recipients[0] if recipients else "")
    )
    original_addresses = getaddresses([str(original)])
    catch_all = original_addresses[0][1].casefold() if original_addresses else ""
    text_body, html_body, web_html_body = _message_bodies(message)
    attachments = _message_attachments(message)
    combined = f"{subject}\n{text_body}"
    received_at = None
    if message.get("Date"):
        try:
            received_at = parsedate_to_datetime(message.get("Date"))
        except (TypeError, ValueError, OverflowError):
            received_at = None
    message_id = str(message.get("Message-ID") or "").strip()
    if not message_id:
        message_id = str(abs(hash(raw[:4096])))
    sender_name = (
        _decode_header(sender_addresses[0][0]).strip()[:500]
        if sender_addresses
        else ""
    )
    return MailMessage(
        provider_message_id=message_id,
        folder=folder,
        subject=subject,
        sender=sender_addresses[0][1].casefold() if sender_addresses else "",
        sender_name=sender_name,
        recipients=recipients,
        catch_all_recipient=catch_all,
        received_at=received_at,
        text_body=text_body,
        html_body=html_body,
        web_html_body=web_html_body,
        matched_values=extract_matches(
            combined, keywords=keywords, custom_pattern=custom_pattern
        ),
        attachments=attachments,
        raw_eml=raw,
    )
