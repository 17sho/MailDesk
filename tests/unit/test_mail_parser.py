from __future__ import annotations

import base64
from email.message import EmailMessage

from mailbox_manager.mail.parser import (
    clean_message_text,
    extract_matches,
    has_visible_email_html,
    html_to_text,
    parse_email_message,
    safe_attachment_filename,
    sanitize_email_html,
)

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)


def test_parse_multipart_message_extracts_code_and_catch_all_recipient() -> None:
    message = EmailMessage()
    message["Subject"] = "登录验证码"
    message["From"] = "Security <security@example.com>"
    message["To"] = "alias@example.net"
    message["X-Original-To"] = "virtual-user@example.net"
    message["Message-ID"] = "<message-1@example.com>"
    message.set_content("Your verification code is 482913. 请勿泄露。", charset="utf-8")
    message.add_alternative("<p>Your code is <b>482913</b></p>", subtype="html")

    parsed = parse_email_message(message.as_bytes(), folder="INBOX")

    assert parsed.provider_message_id == "<message-1@example.com>"
    assert parsed.sender_name == "Security"
    assert parsed.sender == "security@example.com"
    assert parsed.sender_display == "Security <security@example.com>"
    assert parsed.catch_all_recipient == "virtual-user@example.net"
    assert parsed.recipients == ("alias@example.net",)
    assert "482913" in parsed.matched_values
    assert "verification code" in parsed.matched_values


def test_extract_matches_honors_custom_pattern_without_duplicates() -> None:
    matches = extract_matches(
        "Invoice ID: AB-1234; verification code 123456; code 123456",
        keywords=("verification code",),
        custom_pattern=r"AB-\d{4}",
    )

    assert matches == ("123456", "verification code", "AB-1234")


def test_html_only_message_is_converted_to_readable_text() -> None:
    message = EmailMessage()
    message["Subject"] = "Reset Password"
    message["From"] = "support@example.com"
    message["To"] = "owner@example.com"
    message.set_content("<div>Hello&nbsp;<b>Owner</b></div>", subtype="html")

    parsed = parse_email_message(message.as_bytes(), folder="Junk")

    assert "Hello Owner" in parsed.text_body
    assert "<b>" not in parsed.text_body


def test_outlook_template_css_and_comments_are_removed_from_body() -> None:
    html = """
    <html><head><style>
    @font-face {font-family:'wf_segoe-ui'; src:url(example)}
    table {border-collapse: collapse; mso-table-lspace: 0}
    </style></head><body>
    <!--[if mso]><table><tr><td>hidden template</td></tr></table><![endif]-->
    <table><tr><td><h2>欢迎使用 Outlook</h2></td></tr>
    <tr><td>你的邮箱已经可以正常收件。</td></tr></table>
    </body></html>
    """

    text = html_to_text(html)

    assert "欢迎使用 Outlook" in text
    assert "你的邮箱已经可以正常收件" in text
    assert "font-family" not in text
    assert "mso-" not in text
    assert "hidden template" not in text


def test_stored_template_noise_is_cleaned_when_displayed() -> None:
    stale = """@font-face
    {font-family:'wf_segoe-ui'}
    -->
    <!--
    table
    欢迎使用 Outlook
    """

    assert clean_message_text(stale) == "欢迎使用 Outlook"


def test_double_escaped_outlook_markup_is_not_rendered_as_css() -> None:
    encoded = (
        "&lt;html&gt;&lt;head&gt;&lt;style&gt;@font-face {font-family:test}"
        "&lt;/style&gt;&lt;/head&gt;&lt;body&gt;&lt;p&gt;安全代码 638291&lt;/p&gt;"
        "&lt;/body&gt;&lt;/html&gt;"
    )

    assert html_to_text(encoded) == "安全代码 638291"


def test_mime_html_and_cid_image_are_preserved_safely() -> None:
    message = EmailMessage()
    message["Subject"] = "带图片的验证码"
    message["From"] = "security@example.com"
    message["To"] = "owner@example.com"
    message.set_content("验证码是 482913", charset="utf-8")
    message.add_alternative(
        '<p>验证码是 <b>482913</b></p><img src="cid:brand-logo"><script>bad()</script>',
        subtype="html",
    )
    message.get_payload()[1].add_related(
        _PNG,
        maintype="image",
        subtype="png",
        cid="<brand-logo>",
    )

    parsed = parse_email_message(message.as_bytes(), folder="INBOX")

    assert "<b>482913</b>" in parsed.html_body
    assert "data:image/png;base64," in parsed.html_body
    assert "data:image/png;base64," in parsed.web_html_body
    assert "script" not in parsed.html_body
    assert "482913" in parsed.text_body


