from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QDialog,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from mailbox_manager.app import configure_translations
from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    Group,
    MailAttachment,
    MailMessage,
    PostAction,
    ProtocolType,
    ProxyConfig,
    ProxyType,
    SecurityMode,
    Tag,
)
from mailbox_manager.gui.account_model import AccountTableModel
from mailbox_manager.gui.add_account_dialog import AddAccountDialog
from mailbox_manager.gui.close_dialog import (
    CLOSE_ACTION_ASK,
    CLOSE_ACTION_TRAY,
    CloseWindowDialog,
)
from mailbox_manager.gui.compose_dialog import ComposeDialog
from mailbox_manager.gui.content_filter_dialog import ContentFilterDialog
from mailbox_manager.gui.import_dialog import ImportPreviewDialog
from mailbox_manager.gui.mail_viewer_dialog import MailViewerDialog
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.gui.proxy_dialog import AddProxyDialog
from mailbox_manager.gui.settings_dialog import EnterpriseSettingsDialog
from mailbox_manager.importers.smart_parser import SmartAccountParser
from mailbox_manager.services.send_service import (
    OutgoingDraft,
    SendResult,
    SendService,
    SendStatus,
)
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    GroupRepository,
    ProxyRepository,
    SettingsRepository,
    StatisticsRepository,
    TagRepository,
)
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


def _account() -> EmailAccount:
    return EmailAccount(
        account_id=1,
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="owner@example.com",
        secret="must-not-render",
        status=AccountStatus.SUCCESS,
    )


def test_account_table_model_exposes_status_but_not_secret(qtbot) -> None:
    model = AccountTableModel([_account()])

    rendered = [
        model.data(model.index(0, column), Qt.ItemDataRole.DisplayRole)
        for column in range(model.columnCount())
    ]

    assert "owner@example.com" in rendered
    assert "正常" in rendered
    assert all("must-not-render" not in str(value) for value in rendered)


def test_qt_standard_context_menus_are_translated_to_chinese(qtbot) -> None:
    application = QApplication.instance()
    assert application is not None
    assert configure_translations(application) is True
    editor = QLineEdit("text")
    qtbot.addWidget(editor)

    menu = editor.createStandardContextMenu()
    labels = [action.text().replace("&", "") for action in menu.actions()]

    assert any("复制" in label for label in labels)
    assert any("全选" in label for label in labels)


