from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWebEngineCore import QWebEngineSettings

from mailbox_manager.gui.email_body_view import EmailBodyView
from mailbox_manager.mail.web_document import prepare_email_web_document


def test_email_body_view_is_browser_quality_and_security_is_locked_down(qtbot) -> None:
    view = EmailBodyView()
    qtbot.addWidget(view)
    document = prepare_email_web_document(
        "<style>.body{font-size:18px}</style><p class=\"body\">完整正文</p>"
    )

    view.setHtml(document)

    assert "完整正文" in view.toPlainText()
    assert view._profile.isOffTheRecord() is True
    settings = view._page.settings()
    assert (
        settings.testAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled)
        is False
    )
    assert (
        settings.testAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls
        )
        is True
    )
    assert (
        settings.testAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled)
        is False
    )


def test_email_body_view_loads_images_but_blocks_other_network_resources(qtbot) -> None:
    view = EmailBodyView()
    qtbot.addWidget(view)
    view.setHtml(
        '<html><head><link rel="stylesheet" '
        'href="https://network-must-not-run.invalid/style.css"></head><body>'
        '<img src="https://images-load-directly.invalid/banner.png">'
        "安全正文</body></html>"
    )

    qtbot.waitUntil(
        lambda: view.blocked_request_count > 0
        and view.allowed_image_request_count > 0,
        timeout=5_000,
    )

    assert "安全正文" in view.toPlainText()
