from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from mailbox_manager.domain.models import MailMessage
from mailbox_manager.mail.parser import (
    clean_message_text,
    parse_email_message,
    sanitize_email_html,
)

MAX_DISPLAY_EML_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class MessageDisplayContent:
    """Sanitized content selected for a mail body widget."""

    html_fragment: str = ""
    plain_text: str = ""
    source_html: str = ""

    @property
    def uses_html(self) -> bool:
        return bool(self.html_fragment)


class _ValidMediaDetector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "img":
            return
        source = (dict(attrs).get("src") or "").strip().casefold()
        if source.startswith(("data:image/", "http://", "https://")):
            self.found = True


def select_message_display_content(
    html_body: str,
    text_body: str,
    web_html_body: str = "",
) -> MessageDisplayContent:
    """Prefer useful sanitized HTML and fall back to the cleaned plain body.

    Structural markup, blocked content and whitespace alone must not suppress a usable
    ``text/plain`` alternative. A sanitized embedded image is useful even without text.
    """

    source_html = web_html_body or html_body
    candidate_html = html_body or web_html_body
    if candidate_html:
        fragment = sanitize_email_html(candidate_html)
        detector = _ValidMediaDetector()
        detector.feed(fragment)
        detector.close()
        if clean_message_text(fragment).strip() or detector.found:
            return MessageDisplayContent(
                html_fragment=fragment,
                source_html=source_html,
            )
    return MessageDisplayContent(
        plain_text=clean_message_text(text_body),
        source_html=source_html,
    )


def select_stored_message_display_content(message: MailMessage) -> MessageDisplayContent:
    """Select display content and lazily recover legacy HTML from its local EML.

    Old database rows can contain an empty sanitized HTML fragment even though their EML
    still has a complete alternative body and inline images. Recovery is intentionally
    per-message and read-only; opening the application never scans the EML directory.
    """

    selected = select_message_display_content(
        message.html_body,
        message.text_body,
        message.web_html_body,
    )
    if selected.uses_html or not message.eml_path:
        return selected
    recovered_html, recovered_web_html = _recover_html_from_eml(
        message.eml_path, message.folder
    )
    if not recovered_html and not recovered_web_html:
        return selected
    recovered = select_message_display_content(
        recovered_html,
        message.text_body,
        recovered_web_html,
    )
    return recovered if recovered.uses_html else selected


def _recover_html_from_eml(eml_path: str, folder: str) -> tuple[str, str]:
    try:
        path = Path(eml_path)
        if path.suffix.casefold() != ".eml" or path.is_symlink() or not path.is_file():
            return "", ""
        size = path.stat().st_size
        if not 0 < size <= MAX_DISPLAY_EML_BYTES:
            return "", ""
        with path.open("rb") as stream:
            raw = stream.read(MAX_DISPLAY_EML_BYTES + 1)
        if len(raw) > MAX_DISPLAY_EML_BYTES:
            return "", ""
        parsed = parse_email_message(raw, folder=folder or "INBOX")
        return parsed.html_body, parsed.web_html_body
    except Exception:
        return "", ""