def test_main_window_has_required_controls_and_concurrency_bounds(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "gui.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"E" * 32))
    accounts.add_many([_account()])
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)

    assert window.objectName() == "mainWindow"
    assert window.findChild(QSpinBox, "concurrencySpin").minimum() == 1
    assert window.findChild(QSpinBox, "concurrencySpin").maximum() == 50
    assert (
        window.findChild(QSpinBox, "concurrencySpin").buttonSymbols()
        is QAbstractSpinBox.ButtonSymbols.NoButtons
    )
    assert len(window.findChildren(QPushButton, "spinStepButton")) == 2
    assert window.account_model.rowCount() == 1
    assert window.account_stack.currentWidget() is window.account_table
    assert window.add_account_action.text() == "添加邮箱"
    assert window.import_action.text() == "从文件导入"
    assert window.stop_action.isEnabled() is False

    checkbox = window.account_model.index(0, 0)
    window.account_model.setData(checkbox, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert window._selected_accounts()[0].email == "owner@example.com"
    assert window.account_table.selectionMode() is QAbstractItemView.SelectionMode.NoSelection
    window.refresh_accounts()
    assert window._selected_accounts()[0].email == "owner@example.com"
    assert window.selection_count_label.text() == "已勾选 1 个账号"
    assert window.delete_accounts_button.isEnabled() is True


def test_account_checkbox_responds_to_real_mouse_click_without_row_highlight(
    qtbot, tmp_path
) -> None:
    database = Database(tmp_path / "checkbox-click.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"J" * 32))
    accounts.add_many([_account()])
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()
    checkbox = window.account_model.index(0, 0)

    qtbot.mouseClick(
        window.account_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=window.account_table.visualRect(checkbox).center(),
    )

    assert window.account_model.is_checked(0) is True
    assert len(window._selected_accounts()) == 1
    assert window.account_table.selectionModel().selectedRows() == []

    qtbot.mouseClick(
        window.account_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=window.account_table.visualRect(checkbox).center(),
    )
    assert window.account_model.is_checked(0) is False


def test_clicking_email_copies_address_without_changing_checkbox(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "email-copy.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"C" * 32))
    accounts.add_many([_account()])
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()
    QApplication.clipboard().clear()
    email_index = window.account_model.index(0, 1)

    qtbot.mouseClick(
        window.account_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=window.account_table.visualRect(email_index).center(),
    )

    assert QApplication.clipboard().text() == "owner@example.com"
    assert window.page_toast.isVisible() is True
    assert window.page_toast.message_label.text() == "邮箱已复制 · owner@example.com"
    assert window._active_account_id == 1
    assert window.account_model.is_checked(0) is False
    assert window.account_table.selectionModel().selectedRows() == []


def test_email_is_copied_as_soon_as_mouse_is_pressed(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "email-copy-press.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"P" * 32))
    accounts.add_many([_account()])
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()
    QApplication.clipboard().clear()
    email_index = window.account_model.index(0, 1)

    qtbot.mousePress(
        window.account_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=window.account_table.visualRect(email_index).center(),
    )

    assert QApplication.clipboard().text() == "owner@example.com"
    qtbot.mouseRelease(
        window.account_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=window.account_table.visualRect(email_index).center(),
    )


def test_fetch_controls_have_clear_running_stopping_and_idle_states(
    qtbot, tmp_path
) -> None:
    database = Database(tmp_path / "fetch-controls.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"U" * 32))
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)

    window._set_fetch_ui_state("running")
    assert window.start_action.text() == "取件进行中"
    assert window.start_action.isEnabled() is False
    assert window.stop_action.text() == "停止取件"
    assert window.stop_action.isEnabled() is True
    assert window.security_status.property("state") == "running"
    assert window.concurrency_box.isEnabled() is False

    window._set_fetch_ui_state("stopping")
    assert window.stop_action.text() == "正在停止…"
    assert window.stop_action.isEnabled() is False
    assert window.security_status.property("state") == "warning"

    window._set_fetch_ui_state("idle")
    assert window.start_action.text() == "开始并发取件"
    assert window.start_action.isEnabled() is True
    assert window.stop_action.text() == "停止取件"
    assert window.stop_action.isEnabled() is False
    assert window.security_status.property("state") == "secure"
    assert window.concurrency_box.isEnabled() is True

    window._workers[99] = object()  # type: ignore[assignment]
    window.start_fetch()
    assert window.page_toast.message_label.text() == "已有取件任务正在运行"
    window._workers.clear()


def test_stopped_fetch_summary_includes_cancelled_accounts(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "stopped-summary.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"Y" * 32))
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)
    window._workers[7] = object()  # type: ignore[assignment]
    window._fetch_total = 1
    window._fetch_completed = 0
    window._fetch_results = {7: AccountStatus.CANCELLED}
    window._fetch_stop_requested = True

    window._worker_finished(7)

    assert window.statusBar().currentMessage() == (
        "取件已停止：成功 0，取消 1，失败 0，共 1 个账号"
    )
    assert window.page_toast.message_label.text() == window.statusBar().currentMessage()


def test_settings_dialog_uses_responsive_navigation_and_linked_controls(qtbot) -> None:
    dialog = EnterpriseSettingsDialog(
        {
            "folders": ["INBOX", "Junk"],
            "max_messages": 30,
            "post_action": PostAction.NONE.value,
            "schedule_enabled": False,
            "schedule_interval": 10,
        }
    )
    qtbot.addWidget(dialog)

    assert dialog.minimumWidth() >= 720
    assert dialog.navigation.count() == 9
    assert dialog.pages.count() == 9
    assert (
        dialog.pages.widget(0).horizontalScrollBarPolicy()
        is Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert dialog.navigation.currentRow() == 0
    assert dialog.max_messages.suffix() == " 封"
    dialog.max_messages.setValue(0)
    assert dialog.max_messages.text() == "不限制"
    assert dialog.schedule_interval.suffix() == " 分钟"
    assert dialog.action_target.isEnabled() is False
    assert dialog.schedule_interval.isEnabled() is False

    dialog.navigation.setCurrentRow(3)
    assert dialog.pages.currentIndex() == 3
    dialog.post_action.setCurrentIndex(
        dialog.post_action.findData(PostAction.MOVE.value)
    )
    assert dialog.action_target.isEnabled() is True
    assert dialog.confirm_actions.isEnabled() is True
    dialog.schedule_enabled.setChecked(True)
    assert dialog.schedule_interval.isEnabled() is True
    assert dialog.values()["folders"] == ["INBOX", "Junk"]
    dialog.navigation.setCurrentRow(5)
    assert dialog.pages.currentIndex() == 5
    assert dialog.translation_language.currentData() == "zh-CN"
    assert dialog.translation_confirm.isChecked() is True
    dialog.navigation.setCurrentRow(6)
    assert dialog.pages.currentIndex() == 6
    assert dialog.font_size.value() == 10
    assert dialog.font_weight.currentData() == 500
    dialog.navigation.setCurrentRow(7)
    assert dialog.pages.currentIndex() == 7
    assert dialog.values()["dashboard_quick_actions"] == [
        "accounts",
        "fetch",
        "add_account",
        "content_filter",
    ]
    assert dialog.values()["proxy_fetch_enabled"] is False
    assert dialog.values()["close_action"] == CLOSE_ACTION_ASK
    dialog.navigation.setCurrentRow(8)
    assert dialog.pages.currentIndex() == 8
    assert dialog.update_check_button.text() == "检查系统更新"


def test_close_window_dialog_returns_choice_and_remember_flag(qtbot) -> None:
    dialog = CloseWindowDialog(tray_available=True)
    qtbot.addWidget(dialog)
    dialog.remember_checkbox.setChecked(True)

    dialog.tray_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_action == CLOSE_ACTION_TRAY
    assert dialog.remember_choice is True


def test_close_window_dialog_is_compact_and_font_responsive(qtbot) -> None:
    dialog = CloseWindowDialog(tray_available=True)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(20)

    assert dialog.height() < 400
    assert dialog.width() <= 560
    assert dialog.tray_button.height() >= dialog.tray_button.sizeHint().height()
    assert dialog.exit_button.height() >= dialog.exit_button.sizeHint().height()

    large_font = QFont(dialog.font())
    large_font.setPointSize(18)
    dialog.setFont(large_font)
    dialog.adjustSize()
    qtbot.wait(20)

    assert dialog.tray_button.height() >= dialog.tray_button.sizeHint().height()
    assert dialog.exit_button.height() >= dialog.exit_button.sizeHint().height()


def test_close_window_dialog_disables_unavailable_tray_option(qtbot) -> None:
    dialog = CloseWindowDialog(tray_available=False)
    qtbot.addWidget(dialog)

    assert dialog.tray_button.isEnabled() is False
    assert dialog.tray_button.description_label.text() == "当前系统没有可用的系统托盘"


def test_close_choice_can_be_remembered_and_minimizes_to_tray(
    qtbot, tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "close-choice.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"C" * 32)
    settings = SettingsRepository(database)
    window = MainWindow(
        AccountRepository(database, cipher),
        MessageRepository(database),
        settings=settings,
    )
    qtbot.addWidget(window)

    class FakeTray:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def isVisible(self) -> bool:
            return True

        def showMessage(self, _title, message, *_args) -> None:
            self.messages.append(message)

        def hide(self) -> None:
            pass

    class AcceptedCloseDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, _parent=None, *, tray_available=True) -> None:
            assert tray_available is True
            self.selected_action = CLOSE_ACTION_TRAY
            self.remember_choice = True

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    tray = FakeTray()
    window._tray = tray  # type: ignore[assignment]
    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.CloseWindowDialog",
        AcceptedCloseDialog,
    )
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted() is False
    assert tray.messages == ["程序已最小化到系统托盘，将继续静默运行。"]
    saved = settings.get("enterprise_ui", {})
    assert isinstance(saved, dict)
    assert saved["close_action"] == CLOSE_ACTION_TRAY


def test_add_proxy_dialog_builds_named_encrypted_proxy_input(qtbot) -> None:
    dialog = AddProxyDialog()
    qtbot.addWidget(dialog)
    dialog.name_input.setText("本地 SOCKS")
    dialog.host_input.setText("127.0.0.1")
    dialog.port_input.setValue(1080)
    dialog.username_input.setText("proxy-user")
    dialog.password_input.setText("proxy-password")
    dialog.default_proxy.setChecked(True)

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.proxy is not None
    assert dialog.proxy.name == "本地 SOCKS"
    assert dialog.proxy.proxy_type is ProxyType.SOCKS5
    assert dialog.proxy.host == "127.0.0.1"
    assert dialog.proxy.password == "proxy-password"
    assert dialog.proxy.is_default is True
    assert dialog.password_input.echoMode() is QLineEdit.EchoMode.Password


def test_settings_buttons_emit_proxy_and_update_requests(qtbot) -> None:
    dialog = EnterpriseSettingsDialog({"proxy_count": 2})
    qtbot.addWidget(dialog)
    proxy_requests: list[bool] = []
    update_requests: list[bool] = []
    dialog.addProxyRequested.connect(lambda: proxy_requests.append(True))
    dialog.updateCheckRequested.connect(lambda: update_requests.append(True))

    dialog.add_proxy_button.click()
    dialog.update_check_button.click()
    dialog.set_proxy_count(3)

    assert proxy_requests == [True]
    assert update_requests == [True]
    assert dialog.proxy_count_label.text() == "当前已保存 3 个代理"


def test_main_window_add_proxy_dialog_persists_encrypted_proxy(
    qtbot, tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "single-proxy.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"P" * 32)
    accounts = AccountRepository(database, cipher)
    proxies = ProxyRepository(database, cipher)
    window = MainWindow(
        accounts,
        MessageRepository(database),
        proxies=proxies,
    )
    qtbot.addWidget(window)
    expected = ProxyConfig(
        name="香港节点 1",
        proxy_type=ProxyType.SOCKS5,
        host="127.0.0.1",
        port=1080,
        username="proxy-user",
        password="proxy-password",
        is_default=True,
    )

    class AcceptedProxyDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, _parent=None) -> None:
            self.proxy = expected

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.AddProxyDialog",
        AcceptedProxyDialog,
    )

    window._show_add_proxy_dialog()

    saved = proxies.list_all()
    assert len(saved) == 1
    assert saved[0].display_name == "香港节点 1"
    assert saved[0].password == "proxy-password"
    assert saved[0].is_default is True
    with database.connect() as connection:
        ciphertext = connection.execute(
            "SELECT password_ciphertext FROM proxies"
        ).fetchone()["password_ciphertext"]
    assert "proxy-password" not in ciphertext


def test_settings_can_customize_fetch_extraction_rules(qtbot, monkeypatch) -> None:
    dialog = EnterpriseSettingsDialog({"post_action": PostAction.NONE.value})
    qtbot.addWidget(dialog)
    dialog.extract_keywords.setPlainText("订单号\n确认链接,verification code")
    dialog.extract_pattern.setText(r"https?://[^\s]+")

    values = dialog.values()

    assert values["extract_keywords"] == ["订单号", "确认链接", "verification code"]
    assert values["extract_pattern"] == r"https?://[^\s]+"

    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    dialog.extract_pattern.setText(r"(a+)+$")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert warnings


def test_main_window_applies_unlimited_and_custom_extraction_settings(
    qtbot, tmp_path
) -> None:
    database = Database(tmp_path / "fetch-settings.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"X" * 32))
    settings = SettingsRepository(database)
    settings.set(
        "fetch",
        {
            "folders": ["INBOX"],
            "max_messages": 0,
            "extract_keywords": ["订单号", "确认链接"],
            "extract_pattern": r"https?://[^\s]+",
        },
    )
    window = MainWindow(
        accounts,
        MessageRepository(database),
        settings=settings,
    )
    qtbot.addWidget(window)

    request = window._build_fetch_request()

    assert request.unlimited is True
    assert request.keywords == ("订单号", "确认链接")
    assert request.custom_pattern == r"https?://[^\s]+"


def test_settings_validation_keeps_dialog_and_user_input_open(qtbot, monkeypatch) -> None:
    dialog = EnterpriseSettingsDialog({"post_action": PostAction.NONE.value})
    qtbot.addWidget(dialog)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    dialog.post_action.setCurrentIndex(
        dialog.post_action.findData(PostAction.MOVE.value)
    )
    dialog.confirm_actions.setChecked(True)
    dialog.action_target.setText("")

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.navigation.currentRow() == 0
    assert warnings[0][0] == "缺少目标文件夹"
    assert "当前设置内容已保留" in warnings[0][1]


def test_empty_account_list_shows_actionable_empty_state(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "empty.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"G" * 32))
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)

    assert window.account_stack.currentWidget().objectName() == "emptyAccountState"
    assert "添加邮箱" in window.empty_account_label.text()


def test_add_account_dialog_builds_provider_specific_accounts(qtbot) -> None:
    dialog = AddAccountDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.provider_list.count() == 10
    assert dialog.selected_provider_key == "microsoft"
    assert dialog.oauth_card.isVisible() is True
    assert dialog.secret.isVisible() is False

    dialog.provider_list.setCurrentRow(1)
    dialog.email.setText("owner@gmail.com")
    dialog.secret.setText("abcd efgh ijkl mnop")
    gmail = dialog._build_account()
    assert gmail.protocol is ProtocolType.IMAP
    assert gmail.host == "imap.gmail.com"
    assert gmail.secret == "abcdefghijklmnop"
    assert gmail.smtp_host == "smtp.gmail.com"

    dialog.auth_mode.setCurrentIndex(1)
    dialog.client_id.setText("123456789-example.apps.googleusercontent.com")
    dialog.refresh_token.setPlainText("google-refresh-token")
    gmail_oauth = dialog._build_account()
    assert gmail_oauth.oauth_provider == "google"
    assert gmail_oauth.client_id.endswith(".apps.googleusercontent.com")

    dialog.provider_list.setCurrentRow(2)
    dialog.email.setText("owner@qq.com")
    dialog.secret.setText("qq-authorization-code")
    qq_account = dialog._build_account()
    assert qq_account.provider == "QQ 邮箱"
    assert qq_account.host == "imap.qq.com"

    dialog.provider_list.setCurrentRow(9)
    dialog.email.setText("owner@example.org")
    dialog.secret.setText("app-password")
    dialog.host.clear()
    custom = dialog._build_account()
    assert custom.provider == "custom"
    assert custom.host == "imap.example.org"
    assert custom.port == 993


def test_add_account_dialog_builds_microsoft_graph_oauth_account(qtbot) -> None:
    dialog = AddAccountDialog()
    qtbot.addWidget(dialog)
    dialog.email.setText("owner@company.example")
    dialog.client_id.setText("00000000-0000-0000-0000-000000000001")
    dialog.refresh_token.setPlainText("refresh-token-value")

    account = dialog._build_account()

    assert account.protocol is ProtocolType.GRAPH
    assert account.oauth_provider == "microsoft"
    assert account.tenant == "common"


def test_main_window_add_account_flow_saves_and_selects_account(
    qtbot, tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "single-add.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"A" * 32))
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)
    added = EmailAccount(
        email="owner@gmail.com",
        provider="Gmail",
        protocol=ProtocolType.IMAP,
        host="imap.gmail.com",
        port=993,
        security=SecurityMode.SSL,
        username="owner@gmail.com",
        secret="app-password",
    )

    class FakeAddAccountDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, _parent) -> None:
            self.account = added

        def exec(self):
            return self.DialogCode.Accepted

    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.AddAccountDialog",
        FakeAddAccountDialog,
    )

    window.show_add_account()

    stored = accounts.list_all()
    assert len(stored) == 1
    assert stored[0].email == "owner@gmail.com"
    assert window._active_account_id == stored[0].account_id
    assert window.page_toast.message_label.text() == "邮箱已添加 · owner@gmail.com"


def test_import_preview_shows_oauth_mapping_and_allows_row_selection(qtbot) -> None:
    preview = SmartAccountParser().parse_text(
        "owner@outlook.com----password----"
        "00000000-0000-0000-0000-000000000001----refresh-token-value"
    )
    dialog = ImportPreviewDialog(preview)
    qtbot.addWidget(dialog)

    assert dialog.table.item(0, 4).text() == "Microsoft Graph OAuth2"
    assert len(dialog.valid_accounts) == 1
    dialog.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.valid_accounts == ()


def test_batch_import_confirmation_persists_and_reveals_accounts(
    qtbot, tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "batch-import-gui.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"B" * 32))
    window = MainWindow(
        accounts,
        MessageRepository(database),
        statistics=StatisticsRepository(database),
    )
    qtbot.addWidget(window)
    window.account_search.setText("filter-that-hides-new-account")
    preview = SmartAccountParser().parse_text(
        "owner@gmail.com----abcd efgh ijkl mnop"
    )

    class AcceptedImportDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, current_preview, _parent) -> None:
            self.valid_accounts = current_preview.valid_accounts

        def exec(self):
            return self.DialogCode.Accepted

    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.ImportPreviewDialog",
        AcceptedImportDialog,
    )

    window._confirm_import_preview(preview)

    stored = accounts.list_all()
    assert len(stored) == 1
    assert stored[0].email == "owner@gmail.com"
    assert window.main_tabs.currentWidget() is window.account_workspace
    assert window.account_search.text() == ""
    assert window.account_model.rowCount() == 1
    assert window.page_toast.message_label.text() == (
        "批量导入完成 · 新增 1 · 更新 0 · 跳过 0"
    )


def test_workspace_sections_are_resizable_and_sizes_are_persisted(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "splitters.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"S" * 32))
    settings = SettingsRepository(database)
    window = MainWindow(accounts, MessageRepository(database), settings=settings)
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()

    assert window.workspace_splitter.count() == 2
    assert window.content_splitter.count() == 2
    assert window.message_splitter.count() == 2
    assert window.workspace_splitter.handleWidth() >= 7
    assert window.content_splitter.handleWidth() >= 7

    window.workspace_splitter.setSizes([280, 900])
    window.content_splitter.setSizes([400, 290])
    window.message_splitter.setSizes([320, 600])
    window._save_splitter_sizes()

    saved = settings.get("ui_splitters", {})
    assert len(saved["workspace"]) == 2
    assert len(saved["content"]) == 2
    assert len(saved["messages"]) == 2


def test_log_drawer_is_hidden_by_default_and_can_be_toggled(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "log-drawer.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"L" * 32))
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)
    window.show()

    assert window.log_dock.isVisible() is False
    assert not (window.dockOptions() & window.DockOption.AnimatedDocks)
    window.log_action.trigger()
    assert window.log_dock.isVisible() is True
    assert window.log_action.text() == "收起运行日志"
    qtbot.waitUntil(
        lambda: window._log_opacity_animation.state()
        is QAbstractAnimation.State.Stopped
    )
    window.log_action.trigger()
    assert window.log_action.text() == "显示运行日志"
    qtbot.waitUntil(lambda: window.log_dock.isVisible() is False)


def test_main_message_body_initializes_webengine_only_when_used(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "lazy-message-body.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"Y" * 32))
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)

    assert window.message_body.is_initialized is False
    window.message_body.clear()
    assert window.message_body.is_initialized is False

    window.message_body.setPlainText("延迟加载后的正文")

    assert window.message_body.is_initialized is True
    assert window.message_body.toPlainText() == "延迟加载后的正文"


def test_message_view_renders_inline_and_remote_images_directly(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "html-message.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"H" * 32))
    accounts.add_many([_account()])
    messages = MessageRepository(database)
    messages.add_many(
        1,
        (
            MailMessage(
                provider_message_id="html-1",
                folder="INBOX",
                subject="图文邮件",
                text_body="图文正文",
                html_body=(
                    '<p>图文正文</p><img alt="内嵌图" '
                    'src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB'
                    'CAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=">'
                    '<img src="https://images.example.com/banner.png" alt="网络图">'
                ),
            ),
        ),
    )
    window = MainWindow(accounts, messages)
    qtbot.addWidget(window)

    window._account_row_clicked(window.account_model.index(0, 1))

    rendered = window.message_body.document().toHtml()
    assert "图文正文" in window.message_body.toPlainText()
    assert "data:image/png;base64" in rendered
    assert "https://images.example.com/banner.png" in rendered
    assert window.message_tools_bar.isHidden() is False


def test_main_message_detail_displays_image_attachments_and_download_panel(
    qtbot, tmp_path
) -> None:
    database = Database(tmp_path / "main-attachment-image.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"G" * 32))
    accounts.add_many([_account()])
    messages = MessageRepository(database)
    image = b"\x89PNG\r\n\x1a\nsmall-image"
    messages.add_many(
        1,
        (
            MailMessage(
                provider_message_id="image-attachment",
                folder="INBOX",
                subject="图片附件",
                text_body="正文",
                attachments=(
                    MailAttachment(
                        filename="photo.png",
                        content_type="image/png",
                        size=len(image),
                        content=image,
                    ),
                ),
            ),
        ),
    )
    window = MainWindow(accounts, messages)
    qtbot.addWidget(window)

    window._account_row_clicked(window.account_model.index(0, 1))

    rendered = window.message_body.document().toHtml()
    assert window.message_attachment_panel.isHidden() is False
    assert "photo.png" in window.message_attachment_list.item(0).text()
    assert "data:image/png;base64" in rendered
    assert "图片附件" in window.message_body.toPlainText()


def test_batch_delete_removes_checked_accounts_and_messages(
    qtbot, tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "delete-accounts.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"D" * 32))
    accounts.add_many([_account()])
    messages = MessageRepository(database)
    messages.add_many(
        1,
        (MailMessage(provider_message_id="delete-me", folder="INBOX", text_body="body"),),
    )
    window = MainWindow(accounts, messages)
    qtbot.addWidget(window)
    window.account_model.setData(
        window.account_model.index(0, 0),
        Qt.CheckState.Checked,
        Qt.ItemDataRole.CheckStateRole,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    window.delete_selected_accounts()

    assert accounts.list_all() == []
    assert messages.list_for_account(1) == []
    assert window.account_model.rowCount() == 0


def test_immediate_fetch_queues_only_the_active_account(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "quick-fetch.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"U" * 32))
    accounts.add_many([_account()])
    settings = SettingsRepository(database)
    settings.set("fetch", {"folders": ["INBOX"], "max_messages": 37})
    window = MainWindow(accounts, MessageRepository(database), settings=settings)
    qtbot.addWidget(window)
    queued: list[tuple[list[EmailAccount], FetchRequest]] = []
    window._queue_fetch = lambda selected, request: queued.append(  # type: ignore[method-assign]
        (selected, request)
    )

    window._account_row_clicked(window.account_model.index(0, 1))
    window.fetch_active_account()

    assert len(queued) == 1
    selected, request = queued[0]
    assert [account.email for account in selected] == ["owner@example.com"]
    assert request.max_messages == 37


def test_checked_account_can_send_from_compose_dialog_in_background(
    qtbot, tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "compose-send.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"W" * 32))
    accounts.add_many([_account()])
    sent_from: list[str] = []

    class FakeClient:
        def __init__(self, account: EmailAccount) -> None:
            self.account = account

        def send_message(self, _draft: OutgoingDraft) -> SendResult:
            sent_from.append(self.account.email)
            return SendResult(SendStatus.SUCCESS, "已发送")

        def close(self) -> None:
            pass

    service = SendService(client_factory=FakeClient)
    window = MainWindow(
        accounts,
        MessageRepository(database),
        send_service=service,
    )
    qtbot.addWidget(window)
    draft = OutgoingDraft(to=("target@example.net",), text_body="hello")

    class AcceptedComposeDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, selected, _parent) -> None:
            self.accounts = selected
            self.draft = draft

        def exec(self):
            return self.DialogCode.Accepted

    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.ComposeDialog",
        AcceptedComposeDialog,
    )
    monkeypatch.setattr(window._pool, "start", lambda worker: worker.run())
    window.account_model.setData(
        window.account_model.index(0, 0),
        Qt.CheckState.Checked,
        Qt.ItemDataRole.CheckStateRole,
    )

    window.show_compose_dialog()

    assert sent_from == ["owner@example.com"]
    assert window._send_worker is None
    assert window.page_toast.message_label.text() == (
        "发件完成：成功 1，失败 0，共 1 个邮箱"
    )


def test_message_search_and_filtered_copy_are_scoped(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "message-search.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"V" * 32))
    accounts.add_many([_account()])
    stored = accounts.list_all()[0]
    messages = MessageRepository(database)
    messages.add_many(
        stored.account_id,
        (
            MailMessage(
                provider_message_id="searchable",
                folder="INBOX",
                subject="Account notice",
                text_body="Use https://example.com/reset/ABC123 and ignore private footer.",
                html_body=(
                    '<a href="https://example.com/reset/ABC123">Reset</a>'
                ),
            ),
        ),
    )
    window = MainWindow(accounts, messages)
    qtbot.addWidget(window)
    window._account_row_clicked(window.account_model.index(0, 1))
    window.message_search_input.setText("Account notice")
    window.search_messages()

    assert len(window._displayed_messages) == 1
    dialog = ContentFilterDialog(
        messages,
        current_account_id=stored.account_id,
        current_account_email=stored.email,
    )
    qtbot.addWidget(dialog)
    dialog.query_input.setText("https://example.com/reset/*")
    dialog.mode_combo.setCurrentIndex(1)
    dialog.run_filter()
    dialog.copy_results()

    copied = QApplication.clipboard().text()
    assert "https://example.com/reset/ABC123" in copied
    assert "private footer" not in copied


def test_copy_totp_places_only_current_code_on_clipboard(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "totp.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"F" * 32))
    account = EmailAccount(
        email="totp@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="totp@example.com",
        secret="password",
        totp_secret="JBSWY3DPEHPK3PXP",
    )
    accounts.add_many([account])
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)

    assert window.copy_totp(accounts.list_all()[0]) is True
    clipboard_value = QApplication.clipboard().text()
    assert len(clipboard_value) == 6
    assert clipboard_value.isdigit()
    assert "JBSWY3DPEHPK3PXP" not in clipboard_value


def test_enterprise_window_filters_tree_groups_and_shows_dashboard(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "enterprise-gui.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"K" * 32)
    accounts = AccountRepository(database, cipher)
    groups = GroupRepository(database)
    tags = TagRepository(database)
    group_id = groups.create(Group(name="项目A"))
    channel_id = groups.create(Group(name="渠道1", parent_id=group_id))
    tag_id = tags.create(Tag(name="重点"))
    account = _account()
    accounts.add_many([account])
    stored = accounts.list_all()[0]
    accounts.update_group([stored.account_id], channel_id)  # type: ignore[list-item]
    tags.assign(stored.account_id, tag_id)  # type: ignore[arg-type]
    window = MainWindow(
        accounts,
        MessageRepository(database),
        groups=groups,
        tags=tags,
        statistics=StatisticsRepository(database),
    )
    qtbot.addWidget(window)

    assert window.main_tabs.count() == 2
    assert window.main_tabs.widget(0) is window.dashboard
    assert window.dashboard.total_card.value_label.text() == "1"
    window._set_fetch_ui_state("running")
    assert window.dashboard.fetch_button.text() == "取件进行中"
    assert window.dashboard.fetch_button.isEnabled() is False
    window._set_fetch_ui_state("idle")
    assert window.dashboard.fetch_button.text() == "开始批量取件"
    assert window.dashboard.fetch_button.isEnabled() is True
    window.dashboard.navigateAccountsRequested.emit()
    assert window.main_tabs.currentWidget() is window.account_workspace
    root = window.group_tree.topLevelItem(0)
    assert root.child(0).text(0).startswith("未分组")
    assert root.child(1).text(0).startswith("项目A")
    window.group_tree.setCurrentItem(root.child(1))
    assert window.account_model.rowCount() == 1
    assert window.account_model.account_at(0).tags == ("重点",)  # type: ignore[union-attr]
    window.group_tree.setCurrentItem(root.child(0))
    assert window.account_model.rowCount() == 0


def test_account_column_visibility_is_saved_without_sensitive_columns(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "columns.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"N" * 32))
    accounts.add_many([_account()])
    settings = SettingsRepository(database)
    window = MainWindow(accounts, MessageRepository(database), settings=settings)
    qtbot.addWidget(window)

    labels = {action.text() for action in window.column_menu.actions()}
    assert "账号" in labels
    assert "密码" not in labels
    assert "Token" not in labels
    window._column_actions[4].setChecked(False)

    assert window.account_table.isColumnHidden(4) is True
    assert settings.get("account_columns", {}) == {"hidden": [4]}


def test_mail_viewer_groups_folders_and_renders_safe_html(qtbot) -> None:
    account = _account()
    inbox = MailMessage(
        message_id=1,
        provider_message_id="viewer-1",
        folder="INBOX",
        subject="Welcome",
        sender="hello@example.com",
        text_body="Welcome body",
        html_body="<p>Welcome <b>body</b></p><script>bad()</script>",
    )
    junk = MailMessage(
        message_id=2,
        provider_message_id="viewer-2",
        folder="Junk",
        subject="Other folder",
        text_body="Junk body",
    )
    dialog = MailViewerDialog(account, [inbox, junk], selected_message_id=1)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.inbox_list.count() == 1
    assert dialog.special_list.count() == 1
    assert dialog.subject_label.text() == "Welcome"
    assert "Welcome body" in dialog.body.toPlainText()
    assert "bad()" not in dialog.body.toPlainText()

    dialog.search_input.setText("Other folder")
    assert dialog.inbox_list.count() == 0
    assert dialog.special_list.count() == 1


def test_mail_viewer_lists_and_saves_received_attachments(
    qtbot, tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "viewer-attachments.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"T" * 32))
    accounts.add_many([_account()])
    account = accounts.list_all()[0]
    messages = MessageRepository(database)
    messages.add_many(
        account.account_id,
        (
            MailMessage(
                provider_message_id="with-attachment",
                folder="INBOX",
                subject="附件邮件",
                text_body="请查收",
                attachments=(
                    MailAttachment(
                        filename="report.pdf",
                        content_type="application/pdf",
                        size=7,
                        content=b"PDFDATA",
                    ),
                ),
            ),
        ),
    )
    loaded = messages.list_for_account(account.account_id)
    dialog = MailViewerDialog(
        account,
        loaded,
        message_repository=messages,
    )
    qtbot.addWidget(dialog)
    target = tmp_path / "saved-report.pdf"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(target), "所有文件 (*.*)"),
    )

    assert dialog.attachment_panel.isHidden() is False
    assert dialog.attachment_list.count() == 1
    assert "report.pdf" in dialog.attachment_list.item(0).text()
    dialog._save_selected_attachment()

    assert target.read_bytes() == b"PDFDATA"
    assert "附件已保存" in dialog.feedback_label.text()


def test_mail_viewer_link_context_menu_copies_only_the_link(
    qtbot,
) -> None:
    dialog = MailViewerDialog(
        _account(),
        [
            MailMessage(
                provider_message_id="link",
                folder="INBOX",
                html_body='<a href="https://example.com/action?id=7">打开操作</a>',
            )
        ],
    )
    qtbot.addWidget(dialog)
    QApplication.clipboard().clear()

    dialog._copy_link(QUrl("https://example.com/action?id=7"))

    assert QApplication.clipboard().text() == "https://example.com/action?id=7"
    assert dialog.feedback_label.text() == "链接已复制"


def test_compose_dialog_builds_rich_draft_with_attachment(
    qtbot, tmp_path, monkeypatch
) -> None:
    attachment = tmp_path / "invoice.txt"
    attachment.write_text("invoice-data", encoding="utf-8")
    dialog = ComposeDialog([_account()])
    qtbot.addWidget(dialog)
    dialog.to_input.setText("first@example.net; second@example.net")
    dialog.subject_input.setText("测试邮件")
    dialog.body_editor.setText("正文和链接 https://example.net")
    dialog._attachment_paths = [Path(attachment)]
    dialog._refresh_attachments()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.draft is not None
    assert dialog.draft.to == ("first@example.net", "second@example.net")
    assert dialog.draft.subject == "测试邮件"
    assert dialog.draft.attachments[0].filename == "invoice.txt"
    assert dialog.draft.attachments[0].content == b"invoice-data"
