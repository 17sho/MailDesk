from __future__ import annotations

import logging
import os
import platform
import re
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QLockFile, QTimer, QTranslator
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from mailbox_manager import __version__
from mailbox_manager.config import AppPaths
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.gui.modern_style import install_modern_style
from mailbox_manager.observability.logging_config import configure_logging
from mailbox_manager.services.audit_report import AuditReportService
from mailbox_manager.services.automation_service import AutomationService
from mailbox_manager.services.client_factory import ProtocolClientFactory
from mailbox_manager.services.eml_store import EmlStore
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.services.send_service import SendService
from mailbox_manager.services.throttle import ComplianceThrottle
from mailbox_manager.services.update_service import UpdateService, consume_install_result
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    AuditRepository,
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

_TRANSLATORS: list[QTranslator] = []
_UPDATE_HEALTH_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def create_main_window(paths: AppPaths | None = None) -> MainWindow:
    paths = paths or AppPaths.for_current_user()
    paths.ensure()
    database = Database(paths.database)
    database.initialize()
    cipher = CredentialCipher.load_or_create(paths.key_file)
    accounts = AccountRepository(database, cipher)
    messages = MessageRepository(database)
    settings = SettingsRepository(database)
    throttle_values = settings.get("enterprise_ui", {})
    throttle_values = throttle_values if isinstance(throttle_values, dict) else {}
    throttle = ComplianceThrottle(
        max_concurrency_per_identity=int(throttle_values.get("ip_concurrency", 2)),
        min_account_interval=float(throttle_values.get("login_interval_min", 0)),
        max_account_interval=float(throttle_values.get("login_interval_max", 0)),
    )
    eml_store = EmlStore(paths.eml)
    audits = AuditRepository(database)
    proxies = ProxyRepository(database, cipher)
    rules = AutomationRuleRepository(database)
    webhooks = WebhookRepository(database, cipher)
    automation = AutomationService(rules, webhooks, settings, audits)
    fetch_service = FetchService(
        accounts,
        messages,
        client_factory=ProtocolClientFactory(proxies, settings),
        eml_store=eml_store,
        audit_repository=audits,
        throttle=throttle,
        automation=automation,
    )
    return MainWindow(
        accounts,
        messages,
        fetch_service,
        groups=GroupRepository(database),
        tags=TagRepository(database),
        proxies=proxies,
        schedules=ScheduleRepository(database),
        settings=settings,
        webhooks=webhooks,
        rules=rules,
        statistics=StatisticsRepository(database),
        audit_reports=AuditReportService(audits, paths.logs),
        eml_store=eml_store,
        send_service=SendService(audit_repository=audits),
        update_service=UpdateService(
            current_version=__version__,
            updates_dir=paths.updates,
        ),
    )


def configure_ui_font(application: QApplication) -> None:
    if platform.system() == "Darwin":
        application.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        )
        application.setProperty("maildeskBaseFontFamily", application.font().family())
        return
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for filename in ("msyh.ttc", "msyhbd.ttc"):
        font_path = windows_fonts / filename
        if not font_path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                application.setFont(QFont(families[0], 9))
                application.setProperty("maildeskBaseFontFamily", families[0])
                return
    application.setFont(QFont("Microsoft YaHei UI", 9))
    application.setProperty("maildeskBaseFontFamily", application.font().family())


def configure_translations(application: QApplication) -> bool:
    translator = QTranslator(application)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    loaded = translator.load(QLocale("zh_CN"), "qtbase", "_", translations_path)
    if not loaded:
        loaded = translator.load(str(Path(translations_path) / "qtbase_zh_CN.qm"))
    if loaded:
        application.installTranslator(translator)
        _TRANSLATORS.append(translator)
    return loaded


