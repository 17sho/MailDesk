from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QMessageBox

from mailbox_manager.domain.models import EmailAccount, MailMessage, ProtocolType
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    SettingsRepository,
    StatisticsRepository,
)
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


class FakeTranslationService:
    def __init__(self, translated: str = "翻译后的正文") -> None:
        self.translated = translated
        self.calls: list[tuple[str, str]] = []

    def translate(
        self,
        text: str,
        *,
        target_language: str,
        source_language: str = "auto",
    ) -> str:
        del source_language
        self.calls.append((text, target_language))
        return self.translated


class FailingTranslationService(FakeTranslationService):
    def translate(
        self,
        text: str,
        *,
        target_language: str,
        source_language: str = "auto",
    ) -> str:
        del text, target_language, source_language
        raise RuntimeError("private-user@example.com provider-secret")


def _account() -> EmailAccount:
    return EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        secret="app-password",
    )


def _window(
    qtbot,
    tmp_path,
    service,
    *,
    language: str = "zh-CN",
    confirm: bool = False,
) -> tuple[MainWindow, SettingsRepository]:
    database = Database(tmp_path / "main-translation.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"T" * 32))
    accounts.add_many([_account()])
    messages = MessageRepository(database)
    messages.add_many(
        1,
        (
            MailMessage(
                provider_message_id="translation-message",
                folder="INBOX",
                subject="Translate me",
                text_body="Original message body",
                html_body="<p>Original <b>message</b> body</p>",
            ),
        ),
    )
    settings = SettingsRepository(database)
    settings.set(
        "enterprise_ui",
        {
            "translation_language": language,
            "translation_confirm": confirm,
        },
    )
    window = MainWindow(
        accounts,
        messages,
        settings=settings,
        statistics=StatisticsRepository(database),
        translation_service=service,
    )
    qtbot.addWidget(window)
    window._account_row_clicked(window.account_model.index(0, 1))
    return window, settings


def test_main_toolbar_translates_and_toggles_original_without_confirmation(
    qtbot, tmp_path, monkeypatch
) -> None:
    service = FakeTranslationService("这是译文")
    window, _settings = _window(qtbot, tmp_path, service, language="ja")
    monkeypatch.setattr(window._pool, "start", lambda worker: worker.run())

    assert "日语" in window.translation_language_label.text()
    assert window.message_tools_bar.isHidden() is False
    assert window.main_tabs.tabBar().expanding() is False
    assert window.main_tabs.tabBar().drawBase() is False
    assert window.main_tabs.tabBar().usesScrollButtons() is False
    assert window.translate_button.isEnabled() is True
    assert window.translation_toggle_button.isEnabled() is False

    window.translate_button.click()

    assert service.calls == [("Original message body", "ja")]
    assert window.message_body.toPlainText() == "这是译文"
    assert window.translation_toggle_button.text() == "查看原文"
    assert window.translation_toggle_button.isEnabled() is True

    window.translation_toggle_button.click()
    assert "Original message body" in window.message_body.toPlainText()
    assert window.translation_toggle_button.text() == "查看译文"

    window.translation_toggle_button.click()
    assert window.message_body.toPlainText() == "这是译文"


def test_stale_translation_result_cannot_cross_into_new_message(
    qtbot, tmp_path, monkeypatch
) -> None:
    service = FakeTranslationService("旧邮件译文")
    window, _settings = _window(qtbot, tmp_path, service)
    started = []
    monkeypatch.setattr(window._pool, "start", started.append)

    window._translate_current_message()
    assert len(started) == 1
    window._set_displayed_messages(
        [
            MailMessage(
                provider_message_id="new-message",
                folder="INBOX",
                subject="New message",
                text_body="New original body",
            )
        ]
    )
    started[0].run()

    assert window._translated_text == ""
    assert window.translation_toggle_button.isEnabled() is False
    assert window.message_body.toPlainText() == "New original body"


def test_theme_updates_do_not_overwrite_translation(
    qtbot, tmp_path, monkeypatch
) -> None:
    service = FakeTranslationService("保持显示的译文")
    window, _settings = _window(qtbot, tmp_path, service)
    monkeypatch.setattr(window._pool, "start", lambda worker: worker.run())
    window._translate_current_message()
    assert window.message_body.toPlainText() == "保持显示的译文"

    window.toggle_theme()
    assert window.message_body.toPlainText() == "保持显示的译文"

    window.translation_toggle_button.click()
    assert "Original message body" in window.message_body.toPlainText()


def test_settings_change_applies_immediately_to_main_and_open_reader(
    qtbot, tmp_path
) -> None:
    service = FakeTranslationService()
    window, _settings = _window(qtbot, tmp_path, service)
    window.open_mail_viewer()
    reader = window._mail_viewer
    assert reader is not None
    assert reader._translation_service is service

    window._apply_translation_settings("fr", False)

    assert "法语" in window.translation_language_label.text()
    assert "翻译前确认" not in window.translation_language_label.text()
    assert reader._translation_language == "fr"
    assert reader._translation_confirm is False
    reader.close()


def test_translation_confirmation_can_cancel_without_sending_body(
    qtbot, tmp_path, monkeypatch
) -> None:
    service = FakeTranslationService()
    window, _settings = _window(qtbot, tmp_path, service, confirm=True)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
    )

    window._translate_current_message()

    assert service.calls == []
    assert window._active_translation_generation is None


def test_unexpected_translation_error_is_redacted_in_chinese_ui(
    qtbot, tmp_path, monkeypatch
) -> None:
    window, _settings = _window(qtbot, tmp_path, FailingTranslationService())
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, detail: warnings.append((title, detail)),
    )
    monkeypatch.setattr(window._pool, "start", lambda worker: worker.run())

    window._translate_current_message()

    assert warnings == [("翻译失败", "翻译失败，请稍后重试")]
    assert "private-user@example.com" not in str(warnings)
    assert "provider-secret" not in str(warnings)
