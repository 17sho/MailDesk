from __future__ import annotations

import base64
import logging
import threading
from collections import Counter
from html import escape as html_escape
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTableView,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.domain.models import (
    AccountStatus,
    AutomationRule,
    EmailAccount,
    FetchRequest,
    FetchResult,
    Group,
    ImportPreview,
    MailAttachment,
    MailMessage,
    PostAction,
    ProtocolType,
    ProxyType,
    ScheduleConfig,
    Tag,
    WebhookConfig,
)
from mailbox_manager.domain.status import STATUS_LABELS
from mailbox_manager.gui.account_model import (
    AccountCheckHeader,
    AccountTableModel,
    AccountTableView,
)
from mailbox_manager.gui.add_account_dialog import AddAccountDialog
from mailbox_manager.gui.appearance import (
    apply_application_appearance,
    normalized_appearance,
    scaled_stylesheet,
)
from mailbox_manager.gui.close_dialog import (
    CLOSE_ACTION_ASK,
    CLOSE_ACTION_EXIT,
    CLOSE_ACTION_TRAY,
    CLOSE_ACTIONS,
    CloseWindowDialog,
)
from mailbox_manager.gui.compose_dialog import ComposeDialog
from mailbox_manager.gui.content_filter_dialog import ContentFilterDialog
from mailbox_manager.gui.dashboard import DashboardWidget, configured_quick_action_ids
from mailbox_manager.gui.icons import line_icon
from mailbox_manager.gui.import_dialog import ImportPreviewDialog
from mailbox_manager.gui.lazy_email_body_view import LazyEmailBodyView
from mailbox_manager.gui.proxy_dialog import AddProxyDialog
from mailbox_manager.gui.settings_dialog import EnterpriseSettingsDialog
from mailbox_manager.gui.theme import DARK_THEME, LIGHT_THEME
from mailbox_manager.gui.toast import BottomToast
from mailbox_manager.gui.update_dialog import UpdateDialog, UpdateDialogState
from mailbox_manager.gui.workers import (
    DiscoveryWorker,
    FetchWorker,
    SecurityAuditWorker,
    SecurityConsentWorker,
    SendBatchWorker,
    SmtpProbeWorker,
    TranslationWorker,
    UpdateCheckWorker,
    UpdateDownloadWorker,
    UpdateInstallWorker,
)
from mailbox_manager.importers.file_importer import import_file
from mailbox_manager.importers.smart_parser import SmartAccountParser
from mailbox_manager.mail.display import select_stored_message_display_content
from mailbox_manager.mail.parser import clean_message_text
from mailbox_manager.mail.web_document import prepare_email_web_document
from mailbox_manager.services.audit_report import AuditReportService
from mailbox_manager.services.eml_store import EmlStore
from mailbox_manager.services.export_service import (
    export_accounts_csv,
    export_accounts_txt,
    export_messages_csv,
)
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.services.interactive_browser import open_official_webmail
from mailbox_manager.services.proxy_service import parse_proxy_text
from mailbox_manager.services.scheduler_service import ScheduleRunner
from mailbox_manager.services.security_audit import (
    SecurityAuditAuthenticationError,
    SecurityAuditPermissionError,
    SecurityAuditTemporaryError,
)
from mailbox_manager.services.security_authorization import (
    DeviceAuthorizationCancelled,
    DeviceCodeChallenge,
)
from mailbox_manager.services.send_service import BatchSendResult, SendService
from mailbox_manager.services.throttle import ComplianceThrottle
from mailbox_manager.services.totp_service import current_totp
from mailbox_manager.services.translation_service import (
    DEFAULT_TRANSLATION_LANGUAGE,
    TRANSLATION_LANGUAGES,
    TranslationError,
    TranslationService,
    translation_language_label,
)
from mailbox_manager.services.update_service import (
    InstallMode,
    StagedUpdate,
    UpdateError,
    UpdateInfo,
    UpdateSecurityError,
    UpdateService,
)
from mailbox_manager.storage.enterprise_repositories import (
    AutomationRuleRepository,
    GroupRepository,
    ProxyRepository,
    ScheduleRepository,
    SettingsRepository,
    StatisticsRepository,
    TagRepository,
    WebhookRepository,
)
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository

if TYPE_CHECKING:
    from mailbox_manager.gui.mail_viewer_dialog import MailViewerDialog

_GROUP_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_GROUP_NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 2

_TOOLBAR_COMPACT_BREAKPOINT = 1320
_WORKSPACE_COMPACT_BREAKPOINT = 1180

_ONE_SHOT_ENTERPRISE_SETTING_KEYS = frozenset(
    {
        "proxy_text",
        "webhook_name",
        "webhook_url",
        "webhook_secret",
        "rule_name",
        "rule_pattern",
        "rule_action",
        "rule_target",
        "rule_webhook_id",
        "rule_forward",
    }
)
_UI_PREFERENCE_KEYS = frozenset(
    {"dark_theme", "font_family", "font_size", "font_weight"}
)


def _persistent_enterprise_settings(values: dict[str, object]) -> dict[str, object]:
    """Remove import/create-once form fields before saving reusable settings."""

    return {
        key: value
        for key, value in values.items()
        if key not in _ONE_SHOT_ENTERPRISE_SETTING_KEYS | _UI_PREFERENCE_KEYS
    }