def test_parsed_web_body_keeps_static_email_css_and_removes_scripts() -> None:
    message = EmailMessage()
    message["From"] = "sender@example.com"
    message["To"] = "owner@example.com"
    message.set_content("备用正文")
    message.add_alternative(
        "<html><head><style>.card{max-width:600px;padding:24px}</style></head>"
        '<body><table class="card"><tr><td style="font-size:16px">完整正文</td></tr>'
        "<script>bad()</script></table></body></html>",
        subtype="html",
    )

    parsed = parse_email_message(message.as_bytes(), folder="INBOX")

    assert ".card{max-width:600px;padding:24px}" in parsed.web_html_body
    assert 'class="card"' in parsed.web_html_body
    assert 'style="font-size:16px"' in parsed.web_html_body
    assert "完整正文" in parsed.web_html_body
    assert "script" not in parsed.web_html_body


def test_link_wrapped_cid_image_keeps_clickable_destination() -> None:
    message = EmailMessage()
    message["From"] = "security@example.com"
    message["To"] = "owner@example.com"
    message.set_content("打开安全中心")
    message.add_alternative(
        '<a href="https://example.com/security"><img src="cid:button"></a>',
        subtype="html",
    )
    message.get_payload()[1].add_related(
        _PNG,
        maintype="image",
        subtype="png",
        cid="<button>",
    )

    parsed = parse_email_message(message.as_bytes(), folder="INBOX")

    assert '<a href="https://example.com/security">' in parsed.html_body
    assert "data:image/png;base64," in parsed.html_body


def test_protocol_relative_image_link_is_normalized_but_credential_link_is_removed() -> None:
    stored = sanitize_email_html(
        '<a href="//example.com/open"><img src="https://images.example.com/button.png"></a>'
        '<a href="https://user:secret@example.com/private">unsafe</a>',
    )

    assert '<a href="https://example.com/open">' in stored
    assert "user:secret" not in stored


def test_remote_images_are_preserved_in_extracted_html() -> None:
    stored = sanitize_email_html(
        '<p>Hello</p><img src="https://images.example.com/banner.png" alt="横幅">',
    )
    assert 'src="https://images.example.com/banner.png"' in stored
    assert "横幅" in stored


def test_head_meta_and_style_do_not_swallow_xai_style_html_body() -> None:
    html = """
    <html><head><title>Product update</title>
    <meta charset="utf-8"/><meta name="viewport" content="width=device-width">
    <meta http-equiv="x-ua-compatible" content="ie=edge"/>
    <style>body { margin: 0 }</style><style>.hero { display: block }</style>
    </head><body><table><tr><td>
    <img src="https://images.example.com/product-update.png" alt="产品更新"/>
    <h2>New features are ready</h2><p>Read the release summary.</p>
    </td></tr></table></body></html>
    """

    stored = sanitize_email_html(html)

    assert "New features are ready" in stored
    assert "Read the release summary" in stored
    assert len(stored.strip()) > 100
    assert "https://images.example.com/product-update.png" in stored
    assert has_visible_email_html(stored) is True


def test_common_lazy_picture_srcset_and_background_images_are_normalized() -> None:
    png_data = "data:image/png;base64," + base64.b64encode(_PNG).decode()
    html = f"""
    <picture>
      <source srcset="//cdn.example.com/hero.webp 1x, https://cdn.example.com/hero-2x.webp 2x">
      <img alt="Hero">
    </picture>
    <img src="{png_data}" data-src="https://images.example.com/lazy.png" alt="Lazy">
    <table background="https://images.example.com/legacy.png"><tr><td>Legacy</td></tr></table>
    <div style="color:#333; background-image: url('https://images.example.com/bg.png')">
      Background
    </div>
    <img srcset="https://images.example.com/small.png 1x, https://images.example.com/large.png 2x">
    <img src="javascript:alert(1)" alt="unsafe">
    <img src="{png_data}" alt="inline data">
    """

    stored = sanitize_email_html(html)

    expected_urls = (
        "https://cdn.example.com/hero.webp",
        "https://images.example.com/lazy.png",
        "https://images.example.com/legacy.png",
        "https://images.example.com/bg.png",
        "https://images.example.com/small.png",
    )
    assert all(url in stored for url in expected_urls)
    assert "javascript:" not in stored
    assert "srcset=" not in stored
    assert 'src="data:image/png;base64,' in stored