def report_update_health(paths: AppPaths) -> bool:
    """Acknowledge a successful updater restart without trusting arbitrary paths."""

    token = os.environ.pop("MAILDESK_UPDATE_HEALTH_TOKEN", "").strip()
    raw_path = os.environ.pop("MAILDESK_UPDATE_HEALTH_FILE", "").strip()
    if not token and not raw_path:
        return False
    if not _UPDATE_HEALTH_TOKEN_PATTERN.fullmatch(token) or not raw_path:
        raise ValueError("更新健康检查参数无效")
    health_path = Path(raw_path).resolve()
    updates_root = paths.updates.resolve()
    if (
        os.path.normcase(str(health_path.parent))
        != os.path.normcase(str(updates_root))
        or not health_path.name.startswith(".health-")
    ):
        raise ValueError("更新健康检查路径无效")
    updates_root.mkdir(parents=True, exist_ok=True)
    temporary = health_path.with_name(f"{health_path.name}.{os.getpid()}.tmp")
    temporary.write_text(token, encoding="utf-8", newline="")
    temporary.replace(health_path)
    return True


def acquire_instance_lock(paths: AppPaths) -> QLockFile | None:
    """Prevent concurrent processes from sharing the same database and updater."""

    paths.root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(paths.root / ".instance.lock"))
    if not lock.tryLock(100):
        return None
    return lock


def schedule_startup_probe(
    window: MainWindow,
    logger: logging.Logger,
) -> bool:
    """Exercise packaged subsystems that a window-only smoke test cannot cover."""

    probe = os.environ.pop("MAILDESK_STARTUP_PROBE", "").strip().casefold()
    if not probe:
        return False
    if probe != "webengine":
        logger.warning("Unknown MailDesk startup probe: %s", probe)
        return False

    def run_probe() -> None:
        window.message_body.setPlainText("MailDesk packaged WebEngine probe")
        logger.info("MailDesk WebEngine startup probe passed")
        QTimer.singleShot(250, window.request_quit)

    QTimer.singleShot(0, run_probe)
    return True


def run() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("MailDesk")
    application.setOrganizationName("MailDesk")
    install_modern_style(application)
    configure_translations(application)
    configure_ui_font(application)
    icon_path = Path(__file__).parent / "assets" / "app.svg"
    if icon_path.exists():
        application.setWindowIcon(QIcon(str(icon_path)))
    paths = AppPaths.for_current_user()
    logger = configure_logging(paths.logs)
    instance_lock = acquire_instance_lock(paths)
    if instance_lock is None:
        logger.warning("MailDesk startup blocked because another instance is active")
        QMessageBox.information(
            None,
            "MailDesk 已在运行",
            "检测到另一个 MailDesk 实例正在运行。\n\n"
            "请从任务栏或系统托盘打开已有窗口；更新前请先退出其他实例。",
        )
        return 0
    try:
        window = create_main_window(paths)
    except Exception:
        instance_lock.unlock()
        logger.exception("应用初始化失败")
        QMessageBox.critical(None, "MailDesk 启动失败", "无法初始化安全存储，请查看本地日志。")
        return 1
    logger.info("MailDesk started")
    if QSystemTrayIcon.isSystemTrayAvailable():
        application.setQuitOnLastWindowClosed(False)
        tray = QSystemTrayIcon(application.windowIcon(), application)
        tray.setToolTip("MailDesk · 邮箱工作台")
        tray_menu = QMenu()
        show_action = tray_menu.addAction("显示主窗口")
        quit_action = tray_menu.addAction("退出")
        show_action.triggered.connect(window.restore_from_tray)
        quit_action.triggered.connect(window.request_quit)
        tray.activated.connect(
            lambda reason: window.restore_from_tray()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
        tray.setContextMenu(tray_menu)
        window.enable_tray(tray)
        tray.show()
    window.show()
    schedule_startup_probe(window, logger)
    try:
        if report_update_health(paths):
            logger.info("MailDesk update startup health check passed")
    except Exception:
        logger.exception("Unable to report update startup health")
    install_result = consume_install_result(paths.updates)
    if install_result and install_result != "success":
        logger.error("Previous MailDesk update result: %s", install_result)
        QMessageBox.warning(
            window,
            "自动更新已回滚",
            "上一次自动更新未能安全启动，新版本已停止安装并恢复旧版本。\n"
            "您可以继续使用当前版本，并稍后重新检查更新。",
        )
    code = application.exec()
    instance_lock.unlock()
    logging.shutdown()
    return code