class MainWindow(QMainWindow):
    def __init__(
        self,
        accounts: AccountRepository,
        messages: MessageRepository,
        fetch_service: FetchService | None = None,
        *,
        groups: GroupRepository | None = None,
        tags: TagRepository | None = None,
        proxies: ProxyRepository | None = None,
        schedules: ScheduleRepository | None = None,
        settings: SettingsRepository | None = None,
        webhooks: WebhookRepository | None = None,
        rules: AutomationRuleRepository | None = None,
        statistics: StatisticsRepository | None = None,
        audit_reports: AuditReportService | None = None,
        eml_store: EmlStore | None = None,
        send_service: SendService | None = None,
        translation_service: TranslationService | None = None,
        update_service: UpdateService | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("MailDesk · 邮箱工作台")
        self.resize(1440, 900)
        self.setMinimumSize(1080, 680)
        self.setAcceptDrops(True)
        self._accounts = accounts
        self._messages = messages
        self._fetch_service = fetch_service or FetchService(accounts, messages)
        self._groups = groups
        self._tags = tags
        self._proxies = proxies
        self._schedules = schedules
        self._settings = settings
        self._webhooks = webhooks
        self._rules = rules
        self._statistics = statistics
        self._audit_reports = audit_reports
        self._eml_store = eml_store
        self._send_service = send_service or SendService()
        self._update_service = update_service
        self._update_info: UpdateInfo | None = None
        self._staged_update: StagedUpdate | None = None
        self._update_dialog: UpdateDialog | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_install_worker: UpdateInstallWorker | None = None
        self._update_download_worker: UpdateDownloadWorker | None = None
        self._update_operation_id: str | None = None
        self._update_download_identity: tuple[str, str, str, str, str] | None = None
        self._update_check_manual = False
        self._update_received_bytes = 0
        self._update_total_bytes: int | None = None
        translation_values = (
            settings.get("enterprise_ui", {}) if settings is not None else {}
        )
        translation_values = (
            dict(translation_values) if isinstance(translation_values, dict) else {}
        )
        safe_enterprise_values = _persistent_enterprise_settings(translation_values)
        if settings is not None and safe_enterprise_values != translation_values:
            try:
                settings.set("enterprise_ui", safe_enterprise_values)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Unable to remove legacy one-shot fields from enterprise settings"
                )
        translation_values = safe_enterprise_values
        self._translation_service = translation_service or TranslationService()
        self._translation_language = _valid_translation_language(
            str(
                translation_values.get(
                    "translation_language", DEFAULT_TRANSLATION_LANGUAGE
                )
            )
        )
        self._translation_confirm = bool(
            translation_values.get("translation_confirm", True)
        )
        self._proxy_fetch_enabled = bool(
            translation_values.get("proxy_fetch_enabled", False)
        )
        self._dashboard_quick_actions = configured_quick_action_ids(
            translation_values.get("dashboard_quick_actions")
        )
        self._pool = QThreadPool(self)
        # Updating must never wait behind 50 slow IMAP jobs.  A dedicated serial
        # pool makes the confirm -> verify -> external-helper hand-off immediate.
        self._update_pool = QThreadPool(self)
        self._update_pool.setMaxThreadCount(1)
        self._stop_event = threading.Event()
        self._fetch_stop_requested = False
        self._workers: dict[int, FetchWorker] = {}
        self._smtp_workers: dict[int, SmtpProbeWorker] = {}
        self._send_worker: SendBatchWorker | None = None
        self._discovery_workers: dict[int, DiscoveryWorker] = {}
        self._security_workers: dict[int, SecurityAuditWorker] = {}
        self._security_consent_workers: dict[int, SecurityConsentWorker] = {}
        self._security_consent_dialogs: dict[int, QMessageBox] = {}
        self._translation_workers: dict[int, TranslationWorker] = {}
        self._message_generation = 0
        self._translation_generation = 0
        self._active_translation_generation: int | None = None
        self._rendered_html_fragment = ""
        self._original_plain_text = ""
        self._translation_source_text = ""
        self._translated_text = ""
        self._showing_translation = False
        self._current_message: MailMessage | None = None
        self._visible_message_attachments: tuple[MailAttachment, ...] = ()
        self._current_attachment_gallery = ""
        self._active_account_id: int | None = None
        self._content_filter_dialog: ContentFilterDialog | None = None
        self._mail_viewer: MailViewerDialog | None = None
        ui_preferences = settings.get("ui_preferences", {}) if settings is not None else {}
        ui_preferences = ui_preferences if isinstance(ui_preferences, dict) else {}
        appearance = normalized_appearance(ui_preferences)
        self._dark = bool(appearance["dark_theme"])
        self._font_family = str(appearance["font_family"])
        self._font_size = int(appearance["font_size"])
        self._font_weight = int(appearance["font_weight"])
        application = QApplication.instance()
        if application is not None:
            apply_application_appearance(application, appearance)
        self._tray: QSystemTrayIcon | None = None
        self._force_close = False
        self._toolbar_compact: bool | None = None
        self._workspace_compact: bool | None = None
        self._wide_account_column_widths = (
            42,
            310,
            120,
            80,
            260,
            110,
            155,
            95,
        )
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(350)
        self._layout_save_timer.timeout.connect(self._save_splitter_sizes)
        self.account_model = AccountTableModel(self._accounts.list_all())
        self._create_actions()
        self._create_toolbar()
        self._create_content()
        self.page_toast = BottomToast(self)
        self.setStyleSheet(
            scaled_stylesheet(
                DARK_THEME if self._dark else LIGHT_THEME,
                self._font_size,
            )
        )
        self.theme_action.setText("浅色主题" if self._dark else "深色主题")
        if hasattr(self, "dashboard"):
            self.dashboard.apply_theme(self._dark)
        if self._mail_viewer is not None:
            self._mail_viewer.apply_theme(self._dark)
        self.statusBar().showMessage("就绪")
        self.security_status = QLabel("● 本地凭据已加密")
        self.security_status.setObjectName("statusPill")
        self.security_status.setProperty("state", "secure")
        self.security_status.setToolTip("敏感字段由系统安全存储与 Fernet 加密保护")
        self.statusBar().addPermanentWidget(self.security_status)
        self._set_fetch_ui_state("idle")
        self._apply_responsive_layout(self.width())
        if self._schedules is not None:
            self._schedule_runner = ScheduleRunner(self._schedules, self._start_fetch_group)
            self._schedule_timer = QTimer(self)
            self._schedule_timer.setInterval(30_000)
            self._schedule_timer.timeout.connect(self._run_due_schedules)
            self._schedule_timer.start()
        if self._update_service is not None:
            self._startup_update_timer = QTimer(self)
            self._startup_update_timer.setSingleShot(True)
            self._startup_update_timer.setInterval(1800)
            self._startup_update_timer.timeout.connect(
                lambda: self.check_for_updates(manual=False)
            )
            self._startup_update_timer.start()

    def _create_actions(self) -> None:
        self.add_account_action = QAction("添加邮箱", self)
        self.add_account_action.setShortcut("Ctrl+N")
        self.add_account_action.triggered.connect(self.show_add_account)
        self.import_action = QAction("从文件导入", self)
        self.import_action.setShortcut("Ctrl+I")
        self.import_action.triggered.connect(self.choose_import)
        self.paste_import_action = QAction("粘贴批量导入", self)
        self.paste_import_action.setShortcut("Ctrl+Shift+I")
        self.paste_import_action.triggered.connect(self.choose_paste_import)
        self.export_action = QAction("批量导出", self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.triggered.connect(self.choose_export)
        self.compose_action = QAction("写邮件", self)
        self.compose_action.setShortcut("Ctrl+M")
        self.compose_action.setToolTip("使用当前账号或已勾选账号发件")
        self.compose_action.triggered.connect(lambda: self.show_compose_dialog())
        self.start_action = QAction("开始并发取件", self)
        self.start_action.setShortcut("Ctrl+R")
        self.start_action.triggered.connect(self.start_fetch)
        self.stop_action = QAction("停止取件", self)
        self.stop_action.setEnabled(False)
        self.stop_action.setToolTip("安全停止当前取件任务")
        self.stop_action.triggered.connect(self.stop_fetch)
        self.theme_action = QAction("深色主题", self)
        self.theme_action.triggered.connect(self.toggle_theme)
        self.settings_action = QAction("系统设置", self)
        self.settings_action.triggered.connect(self.show_settings)
        self.audit_action = QAction("导出审计报告", self)
        self.audit_action.triggered.connect(self.export_audit_report)
        self.reset_layout_action = QAction("重置界面布局", self)
        self.reset_layout_action.setShortcut("Ctrl+0")
        self.reset_layout_action.triggered.connect(self.reset_layout)
        self.log_action = QAction("显示运行日志", self)
        self.log_action.setCheckable(True)
        self.log_action.setShortcut("Ctrl+L")
        self.log_action.triggered.connect(self._toggle_log_drawer)
        self.check_updates_action = QAction("检查更新", self)
        self.check_updates_action.setToolTip("立即检查 GitHub 正式发行版本")
        self.check_updates_action.setEnabled(self._update_service is not None)
        self.check_updates_action.triggered.connect(
            lambda: self.check_for_updates(manual=True)
        )

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        self.main_toolbar = toolbar
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        brand = QWidget()
        self.brand_widget = brand
        brand.setObjectName("brandWidget")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 10, 0)
        brand_layout.setSpacing(8)
        brand_mark = QLabel("M")
        brand_mark.setObjectName("brandMark")
        brand_mark.setFixedSize(32, 32)
        brand_copy = QWidget()
        self.brand_copy = brand_copy
        brand_copy.setObjectName("brandCopy")
        brand_copy_layout = QVBoxLayout(brand_copy)
        brand_copy_layout.setContentsMargins(0, 0, 0, 0)
        brand_copy_layout.setSpacing(0)
        brand_title = QLabel("MailDesk")
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel("多邮箱工作台")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_copy_layout.addWidget(brand_title)
        brand_copy_layout.addWidget(brand_subtitle)
        brand_layout.addWidget(brand_mark)
        brand_layout.addWidget(brand_copy)
        toolbar.addWidget(brand)
        toolbar.addSeparator()

        toolbar.addAction(self.add_account_action)
        add_account_button = toolbar.widgetForAction(self.add_account_action)
        if add_account_button is not None:
            add_account_button.setObjectName("addAccountToolButton")
        self.add_account_tool_button = add_account_button

        self.import_menu_button = QToolButton()
        self.import_menu_button.setObjectName("importMenuButton")
        self.import_menu_button.setText("批量导入")
        self.import_menu_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.import_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        import_menu = QMenu(self.import_menu_button)
        import_menu.addAction(self.import_action)
        import_menu.addAction(self.paste_import_action)
        self.import_menu_button.setMenu(import_menu)
        self.import_toolbar_action = toolbar.addWidget(self.import_menu_button)
        toolbar.addAction(self.export_action)
        self.export_tool_button = toolbar.widgetForAction(self.export_action)
        toolbar.addAction(self.compose_action)
        self.compose_tool_button = toolbar.widgetForAction(self.compose_action)
        self.fetch_separator_action = toolbar.addSeparator()
        toolbar.addAction(self.start_action)
        primary_button = toolbar.widgetForAction(self.start_action)
        if primary_button is not None:
            primary_button.setObjectName("primaryToolButton")
            self.start_tool_button = primary_button
        toolbar.addAction(self.stop_action)
        stop_button = toolbar.widgetForAction(self.stop_action)
        if stop_button is not None:
            stop_button.setObjectName("dangerToolButton")
            self.stop_tool_button = stop_button

        self.toolbar_more_button = QToolButton()
        self.toolbar_more_button.setObjectName("toolbarMoreButton")
        self.toolbar_more_button.setText("更多")
        self.toolbar_more_button.setAccessibleName("更多邮箱操作")
        self.toolbar_more_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toolbar_more_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        more_menu = QMenu(self.toolbar_more_button)
        more_menu.addAction(self.add_account_action)
        more_menu.addSeparator()
        more_menu.addAction(self.import_action)
        more_menu.addAction(self.paste_import_action)
        more_menu.addAction(self.export_action)
        more_menu.addSeparator()
        more_menu.addAction(self.compose_action)
        self.toolbar_more_button.setMenu(more_menu)
        self.toolbar_more_action = toolbar.addWidget(self.toolbar_more_button)
        self.toolbar_more_action.setVisible(False)

        spacer = QWidget()
        spacer.setObjectName("toolbarSpacer")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self.update_tool_button = QToolButton()
        self.update_tool_button.setObjectName("updateToolButton")
        self.update_tool_button.setText("更新")
        self.update_tool_button.setAccessibleName("查看可用更新")
        self.update_tool_button.setToolTip("有新的 MailDesk 正式版本可用")
        self.update_tool_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.update_tool_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_tool_button.clicked.connect(self._on_update_button_clicked)
        self.update_toolbar_action = toolbar.addWidget(self.update_tool_button)
        self.update_toolbar_action.setVisible(False)
        self.update_tool_button.hide()

        self.concurrency_box = QWidget()
        self.concurrency_box.setObjectName("concurrencyBox")
        concurrency_layout = QHBoxLayout(self.concurrency_box)
        concurrency_layout.setContentsMargins(0, 0, 4, 0)
        concurrency_layout.setSpacing(6)
        concurrency_label = QLabel("并发任务")
        self.concurrency_label = concurrency_label
        concurrency_label.setObjectName("mutedLabel")
        concurrency_layout.addWidget(concurrency_label)
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setObjectName("concurrencySpin")
        self.concurrency_spin.setAccessibleName("并发任务数量")
        self.concurrency_spin.setRange(1, 50)
        self.concurrency_spin.setValue(5)
        self.concurrency_spin.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.concurrency_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.concurrency_spin.setAccelerated(True)
        self.concurrency_spin.setFixedWidth(42)
        stepper = QWidget()
        stepper.setObjectName("concurrencyStepper")
        stepper_layout = QHBoxLayout(stepper)
        stepper_layout.setContentsMargins(1, 1, 1, 1)
        stepper_layout.setSpacing(0)
        decrease_button = QPushButton("−")
        decrease_button.setObjectName("spinStepButton")
        decrease_button.setAccessibleName("减少并发任务")
        decrease_button.setFixedSize(27, 32)
        decrease_button.clicked.connect(self.concurrency_spin.stepDown)
        increase_button = QPushButton("+")
        increase_button.setObjectName("spinStepButton")
        increase_button.setAccessibleName("增加并发任务")
        increase_button.setFixedSize(27, 32)
        increase_button.clicked.connect(self.concurrency_spin.stepUp)
        stepper_layout.addWidget(decrease_button)
        stepper_layout.addWidget(self.concurrency_spin)
        stepper_layout.addWidget(increase_button)
        concurrency_layout.addWidget(stepper)
        toolbar.addWidget(self.concurrency_box)
        toolbar.addSeparator()

        self.tools_menu_button = QToolButton()
        self.tools_menu_button.setObjectName("toolsMenuButton")
        self.tools_menu_button.setText("工具")
        self.tools_menu_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.tools_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        tools_menu = QMenu(self.tools_menu_button)
        tools_menu.addAction(self.log_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.check_updates_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.reset_layout_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.audit_action)
        self.tools_menu_button.setMenu(tools_menu)
        toolbar.addWidget(self.tools_menu_button)
        toolbar.addAction(self.theme_action)
        theme_button = toolbar.widgetForAction(self.theme_action)
        self.theme_tool_button = theme_button
        if isinstance(theme_button, QToolButton):
            theme_button.setObjectName("themeToolButton")
            theme_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            theme_button.setAccessibleName("切换深色或浅色主题")
        toolbar.addAction(self.settings_action)
        self.settings_tool_button = toolbar.widgetForAction(self.settings_action)
        if isinstance(self.settings_tool_button, QToolButton):
            self.settings_tool_button.setObjectName("settingsToolButton")
        self._set_toolbar_icons()
        self.addToolBar(toolbar)

    def _set_toolbar_icons(self) -> None:
        neutral = "#94a3b8" if self._dark else "#526176"
        self.add_account_action.setIcon(line_icon("mail-plus", "#2563eb"))
        self.import_action.setIcon(line_icon("import", neutral))
        self.paste_import_action.setIcon(line_icon("paste", neutral))
        self.export_action.setIcon(line_icon("export", neutral))
        self.compose_action.setIcon(line_icon("mail", neutral))
        self.start_action.setIcon(line_icon("play", "#ffffff"))
        self.stop_action.setIcon(line_icon("stop", "#ef4444"))
        self.theme_action.setIcon(line_icon("sun" if self._dark else "moon", neutral))
        self.settings_action.setIcon(line_icon("settings", neutral))
        self.audit_action.setIcon(line_icon("audit", neutral))
        self.check_updates_action.setIcon(line_icon("refresh", neutral))
        self.import_menu_button.setIcon(line_icon("import", neutral))
        self.tools_menu_button.setIcon(line_icon("tools", neutral))
        self.update_tool_button.setIcon(line_icon("sparkles", "#ffffff"))

    def _set_fetch_ui_state(self, state: str) -> None:
        if state == "running":
            self.start_action.setText("取件进行中")
            self.start_action.setEnabled(False)
            self.stop_action.setText("停止取件")
            self.stop_action.setToolTip("安全停止当前取件任务")
            self.stop_action.setEnabled(True)
            if hasattr(self, "quick_fetch_button"):
                self.quick_fetch_button.setEnabled(False)
            status_text, status_state = "● 正在收取邮件", "running"
        elif state == "stopping":
            self.start_action.setText("取件进行中")
            self.start_action.setEnabled(False)
            self.stop_action.setText("正在停止…")
            self.stop_action.setToolTip("正在等待当前网络请求安全结束")
            self.stop_action.setEnabled(False)
            if hasattr(self, "quick_fetch_button"):
                self.quick_fetch_button.setEnabled(False)
            status_text, status_state = "● 正在安全停止", "warning"
        else:
            self.start_action.setText("开始并发取件")
            self.start_action.setEnabled(True)
            self.stop_action.setText("停止取件")
            self.stop_action.setToolTip("当前没有正在运行的取件任务")
            self.stop_action.setEnabled(False)
            if hasattr(self, "quick_fetch_button"):
                self.quick_fetch_button.setEnabled(self._active_account_id is not None)
            status_text, status_state = "● 本地凭据已加密", "secure"
        if hasattr(self, "concurrency_box"):
            self.concurrency_box.setEnabled(state == "idle")
        if hasattr(self, "dashboard"):
            self.dashboard.set_fetch_state(state)
        if hasattr(self, "security_status"):
            self.security_status.setText(status_text)
            self.security_status.setProperty("state", status_state)
            self.security_status.setToolTip(
                {
                    "running": "取件任务正在运行",
                    "warning": "已请求停止，正在等待网络请求安全结束",
                    "secure": "敏感字段由系统安全存储与 Fernet 加密保护",
                }[status_state]
            )
            self.security_status.style().unpolish(self.security_status)
            self.security_status.style().polish(self.security_status)

    def _create_content(self) -> None:
        outer = self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.setObjectName("workspaceSplitter")
        outer.setHandleWidth(7)
        outer.setChildrenCollapsible(False)
        outer.setOpaqueResize(True)

        sidebar = QWidget()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 16, 12, 14)
        sidebar_layout.setSpacing(10)
        sidebar_title_row = QHBoxLayout()
        sidebar_title = QLabel("账号分组")
        sidebar_title.setObjectName("sectionTitle")
        sidebar_title_row.addWidget(sidebar_title)
        sidebar_title_row.addStretch(1)
        sidebar_layout.addLayout(sidebar_title_row)
        sidebar_caption = QLabel("按项目组织邮箱，右键管理分组")
        self.sidebar_caption = sidebar_caption
        sidebar_caption.setObjectName("sectionCaption")
        sidebar_caption.setWordWrap(True)
        sidebar_layout.addWidget(sidebar_caption)

        self.group_tree = QTreeWidget()
        self.group_tree.setObjectName("groupTree")
        self.group_tree.setHeaderHidden(True)
        self.group_tree.setIndentation(14)
        self.group_tree.setUniformRowHeights(True)
        self.group_tree.setAnimated(True)
        self.group_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.group_tree.customContextMenuRequested.connect(self._show_group_context_menu)
        self.group_tree.itemSelectionChanged.connect(self.refresh_accounts)
        self._populate_groups()
        sidebar_layout.addWidget(self.group_tree, 1)
        self.sidebar_count = QLabel()
        self.sidebar_count.setObjectName("mutedLabel")
        sidebar_layout.addWidget(self.sidebar_count)
        sidebar.setMinimumWidth(150)
        outer.addWidget(sidebar)

        vertical = self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        vertical.setObjectName("contentSplitter")
        vertical.setHandleWidth(7)
        vertical.setChildrenCollapsible(False)
        vertical.setOpaqueResize(True)
        self.account_table = AccountTableView()
        self.account_table.setObjectName("accountTable")
        self.account_table.setModel(self.account_model)
        self.account_table.setSelectionMode(QTableView.SelectionMode.NoSelection)
        self.account_table.setSortingEnabled(False)
        self.account_table.setAlternatingRowColors(True)
        self.account_table.setShowGrid(False)
        self.account_table.verticalHeader().setVisible(False)
        self.account_table.verticalHeader().setDefaultSectionSize(42)
        self.account_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.account_table.customContextMenuRequested.connect(self._show_account_context_menu)
        account_header = AccountCheckHeader(self.account_model, self.account_table)
        self.account_header = account_header
        self.account_table.setHorizontalHeader(account_header)
        account_header.setHighlightSections(False)
        account_header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        account_header.setMinimumSectionSize(36)
        account_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        account_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        account_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for section, width in enumerate(self._wide_account_column_widths):
            account_header.resizeSection(section, width)
        self.column_menu = QMenu(self)
        self._column_actions: dict[int, QAction] = {}
        column_preferences = (
            self._settings.get("account_columns", {})
            if self._settings is not None
            else {}
        )
        hidden_columns = set(
            column_preferences.get("hidden", [])
            if isinstance(column_preferences, dict)
            else []
        )
        for column in range(1, self.account_model.columnCount()):
            action = self.column_menu.addAction(self.account_model.HEADERS[column])
            action.setCheckable(True)
            action.setChecked(column not in hidden_columns)
            action.toggled.connect(
                lambda visible, selected_column=column: self._set_account_column_visible(
                    selected_column, visible
                )
            )
            self._column_actions[column] = action
            self.account_table.setColumnHidden(column, column in hidden_columns)
        account_header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        account_header.customContextMenuRequested.connect(
            lambda position: self.column_menu.exec(account_header.mapToGlobal(position))
        )
        self.account_table.accountActivated.connect(self._account_row_clicked)
        self.account_table.emailCopyRequested.connect(self._copy_account_email)
        self.account_model.checkedChanged.connect(self._checked_accounts_changed)
        self.account_stack = QStackedWidget()
        self.account_stack.setObjectName("accountStack")
        self.account_stack.addWidget(self.account_table)
        empty_state = QWidget()
        empty_state.setObjectName("emptyAccountState")
        empty_layout = QVBoxLayout(empty_state)
        empty_layout.setSpacing(9)
        empty_layout.addStretch(1)
        empty_icon = QLabel()
        empty_icon.setObjectName("emptyStateIcon")
        empty_icon.setFixedSize(50, 50)
        empty_icon.setPixmap(line_icon("mail", "#2563eb", 24).pixmap(24, 24))
        empty_layout.addWidget(empty_icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_title = QLabel("集中管理你的第一个邮箱")
        empty_title.setObjectName("emptyStateTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        self.empty_account_label = QLabel(
            "还没有邮箱账号。点击“添加邮箱”选择服务商逐个添加，\n"
            "也可以导入 TXT、CSV 或 JSON 批量创建账号。"
        )
        self.empty_account_label.setObjectName("emptyStateText")
        self.empty_account_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_account_label.setAccessibleName("账号列表为空")
        empty_layout.addWidget(self.empty_account_label)
        empty_actions = QHBoxLayout()
        empty_actions.addStretch(1)
        add_button = QPushButton("添加邮箱")
        add_button.setObjectName("primaryButton")
        add_button.setAccessibleName("选择邮箱服务商并添加账号")
        add_button.clicked.connect(self.show_add_account)
        empty_actions.addWidget(add_button)
        import_button = QPushButton("批量导入")
        import_button.setAccessibleName("从文件批量导入邮箱账号")
        import_button.clicked.connect(self.choose_import)
        empty_actions.addWidget(import_button)
        paste_button = QPushButton("粘贴导入")
        paste_button.clicked.connect(self.choose_paste_import)
        empty_actions.addWidget(paste_button)
        empty_actions.addStretch(1)
        empty_layout.addLayout(empty_actions)
        empty_layout.addStretch(1)
        self.account_stack.addWidget(empty_state)
        account_panel = QWidget()
        account_panel.setObjectName("accountPanel")
        account_layout = QVBoxLayout(account_panel)
        self.account_layout = account_layout
        account_layout.setContentsMargins(16, 14, 16, 8)
        account_layout.setSpacing(10)
        account_title_row = QHBoxLayout()
        account_title = QLabel("邮箱账号")
        account_title.setObjectName("sectionTitle")
        account_title_row.addWidget(account_title)
        self.account_count_label = QLabel()
        self.account_count_label.setObjectName("countBadge")
        account_title_row.addWidget(self.account_count_label)
        account_title_row.addStretch(1)
        self.quick_fetch_button = QPushButton("立即取件")
        self.quick_fetch_button.setObjectName("primaryButton")
        self.quick_fetch_button.setToolTip("仅收取当前单击查看的邮箱账号")
        self.quick_fetch_button.setEnabled(False)
        self.quick_fetch_button.clicked.connect(self.fetch_active_account)
        account_title_row.addWidget(self.quick_fetch_button)
        self.column_menu_button = QToolButton()
        self.column_menu_button.setObjectName("columnMenuButton")
        self.column_menu_button.setText("显示列")
        self.column_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.column_menu_button.setMenu(self.column_menu)
        account_title_row.addWidget(self.column_menu_button)
        self.selection_count_label = QLabel("未选择账号")
        self.selection_count_label.setObjectName("selectionBadge")
        account_title_row.addWidget(self.selection_count_label)
        self.send_accounts_button = QPushButton("批量发件")
        self.send_accounts_button.setObjectName("secondaryButton")
        self.send_accounts_button.setEnabled(False)
        self.send_accounts_button.clicked.connect(lambda: self.show_compose_dialog())
        account_title_row.addWidget(self.send_accounts_button)
        self.delete_accounts_button = QPushButton("删除所选")
        self.delete_accounts_button.setObjectName("dangerButton")
        self.delete_accounts_button.setEnabled(False)
        self.delete_accounts_button.clicked.connect(self.delete_selected_accounts)
        account_title_row.addWidget(self.delete_accounts_button)
        account_layout.addLayout(account_title_row)
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)
        self.account_search = QLineEdit()
        self.account_search.setObjectName("accountSearch")
        self.account_search.setPlaceholderText("搜索账号、邮箱类型或状态…")
        self.account_search.setClearButtonEnabled(True)
        self.account_search.setMinimumHeight(36)
        self.account_search.setMinimumWidth(150)
        self.account_search.textChanged.connect(self.refresh_accounts)
        filter_layout.addWidget(self.account_search, 1)
        self.tag_filter = QComboBox()
        self.tag_filter.setMinimumHeight(36)
        self.tag_filter.setMinimumWidth(140)
        self.tag_filter.setAccessibleName("按标签筛选账号")
        self._populate_tag_filter()
        self.tag_filter.currentIndexChanged.connect(self.refresh_accounts)
        filter_layout.addWidget(self.tag_filter)
        self.status_filter = QComboBox()
        self.status_filter.setMinimumHeight(36)
        self.status_filter.setMinimumWidth(132)
        self.status_filter.setAccessibleName("按连接状态筛选账号")
        self.status_filter.addItem("全部状态", None)
        self.status_filter.addItem("异常账号", "abnormal")
        self.status_filter.addItem("正常可用", AccountStatus.SUCCESS.value)
        self.status_filter.addItem("未连接", AccountStatus.DISCONNECTED.value)
        self.status_filter.addItem("连接中", AccountStatus.CONNECTING.value)
        self.status_filter.currentIndexChanged.connect(self.refresh_accounts)
        filter_layout.addWidget(self.status_filter)
        self.group_move_combo = QComboBox()
        self.group_move_combo.setMinimumHeight(36)
        self.group_move_combo.setMinimumWidth(160)
        self.group_move_combo.setAccessibleName("选择账号目标分组")
        self._populate_group_move_combo()
        filter_layout.addWidget(self.group_move_combo)
        self.move_group_button = QPushButton("移动")
        self.move_group_button.setMinimumHeight(36)
        self.move_group_button.setEnabled(False)
        self.move_group_button.clicked.connect(self._move_selected_to_group)
        filter_layout.addWidget(self.move_group_button)
        account_layout.addLayout(filter_layout)
        account_layout.addWidget(self.account_stack)
        vertical.addWidget(account_panel)
        self._update_account_empty_state()
        details_panel, log_panel = self._create_details()
        vertical.addWidget(details_panel)
        vertical.setStretchFactor(0, 3)
        vertical.setStretchFactor(1, 2)
        vertical.setSizes([520, 360])
        outer.addWidget(vertical)
        outer.setStretchFactor(0, 0)
        outer.setStretchFactor(1, 1)
        outer.setSizes([230, 1210])
        self.account_workspace = outer
        if self._statistics is not None:
            self.main_tabs = QTabWidget()
            self.main_tabs.setObjectName("mainTabs")
            self.main_tabs.setDocumentMode(True)
            self.main_tabs.tabBar().setExpanding(False)
            self.main_tabs.tabBar().setDrawBase(False)
            self.main_tabs.tabBar().setUsesScrollButtons(False)
            self.dashboard = DashboardWidget(
                self._statistics,
                self._messages,
                quick_action_ids=self._dashboard_quick_actions,
                proxy_enabled=self._proxy_fetch_enabled,
            )
            self.main_tabs.addTab(self.dashboard, "工作台概览")
            self.main_tabs.addTab(outer, "账号与邮件")
            self.dashboard.navigateAccountsRequested.connect(self._show_all_accounts)
            self.dashboard.startFetchRequested.connect(self.start_fetch)
            self.dashboard.importRequested.connect(self.show_add_account)
            self.dashboard.contentFilterRequested.connect(self.show_content_filter)
            self.dashboard.abnormalAccountsRequested.connect(
                self._show_abnormal_accounts
            )
            self.dashboard.proxyToggleRequested.connect(
                self._set_proxy_fetch_enabled
            )
            self.dashboard.recentMessageRequested.connect(self._open_recent_message)
            self.main_tabs.currentChanged.connect(self._main_tab_changed)
            self.setCentralWidget(self.main_tabs)
        else:
            self.setCentralWidget(outer)
        self._create_log_dock(log_panel)
        self._restore_splitter_sizes()
        for splitter in (
            self.workspace_splitter,
            self.content_splitter,
            self.message_splitter,
        ):
            splitter.splitterMoved.connect(self._schedule_layout_save)

    def _create_details(self) -> tuple[QWidget, QWidget]:
        panel = QWidget()
        panel.setObjectName("detailsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 7, 16, 14)
        layout.setSpacing(9)
        detail_title_row = QHBoxLayout()
        detail_title = QLabel("邮件详情")
        detail_title.setObjectName("sectionTitle")
        detail_title_row.addWidget(detail_title)
        self.selected_account_label = QLabel("选择一个账号查看最近邮件")
        self.selected_account_label.setObjectName("sectionCaption")
        detail_title_row.addWidget(self.selected_account_label)
        detail_title_row.addStretch(1)
        layout.addLayout(detail_title_row)

        details = self.message_splitter = QSplitter(Qt.Orientation.Horizontal)
        details.setObjectName("messageSplitter")
        details.setHandleWidth(7)
        details.setChildrenCollapsible(False)
        details.setOpaqueResize(True)
        message_panel = QFrame()
        message_panel.setObjectName("messagePanel")
        message_panel.setMinimumWidth(245)
        message_layout = QVBoxLayout(message_panel)
        message_layout.setContentsMargins(10, 9, 10, 8)
        message_layout.setSpacing(7)
        message_header = QHBoxLayout()
        message_title = QLabel("邮件列表")
        message_title.setObjectName("sectionTitle")
        message_header.addWidget(message_title)
        message_header.addStretch(1)
        self.open_reader_button = QPushButton("阅读器")
        self.open_reader_button.setObjectName("ghostButton")
        self.open_reader_button.setToolTip("在独立窗口中沉浸查看当前邮箱邮件")
        self.open_reader_button.clicked.connect(lambda: self.open_mail_viewer())
        message_header.addWidget(self.open_reader_button)
        self.content_filter_button = QPushButton("筛选导出")
        self.content_filter_button.setObjectName("ghostButton")
        self.content_filter_button.setToolTip("只提取匹配文字或链接，不导出完整正文")
        self.content_filter_button.clicked.connect(self.show_content_filter)
        message_header.addWidget(self.content_filter_button)
        self.message_count_label = QLabel("0 封")
        self.message_count_label.setObjectName("countBadge")
        message_header.addWidget(self.message_count_label)
        message_layout.addLayout(message_header)
        message_search_layout = QHBoxLayout()
        message_search_layout.setSpacing(6)
        self.message_search_input = QLineEdit()
        self.message_search_input.setObjectName("messageSearchInput")
        self.message_search_input.setPlaceholderText("搜索本地邮件…")
        self.message_search_input.setClearButtonEnabled(True)
        self.message_search_input.returnPressed.connect(self.search_messages)
        self.message_search_input.textChanged.connect(self._message_search_text_changed)
        message_search_layout.addWidget(self.message_search_input, 1)
        self.message_search_scope = QComboBox()
        self.message_search_scope.setObjectName("messageSearchScope")
        self.message_search_scope.addItem("当前邮箱", "current")
        self.message_search_scope.addItem("全部邮箱", "all")
        self.message_search_scope.setMaximumWidth(110)
        self.message_search_scope.currentIndexChanged.connect(
            self._message_search_scope_changed
        )
        message_search_layout.addWidget(self.message_search_scope)
        message_search_button = QPushButton("搜索")
        message_search_button.clicked.connect(self.search_messages)
        message_search_layout.addWidget(message_search_button)
        message_layout.addLayout(message_search_layout)
        self.message_list = QListWidget()
        self.message_list.setObjectName("messageList")
        self.message_list.setSpacing(1)
        self.message_list.setWordWrap(True)
        self.message_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.message_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.message_list.setAccessibleName("邮件列表")
        self.message_list.currentRowChanged.connect(self._message_selected)
        self.message_list.itemDoubleClicked.connect(
            lambda _item: self._open_reader_for_message_row(self.message_list.currentRow())
        )
        self.message_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.message_list.customContextMenuRequested.connect(self._show_message_context_menu)
        message_layout.addWidget(self.message_list)
        details.addWidget(message_panel)

        content_panel = QFrame()
        content_panel.setObjectName("contentPanel")
        content_panel.setMinimumWidth(320)
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(10, 9, 10, 8)
        content_layout.setSpacing(7)
        self.message_context_label = QLabel("选择一封邮件查看正文与提取结果")
        self.message_context_label.setObjectName("sectionCaption")
        self.message_context_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        content_layout.addWidget(self.message_context_label)
        tabs = QTabWidget()
        tabs.setObjectName("messageTabs")
        tabs.setDocumentMode(True)
        body_tab = QWidget()
        body_tab.setObjectName("messageBodyTab")
        # QWebEngineView needs a native host.  Creating that host only when this
        # hidden tab is first shown makes Qt rebuild the top-level Windows HWND,
        # which looks like the application closed and reopened.  Realize the
        # stable host with the rest of the main-window hierarchy instead.
        body_tab.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        body_layout = QVBoxLayout(body_tab)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self.message_tools_bar = QFrame()
        self.message_tools_bar.setObjectName("mailTranslationBar")
        message_tools_layout = QHBoxLayout(self.message_tools_bar)
        message_tools_layout.setContentsMargins(10, 6, 8, 6)
        message_tools_layout.setSpacing(8)
        message_tools_layout.addStretch(1)
        translation_confirmation = " · 翻译前确认" if self._translation_confirm else ""
        self.translation_language_label = QLabel(
            f"目标语言：{translation_language_label(self._translation_language)}"
            f"{translation_confirmation}"
        )
        self.translation_language_label.setObjectName("mailTranslationLanguage")
        message_tools_layout.addWidget(self.translation_language_label)
        self.translation_toggle_button = QPushButton("查看译文")
        self.translation_toggle_button.setObjectName("translationToggleButton")
        self.translation_toggle_button.setEnabled(False)
        self.translation_toggle_button.clicked.connect(self._toggle_translation_view)
        message_tools_layout.addWidget(self.translation_toggle_button)
        self.translate_button = QPushButton("翻译邮件")
        self.translate_button.setObjectName("translationButton")
        self.translate_button.setToolTip(
            "仅发送当前邮件正文，不发送附件、账号密码或 Token"
        )
        self.translate_button.setEnabled(False)
        self.translate_button.clicked.connect(self._translate_current_message)
        message_tools_layout.addWidget(self.translate_button)
        self.message_tools_bar.hide()
        body_layout.addWidget(self.message_tools_bar)
        self.message_attachment_panel = QFrame()
        self.message_attachment_panel.setObjectName("mailAttachmentPanel")
        attachment_layout = QVBoxLayout(self.message_attachment_panel)
        attachment_layout.setContentsMargins(10, 7, 10, 8)
        attachment_layout.setSpacing(5)
        attachment_header = QHBoxLayout()
        self.message_attachment_title = QLabel("附件")
        self.message_attachment_title.setObjectName("mailAttachmentTitle")
        attachment_header.addWidget(self.message_attachment_title)
        attachment_header.addStretch(1)
        save_attachment = QPushButton("保存选中")
        save_attachment.setObjectName("attachmentActionButton")
        save_attachment.clicked.connect(self._save_selected_message_attachment)
        attachment_header.addWidget(save_attachment)
        save_all_attachments = QPushButton("全部保存")
        save_all_attachments.setObjectName("attachmentActionButton")
        save_all_attachments.clicked.connect(self._save_all_message_attachments)
        attachment_header.addWidget(save_all_attachments)
        attachment_layout.addLayout(attachment_header)
        self.message_attachment_list = QListWidget()
        self.message_attachment_list.setObjectName("mailAttachmentList")
        self.message_attachment_list.setMaximumHeight(90)
        self.message_attachment_list.itemDoubleClicked.connect(
            lambda _item: self._save_selected_message_attachment()
        )
        attachment_layout.addWidget(self.message_attachment_list)
        self.message_attachment_panel.hide()
        body_layout.addWidget(self.message_attachment_panel)
        self.message_body = LazyEmailBodyView()
        self.message_body.setObjectName("messageBody")
        self.message_body.setAccessibleName("邮件正文")
        self.message_body.setPlaceholderText("选择一封邮件后在此查看正文")
        self.message_body.anchorClicked.connect(self._open_message_link)
        self.message_body.feedbackRequested.connect(
            lambda text: self.page_toast.show_message(text)
        )
        body_layout.addWidget(self.message_body, 1)
        self.match_view = QPlainTextEdit()
        self.match_view.setObjectName("matchView")
        self.match_view.setReadOnly(True)
        self.match_view.setAccessibleName("验证码与关键词")
        self.match_view.setPlaceholderText("验证码、关键词和自定义规则结果将在此显示")
        tabs.addTab(body_tab, "邮件正文")
        tabs.addTab(self.match_view, "提取结果")
        content_layout.addWidget(tabs)
        details.addWidget(content_panel)
        details.setSizes([360, 780])
        layout.addWidget(details, 3)

        log_section = QWidget()
        log_section.setObjectName("logDrawerContent")
        log_layout = QVBoxLayout(log_section)
        log_layout.setContentsMargins(10, 8, 10, 8)
        log_layout.setSpacing(0)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setPlaceholderText("取件日志将在这里显示（凭据会被脱敏）")
        log_layout.addWidget(self.log_view)
        self._displayed_messages: list[MailMessage] = []
        self._displayed_message_accounts: list[str] = []
        return panel, log_section

    def _create_log_dock(self, content: QWidget) -> None:
        # QMainWindow's geometry animation repeatedly resizes the native
        # QtWebEngine surface and can expose black backing-store frames.
        self.setDockOptions(
            self.dockOptions() & ~QMainWindow.DockOption.AnimatedDocks
        )
        self.log_dock = QDockWidget("运行日志", self)
        self.log_dock.setObjectName("logDock")
        self.log_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.log_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.log_dock.setMinimumHeight(140)
        self.log_dock.setWidget(content)

        title_bar = QWidget()
        title_bar.setObjectName("logDrawerTitle")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 7, 8, 7)
        title_layout.setSpacing(7)
        title = QLabel("运行日志")
        title.setObjectName("sectionTitle")
        title_layout.addWidget(title)
        privacy = QLabel("凭据已脱敏")
        privacy.setObjectName("privacyBadge")
        title_layout.addWidget(privacy)
        title_layout.addStretch(1)
        clear_button = QPushButton("清空")
        clear_button.setObjectName("ghostButton")
        clear_button.clicked.connect(self.log_view.clear)
        title_layout.addWidget(clear_button)
        close_button = QPushButton("收起")
        close_button.setObjectName("ghostButton")
        close_button.clicked.connect(
            lambda _checked=False: self._set_log_drawer_visible(False)
        )
        title_layout.addWidget(close_button)
        self.log_dock.setTitleBarWidget(title_bar)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self._log_drawer_target_visible = False
        self._log_drawer_transition_active = False
        # Fade only the log content.  The drawer surface and title stay painted,
        # so there is never an empty/black frame while the central layout settles.
        self._log_opacity_effect = QGraphicsOpacityEffect(content)
        self._log_opacity_effect.setOpacity(1.0)
        content.setGraphicsEffect(self._log_opacity_effect)
        self._log_opacity_animation = QPropertyAnimation(
            self._log_opacity_effect, b"opacity", self
        )
        self._log_opacity_animation.finished.connect(
            self._log_drawer_animation_finished
        )
        self.log_dock.visibilityChanged.connect(self._log_visibility_changed)
        self.log_dock.hide()

    def _toggle_log_drawer(self, visible: bool) -> None:
        self._set_log_drawer_visible(visible)

    def _set_log_drawer_visible(self, visible: bool) -> None:
        visible = bool(visible)
        self._log_drawer_target_visible = visible
        self._sync_log_action(visible)
        self._log_opacity_animation.stop()
        self._log_drawer_transition_active = True
        if visible and not self.log_dock.isVisible():
            self._log_opacity_effect.setOpacity(0.0)
            self.log_dock.show()
        elif not visible and not self.log_dock.isVisible():
            self._log_opacity_effect.setOpacity(1.0)
            self._log_drawer_transition_active = False
            return

        start = self._log_opacity_effect.opacity()
        end = 1.0 if visible else 0.0
        if abs(start - end) < 0.01:
            self._log_drawer_animation_finished()
            return
        self._log_opacity_animation.setStartValue(start)
        self._log_opacity_animation.setEndValue(end)
        self._log_opacity_animation.setDuration(
            max(70, round(130 * abs(end - start)))
        )
        self._log_opacity_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic if visible else QEasingCurve.Type.InCubic
        )
        self._log_opacity_animation.start()

    def _log_drawer_animation_finished(self) -> None:
        if not self._log_drawer_target_visible:
            self.log_dock.hide()
        self._log_opacity_effect.setOpacity(1.0)
        self._log_drawer_transition_active = False
        self._sync_log_action(self._log_drawer_target_visible)

    def _log_visibility_changed(self, visible: bool) -> None:
        if self._log_drawer_transition_active:
            return
        self._log_drawer_target_visible = visible
        self._sync_log_action(visible)

    def _sync_log_action(self, visible: bool) -> None:
        self.log_action.blockSignals(True)
        self.log_action.setChecked(visible)
        self.log_action.setText("收起运行日志" if visible else "显示运行日志")
        self.log_action.blockSignals(False)

    def _schedule_layout_save(self, *_args) -> None:
        if self._settings is not None:
            self._layout_save_timer.start()

    def _restore_splitter_sizes(self) -> None:
        if self._settings is None:
            return
        saved = self._settings.get("ui_splitters", {})
        if not isinstance(saved, dict):
            return
        splitters = {
            "workspace": self.workspace_splitter,
            "content": self.content_splitter,
            "messages": self.message_splitter,
        }
        for key, splitter in splitters.items():
            sizes = saved.get(key)
            if (
                isinstance(sizes, list)
                and len(sizes) == splitter.count()
                and all(isinstance(size, int) and size > 0 for size in sizes)
            ):
                splitter.setSizes(sizes)

    def _save_splitter_sizes(self) -> None:
        if self._settings is None:
            return
        self._settings.set(
            "ui_splitters",
            {
                "workspace": self.workspace_splitter.sizes(),
                "content": self.content_splitter.sizes(),
                "messages": self.message_splitter.sizes(),
            },
        )

    def reset_layout(self) -> None:
        self.workspace_splitter.setSizes([230, 1210])
        self.content_splitter.setSizes([520, 360])
        self.message_splitter.setSizes([360, 780])
        self._save_splitter_sizes()
        self.statusBar().showMessage("界面分区已恢复默认大小", 5000)

    def _set_account_column_visible(self, column: int, visible: bool) -> None:
        self.account_table.setColumnHidden(column, not visible)
        if self._settings is not None:
            hidden = [
                index
                for index in range(1, self.account_model.columnCount())
                if self.account_table.isColumnHidden(index)
            ]
            self._settings.set("account_columns", {"hidden": hidden})

    def _populate_groups(self) -> None:
        selected_kind, selected_id = (
            self._selected_group_state()
            if self.group_tree.topLevelItemCount()
            else ("all", None)
        )
        expanded_ids: set[int] = set()
        if self.group_tree.topLevelItemCount():
            pending = [self.group_tree.topLevelItem(0)]
            while pending:
                item = pending.pop(0)
                group_id = item.data(0, Qt.ItemDataRole.UserRole)
                if item.isExpanded() and isinstance(group_id, int):
                    expanded_ids.add(group_id)
                pending.extend(item.child(index) for index in range(item.childCount()))

        accounts = self._accounts.list_all()
        direct_counts = Counter(account.group_id for account in accounts)
        self.group_tree.blockSignals(True)
        self.group_tree.clear()
        root = QTreeWidgetItem([f"全部账号  {len(accounts)}"])
        root.setData(0, Qt.ItemDataRole.UserRole, None)
        root.setData(0, _GROUP_KIND_ROLE, "all")
        root.setData(0, _GROUP_NAME_ROLE, "全部账号")
        root.setIcon(0, line_icon("mail", "#3b82f6", 16))
        self.group_tree.addTopLevelItem(root)
        ungrouped = QTreeWidgetItem([f"未分组  {direct_counts.get(None, 0)}"])
        ungrouped.setData(0, Qt.ItemDataRole.UserRole, None)
        ungrouped.setData(0, _GROUP_KIND_ROLE, "ungrouped")
        ungrouped.setData(0, _GROUP_NAME_ROLE, "未分组")
        ungrouped.setIcon(0, line_icon("folder", "#94a3b8", 16))
        root.addChild(ungrouped)
        if self._groups is not None:
            groups = self._groups.list_all()
            children: dict[int | None, list[Group]] = {}
            for group in groups:
                children.setdefault(group.parent_id, []).append(group)

            count_cache: dict[int, int] = {}

            def group_count(group_id: int) -> int:
                if group_id not in count_cache:
                    count_cache[group_id] = direct_counts.get(group_id, 0) + sum(
                        group_count(child.group_id)
                        for child in children.get(group_id, [])
                        if child.group_id is not None
                    )
                return count_cache[group_id]

            def add_children(parent_item: QTreeWidgetItem, parent_id: int | None) -> None:
                for group in children.get(parent_id, []):
                    count = group_count(group.group_id) if group.group_id is not None else 0
                    item = QTreeWidgetItem([f"{group.name}  {count}"])
                    item.setData(0, Qt.ItemDataRole.UserRole, group.group_id)
                    item.setData(0, _GROUP_KIND_ROLE, "group")
                    item.setData(0, _GROUP_NAME_ROLE, group.name)
                    item.setIcon(0, line_icon("folder", "#64748b", 16))
                    parent_item.addChild(item)
                    add_children(item, group.group_id)
                    if group.group_id in expanded_ids:
                        item.setExpanded(True)

            add_children(root, None)
        root.setExpanded(True)
        selected = self._find_group_item(selected_kind, selected_id) or root
        selected.setSelected(True)
        self.group_tree.setCurrentItem(selected)
        self.group_tree.blockSignals(False)
        self._populate_group_move_combo()

    def _find_group_item(
        self, kind: str, group_id: int | None
    ) -> QTreeWidgetItem | None:
        iterator = [
            self.group_tree.topLevelItem(index)
            for index in range(self.group_tree.topLevelItemCount())
        ]
        while iterator:
            item = iterator.pop(0)
            if (
                item.data(0, _GROUP_KIND_ROLE) == kind
                and item.data(0, Qt.ItemDataRole.UserRole) == group_id
            ):
                return item
            iterator.extend(item.child(index) for index in range(item.childCount()))
        return None

    def _selected_group_state(self) -> tuple[str, int | None]:
        item = self.group_tree.currentItem() if hasattr(self, "group_tree") else None
        if item is None:
            return "all", None
        return (
            str(item.data(0, _GROUP_KIND_ROLE) or "all"),
            item.data(0, Qt.ItemDataRole.UserRole),
        )

    def _selected_group_id(self) -> int | None:
        kind, group_id = self._selected_group_state()
        return group_id if kind == "group" else None

    def _selected_group_accounts(self, *, query: str = "", tag_id: int | None = None):
        kind, group_id = self._selected_group_state()
        if kind == "ungrouped":
            return self._accounts.list_all(ungrouped=True, query=query, tag_id=tag_id)
        if kind == "group" and group_id is not None:
            group_ids = [group_id]
            if self._groups is not None:
                group_ids.extend(self._groups.descendant_ids(group_id))
            return self._accounts.list_all(group_ids=group_ids, query=query, tag_id=tag_id)
        return self._accounts.list_all(query=query, tag_id=tag_id)

    def refresh_accounts(self, *_args) -> None:
        query = self.account_search.text() if hasattr(self, "account_search") else ""
        tag_id = self.tag_filter.currentData() if hasattr(self, "tag_filter") else None
        accounts = self._selected_group_accounts(query=query, tag_id=tag_id)
        status_filter = (
            self.status_filter.currentData() if hasattr(self, "status_filter") else None
        )
        if status_filter == "abnormal":
            normal_states = {
                AccountStatus.SUCCESS,
                AccountStatus.DISCONNECTED,
                AccountStatus.CONNECTING,
            }
            accounts = [account for account in accounts if account.status not in normal_states]
        elif isinstance(status_filter, str) and status_filter:
            accounts = [
                account for account in accounts if account.status.value == status_filter
            ]
        self.account_model.set_accounts(accounts)
        self._update_account_empty_state()
        self._checked_accounts_changed()
        active = next(
            (
                account
                for account in self.account_model.accounts()
                if account.account_id == self._active_account_id
            ),
            None,
        )
        if active is not None:
            self._show_account_details(active)
        elif self._active_account_id is not None:
            self._active_account_id = None
            self._show_account_details(None)

    def _populate_tag_filter(self) -> None:
        current = self.tag_filter.currentData() if hasattr(self, "tag_filter") else None
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("全部标签", None)
        if self._tags is not None:
            for tag in self._tags.list_all():
                self.tag_filter.addItem(tag.name, tag.tag_id)
        index = self.tag_filter.findData(current)
        self.tag_filter.setCurrentIndex(max(0, index))
        self.tag_filter.blockSignals(False)

    def _populate_group_move_combo(self) -> None:
        if not hasattr(self, "group_move_combo"):
            return
        self.group_move_combo.blockSignals(True)
        self.group_move_combo.clear()
        self.group_move_combo.addItem("移动到分组…", "choose")
        self.group_move_combo.addItem("未分组", None)
        if self._groups is not None:
            groups = self._groups.list_all()
            by_id = {group.group_id: group for group in groups}

            def group_path(group: Group) -> str:
                names = [group.name]
                parent_id = group.parent_id
                visited: set[int] = set()
                while parent_id is not None and parent_id not in visited:
                    visited.add(parent_id)
                    parent = by_id.get(parent_id)
                    if parent is None:
                        break
                    names.append(parent.name)
                    parent_id = parent.parent_id
                return " / ".join(reversed(names))

            for group in groups:
                self.group_move_combo.addItem(group_path(group), group.group_id)
        self.group_move_combo.setCurrentIndex(0)
        self.group_move_combo.blockSignals(False)

    def _move_selected_to_group(self) -> None:
        selected_ids = [
            account.account_id
            for account in self._selected_accounts()
            if account.account_id is not None
        ]
        target = self.group_move_combo.currentData()
        if not selected_ids:
            self.statusBar().showMessage("请先选择需要移动的账号", 5000)
            return
        if target == "choose":
            self.statusBar().showMessage("请选择目标分组", 5000)
            return
        self._accounts.update_group(selected_ids, target)
        self._populate_groups()
        self.refresh_accounts()
        self.group_move_combo.setCurrentIndex(0)
        self.statusBar().showMessage(f"已移动 {len(selected_ids)} 个账号", 5000)

    def delete_selected_accounts(self) -> None:
        selected = self._selected_accounts()
        account_ids = [
            account.account_id for account in selected if account.account_id is not None
        ]
        if not account_ids:
            self.statusBar().showMessage("请先勾选需要删除的账号", 5000)
            return
        running = sorted(set(account_ids).intersection(self._workers))
        if running:
            QMessageBox.warning(
                self,
                "暂时不能删除",
                f"其中 {len(running)} 个账号正在取件，请先停止并等待任务结束。",
            )
            return
        preview = "\n".join(f"• {account.email}" for account in selected[:6])
        if len(selected) > 6:
            preview += f"\n• 以及另外 {len(selected) - 6} 个账号"
        answer = QMessageBox.warning(
            self,
            "确认批量删除账号",
            f"即将永久删除 {len(account_ids)} 个账号：\n\n{preview}\n\n"
            "对应的本地邮件记录、标签关联和已保存的 EML 原件也会一并删除。此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        deleted = self._accounts.delete_many(account_ids)
        if self._eml_store is not None:
            for account_id in account_ids:
                try:
                    self._eml_store.delete_account(account_id)
                except OSError:
                    self.log_view.appendPlainText(
                        f"账号 {account_id} 的部分 EML 原件未能删除，请稍后手动清理。"
                    )
        if self._active_account_id in account_ids:
            self._active_account_id = None
            self._show_account_details(None)
        self.account_model.set_all_checked(False)
        self._populate_groups()
        self.refresh_accounts()
        if hasattr(self, "dashboard"):
            self.dashboard.refresh()
        self.statusBar().showMessage(f"已删除 {deleted} 个账号及其本地邮件数据", 8000)

    def _update_account_empty_state(self) -> None:
        visible_count = self.account_model.rowCount()
        total_count = len(self._accounts.list_all())
        self.account_stack.setCurrentIndex(0 if visible_count else 1)
        if hasattr(self, "account_count_label"):
            count_text = (
                f"{visible_count} / {total_count} 个账号"
                if visible_count != total_count
                else f"{total_count} 个账号"
            )
            self.account_count_label.setText(count_text)
        if hasattr(self, "sidebar_count"):
            self.sidebar_count.setText(f"共 {total_count} 个邮箱账号")

    def _show_group_context_menu(self, position) -> None:
        if self._groups is None:
            return
        item = self.group_tree.itemAt(position)
        menu = QMenu(self)
        kind = str(item.data(0, _GROUP_KIND_ROLE) or "all") if item else "all"
        group_id = (
            item.data(0, Qt.ItemDataRole.UserRole) if item and kind == "group" else None
        )
        add_action = menu.addAction("新建子分组" if group_id is not None else "新建分组")
        rename_action = menu.addAction("重命名分组")
        delete_action = menu.addAction("删除分组")
        delete_action.setEnabled(group_id is not None)
        rename_action.setEnabled(group_id is not None)
        selected = menu.exec(self.group_tree.viewport().mapToGlobal(position))
        if selected is add_action:
            name, accepted = QInputDialog.getText(self, "新建分组", "分组名称：")
            if accepted and name.strip():
                try:
                    self._groups.create(Group(name=name, parent_id=group_id))
                    self._populate_groups()
                except Exception as exc:
                    QMessageBox.warning(self, "创建失败", str(exc))
        elif selected is rename_action and group_id is not None:
            name, accepted = QInputDialog.getText(
                self,
                "重命名分组",
                "新名称：",
                text=str(item.data(0, _GROUP_NAME_ROLE)),
            )
            if accepted and name.strip():
                self._groups.rename(group_id, name)
                self._populate_groups()
        elif selected is delete_action and group_id is not None:
            answer = QMessageBox.question(
                self,
                "确认删除",
                "删除分组会同时删除其子分组；账号本身会保留并移到未分组。是否继续？",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._groups.delete(group_id)
                self._populate_groups()
                self.refresh_accounts()

    def _main_tab_changed(self, index: int) -> None:
        if hasattr(self, "dashboard") and self.main_tabs.widget(index) is self.dashboard:
            self.dashboard.refresh()

    def _show_accounts_workspace(self) -> None:
        if hasattr(self, "main_tabs"):
            self.main_tabs.setCurrentWidget(self.account_workspace)

    def _show_all_accounts(self) -> None:
        self._show_accounts_workspace()
        root = self.group_tree.topLevelItem(0)
        if root is not None:
            self.group_tree.setCurrentItem(root)
        self.account_search.clear()
        self.tag_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)
        self.refresh_accounts()

    def _show_abnormal_accounts(self) -> None:
        self._show_accounts_workspace()
        root = self.group_tree.topLevelItem(0)
        if root is not None:
            self.group_tree.setCurrentItem(root)
        self.account_search.clear()
        self.tag_filter.setCurrentIndex(0)
        index = self.status_filter.findData("abnormal")
        self.status_filter.setCurrentIndex(max(0, index))
        self.refresh_accounts()
        count = self.account_model.rowCount()
        self.statusBar().showMessage(f"已筛选全部异常账号：{count} 个", 6000)
        self.page_toast.show_message(f"已显示 {count} 个异常账号")

    def _set_proxy_fetch_enabled(
        self,
        enabled: bool,
        *,
        persist: bool = True,
        notify: bool = True,
    ) -> bool:
        requested_state = bool(enabled)
        previous_state = self._proxy_fetch_enabled
        dashboard = getattr(self, "dashboard", None)
        if dashboard is not None:
            dashboard.set_proxy_toggle_enabled(False)
        try:
            if persist and self._settings is not None:
                values = self._settings.get("enterprise_ui", {})
                values = dict(values) if isinstance(values, dict) else {}
                values["proxy_fetch_enabled"] = requested_state
                self._settings.set("enterprise_ui", values)
        except Exception as exc:
            self._proxy_fetch_enabled = previous_state
            if dashboard is not None:
                dashboard.set_proxy_state(previous_state)
            message = f"代理开关保存失败，已保持原状态：{exc}"
            self.statusBar().showMessage(message, 8000)
            self.page_toast.show_message("代理开关保存失败，状态未改变")
            if notify:
                QMessageBox.warning(self, "代理设置保存失败", message)
            return False
        finally:
            if dashboard is not None:
                dashboard.set_proxy_toggle_enabled(True)

        self._proxy_fetch_enabled = requested_state
        if dashboard is not None:
            dashboard.set_proxy_state(requested_state)
        if notify:
            message = (
                "全局代理池已开启，未绑定固定代理的账号将轮询取件"
                if self._proxy_fetch_enabled
                else "全局代理池已关闭，未绑定固定代理的账号将使用本地网络"
            )
            self.statusBar().showMessage(message, 7000)
            self.page_toast.show_message(message)
        return True

    def _open_recent_message(self, account_id: int, message_id: int) -> None:
        account = self._accounts.get(account_id)
        if account is None:
            return
        self._show_accounts_workspace()
        root = self.group_tree.topLevelItem(0)
        if root is not None:
            self.group_tree.setCurrentItem(root)
        self.account_search.clear()
        self.tag_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)
        self._active_account_id = account_id
        self._show_account_details(account)
        for row, message in enumerate(self._displayed_messages):
            if message.message_id == message_id:
                self.message_list.setCurrentRow(row)
                break
        self.open_mail_viewer(message_id, account_id=account_id)

    def choose_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择账号文件", "", "账号文件 (*.txt *.csv *.json)"
        )
        if path:
            self.import_path(Path(path))

    def show_add_account(self) -> None:
        dialog = AddAccountDialog(self)
        if dialog.exec() != AddAccountDialog.DialogCode.Accepted or dialog.account is None:
            return
        account = dialog.account
        result = self._accounts.add_many([account])
        self._populate_groups()
        self.refresh_accounts()
        stored = next(
            (
                item
                for item in self._accounts.list_all()
                if item.email == account.email and item.protocol is account.protocol
            ),
            None,
        )
        if stored is not None:
            self._show_accounts_workspace()
            root = self.group_tree.topLevelItem(0)
            if root is not None:
                self.group_tree.setCurrentItem(root)
            self._active_account_id = stored.account_id
            self._show_account_details(stored)
        if result.inserted:
            message, tone = f"邮箱已添加 · {account.email}", "success"
        elif result.updated:
            message, tone = f"邮箱配置已更新 · {account.email}", "success"
        else:
            message, tone = f"邮箱已存在，配置没有变化 · {account.email}", "info"
        self.page_toast.show_message(message, tone=tone, duration=3600)

    def import_path(self, path: Path) -> None:
        try:
            preview = import_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self._confirm_import_preview(preview)

    def choose_paste_import(self) -> None:
        text, accepted = QInputDialog.getMultiLineText(
            self,
            "智能粘贴导入",
            "粘贴任意格式账号文本；程序会识别邮箱、相邻授权码和 OAuth 字段：",
        )
        if not accepted or not text.strip():
            return
        try:
            preview = SmartAccountParser().parse_text(text)
        except Exception as exc:
            QMessageBox.warning(self, "解析失败", str(exc))
            return
        self._confirm_import_preview(preview)

    def _confirm_import_preview(self, preview: ImportPreview) -> None:
        dialog = ImportPreviewDialog(preview, self)
        if dialog.exec() == ImportPreviewDialog.DialogCode.Accepted:
            result = self._accounts.add_many(list(dialog.valid_accounts))
            self._populate_groups()
            self._show_accounts_workspace()
            root = self.group_tree.topLevelItem(0)
            if root is not None:
                self.group_tree.setCurrentItem(root)
            self.account_search.clear()
            self.tag_filter.setCurrentIndex(0)
            self.refresh_accounts()
            summary = (
                f"批量导入完成 · 新增 {result.inserted} · 更新 {result.updated} · "
                f"跳过 {result.duplicates}"
            )
            self.statusBar().showMessage(summary, 8000)
            self.page_toast.show_message(
                summary,
                tone="success" if result.inserted or result.updated else "info",
                duration=5000,
            )

    def choose_export(self) -> None:
        path, selected = QFileDialog.getSaveFileName(
            self,
            "批量导出",
            "accounts.csv",
            "账号状态 CSV (*.csv);;邮件结果 CSV (*.csv);;账号状态 TXT (*.txt)",
        )
        if not path:
            return
        target = Path(path)
        if selected.startswith("邮件结果"):
            export_messages_csv(self._displayed_messages, target)
        elif selected.startswith("账号状态 TXT") or target.suffix.casefold() == ".txt":
            export_accounts_txt(self.account_model.accounts(), target)
        else:
            export_accounts_csv(self.account_model.accounts(), target)
        self.statusBar().showMessage(f"已安全导出到 {target}", 8000)

    def start_fetch(self) -> None:
        if self._workers:
            self.statusBar().showMessage("已有取件任务正在运行", 5000)
            self.page_toast.show_message(
                "已有取件任务正在运行",
                tone="warning",
            )
            return
        accounts = self._selected_accounts() or self.account_model.accounts()
        if not accounts:
            QMessageBox.information(self, "没有账号", "请先导入至少一个邮箱账号。")
            return
        try:
            request = self._build_fetch_request()
        except ValueError as exc:
            QMessageBox.warning(self, "收件设置无效", str(exc))
            return
        self._queue_fetch(accounts, request)

    def fetch_active_account(self) -> None:
        if self._workers:
            self.statusBar().showMessage("已有取件任务正在运行，请等待完成或先停止", 5000)
            return
        account = (
            self._accounts.get(self._active_account_id)
            if self._active_account_id is not None
            else None
        )
        if account is None:
            self.statusBar().showMessage("请先单击一个账号，再执行立即取件", 5000)
            return
        try:
            request = self._build_fetch_request()
        except ValueError as exc:
            QMessageBox.warning(self, "收件设置无效", str(exc))
            return
        self._queue_fetch([account], request)

    def _queue_fetch(
        self, accounts: list[EmailAccount], request: FetchRequest
    ) -> None:
        if self._workers:
            self.statusBar().showMessage("已有取件任务正在运行", 5000)
            return
        self._pool.setMaxThreadCount(self.concurrency_spin.value())
        self._fetch_stop_requested = False
        self._stop_event.clear()
        self._set_fetch_ui_state("running")
        for account in accounts:
            if account.account_id is None:
                continue
            worker = FetchWorker(self._fetch_service, account, request, self._stop_event)
            worker.signals.status.connect(self._worker_status)
            worker.signals.result.connect(self._worker_result)
            worker.signals.finished.connect(self._worker_finished)
            self._workers[account.account_id] = worker
            self._pool.start(worker)
        self._fetch_total = len(self._workers)
        self._fetch_completed = 0
        self._fetch_results: dict[int, AccountStatus] = {}
        if not self._workers:
            self._set_fetch_ui_state("idle")
            return
        self.statusBar().showMessage(f"正在收取 0 / {self._fetch_total} 个账号")

    def _build_fetch_request(self) -> FetchRequest:
        values = (
            self._settings.get("fetch", {})
            if self._settings is not None
            else {}
        )
        values = values if isinstance(values, dict) else {}
        keyword_values = values.get("extract_keywords", FetchRequest().keywords)
        keywords = (
            tuple(str(item) for item in keyword_values if str(item).strip())
            if isinstance(keyword_values, (list, tuple))
            else tuple(
                item.strip()
                for item in str(keyword_values).split(",")
                if item.strip()
            )
        )
        return FetchRequest(
            folders=tuple(values.get("folders", ["INBOX"])),
            max_messages=int(values.get("max_messages", 20)),
            keywords=keywords,
            custom_pattern=str(values.get("extract_pattern", "")),
            include_raw=bool(values.get("save_eml", False)),
            include_special_folders=bool(values.get("include_special", False)),
            post_action=PostAction(str(values.get("post_action", PostAction.NONE.value))),
            action_target_folder=str(values.get("action_target", "")),
            confirmed_actions=bool(values.get("confirm_actions", False)),
        )

    def _start_fetch_group(self, group_id: int | None) -> None:
        group_ids = [group_id] if group_id is not None else None
        if group_id is not None and self._groups is not None:
            group_ids.extend(self._groups.descendant_ids(group_id))
        accounts = (
            self._accounts.list_all(group_ids=group_ids)
            if group_ids is not None
            else self._accounts.list_all()
        )
        if accounts:
            self._queue_fetch(accounts, self._build_fetch_request())

    def _run_due_schedules(self) -> None:
        if hasattr(self, "_schedule_runner") and not self._workers:
            try:
                count = self._schedule_runner.run_due()
                if count:
                    self.log_view.appendPlainText(f"定时调度触发 {count} 个账号组")
            except Exception as exc:
                self.log_view.appendPlainText(f"定时调度失败：{exc}")

    def stop_fetch(self) -> None:
        self._stop_event.set()
        if not self._workers:
            return
        self._fetch_stop_requested = True
        self._set_fetch_ui_state("stopping")
        self.log_view.appendPlainText("已请求停止；正在进行的网络请求会在超时后结束。")
        self.statusBar().showMessage("已请求安全停止，正在等待当前网络请求结束")
        self.page_toast.show_message(
            "已请求安全停止，正在等待当前任务结束",
            tone="warning",
            duration=3200,
        )

    def _worker_status(self, account_id: int, status: AccountStatus, detail: str) -> None:
        if status in {
            AccountStatus.CONNECTING,
            AccountStatus.CANCELLED,
            AccountStatus.UNKNOWN_ERROR,
        }:
            self._accounts.update_status(account_id, status, detail)
        if status is not AccountStatus.CONNECTING:
            self._fetch_results[account_id] = status
        account = next(
            (item for item in self.account_model.accounts() if item.account_id == account_id), None
        )
        label = account.email if account else f"账号 {account_id}"
        self.log_view.appendPlainText(f"{label} · {STATUS_LABELS[status]} · {detail}")
        self.refresh_accounts()

    def _worker_result(self, account_id: int, result: FetchResult) -> None:
        if account_id == self._active_account_id:
            self._show_account_details(self._accounts.get(account_id))
        if self._mail_viewer is not None and self._mail_viewer.account_id == account_id:
            self._mail_viewer.set_messages(self._messages.list_for_account(account_id))
        if result.messages:
            self.log_view.appendPlainText(f"账号 {account_id} 新处理 {len(result.messages)} 封邮件")
            if self._tray is not None and self._tray.isVisible():
                self._tray.showMessage(
                    "MailDesk 新邮件",
                    f"账号 {account_id} 新处理 {len(result.messages)} 封邮件",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )

    def _worker_finished(self, account_id: int) -> None:
        self._workers.pop(account_id, None)
        self._fetch_completed = getattr(self, "_fetch_completed", 0) + 1
        total = getattr(self, "_fetch_total", self._fetch_completed)
        if not self._workers:
            was_stopped = self._fetch_stop_requested
            self._set_fetch_ui_state("idle")
            success_count = sum(
                status is AccountStatus.SUCCESS for status in self._fetch_results.values()
            )
            cancelled_count = sum(
                status is AccountStatus.CANCELLED
                for status in self._fetch_results.values()
            )
            failed_count = sum(
                status
                not in {
                    AccountStatus.SUCCESS,
                    AccountStatus.CANCELLED,
                }
                for status in self._fetch_results.values()
            )
            unreported_count = max(
                0,
                total - success_count - cancelled_count - failed_count,
            )
            if was_stopped:
                cancelled_count += unreported_count
                summary = (
                    f"取件已停止：成功 {success_count}，取消 {cancelled_count}，"
                    f"失败 {failed_count}，共 {total} 个账号"
                )
                tone = "warning"
            else:
                failed_count += unreported_count
                summary = (
                    f"收件完成：成功 {success_count}，失败 {failed_count}，"
                    f"共 {total} 个账号"
                )
                tone = "success"
            self._fetch_stop_requested = False
            self.statusBar().showMessage(summary, 10_000)
            self.page_toast.show_message(summary, tone=tone, duration=4200)
        else:
            self.statusBar().showMessage(
                f"正在收取 {self._fetch_completed} / {total} 个账号"
            )

    def _selected_accounts(self) -> list[EmailAccount]:
        return self.account_model.checked_accounts()

    def _checked_accounts_changed(self) -> None:
        selected = self._selected_accounts()
        if self._workspace_compact:
            selection_text = f"{len(selected)} 个" if selected else "未选"
        else:
            selection_text = (
                f"已勾选 {len(selected)} 个账号" if selected else "未勾选账号"
            )
        self.selection_count_label.setText(selection_text)
        self.selection_count_label.setToolTip(
            f"已勾选 {len(selected)} 个账号" if selected else "当前没有勾选账号"
        )
        self.move_group_button.setEnabled(bool(selected))
        self.delete_accounts_button.setEnabled(bool(selected))
        self.send_accounts_button.setEnabled(bool(selected) and self._send_worker is None)
        self.start_action.setToolTip(
            f"收取勾选的 {len(selected)} 个账号" if selected else "收取当前列表全部账号"
        )

    def _account_row_clicked(self, index) -> None:
        account = self.account_model.account_at(index.row()) if index.isValid() else None
        if account is None:
            return
        self._active_account_id = account.account_id
        self._show_account_details(account)

    def _copy_account_email(self, index) -> None:
        account = (
            self.account_model.account_at(index.row())
            if index.isValid() and index.column() == 1
            else None
        )
        if account is None:
            return
        self._copy_email_address(account.email)

    def _copy_email_address(self, email_address: str) -> None:
        email_address = email_address.strip()
        clipboard = QApplication.clipboard()
        clipboard.setText(email_address)
        QTimer.singleShot(0, lambda value=email_address: clipboard.setText(value))
        self.page_toast.show_message(f"邮箱已复制 · {email_address}")

    def _show_account_details(self, account: EmailAccount | None) -> None:
        self.quick_fetch_button.setEnabled(account is not None and not self._workers)
        account_detail = (
            f" · {account.status_detail}" if account and account.status_detail else ""
        )
        self.selected_account_label.setText(
            f"{account.email} · {STATUS_LABELS[account.status]}"
            + account_detail
            if account
            else "单击一个账号查看最近邮件"
        )
        if self.message_search_input.text().strip():
            self.search_messages()
            return
        messages = (
            self._messages.list_for_account(account.account_id)
            if account and account.account_id is not None
            else []
        )
        self._set_displayed_messages(messages)

    def _set_displayed_messages(
        self,
        messages: list[MailMessage],
        account_emails: list[str] | None = None,
        *,
        empty_text: str = "暂无邮件，执行取件后将在这里显示",
        count_suffix: str = "封",
    ) -> None:
        self._displayed_messages = messages
        self._displayed_message_accounts = account_emails or [""] * len(messages)
        self.message_list.clear()
        for index, message in enumerate(self._displayed_messages):
            received = (
                message.received_at.astimezone().strftime("%m-%d %H:%M")
                if message.received_at
                else ""
            )
            account_email = self._displayed_message_accounts[index]
            sender = message.sender_display or "未知发件人"
            account_meta = "  ·  ".join(
                item for item in (account_email, received) if item
            )
            self.message_list.addItem(
                f"{message.subject or '(无主题)'}\n"
                f"发件人：{sender}\n"
                f"收件账号：{account_meta}"
            )
        self.message_count_label.setText(f"{len(self._displayed_messages)} {count_suffix}")
        if self._displayed_messages:
            self.message_list.setCurrentRow(0)
        else:
            self._message_generation += 1
            self._invalidate_translation()
            self._rendered_html_fragment = ""
            self._original_plain_text = ""
            self._translation_source_text = ""
            self._current_message = None
            self._current_attachment_gallery = ""
            self._populate_message_attachments(())
            self.message_tools_bar.hide()
            self.message_body.clear()
            self.match_view.clear()
            self.message_context_label.setText(empty_text)
            self._refresh_translation_controls()

    def search_messages(self) -> None:
        query = self.message_search_input.text().strip()
        if not query:
            account = (
                self._accounts.get(self._active_account_id)
                if self._active_account_id is not None
                else None
            )
            self._show_account_details(account)
            return
        scope = self.message_search_scope.currentData()
        account_id = self._active_account_id if scope == "current" else None
        if scope == "current" and account_id is None:
            self._set_displayed_messages(
                [], empty_text="请先单击一个账号，或切换为“全部邮箱”搜索", count_suffix="条"
            )
            return
        hits = self._messages.search(query, account_id=account_id)
        self._set_displayed_messages(
            [hit.message for hit in hits],
            [hit.account_email for hit in hits],
            empty_text=f"没有找到包含“{query[:80]}”的本地邮件",
            count_suffix="条",
        )
        self.statusBar().showMessage(f"本地邮件搜索完成：{len(hits)} 条结果", 5000)

    def _message_search_text_changed(self, text: str) -> None:
        if not text.strip():
            account = (
                self._accounts.get(self._active_account_id)
                if self._active_account_id is not None
                else None
            )
            self._show_account_details(account)

    def _message_search_scope_changed(self, _index: int) -> None:
        if self.message_search_input.text().strip():
            self.search_messages()

    def show_content_filter(self) -> None:
        account = (
            self._accounts.get(self._active_account_id)
            if self._active_account_id is not None
            else None
        )
        dialog = ContentFilterDialog(
            self._messages,
            current_account_id=account.account_id if account else None,
            current_account_email=account.email if account else "",
            parent=self,
        )
        self._content_filter_dialog = dialog
        dialog.exec()
        self._content_filter_dialog = None

    def show_compose_dialog(
        self, accounts: list[EmailAccount] | None = None
    ) -> None:
        if self._send_worker is not None:
            self.page_toast.show_message("已有发件任务正在运行", tone="warning")
            return
        senders = list(accounts or self._selected_accounts())
        if not senders and self._active_account_id is not None:
            active = self._accounts.get(self._active_account_id)
            if active is not None:
                senders = [active]
        if not senders:
            self.page_toast.show_message(
                "请先单击一个账号，或勾选需要批量发件的账号",
                tone="warning",
            )
            return
        dialog = ComposeDialog(senders, self)
        if dialog.exec() != ComposeDialog.DialogCode.Accepted or dialog.draft is None:
            return
        draft = dialog.draft
        self.log_view.appendPlainText(
            f"发件开始 · 账号 {len(senders)} · 收件人 {len(draft.all_recipients)} · "
            f"附件 {len(draft.attachments)}"
        )
        worker = SendBatchWorker(self._send_service, senders, draft)
        worker.signals.result.connect(self._send_batch_result)
        worker.signals.finished.connect(self._send_batch_finished)
        self._send_worker = worker
        self.compose_action.setEnabled(False)
        self.send_accounts_button.setEnabled(False)
        self.statusBar().showMessage(f"正在使用 {len(senders)} 个邮箱发送邮件…")
        self.page_toast.show_message(
            f"发件任务已开始 · {len(senders)} 个邮箱",
            tone="info",
        )
        self._pool.start(worker)

    def _send_batch_result(
        self,
        result: BatchSendResult | None,
        error: Exception | None,
    ) -> None:
        if error is not None or result is None:
            self.log_view.appendPlainText("发件异常 · 任务未完成，请检查账号配置或审计日志")
            self.statusBar().showMessage("发件任务失败", 8000)
            self.page_toast.show_message("发件任务失败，请查看账号配置", tone="warning")
            return
        total = len(result.results)
        for index, item in enumerate(result.results, 1):
            outcome = "成功" if item.result.is_success else "失败"
            self.log_view.appendPlainText(
                f"发件账号 {index}/{total} · {outcome} · {item.result.status.value}"
            )
        summary = (
            f"发件完成：成功 {result.success_count}，失败 {result.failure_count}，"
            f"共 {total} 个邮箱"
        )
        self.log_view.appendPlainText(summary)
        tone = "success" if result.failure_count == 0 else "warning"
        self.statusBar().showMessage(summary, 10_000)
        self.page_toast.show_message(summary, tone=tone, duration=5200)
        failures = [item for item in result.results if not item.result.is_success]
        if failures:
            details = "\n".join(
                f"{item.account_email}：{item.result.detail or item.result.status.value}"
                for item in failures[:12]
            )
            if len(failures) > 12:
                details += f"\n另有 {len(failures) - 12} 个失败账号"
            QMessageBox.warning(self, "部分邮件发送失败", details)

    def _send_batch_finished(self) -> None:
        self._send_worker = None
        self.compose_action.setEnabled(True)
        self._checked_accounts_changed()

    def _open_reader_for_message_row(self, row: int) -> None:
        if not 0 <= row < len(self._displayed_messages):
            return
        message = self._displayed_messages[row]
        self.open_mail_viewer(message.message_id, account_id=message.account_id)

    def open_mail_viewer(
        self,
        selected_message_id: int | None = None,
        *,
        account_id: int | None = None,
    ) -> None:
        target_account_id = account_id or self._active_account_id
        account = self._accounts.get(target_account_id) if target_account_id else None
        if account is None or account.account_id is None:
            self.statusBar().showMessage("请先单击一个账号再打开邮件阅读器", 5000)
            return
        self._active_account_id = account.account_id
        if self._mail_viewer is not None:
            self._mail_viewer.close()
        from mailbox_manager.gui.mail_viewer_dialog import MailViewerDialog

        dialog = MailViewerDialog(
            account,
            self._messages.list_for_account(account.account_id),
            dark=self._dark,
            selected_message_id=selected_message_id,
            message_repository=self._messages,
            translation_service=self._translation_service,
            translation_language=self._translation_language,
            translation_confirm=self._translation_confirm,
            parent=self,
        )
        dialog.fetchRequested.connect(self._fetch_from_mail_viewer)
        dialog.composeRequested.connect(self._compose_from_account_id)
        dialog.filterRequested.connect(self.show_content_filter)
        dialog.finished.connect(lambda _result: self._clear_mail_viewer(dialog))
        self._mail_viewer = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _fetch_from_mail_viewer(self, account_id: int) -> None:
        account = self._accounts.get(account_id)
        if account is None:
            return
        self._active_account_id = account_id
        self._show_account_details(account)
        self.fetch_active_account()

    def _compose_from_account_id(self, account_id: int) -> None:
        account = self._accounts.get(account_id)
        if account is not None:
            self.show_compose_dialog([account])

    def _clear_mail_viewer(self, dialog: MailViewerDialog) -> None:
        if self._mail_viewer is dialog:
            self._mail_viewer = None

    def _message_selected(self, row: int) -> None:
        if not 0 <= row < len(self._displayed_messages):
            return
        self._message_generation += 1
        self._invalidate_translation()
        message = self._displayed_messages[row]
        self._current_message = message
        self._populate_message_attachments(message.attachments)
        self._current_attachment_gallery = self._attachment_gallery_html(
            self._visible_message_attachments
        )
        context = [message.subject or "(无主题)"]
        context.append(f"发件人 {message.sender_display or '未知发件人'}")
        if row < len(self._displayed_message_accounts):
            account_email = self._displayed_message_accounts[row]
            if account_email:
                context.append(account_email)
        if message.folder:
            context.append(message.folder)
        if message.catch_all_recipient:
            context.append(f"路由至 {message.catch_all_recipient}")
        self.message_context_label.setText("  ·  ".join(context))
        display_content = select_stored_message_display_content(message)
        self._original_plain_text = display_content.plain_text
        self._translation_source_text = clean_message_text(message.text_body)
        if not self._translation_source_text:
            self._translation_source_text = clean_message_text(
                display_content.html_fragment or display_content.source_html
            )
        self.message_tools_bar.show()
        if display_content.uses_html:
            self._rendered_html_fragment = display_content.source_html
            self._render_email_html(self._rendered_html_fragment)
        else:
            plain_text = display_content.plain_text
            if self._current_attachment_gallery:
                self._rendered_html_fragment = (
                    f"<div>{html_escape(plain_text).replace(chr(10), '<br>')}</div>"
                )
                self._render_email_html(self._rendered_html_fragment)
            else:
                self._rendered_html_fragment = ""
                self.message_body.setPlainText(plain_text)
        self.match_view.setPlainText("\n".join(message.matched_values) or "未提取到匹配内容")
        self._refresh_translation_controls()

    def _render_original_message_view(self) -> None:
        if self._current_message is None:
            return
        self._showing_translation = False
        self.message_tools_bar.show()
        if self._rendered_html_fragment:
            self._render_email_html(self._rendered_html_fragment)
        else:
            self.message_body.setPlainText(self._original_plain_text)
        if self._translated_text:
            self.translation_toggle_button.setText("查看译文")

    def _render_translation_view(self) -> None:
        if not self._translated_text:
            return
        self._showing_translation = True
        self.message_tools_bar.show()
        self.message_body.setPlainText(self._translated_text)
        self.translation_toggle_button.setText("查看原文")

    def _toggle_translation_view(self) -> None:
        if not self._translated_text:
            return
        if self._showing_translation:
            self._render_original_message_view()
        else:
            self._render_translation_view()

    def _translate_current_message(self) -> None:
        source_text = self._translation_source_text.strip()
        if self._current_message is None or not source_text:
            self.page_toast.show_message("当前邮件没有可翻译的正文", tone="warning")
            return
        expected_generation = self._translation_generation
        if self._translation_confirm:
            language = translation_language_label(self._translation_language)
            answer = QMessageBox.question(
                self,
                "确认翻译邮件",
                "翻译时会将当前邮件正文发送到 Google 公共翻译服务。\n"
                "不会发送附件、邮箱密码、Refresh Token 或账号配置。\n\n"
                f"目标语言：{language}\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if expected_generation != self._translation_generation:
            return
        self._translation_generation += 1
        generation = self._translation_generation
        self._active_translation_generation = generation
        self._refresh_translation_controls()
        worker = TranslationWorker(
            generation,
            source_text,
            self._translation_language,
            self._translation_service,
        )
        worker.signals.result.connect(self._translation_loaded)
        worker.signals.finished.connect(self._translation_finished)
        self._translation_workers[generation] = worker
        self._pool.start(worker)

    def _translation_loaded(
        self, generation: int, translated: str, error: object
    ) -> None:
        if generation != self._translation_generation:
            return
        self._active_translation_generation = None
        if error is not None:
            detail = (
                str(error)
                if isinstance(error, TranslationError)
                else "翻译失败，请稍后重试"
            )
            self._refresh_translation_controls()
            QMessageBox.warning(self, "翻译失败", detail)
            return
        translated = translated.strip()
        if not translated:
            self._refresh_translation_controls()
            QMessageBox.warning(self, "翻译失败", "翻译服务没有返回有效内容")
            return
        self._translated_text = translated
        self._render_translation_view()
        self._refresh_translation_controls()
        self.page_toast.show_message(
            f"已翻译为{translation_language_label(self._translation_language)}"
        )

    def _translation_finished(self, generation: int) -> None:
        self._translation_workers.pop(generation, None)
        if (
            generation == self._translation_generation
            and self._active_translation_generation == generation
        ):
            self._active_translation_generation = None
            self._refresh_translation_controls()

    def _invalidate_translation(self) -> None:
        self._translation_generation += 1
        self._active_translation_generation = None
        self._translated_text = ""
        self._showing_translation = False
        if hasattr(self, "translation_toggle_button"):
            self.translation_toggle_button.setText("查看译文")
        self._refresh_translation_controls()

    def _refresh_translation_controls(self) -> None:
        if not hasattr(self, "translate_button"):
            return
        busy = self._active_translation_generation is not None
        can_translate = bool(self._current_message and self._translation_source_text)
        self.translate_button.setEnabled(can_translate and not busy)
        self.translate_button.setText(
            "正在翻译…"
            if busy
            else "重新翻译"
            if self._translated_text
            else "翻译邮件"
        )
        self.translation_toggle_button.setEnabled(bool(self._translated_text))

    def _apply_translation_settings(
        self, target_language: str, require_confirmation: bool
    ) -> None:
        language = _valid_translation_language(target_language)
        language_changed = language != self._translation_language
        was_showing_translation = self._showing_translation
        self._translation_language = language
        self._translation_confirm = bool(require_confirmation)
        confirmation = " · 翻译前确认" if self._translation_confirm else ""
        self.translation_language_label.setText(
            f"目标语言：{translation_language_label(language)}{confirmation}"
        )
        if language_changed:
            self._invalidate_translation()
            if was_showing_translation:
                self._render_original_message_view()
        if self._mail_viewer is not None:
            self._mail_viewer.update_translation_settings(
                self._translation_language,
                self._translation_confirm,
            )
        self._refresh_translation_controls()

    def _render_email_html(self, fragment: str) -> None:
        source = fragment + self._current_attachment_gallery
        subject = self._current_message.subject if self._current_message else ""
        self.message_body.setHtml(
            prepare_email_web_document(
                source,
                preheader_hint=subject,
            )
        )

    def _populate_message_attachments(
        self, attachments: tuple[MailAttachment, ...]
    ) -> None:
        self._visible_message_attachments = tuple(
            attachment
            for attachment in attachments
            if attachment.disposition.casefold() != "inline"
        )
        self.message_attachment_list.clear()
        for index, attachment in enumerate(self._visible_message_attachments):
            state = " · 内容未保存" if attachment.is_truncated else ""
            self.message_attachment_list.addItem(
                f"{attachment.filename}    {_attachment_size(attachment.size)}{state}"
            )
            self.message_attachment_list.item(index).setData(
                Qt.ItemDataRole.UserRole, index
            )
        count = len(self._visible_message_attachments)
        total = sum(attachment.size for attachment in self._visible_message_attachments)
        self.message_attachment_title.setText(
            f"附件 {count} 个 · {_attachment_size(total)}"
        )
        self.message_attachment_panel.setVisible(bool(count))
        if count:
            self.message_attachment_list.setCurrentRow(0)

    def _selected_message_attachment(self) -> MailAttachment | None:
        item = self.message_attachment_list.currentItem()
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not 0 <= index < len(
            self._visible_message_attachments
        ):
            return None
        return self._visible_message_attachments[index]

    def _load_message_attachment(
        self, attachment: MailAttachment
    ) -> MailAttachment | None:
        if attachment.content is not None:
            return attachment
        if attachment.attachment_id is None:
            return None
        return self._messages.get_attachment(attachment.attachment_id)

    def _attachment_gallery_html(
        self, attachments: tuple[MailAttachment, ...]
    ) -> str:
        figures: list[str] = []
        for attachment in attachments:
            if not attachment.content_type.casefold().startswith("image/"):
                continue
            loaded = self._load_message_attachment(attachment)
            if (
                loaded is None
                or loaded.content is None
                or loaded.is_truncated
                or len(loaded.content) > 4 * 1024 * 1024
            ):
                continue
            encoded = base64.b64encode(loaded.content).decode("ascii")
            figures.append(
                "<figure>"
                f'<img src="data:{html_escape(loaded.content_type)};base64,{encoded}" '
                f'alt="{html_escape(loaded.filename)}">'
                f"<figcaption>{html_escape(loaded.filename)}</figcaption>"
                "</figure>"
            )
        if not figures:
            return ""
        return '<section class="attachment-gallery"><b>图片附件</b>' + "".join(
            figures
        ) + "</section>"

    def _save_selected_message_attachment(self) -> None:
        attachment = self._selected_message_attachment()
        if attachment is None:
            return
        loaded = self._load_message_attachment(attachment)
        if loaded is None or loaded.content is None or loaded.is_truncated:
            QMessageBox.warning(
                self,
                "附件不可用",
                "该附件内容未保存在本地，请重新取件后再试。",
            )
            return
        filename = _attachment_filename(loaded.filename)
        target, _ = QFileDialog.getSaveFileName(
            self, "保存附件", filename, "所有文件 (*.*)"
        )
        if not target:
            return
        try:
            Path(target).write_bytes(loaded.content)
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.page_toast.show_message(f"附件已保存 · {Path(target).name}")

    def _save_all_message_attachments(self) -> None:
        if not self._visible_message_attachments:
            return
        directory = QFileDialog.getExistingDirectory(self, "选择附件保存目录")
        if not directory:
            return
        target_directory = Path(directory)
        try:
            used_names = {path.name.casefold() for path in target_directory.iterdir()}
        except OSError:
            used_names = set()
        saved = 0
        skipped = 0
        for attachment in self._visible_message_attachments:
            loaded = self._load_message_attachment(attachment)
            if loaded is None or loaded.content is None or loaded.is_truncated:
                skipped += 1
                continue
            filename = _unique_attachment_filename(
                _attachment_filename(loaded.filename), used_names
            )
            try:
                (target_directory / filename).write_bytes(loaded.content)
            except OSError:
                skipped += 1
                continue
            saved += 1
        self.page_toast.show_message(
            f"附件保存完成 · 成功 {saved} · 跳过 {skipped}"
        )

    def _open_message_link(self, url: QUrl) -> None:
        if url.scheme().casefold() not in {"http", "https", "mailto"}:
            return
        answer = QMessageBox.question(
            self,
            "打开外部链接",
            f"即将在系统默认程序中打开：\n{url.toString()[:500]}\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(url)

    def toggle_theme(self) -> None:
        self._apply_appearance_preferences(
            {
                "dark_theme": not self._dark,
                "font_family": self._font_family,
                "font_size": self._font_size,
                "font_weight": self._font_weight,
            },
            persist=True,
        )

    def _apply_appearance_preferences(
        self,
        values: dict[str, object],
        *,
        persist: bool,
    ) -> None:
        appearance = normalized_appearance(values)
        self._dark = bool(appearance["dark_theme"])
        self._font_family = str(appearance["font_family"])
        self._font_size = int(appearance["font_size"])
        self._font_weight = int(appearance["font_weight"])
        application = QApplication.instance()
        if application is not None:
            apply_application_appearance(application, appearance)
            self.setFont(application.font())
        self.setStyleSheet(
            scaled_stylesheet(
                DARK_THEME if self._dark else LIGHT_THEME,
                self._font_size,
            )
        )
        self.theme_action.setText("浅色主题" if self._dark else "深色主题")
        self._set_toolbar_icons()
        if hasattr(self, "dashboard"):
            self.dashboard.apply_theme(self._dark)
        if self._showing_translation:
            self._render_translation_view()
        elif self._rendered_html_fragment:
            self._render_email_html(self._rendered_html_fragment)
        if persist and self._settings is not None:
            self._settings.set("ui_preferences", appearance)

    def _show_account_context_menu(self, position) -> None:
        index = self.account_table.indexAt(position)
        account = self.account_model.account_at(index.row()) if index.isValid() else None
        if account is None:
            return
        if not self.account_model.is_checked(index.row()):
            self.account_model.set_checked(index.row(), True, exclusive=True)
        self._active_account_id = account.account_id
        self._show_account_details(account)
        selected_ids = [
            item.account_id
            for item in self._selected_accounts()
            if item.account_id is not None
        ]
        menu = QMenu(self)
        copy_email_action = menu.addAction("复制邮箱地址")
        compose_action = menu.addAction("使用此邮箱写信")
        compose_action.setEnabled(self._send_worker is None)
        quick_fetch_action = menu.addAction("立即取件此账号")
        quick_fetch_action.setEnabled(not self._workers)
        menu.addSeparator()
        copy_action = menu.addAction("复制当前 2FA 动态码")
        copy_action.setEnabled(bool(account.totp_secret))
        smtp_action = menu.addAction("发送 SMTP 自检邮件到本账号")
        smtp_action.setEnabled(bool(account.smtp_host and account.smtp_port))
        discovery_action = menu.addAction("自动探测 IMAP 配置")
        discovery_action.setEnabled(account.protocol is not ProtocolType.GRAPH)
        browser_action = menu.addAction("在浏览器中打开官方邮箱设置")
        security_action = menu.addAction("只读检查 Outlook 转发规则（需额外权限）")
        security_action.setToolTip("需要 Microsoft MailboxSettings.Read 委托权限")
        security_action.setEnabled(account.protocol is ProtocolType.GRAPH)
        group_actions: dict[object, int | None] = {}
        if self._groups is not None:
            group_menu = menu.addMenu("移动到分组")
            no_group = group_menu.addAction("未分组")
            group_actions[no_group] = None
            for group in self._groups.list_all():
                action = group_menu.addAction(group.name)
                group_actions[action] = group.group_id
        tag_actions: dict[object, tuple[int, bool]] = {}
        if self._tags is not None:
            tag_menu = menu.addMenu("标签")
            for tag in self._tags.list_all():
                action = tag_menu.addAction(tag.name)
                action.setCheckable(True)
                assigned = tag.name in account.tags
                action.setChecked(assigned)
                if tag.tag_id is not None:
                    tag_actions[action] = (tag.tag_id, assigned)
            tag_menu.addSeparator()
            create_tag_action = tag_menu.addAction("新建标签…")
        else:
            create_tag_action = None
        proxy_actions: dict[object, int | None] = {}
        if self._proxies is not None:
            proxy_menu = menu.addMenu("绑定固定代理")
            direct_action = proxy_menu.addAction("直连")
            proxy_actions[direct_action] = None
            for proxy in self._proxies.list_all():
                label = proxy.display_name
                if proxy.name:
                    label = f"{label} · {proxy.identity}"
                if proxy.is_default:
                    label = f"★ {label}"
                action = proxy_menu.addAction(label)
                proxy_actions[action] = proxy.proxy_id
        menu.addSeparator()
        delete_accounts_action = menu.addAction(f"删除所选账号（{len(selected_ids)}）…")
        selected = menu.exec(self.account_table.viewport().mapToGlobal(position))
        if selected is copy_email_action:
            self._copy_email_address(account.email)
        elif selected is compose_action:
            self.show_compose_dialog([account])
        elif selected is quick_fetch_action:
            self.fetch_active_account()
        elif selected is copy_action:
            self.copy_totp(account)
        elif selected is smtp_action:
            self._start_smtp_probe(account)
        elif selected is discovery_action:
            self._start_discovery(account)
        elif selected is browser_action:
            if not open_official_webmail(account):
                QMessageBox.information(
                    self,
                    "需要手动设置",
                    "该域名没有内置官方入口，请在浏览器中手动打开邮箱服务商设置页。",
                )
        elif selected is security_action:
            self._start_security_audit(account)
        elif selected in group_actions and selected_ids:
            self._accounts.update_group(selected_ids, group_actions[selected])
            self.refresh_accounts()
            self._populate_groups()
        elif selected in tag_actions and selected_ids and self._tags is not None:
            tag_id, assigned = tag_actions[selected]
            for account_id in selected_ids:
                if assigned:
                    self._tags.unassign(account_id, tag_id)
                else:
                    self._tags.assign(account_id, tag_id)
            self.refresh_accounts()
        elif selected is create_tag_action and self._tags is not None:
            name, accepted = QInputDialog.getText(self, "新建标签", "标签名称：")
            if accepted and name.strip():
                try:
                    tag_id = self._tags.create(Tag(name=name.strip()))
                    for account_id in selected_ids:
                        self._tags.assign(account_id, tag_id)
                    self._populate_tag_filter()
                    self.refresh_accounts()
                except Exception as exc:
                    QMessageBox.warning(self, "创建失败", str(exc))
        elif selected in proxy_actions and selected_ids:
            self._accounts.bind_proxy(selected_ids, proxy_actions[selected])
            self.refresh_accounts()
        elif selected is delete_accounts_action:
            self.delete_selected_accounts()

    def _start_smtp_probe(self, account: EmailAccount) -> None:
        answer = QMessageBox.question(
            self,
            "确认 SMTP 自检",
            f"将向你确认拥有的同一邮箱 {account.email} 发送一封 UUID 测试邮件。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes or account.account_id is None:
            return
        worker = SmtpProbeWorker(account)
        worker.signals.result.connect(self._smtp_probe_result)
        worker.signals.finished.connect(self._smtp_probe_finished)
        self._smtp_workers[account.account_id] = worker
        self._pool.start(worker)

    def _smtp_probe_result(
        self, account_id: int, status: AccountStatus, detail: str
    ) -> None:
        self.log_view.appendPlainText(f"账号 {account_id} · {STATUS_LABELS[status]} · {detail}")

    def _smtp_probe_finished(self, account_id: int) -> None:
        self._smtp_workers.pop(account_id, None)

    def _start_discovery(self, account: EmailAccount) -> None:
        if account.account_id is None:
            return
        worker = DiscoveryWorker(account)
        worker.signals.result.connect(self._discovery_result)
        worker.signals.finished.connect(self._discovery_finished)
        self._discovery_workers[account.account_id] = worker
        self.log_view.appendPlainText(f"{account.email} · 开始受限 IMAP 自动探测")
        self._pool.start(worker)

    def _discovery_result(self, account_id: int, result) -> None:
        if result is None:
            self.log_view.appendPlainText(f"账号 {account_id} · 未发现可用 IMAP 配置")
            return
        host, port, security = result
        self._accounts.update_connection(
            account_id, host=host, port=port, security=security
        )
        self.log_view.appendPlainText(
            f"账号 {account_id} · 已发现并保存 {host}:{port} ({security.value})"
        )
        self.refresh_accounts()

    def _discovery_finished(self, account_id: int) -> None:
        self._discovery_workers.pop(account_id, None)

    def _start_security_audit(self, account: EmailAccount) -> None:
        if account.account_id is None:
            return
        worker = SecurityAuditWorker(account)
        worker.signals.result.connect(self._security_audit_result)
        worker.signals.finished.connect(self._security_audit_finished)
        self._security_workers[account.account_id] = worker
        self._pool.start(worker)

    def _security_audit_result(
        self, account_id: int, findings: object, error: object
    ) -> None:
        if isinstance(error, SecurityAuditPermissionError):
            dialog = QMessageBox(self)
            dialog.setWindowTitle("需要额外 Microsoft 权限")
            dialog.setIcon(QMessageBox.Icon.Information)
            dialog.setText("当前账号可以正常收件，但没有读取 Outlook 收件规则的权限。")
            dialog.setInformativeText(
                "安全审计需要 MailboxSettings.Read 委托权限。可以通过微软官方设备码流程"
                "重新授权 Mail.Read 与 MailboxSettings.Read；账号密码不会交给 MailDesk。"
            )
            authorize_button = dialog.addButton(
                "重新授权", QMessageBox.ButtonRole.AcceptRole
            )
            dialog.addButton("暂不授权", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            if dialog.clickedButton() is authorize_button:
                account = self._accounts.get(account_id)
                if account is not None:
                    self._start_security_consent(account)
            return
        if isinstance(error, SecurityAuditAuthenticationError):
            QMessageBox.warning(
                self,
                "Microsoft 授权已失效",
                "该账号需要重新登录授权。普通取件也可能随后失效，请重新导入有效授权信息。",
            )
            return
        if isinstance(error, SecurityAuditTemporaryError):
            QMessageBox.information(
                self, "暂时无法审计", "Microsoft Graph 当前繁忙或受到限流，请稍后重试。"
            )
            return
        if error:
            QMessageBox.warning(self, "安全审计失败", "无法读取 Outlook 收件规则。")
            return
        items = findings if isinstance(findings, list) else []
        if not items:
            QMessageBox.information(self, "安全审计", "未发现转发、重定向或删除规则。")
            return
        detail = "\n".join(
            f"• {item.rule_name} [{item.finding_type}] {item.detail}" for item in items
        )
        QMessageBox.warning(
            self,
            "发现需要复核的收件规则",
            detail + "\n\nMailDesk 只读检查，不会自动删除。请在官方 Outlook 设置页确认处理。",
        )

    def _security_audit_finished(self, account_id: int) -> None:
        self._security_workers.pop(account_id, None)

    def _start_security_consent(self, account: EmailAccount) -> None:
        if account.account_id is None or account.account_id in self._security_consent_workers:
            return
        worker = SecurityConsentWorker(account)
        worker.signals.challenge.connect(self._security_consent_challenge)
        worker.signals.result.connect(self._security_consent_result)
        worker.signals.finished.connect(self._security_consent_finished)
        self._security_consent_workers[account.account_id] = worker
        self.statusBar().showMessage("正在向 Microsoft 请求设备验证码…")
        self._pool.start(worker)

    def _security_consent_challenge(
        self, account_id: int, challenge: DeviceCodeChallenge
    ) -> None:
        QApplication.clipboard().setText(challenge.user_code)
        target = challenge.verification_uri_complete or challenge.verification_uri
        QDesktopServices.openUrl(QUrl(target))
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Microsoft 安全审计授权")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText(f"设备验证码：{challenge.user_code}")
        dialog.setInformativeText(
            "验证码已复制，并已打开微软官方登录页面。请在浏览器中登录对应账号并确认"
            " Mail.Read 与 MailboxSettings.Read 权限；完成后此窗口会自动关闭。"
        )
        cancel_button = dialog.addButton("取消授权", QMessageBox.ButtonRole.RejectRole)
        cancel_button.clicked.connect(lambda: self._cancel_security_consent(account_id))
        dialog.rejected.connect(lambda: self._cancel_security_consent(account_id))
        self._security_consent_dialogs[account_id] = dialog
        dialog.open()

    def _cancel_security_consent(self, account_id: int) -> None:
        worker = self._security_consent_workers.get(account_id)
        if worker is not None:
            worker.cancel()

    def _security_consent_result(
        self, account_id: int, refresh_token: str, error: object
    ) -> None:
        dialog = self._security_consent_dialogs.pop(account_id, None)
        if dialog is not None:
            dialog.close()
        if isinstance(error, DeviceAuthorizationCancelled):
            self.statusBar().showMessage("已取消 Microsoft 重新授权", 5000)
            return
        if error or not refresh_token:
            detail = str(error) if error else "Microsoft 未返回 Refresh Token"
            QMessageBox.warning(self, "重新授权失败", detail)
            return
        try:
            self._accounts.update_refresh_token(account_id, refresh_token)
        except ValueError as exc:
            QMessageBox.warning(self, "保存授权失败", str(exc))
            return
        self.refresh_accounts()
        QMessageBox.information(
            self,
            "重新授权成功",
            "新的 Microsoft Refresh Token 已使用本机密钥加密保存，现在将重新执行只读安全审计。",
        )
        account = self._accounts.get(account_id)
        if account is not None:
            self._start_security_audit(account)

    def _security_consent_finished(self, account_id: int) -> None:
        self._security_consent_workers.pop(account_id, None)

    def _show_message_context_menu(self, position) -> None:
        row = self.message_list.indexAt(position).row()
        if not 0 <= row < len(self._displayed_messages):
            return
        menu = QMenu(self)
        export_action = menu.addAction("导出邮件原件 .eml")
        selected = menu.exec(self.message_list.viewport().mapToGlobal(position))
        if selected is not export_action:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出邮件原件", "message.eml", "EML (*.eml)"
        )
        if not path:
            return
        try:
            if self._eml_store is None:
                raise ValueError("EML 存储服务未配置")
            self._eml_store.export(self._displayed_messages[row], Path(path))
            self.statusBar().showMessage(f"邮件原件已导出到 {path}", 8000)
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def copy_totp(self, account: EmailAccount) -> bool:
        if not account.totp_secret:
            self.statusBar().showMessage("该账号未配置 TOTP 密钥", 5000)
            return False
        try:
            code = current_totp(account.totp_secret)
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 5000)
            return False
        QApplication.clipboard().setText(code)
        self.statusBar().showMessage("2FA 动态码已复制，30 秒后自动清除", 5000)
        from PySide6.QtCore import QTimer

        QTimer.singleShot(30_000, lambda: self._clear_clipboard(code))
        return True

    def _clear_clipboard(self, expected: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard.text() == expected:
            clipboard.clear()

    def enable_tray(self, tray: QSystemTrayIcon) -> None:
        self._tray = tray

    def check_for_updates(self, *, manual: bool = True) -> None:
        """Check the latest stable GitHub release on the shared worker pool."""

        if self._update_service is None:
            if manual:
                QMessageBox.information(
                    self,
                    "检查更新",
                    "当前运行方式没有配置在线更新服务。",
                )
            return
        if self._update_download_worker is not None:
            if manual:
                self.statusBar().showMessage("更新正在后台下载，无需重复检查。", 4000)
                self._show_update_dialog()
            return
        if self._update_check_worker is not None:
            self._update_check_manual = self._update_check_manual or manual
            if manual:
                self.statusBar().showMessage("正在检查新版本…", 3000)
            return

        self._update_check_manual = manual
        worker = UpdateCheckWorker(self._update_service)
        self._update_check_worker = worker
        worker.signals.result.connect(self._on_update_check_result)
        worker.signals.finished.connect(self._on_update_check_finished)
        self._update_pool.start(worker)
        if manual:
            self.statusBar().showMessage("正在检查新版本…")

    def _on_update_check_result(self, update: object, error: object) -> None:
        manual = self._update_check_manual
        if error is not None:
            logging.getLogger(__name__).warning("Update check failed: %s", error)
            if manual:
                message = (
                    str(error)
                    if isinstance(error, UpdateError)
                    else "检查更新失败，请稍后重试。"
                )
                QMessageBox.warning(self, "检查更新失败", message)
            return
        if update is None:
            if self._staged_update is None:
                self._update_info = None
                self.update_toolbar_action.setVisible(False)
                self.update_tool_button.hide()
            if manual:
                version = (
                    self._update_service.current_version
                    if self._update_service is not None
                    else "当前"
                )
                QMessageBox.information(
                    self,
                    "已是最新版本",
                    f"MailDesk v{version} 已是最新正式版本。",
                )
            return
        if not isinstance(update, UpdateInfo):
            logging.getLogger(__name__).error("Update service returned an invalid result")
            if manual:
                QMessageBox.warning(self, "检查更新失败", "更新服务返回了无效结果。")
            return

        if self._update_download_worker is not None:
            active_identity = self._update_download_identity
            if active_identity is not None and self._update_identity(update) != active_identity:
                logging.getLogger(__name__).info(
                    "Ignored a newer update check while another release is downloading"
                )
            return

        previous_staged = self._staged_update
        self._update_info = update
        if (
            previous_staged is None
            or previous_staged.update.release.version != update.release.version
        ):
            self._staged_update = None
        skipped = (
            self._settings.get("skipped_update_version", "")
            if self._settings is not None
            else ""
        )
        if str(skipped).strip().removeprefix("v") == update.release.version and not manual:
            self.update_toolbar_action.setVisible(False)
            self.update_tool_button.hide()
            return

        self._set_update_button_state("available")
        self._show_update_dialog()

    def _on_update_check_finished(self) -> None:
        self._update_check_worker = None
        self._update_check_manual = False
        self.statusBar().showMessage("就绪", 2500)

    def _show_update_dialog(self) -> None:
        update = self._update_info
        service = self._update_service
        if update is None or service is None:
            return
        if self._update_dialog is None:
            dialog = UpdateDialog(
                service.current_version,
                update.release.version,
                update.release.notes,
                self,
            )
            dialog.downloadRequested.connect(self._start_update_download)
            dialog.skipVersionRequested.connect(self._skip_update_version)
            dialog.installRequested.connect(self._confirm_update_install)
            self._update_dialog = dialog
        else:
            dialog = self._update_dialog
            if dialog.latest_version.removeprefix("v") != update.release.version:
                dialog.set_release(
                    service.current_version,
                    update.release.version,
                    update.release.notes,
                )

        if self._staged_update is not None:
            dialog.set_download_complete()
        elif self._update_download_worker is not None:
            dialog.set_downloading()
            self._apply_update_progress_to_dialog()
        elif dialog.state is not UpdateDialogState.ERROR:
            dialog.set_release(
                service.current_version,
                update.release.version,
                update.release.notes,
            )

        if not update.install_supported:
            dialog.primary_button.setText("打开发布页")
            dialog.primary_button.setIcon(line_icon("export", "#ffffff", 18))
        if self._update_install_worker is not None:
            dialog.set_install_status(
                "正在校验安装文件",
                "正在后台核对新版全部文件，完成后将自动关闭并重新启动。",
            )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_update_button_clicked(self) -> None:
        if self._update_info is None:
            self.check_for_updates(manual=True)
            return
        self._show_update_dialog()

    def _start_update_download(self, version: str) -> None:
        service = self._update_service
        update = self._update_info
        if service is None or update is None:
            return
        if version.strip().removeprefix("v") != update.release.version:
            logging.getLogger(__name__).warning(
                "Ignored a download request for a stale update dialog"
            )
            return
        if not update.install_supported or update.install_mode is InstallMode.SOURCE:
            QDesktopServices.openUrl(QUrl(update.release.page_url))
            if self._update_dialog is not None:
                self._update_dialog.reject()
            return
        if self._update_download_worker is not None:
            return

        self._update_received_bytes = 0
        self._update_total_bytes = update.asset.size if update.asset is not None else None
        operation_id = uuid4().hex
        self._update_operation_id = operation_id
        self._update_download_identity = self._update_identity(update)
        worker = UpdateDownloadWorker(service, update, operation_id)
        self._update_download_worker = worker
        worker.signals.progress.connect(self._on_update_download_progress)
        worker.signals.status.connect(self._on_update_download_status)
        worker.signals.result.connect(self._on_update_download_result)
        worker.signals.finished.connect(self._on_update_download_finished)
        if self._update_dialog is not None:
            self._update_dialog.set_downloading()
        self.check_updates_action.setEnabled(False)
        self._set_update_button_state("downloading", 0)
        self._update_pool.start(worker)

    def _on_update_download_progress(
        self, operation_id: str, received: int, total: object
    ) -> None:
        if operation_id != self._update_operation_id:
            return
        safe_total = total if isinstance(total, int) and total > 0 else None
        self._update_received_bytes = max(0, received)
        self._update_total_bytes = safe_total
        percent = (
            min(100, int(self._update_received_bytes * 100 / safe_total))
            if safe_total
            else None
        )
        self._set_update_button_state("downloading", percent)
        self._apply_update_progress_to_dialog()

    def _apply_update_progress_to_dialog(self) -> None:
        if self._update_dialog is None:
            return
        total = self._update_total_bytes
        percent = (
            min(100, int(self._update_received_bytes * 100 / total))
            if total
            else None
        )
        self._update_dialog.set_download_progress(
            percent,
            received_bytes=self._update_received_bytes,
            total_bytes=total,
        )

    def _on_update_download_status(self, operation_id: str, message: str) -> None:
        if operation_id != self._update_operation_id:
            return
        self.statusBar().showMessage(message)
        if self._update_dialog is not None:
            self._update_dialog.set_download_status(message)

    def _on_update_download_result(
        self, operation_id: str, staged: object, error: object
    ) -> None:
        if operation_id != self._update_operation_id:
            return
        if error is not None:
            logging.getLogger(__name__).warning("Update download failed: %s", error)
            message = str(error) if isinstance(error, UpdateError) else "更新下载失败，请稍后重试。"
            self._set_update_button_state("available")
            if self._update_dialog is not None:
                self._update_dialog.set_download_error(message)
                self._update_dialog.show()
                self._update_dialog.raise_()
            return
        if not isinstance(staged, StagedUpdate):
            self._set_update_button_state("available")
            if self._update_dialog is not None:
                self._update_dialog.set_download_error("更新暂存结果无效，请重新下载。")
            return
        if self._update_identity(staged.update) != self._update_download_identity:
            logging.getLogger(__name__).error(
                "Rejected a staged update that does not match the active operation"
            )
            self._set_update_button_state("available")
            if self._update_dialog is not None:
                self._update_dialog.set_download_error(
                    "更新包版本与当前任务不一致，已阻止安装。"
                )
            return

        self._staged_update = staged
        self._set_update_button_state("ready")
        if self._update_dialog is not None:
            self._update_dialog.set_download_complete()
            self._update_dialog.show()
            self._update_dialog.raise_()
            self._update_dialog.activateWindow()
        if self._tray is not None and self._tray.isVisible():
            self._tray.showMessage(
                "MailDesk 更新已就绪",
                "新版已在后台下载并校验完成，可重启安装。",
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )

    def _on_update_download_finished(self, operation_id: str) -> None:
        if operation_id != self._update_operation_id:
            return
        self._update_download_worker = None
        self._update_operation_id = None
        self.check_updates_action.setEnabled(self._update_service is not None)
        if self._staged_update is None:
            self.statusBar().showMessage("更新未完成", 5000)
        else:
            self.statusBar().showMessage("更新已准备就绪", 5000)

    def _skip_update_version(self, version: str) -> None:
        normalized = version.strip().removeprefix("v")
        if self._settings is not None:
            self._settings.set("skipped_update_version", normalized)
        self.update_toolbar_action.setVisible(False)
        self.update_tool_button.hide()
        self.statusBar().showMessage(f"已跳过 v{normalized}", 5000)

    def _confirm_update_install(self, version: str) -> None:
        service = self._update_service
        staged = self._staged_update
        dialog = self._update_dialog
        if service is None or staged is None:
            logging.getLogger("maildesk.update").warning(
                "Install request rejected because no verified staged update exists"
            )
            if dialog is not None:
                dialog.set_download_error("更新尚未准备完成，请重新下载。")
                dialog.show()
            self.statusBar().showMessage("更新尚未准备完成，请重新下载", 6000)
            return
        if (
            version.strip().removeprefix("v") != staged.update.release.version
            or self._update_identity(staged.update) != self._update_download_identity
        ):
            logging.getLogger("maildesk.update").warning(
                "Install request rejected because the staged release identity changed"
            )
            if dialog is not None:
                dialog.set_download_error("更新版本状态已变化，请重新检查并下载。")
                dialog.show()
            self.statusBar().showMessage("更新版本状态已变化，请重新下载", 6000)
            return
        if self._update_install_worker is not None:
            logging.getLogger("maildesk.update").info(
                "Ignored duplicate install request while installer preparation is active"
            )
            self.statusBar().showMessage("正在准备安装，请稍候…", 4000)
            return
        answer = QMessageBox.question(
            self,
            "确认重启并安装",
            "MailDesk 将关闭并安装已校验的新版本，随后自动重新启动。\n\n"
            "请先确认当前编辑内容已经保存。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            if dialog is not None:
                dialog.set_download_complete()
            return
        self.check_updates_action.setEnabled(False)
        if dialog is not None:
            dialog.set_install_status(
                "正在准备安装",
                "正在后台核对已签名的本地更新文件，随后启动安装助手。",
            )
        self.statusBar().showMessage("正在校验更新文件并启动安装助手…")
        logging.getLogger("maildesk.update").info(
            "User confirmed installation of v%s (%s)",
            staged.update.release.version,
            staged.update.install_mode.value,
        )
        self._launch_staged_update(service, staged, dialog)

    def _launch_staged_update(
        self,
        service: UpdateService,
        staged: StagedUpdate,
        dialog: UpdateDialog | None,
    ) -> None:
        if self._update_install_worker is not None:
            return
        worker = UpdateInstallWorker(service, staged)
        self._update_install_worker = worker
        worker.signals.status.connect(self._on_update_installer_status)
        worker.signals.result.connect(self._on_update_installer_result)
        worker.signals.finished.connect(self._on_update_installer_finished)
        if dialog is not None:
            dialog.set_install_status(
                "正在校验安装文件",
                "正在后台核对新版全部文件，完成后将自动关闭并重新启动。",
            )
        self.statusBar().showMessage("正在校验更新文件并启动安装助手…")
        logging.getLogger("maildesk.update").info(
            "Preparing verified update installer from %s",
            staged.staging_root,
        )
        self._update_pool.start(worker)

    def _on_update_installer_status(self, message: str) -> None:
        logging.getLogger("maildesk.update").info("%s", message)
        self.statusBar().showMessage(message)
        if self._update_dialog is not None:
            self._update_dialog.set_install_status(
                message,
                "请稍候，安装助手接管后 MailDesk 会自动关闭并重新启动。",
            )

    def _on_update_installer_result(self, plan: object, error: object) -> None:
        service = self._update_service
        staged = self._staged_update
        dialog = self._update_dialog
        if service is None or staged is None:
            logging.getLogger("maildesk.update").error(
                "Installer result arrived after update state was cleared"
            )
            self.statusBar().showMessage("更新状态异常，请重新下载", 6000)
            return
        if error is not None:
            exc = error
            logging.getLogger("maildesk.update").error(
                "Unable to start update installer: %s",
                exc,
            )
            message = str(exc) if isinstance(exc, UpdateError) else "无法启动更新安装程序。"
            QMessageBox.warning(self, "无法安装更新", message)
            if isinstance(exc, UpdateSecurityError):
                service.discard_staged_update(staged)
                self._staged_update = None
                self._update_download_identity = None
                self._set_update_button_state("available")
                if dialog is not None:
                    dialog.set_download_error(message)
            elif dialog is not None:
                dialog.set_download_complete()
            return
        logging.getLogger("maildesk.update").info(
            "Update installer accepted the hand-off"
        )
        if dialog is not None:
            dialog.accept()
        self.statusBar().showMessage("安装助手已接管，正在退出 MailDesk…")
        self.request_quit()

    def _on_update_installer_finished(self) -> None:
        self._update_install_worker = None

    def _set_update_button_state(
        self, state: str, percent: int | None = None
    ) -> None:
        button = self.update_tool_button
        button.setProperty("state", state)
        if state == "ready":
            button.setText("重启更新")
            button.setIcon(line_icon("refresh", "#ffffff"))
            button.setToolTip("更新已下载并校验完成，点击重启安装")
        elif state == "downloading":
            button.setText("下载中…" if percent is None else f"更新 {percent}%")
            button.setIcon(line_icon("download", "#ffffff"))
            button.setToolTip("更新正在后台下载，可继续使用 MailDesk")
        else:
            button.setText("更新")
            button.setIcon(line_icon("sparkles", "#ffffff"))
            button.setToolTip("有新的 MailDesk 正式版本可用")
        self.update_toolbar_action.setVisible(True)
        button.show()
        button.style().unpolish(button)
        button.style().polish(button)
        button.updateGeometry()

    @staticmethod
    def _update_identity(update: UpdateInfo) -> tuple[str, str, str, str, str]:
        asset = update.asset
        return (
            update.release.version,
            update.install_mode.value,
            asset.name if asset is not None else "",
            (asset.digest or "") if asset is not None else "",
            update.expected_sha256 or "",
        )

    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def request_quit(self) -> None:
        self._force_close = True
        self.stop_fetch()
        if self._tray is not None:
            self._tray.hide()
        self.close()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def show_settings(self) -> None:
        current = (
            self._settings.get("enterprise_ui", {})
            if self._settings is not None
            else {}
        )
        current = current if isinstance(current, dict) else {}
        current = dict(current)
        if self._settings is not None:
            fetch_values = self._settings.get("fetch", {})
            if isinstance(fetch_values, dict):
                current.update(fetch_values)
            ui_values = self._settings.get("ui_preferences", {})
            if isinstance(ui_values, dict):
                current.update(normalized_appearance(ui_values))
        else:
            current.update(
                {
                    "dark_theme": self._dark,
                    "font_family": self._font_family,
                    "font_size": self._font_size,
                    "font_weight": self._font_weight,
                }
            )
        if self._schedules is not None:
            selected_group_id = self._selected_group_id()
            selected_schedule = next(
                (
                    item
                    for item in self._schedules.list_all()
                    if item.group_id == selected_group_id
                ),
                None,
            )
            current["schedule_enabled"] = bool(
                selected_schedule and selected_schedule.enabled
            )
            if selected_schedule is not None:
                current["schedule_interval"] = selected_schedule.interval_minutes
        if self._proxies is not None:
            current["proxy_count"] = len(self._proxies.list_all())
        webhook_options = (
            [
                (item.webhook_id, item.name)
                for item in self._webhooks.list_all()
                if item.webhook_id is not None
            ]
            if self._webhooks is not None
            else []
        )
        dialog = EnterpriseSettingsDialog(
            current,
            self,
            webhook_options=webhook_options,
        )
        if hasattr(dialog, "addProxyRequested"):
            dialog.addProxyRequested.connect(
                lambda: self._show_add_proxy_dialog(dialog)
            )
        if hasattr(dialog, "updateCheckRequested"):
            dialog.updateCheckRequested.connect(
                lambda: self.check_for_updates(manual=True)
            )
        if dialog.exec() != EnterpriseSettingsDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            action = PostAction(str(values["post_action"]))
            if action is not PostAction.NONE and not values["confirm_actions"]:
                raise ValueError("启用邮件后处理必须勾选副作用确认")
            if action is PostAction.MOVE and not values["action_target"]:
                raise ValueError("移动邮件必须填写目标文件夹")
            if int(values["login_interval_max"]) < int(values["login_interval_min"]):
                raise ValueError("最大登录间隔不能小于最小间隔")
            if self._settings is not None:
                self._settings.set(
                    "enterprise_ui", _persistent_enterprise_settings(values)
                )
                self._settings.set(
                    "fetch",
                    {
                        key: values[key]
                        for key in (
                            "folders",
                            "max_messages",
                            "include_special",
                            "extract_keywords",
                            "extract_pattern",
                            "post_action",
                            "action_target",
                            "confirm_actions",
                        )
                    },
                )
                self._settings.set("webhook_allowed_hosts", values["webhook_hosts"])
            throttle = ComplianceThrottle(
                max_concurrency_per_identity=int(values["ip_concurrency"]),
                min_account_interval=float(values["login_interval_min"]),
                max_account_interval=float(values["login_interval_max"]),
            )
            self._fetch_service.set_throttle(throttle)
            self._save_enterprise_settings(values)
            self._dashboard_quick_actions = configured_quick_action_ids(
                values.get("dashboard_quick_actions")
            )
            if hasattr(self, "dashboard"):
                self.dashboard.set_quick_actions(self._dashboard_quick_actions)
                self.dashboard.refresh()
            self._set_proxy_fetch_enabled(
                bool(values.get("proxy_fetch_enabled", False)),
                persist=False,
                notify=False,
            )
            self._apply_translation_settings(
                str(
                    values.get(
                        "translation_language", DEFAULT_TRANSLATION_LANGUAGE
                    )
                ),
                bool(values.get("translation_confirm", True)),
            )
            self._apply_appearance_preferences(values, persist=True)
            self.statusBar().showMessage("企业设置已保存", 8000)
            self.page_toast.show_message("系统设置已保存并应用")
        except Exception as exc:
            QMessageBox.warning(self, "设置保存失败", str(exc))

    def _show_add_proxy_dialog(self, parent: QWidget | None = None) -> None:
        if self._proxies is None:
            QMessageBox.information(
                parent or self,
                "代理功能不可用",
                "当前运行方式没有配置代理存储。",
            )
            return
        dialog = AddProxyDialog(parent or self)
        if dialog.exec() != AddProxyDialog.DialogCode.Accepted or dialog.proxy is None:
            return
        try:
            self._proxies.add(dialog.proxy)
        except Exception as exc:
            QMessageBox.warning(parent or self, "代理保存失败", str(exc))
            return
        count = len(self._proxies.list_all())
        if isinstance(parent, EnterpriseSettingsDialog):
            parent.set_proxy_count(count)
        if hasattr(self, "dashboard"):
            self.dashboard.refresh()
        message = f"代理“{dialog.proxy.display_name}”已加密保存"
        self.statusBar().showMessage(message, 6000)
        self.page_toast.show_message(message)

    def _save_enterprise_settings(self, values: dict[str, object]) -> None:
        proxy_text = str(values.get("proxy_text", "")).strip()
        if proxy_text and self._proxies is not None:
            proxy_type = ProxyType(str(values["proxy_type"]))
            for proxy in parse_proxy_text(proxy_text, proxy_type):
                try:
                    self._proxies.add(proxy)
                except Exception:
                    continue
        new_webhook_id: int | None = None
        if values.get("webhook_name") and values.get("webhook_url") and self._webhooks:
            new_webhook_id = self._webhooks.add(
                WebhookConfig(
                    name=str(values["webhook_name"]),
                    url=str(values["webhook_url"]),
                    secret=str(values["webhook_secret"]),
                )
            )
        if values.get("rule_name") and values.get("rule_pattern") and self._rules:
            selected_webhook = values.get("rule_webhook_id")
            webhook_id = (
                new_webhook_id
                if selected_webhook == "new"
                else int(selected_webhook)
                if selected_webhook not in {None, ""}
                else None
            )
            self._rules.add(
                AutomationRule(
                    name=str(values["rule_name"]),
                    pattern=str(values["rule_pattern"]),
                    action=PostAction(str(values["rule_action"])),
                    target_folder=str(values["rule_target"]),
                    webhook_id=webhook_id,
                    forward_to=str(values["rule_forward"]),
                )
            )
        if self._schedules is not None:
            self._schedules.upsert(
                ScheduleConfig(
                    group_id=self._selected_group_id(),
                    interval_minutes=int(values["schedule_interval"]),
                    enabled=bool(values["schedule_enabled"]),
                )
            )

    def export_audit_report(self) -> None:
        if self._audit_reports is None:
            QMessageBox.information(self, "审计报告", "审计报告服务未配置。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出错误排查报告", "maildesk-audit.zip", "ZIP (*.zip)"
        )
        if path:
            try:
                self._audit_reports.export(Path(path))
                self.statusBar().showMessage(f"审计报告已导出到 {path}", 8000)
            except Exception as exc:
                QMessageBox.warning(self, "导出失败", str(exc))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and Path(urls[0].toLocalFile()).suffix.casefold() in {
            ".txt",
            ".csv",
            ".json",
        }:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.import_path(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_splitter_sizes()
        tray_available = self._tray is not None and self._tray.isVisible()
        if not self._force_close:
            action = self._configured_close_action()
            if not tray_available and action in {
                CLOSE_ACTION_ASK,
                CLOSE_ACTION_TRAY,
            }:
                action = CLOSE_ACTION_EXIT
            if action == CLOSE_ACTION_ASK:
                dialog = CloseWindowDialog(self, tray_available=tray_available)
                if (
                    dialog.exec() != CloseWindowDialog.DialogCode.Accepted
                    or dialog.selected_action is None
                ):
                    event.ignore()
                    return
                action = dialog.selected_action
                if dialog.remember_choice:
                    self._persist_close_action(action)
            if action == CLOSE_ACTION_TRAY and tray_available:
                self.hide()
                self._tray.showMessage(
                    "MailDesk",
                    "程序已最小化到系统托盘，将继续静默运行。",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
                event.ignore()
                return
            if action == CLOSE_ACTION_EXIT:
                self._force_close = True
                if self._tray is not None:
                    self._tray.hide()

        self._shutdown_before_close()
        event.accept()
        if self._force_close and self._tray is not None:
            application = QApplication.instance()
            if application is not None:
                QTimer.singleShot(0, application.quit)

    def _configured_close_action(self) -> str:
        values = (
            self._settings.get("enterprise_ui", {})
            if self._settings is not None
            else {}
        )
        action = (
            str(values.get("close_action", CLOSE_ACTION_ASK))
            if isinstance(values, dict)
            else CLOSE_ACTION_ASK
        )
        return action if action in CLOSE_ACTIONS else CLOSE_ACTION_ASK

    def _persist_close_action(self, action: str) -> None:
        if self._settings is None or action not in CLOSE_ACTIONS:
            return
        values = self._settings.get("enterprise_ui", {})
        values = dict(values) if isinstance(values, dict) else {}
        values["close_action"] = action
        self._settings.set("enterprise_ui", values)

    def _shutdown_before_close(self) -> None:
        self.stop_fetch()
        if self._update_download_worker is not None:
            self._update_download_worker.cancel()
        self._translation_generation += 1
        self._active_translation_generation = None
        self.message_body.shutdown()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())
        if hasattr(self, "page_toast"):
            self.page_toast.reposition()

    def _apply_responsive_layout(self, available_width: int) -> None:
        """Keep every primary workflow reachable at supported window widths."""

        self._set_toolbar_compact(
            available_width < _TOOLBAR_COMPACT_BREAKPOINT
        )
        self._set_workspace_compact(
            available_width < _WORKSPACE_COMPACT_BREAKPOINT
        )

    def _set_toolbar_compact(self, compact: bool) -> None:
        if not hasattr(self, "main_toolbar") or compact == self._toolbar_compact:
            return

        self._toolbar_compact = compact
        self.brand_copy.setVisible(not compact)
        self.import_toolbar_action.setVisible(not compact)
        self.toolbar_more_action.setVisible(compact)
        self.concurrency_label.setVisible(not compact)

        if compact:
            self.main_toolbar.removeAction(self.export_action)
            self.main_toolbar.removeAction(self.compose_action)
        else:
            toolbar_actions = self.main_toolbar.actions()
            if self.export_action not in toolbar_actions:
                self.main_toolbar.insertAction(
                    self.fetch_separator_action, self.export_action
                )
            if self.compose_action not in self.main_toolbar.actions():
                self.main_toolbar.insertAction(
                    self.fetch_separator_action, self.compose_action
                )

        responsive_buttons = (
            "add_account_tool_button",
            "start_tool_button",
            "stop_tool_button",
            "tools_menu_button",
            "settings_tool_button",
        )
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        for name in responsive_buttons:
            button = getattr(self, name, None)
            if isinstance(button, QToolButton):
                button.setToolButtonStyle(style)

        if isinstance(getattr(self, "theme_tool_button", None), QToolButton):
            self.theme_tool_button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
            )

        self.main_toolbar.setProperty("compact", compact)
        self.main_toolbar.style().unpolish(self.main_toolbar)
        self.main_toolbar.style().polish(self.main_toolbar)
        self.main_toolbar.updateGeometry()

    def _set_workspace_compact(self, compact: bool) -> None:
        if not hasattr(self, "account_header") or compact == self._workspace_compact:
            return

        if compact:
            self._wide_account_column_widths = tuple(
                self.account_header.sectionSize(section)
                for section in range(self.account_model.columnCount())
            )
            column_widths = (38, 220, 92, 68, 125, 85, 125, 82)
        else:
            column_widths = self._wide_account_column_widths

        self._workspace_compact = compact
        for section, width in enumerate(column_widths):
            self.account_header.resizeSection(section, width)

        self.sidebar.setMinimumWidth(150 if compact else 170)
        self.sidebar_caption.setVisible(not compact)
        self.account_layout.setContentsMargins(
            12 if compact else 16,
            12 if compact else 14,
            12 if compact else 16,
            8,
        )
        self.quick_fetch_button.setText("取件" if compact else "立即取件")
        self.column_menu_button.setText("列" if compact else "显示列")
        self.send_accounts_button.setText("发件" if compact else "批量发件")
        self.delete_accounts_button.setText("删除" if compact else "删除所选")
        self.open_reader_button.setText("阅读" if compact else "阅读器")
        self.content_filter_button.setText("筛选" if compact else "筛选导出")
        self.tag_filter.setMinimumWidth(104 if compact else 140)
        self.status_filter.setMinimumWidth(104 if compact else 132)
        self.group_move_combo.setMinimumWidth(124 if compact else 160)
        self.message_search_scope.setMaximumWidth(94 if compact else 110)
        self.translation_language_label.setVisible(not compact)
        self._checked_accounts_changed()


def _valid_translation_language(value: str) -> str:
    supported = {code for code, _label in TRANSLATION_LANGUAGES}
    return value if value in supported else DEFAULT_TRANSLATION_LANGUAGE


def _attachment_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def _attachment_filename(value: str) -> str:
    return Path(value or "附件").name.strip().rstrip(". ") or "附件"


def _unique_attachment_filename(filename: str, used_names: set[str]) -> str:
    candidate = filename
    stem = Path(filename).stem or "附件"
    suffix = Path(filename).suffix
    counter = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    used_names.add(candidate.casefold())
    return candidate
