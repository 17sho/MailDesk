from __future__ import annotations

import base64
import re
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

from mailbox_manager.mail.parser import (
    MAX_HTML_SOURCE_LENGTH,
    MAX_INLINE_IMAGE_SIZE,
    normalize_email_html,
    repair_mojibake,
)

MAX_WEB_DOCUMENT_LENGTH = 12 * 1024 * 1024
MAX_IMAGE_REFERENCE_LENGTH = 4096
_SAFE_IMAGE_MIMES = {
    "image/gif",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
_DATA_IMAGE_PATTERN = re.compile(
    r"(?is)^data:(image/(?:png|jpeg|jpg|gif|webp));base64,([a-z0-9+/=\s]+)$"
)
_CSS_URL_PATTERN = re.compile(
    r"(?is)url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^)'\"\s][^)]*))\s*\)"
)
_CSS_IMPORT_PATTERN = re.compile(r"(?is)@import\s+(?:url\([^)]*\)|[^;]+);?")
_CSS_DANGEROUS_PATTERN = re.compile(
    r"(?is)(?:expression\s*\(|javascript\s*:|vbscript\s*:|"
    r"-moz-binding\s*:|behavior\s*:|binding\s*:)"
)
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SAFE_DIMENSION_PATTERN = re.compile(r"^\s*(?:\d{1,4}(?:\.\d{1,2})?(?:px|%)?|auto)\s*$", re.I)
_SAFE_CLASS_PATTERN = re.compile(r"[^a-zA-Z0-9_\- ]+")
_SAFE_ID_PATTERN = re.compile(r"[^a-zA-Z0-9_\-:.]+")
_SRCSET_SPLIT = re.compile(r"\s*,\s*")
_SRCSET_DESCRIPTOR = re.compile(r"\s+(?:\d+(?:\.\d+)?x|\d+w)\s*$", re.I)
_LEADING_PREHEADER_PATTERN = re.compile(
    r"(?is)^(?P<prefix>\s*(?:<style\b[^>]*>.*?</style>\s*)*)"
    r"(?P<div><div\b[^>]*>(?P<body>.*?)</div>)\s*(?=<table\b)"
)
_LAZY_SOURCE_ATTRIBUTES = ("data-src", "data-original", "data-lazy-src")

_ALLOWED_TAGS = {
    "a",
    "abbr",
    "address",
    "article",
    "aside",
    "b",
    "blockquote",
    "br",
    "caption",
    "center",
    "code",
    "col",
    "colgroup",
    "dd",
    "del",
    "details",
    "div",
    "dl",
    "dt",
    "em",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "i",
    "img",
    "ins",
    "kbd",
    "li",
    "main",
    "mark",
    "nav",
    "ol",
    "p",
    "pre",
    "q",
    "s",
    "samp",
    "section",
    "small",
    "span",
    "strong",
    "sub",
    "summary",
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
    "var",
}
_VOID_TAGS = {"br", "col", "hr", "img"}
_ACTIVE_CONTAINER_TAGS = {
    "applet",
    "audio",
    "canvas",
    "iframe",
    "object",
    "script",
    "svg",
    "template",
    "video",
}
_ACTIVE_VOID_TAGS = {"base", "embed", "input", "link", "meta", "source", "track"}
_TRANSPARENT_TAGS = {"body", "form", "head", "html", "picture"}
_IGNORED_TEXT_TAGS = {"title"}
_TABLE_ATTRIBUTES = {
    "align",
    "bgcolor",
    "border",
    "cellpadding",
    "cellspacing",
    "height",
    "role",
    "valign",
    "width",
}
_CELL_ATTRIBUTES = {
    "align",
    "bgcolor",
    "colspan",
    "height",
    "rowspan",
    "valign",
    "width",
}


def _normalize_reference(value: str) -> str:
    source = unescape(value or "").strip()
    if not source or _CONTROL_PATTERN.search(source):
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
    if len(source) > MAX_IMAGE_REFERENCE_LENGTH:
        return ""
    if lowered.startswith(("http://", "https://")):
        parsed = urlsplit(source)
        if parsed.hostname and parsed.username is None and parsed.password is None:
            return source
    return ""


def _safe_link(value: str) -> str:
    target = unescape(value or "").strip()
    if not target or len(target) > 4096 or _CONTROL_PATTERN.search(target):
        return ""
    if target.startswith("//"):
        target = "https:" + target
    parsed = urlsplit(target)
    if (
        parsed.scheme.casefold() in {"http", "https", "mailto"}
        and parsed.username is None
        and parsed.password is None
    ):
        return target
    return ""


def _data_image_uri(content_type: str, payload: bytes) -> str:
    mime = content_type.casefold().split(";", 1)[0].strip()
    if mime not in _SAFE_IMAGE_MIMES or not payload or len(payload) > MAX_INLINE_IMAGE_SIZE:
        return ""
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _preferred_image_source(values: dict[str, str]) -> str:
    for name in _LAZY_SOURCE_ATTRIBUTES:
        candidate = _normalize_reference(values.get(name, ""))
        if candidate:
            return candidate
    candidate = _normalize_reference(values.get("src", ""))
    if candidate:
        return candidate
    for raw_candidate in _SRCSET_SPLIT.split(values.get("srcset", "")[:16_384]):
        candidate = _normalize_reference(_SRCSET_DESCRIPTOR.sub("", raw_candidate.strip()))
        if candidate:
            return candidate
    return ""


def _replace_css_urls(
    value: str,
    *,
    inline_images: dict[str, tuple[str, bytes]],
) -> str:
    css = _CSS_IMPORT_PATTERN.sub("", value[:200_000])
    if _CSS_DANGEROUS_PATTERN.search(css):
        css = _CSS_DANGEROUS_PATTERN.sub("blocked(", css)

    def replace(match: re.Match[str]) -> str:
        source = next((item for item in match.groups() if item is not None), "")
        normalized = _normalize_reference(source)
        if not normalized:
            return "none"
        lowered = normalized.casefold()
        rendered = ""
        if lowered.startswith("cid:"):
            content_id = normalized[4:].strip().strip("<>").casefold()
            image = inline_images.get(content_id)
            if image:
                rendered = _data_image_uri(*image)
        elif lowered.startswith(("http://", "https://", "data:")):
            rendered = normalized
        return f'url("{rendered}")' if rendered else "none"

    return _CSS_URL_PATTERN.sub(replace, css)


class _WebHtmlSanitizer(HTMLParser):
    def __init__(
        self,
        *,
        inline_images: dict[str, tuple[str, bytes]],
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._blocked_depth = 0
        self._ignored_text_depth = 0
        self._style_depth = 0
        self._inline_images = {
            key.strip().strip("<>").casefold(): value for key, value in inline_images.items()
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if self._blocked_depth:
            if tag in _ACTIVE_CONTAINER_TAGS:
                self._blocked_depth += 1
            return
        if tag in _ACTIVE_CONTAINER_TAGS:
            self._blocked_depth = 1
            return
        if tag in _ACTIVE_VOID_TAGS:
            return
        if tag in _IGNORED_TEXT_TAGS:
            self._ignored_text_depth += 1
            return
        if tag == "style":
            self._style_depth += 1
            self.parts.append("<style>")
            return
        if tag in _TRANSPARENT_TAGS or tag not in _ALLOWED_TAGS:
            return
        values = {name.casefold(): (value or "") for name, value in attrs}
        if tag == "img":
            self._append_image(values)
            return
        safe_attrs = self._safe_attributes(tag, values)
        rendered = "".join(
            f' {name}="{escape(value, quote=True)}"' for name, value in safe_attrs
        )
        self.parts.append(f"<{tag}{rendered}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in _ACTIVE_CONTAINER_TAGS | _ACTIVE_VOID_TAGS | _IGNORED_TEXT_TAGS:
            return
        if lowered == "style":
            self.parts.append("<style></style>")
            return
        self.handle_starttag(lowered, attrs)
        if lowered in _ALLOWED_TAGS and lowered not in _VOID_TAGS:
            self.handle_endtag(lowered)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._blocked_depth:
            if tag in _ACTIVE_CONTAINER_TAGS:
                self._blocked_depth = max(0, self._blocked_depth - 1)
            return
        if tag in _IGNORED_TEXT_TAGS:
            self._ignored_text_depth = max(0, self._ignored_text_depth - 1)
            return
        if tag == "style":
            if self._style_depth:
                self._style_depth -= 1
                self.parts.append("</style>")
            return
        if tag in _ALLOWED_TAGS and tag not in _VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._blocked_depth or self._ignored_text_depth:
            return
        if self._style_depth:
            self.parts.append(
                _replace_css_urls(
                    data,
                    inline_images=self._inline_images,
                )
            )
            return
        self.parts.append(escape(repair_mojibake(data)))

    def _safe_attributes(
        self, tag: str, values: dict[str, str]
    ) -> list[tuple[str, str]]:
        safe: list[tuple[str, str]] = []
        class_name = _SAFE_CLASS_PATTERN.sub("", values.get("class", ""))[:500].strip()
        if class_name:
            safe.append(("class", class_name))
        element_id = _SAFE_ID_PATTERN.sub("", values.get("id", ""))[:200].strip()
        if element_id:
            safe.append(("id", element_id))
        for name in ("title", "lang", "dir", "role"):
            value = _CONTROL_PATTERN.sub("", values.get(name, ""))[:500].strip()
            if value:
                safe.append((name, value))
        for name, value in values.items():
            if name.startswith("aria-"):
                cleaned = _CONTROL_PATTERN.sub("", value)[:500].strip()
                if cleaned:
                    safe.append((name, cleaned))
        style = values.get("style", "").strip()
        if style:
            cleaned_style = _replace_css_urls(
                style,
                inline_images=self._inline_images,
            )
            if cleaned_style.strip():
                safe.append(("style", cleaned_style[:20_000]))
        if tag == "a":
            href = _safe_link(values.get("href", ""))
            if href:
                safe.append(("href", href))
        allowed = (
            _TABLE_ATTRIBUTES
            if tag == "table"
            else _CELL_ATTRIBUTES
            if tag in {"td", "th"}
            else set()
        )
        for name in allowed:
            value = _CONTROL_PATTERN.sub("", values.get(name, ""))[:100].strip()
            if not value:
                continue
            if name in {"width", "height"} and not _SAFE_DIMENSION_PATTERN.fullmatch(value):
                continue
            if name in {
                "border",
                "cellpadding",
                "cellspacing",
                "colspan",
                "rowspan",
            } and (not value.isdigit() or not 0 <= int(value) <= 1000):
                continue
            if name in {"align", "valign"} and value.casefold() not in {
                "baseline",
                "bottom",
                "center",
                "justify",
                "left",
                "middle",
                "right",
                "top",
            }:
                continue
            safe.append((name, value))
        return list(dict.fromkeys(safe))

    def _append_image(self, values: dict[str, str]) -> None:
        source = _preferred_image_source(values)
        alt = repair_mojibake(values.get("alt", "").strip())[:500]
        rendered_source = ""
        if source.casefold().startswith("cid:"):
            content_id = source[4:].strip().strip("<>").casefold()
            image = self._inline_images.get(content_id)
            if image:
                rendered_source = _data_image_uri(*image)
        elif source.casefold().startswith(("http://", "https://", "data:")):
            rendered_source = source
        classes = _SAFE_CLASS_PATTERN.sub("", values.get("class", ""))[:500].split()
        path = urlsplit(source).path.casefold()
        if "logo" in path or "wordmark" in path:
            classes.append("maildesk-brand-image")
        safe: list[tuple[str, str]] = []
        if rendered_source:
            safe.append(("src", rendered_source))
        if alt:
            safe.append(("alt", alt))
        if classes:
            safe.append(("class", " ".join(dict.fromkeys(classes))))
        for name in ("width", "height"):
            value = values.get(name, "").strip()
            if _SAFE_DIMENSION_PATTERN.fullmatch(value):
                safe.append((name, value))
        style = values.get("style", "").strip()
        if style:
            cleaned_style = _replace_css_urls(
                style,
                inline_images=self._inline_images,
            )
            if cleaned_style.strip():
                safe.append(("style", cleaned_style[:20_000]))
        rendered = "".join(
            f' {name}="{escape(value, quote=True)}"' for name, value in safe
        )
        if rendered_source:
            self.parts.append(f"<img{rendered}>")
        elif alt:
            self.parts.append(f'<span class="maildesk-image-alt">{escape(alt)}</span>')


_READER_CSS = r"""
* { box-sizing: border-box; }
html, body { margin: 0 !important; padding: 0 !important; min-height: 100%;
  background: #ffffff !important; color: #172033; }
body { overflow-wrap: anywhere; word-break: normal; }
.maildesk-email-root { width: 100%; min-height: 100%; padding: 28px 32px 48px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }
.maildesk-email-root > table { width: 100% !important; max-width: 680px !important;
  margin-left: auto !important; margin-right: auto !important; }
.maildesk-preheader-hidden { display: none !important; max-height: 0 !important;
  overflow: hidden !important; opacity: 0 !important; }
table { max-width: 100%; border-collapse: collapse; }
td, th { max-width: 100%; }
img { max-width: 100% !important; height: auto; }
img.maildesk-brand-image { display: block; width: auto !important;
  max-width: 220px !important; height: auto !important; }
p, li { line-height: 1.55; }
a { color: #0f9f85; }
pre, code { white-space: pre-wrap; overflow-wrap: anywhere; }
.maildesk-email-root table table table table a:only-child {
  display: inline-block; padding: 11px 18px; border-radius: 4px;
  background: #10a37f; color: #ffffff !important; font-weight: 600;
  text-decoration: none;
}
"""


def sanitize_email_web_source(
    value: str,
    *,
    inline_images: dict[str, tuple[str, bytes]] | None = None,
) -> str:
    """Retain static email layout while removing active and unsafe content."""

    parser = _WebHtmlSanitizer(
        inline_images=inline_images or {},
    )
    parser.feed(normalize_email_html(value[:MAX_HTML_SOURCE_LENGTH]))
    parser.close()
    return "".join(parser.parts)[:MAX_WEB_DOCUMENT_LENGTH]


def prepare_email_web_document(
    value: str,
    *,
    inline_images: dict[str, tuple[str, bytes]] | None = None,
    preheader_hint: str = "",
) -> str:
    """Create an isolated, browser-quality HTML document for an email body.

    Layout CSS and static markup are retained, while active content, event handlers,
    unsafe URLs and external stylesheets are removed. Extracted image URLs remain
    available to the reader while non-image browser requests are blocked by the GUI.
    """

    fragment = sanitize_email_web_source(
        value,
        inline_images=inline_images or {},
    )
    fragment = _hide_matching_leading_preheader(fragment, preheader_hint)
    document = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "</head><body><main class=\"maildesk-email-root\">"
        + fragment
        + "</main><style>"
        + _READER_CSS
        + "</style></body></html>"
    )
    return document[:MAX_WEB_DOCUMENT_LENGTH]


def _hide_matching_leading_preheader(fragment: str, hint: str) -> str:
    normalized_hint = " ".join(hint.casefold().split())
    if len(normalized_hint) < 5:
        return fragment
    match = _LEADING_PREHEADER_PATTERN.match(fragment)
    if match is None:
        return fragment
    text = re.sub(r"(?is)<[^>]+>", " ", match.group("body"))
    normalized_text = " ".join(unescape(text).casefold().split())
    if not 5 <= len(normalized_text) <= 200:
        return fragment
    matches_hint = (
        normalized_text in normalized_hint or normalized_hint in normalized_text
    )
    nearby_body = fragment[match.end() : match.end() + 8_000]
    looks_like_branded_preheader = "maildesk-brand-image" in nearby_body
    if not matches_hint and not looks_like_branded_preheader:
        return fragment
    wrapped = (
        match.group("prefix")
        + '<div class="maildesk-preheader-hidden">'
        + match.group("div")
        + "</div>"
    )
    return wrapped + fragment[match.end() :]


def prepare_plain_web_document(value: str) -> str:
    text = escape(repair_mojibake(value)).replace("\n", "<br>")
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        '<main class="maildesk-email-root"><div class="maildesk-plain">'
        + text
        + "</div></main><style>"
        + _READER_CSS
        + ".maildesk-plain{white-space:normal;line-height:1.6;font-size:15px;}</style>"
        "</body></html>"
    )