def test_visible_html_detection_rejects_only_head_noise_but_accepts_image_only_mail() -> None:
    assert has_visible_email_html("   ") is False
    assert (
        has_visible_email_html(
            "<html><head><meta charset='utf-8'><style>body{color:red}</style></head></html>"
        )
        is False
    )
    assert has_visible_email_html('<img src="https://images.example.com/only.png">') is True
    assert (
        has_visible_email_html(
            '<div style="background-image:url(https://images.example.com/only-bg.png)"></div>'
        )
        is True
    )


def test_mime_attachments_keep_unicode_filename_content_and_inline_metadata() -> None:
    message = EmailMessage()
    message["Subject"] = "附件测试"
    message["From"] = "sender@example.com"
    message["To"] = "owner@example.com"
    message.set_content("请查收附件", charset="utf-8")
    message.add_attachment(
        "第一份报告".encode(),
        maintype="application",
        subtype="octet-stream",
        filename="月度报告.txt",
    )
    message.add_attachment(
        b"second",
        maintype="application",
        subtype="octet-stream",
        filename="月度报告.txt",
        disposition="inline",
        cid="named-inline",
    )

    parsed = parse_email_message(message.as_bytes(), folder="INBOX")

    assert [attachment.filename for attachment in parsed.attachments] == [
        "月度报告.txt",
        "月度报告 (2).txt",
    ]
    assert parsed.attachments[0].content == "第一份报告".encode()
    assert parsed.attachments[0].size == len("第一份报告".encode())
    assert parsed.attachments[1].is_inline is True
    assert parsed.attachments[1].content_id == "named-inline"


def test_attachment_filename_removes_paths_reserved_names_and_bidi_controls() -> None:
    assert safe_attachment_filename(r"C:\Users\sender\CON?.txt") == "CON_.txt"
    assert safe_attachment_filename("NUL.txt") == "_NUL.txt"
    assert safe_attachment_filename("../../invoice\u202egnp.exe") == "invoicegnp.exe"
    assert safe_attachment_filename("   ", fallback_index=7) == "attachment-7"


def test_oversized_attachment_remains_visible_but_binary_is_not_retained(
    monkeypatch,
) -> None:
    from mailbox_manager.mail import parser

    monkeypatch.setattr(parser, "MAX_ATTACHMENT_SIZE", 4)
    message = EmailMessage()
    message["From"] = "sender@example.com"
    message["To"] = "owner@example.com"
    message.set_content("body")
    message.add_attachment(
        b"12345",
        maintype="application",
        subtype="octet-stream",
        filename="large.bin",
    )

    attachment = parse_email_message(message.as_bytes(), folder="INBOX").attachments[0]

    assert attachment.filename == "large.bin"
    assert attachment.size == 5
    assert attachment.is_truncated is True
    assert attachment.content is None


def test_attached_eml_is_one_attachment_and_does_not_leak_nested_files() -> None:
    nested = EmailMessage()
    nested["From"] = "nested@example.com"
    nested["To"] = "owner@example.com"
    nested.set_content("nested body")
    nested.add_attachment(
        b"nested file",
        maintype="application",
        subtype="octet-stream",
        filename="nested.bin",
    )
    message = EmailMessage()
    message["From"] = "sender@example.com"
    message["To"] = "owner@example.com"
    message.set_content("parent body")
    message.add_attachment(nested, filename="forwarded.eml")

    parsed = parse_email_message(message.as_bytes(), folder="INBOX")

    assert [attachment.filename for attachment in parsed.attachments] == ["forwarded.eml"]
    assert parsed.attachments[0].content
    assert b"nested@example.com" in parsed.attachments[0].content
