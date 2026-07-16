from __future__ import annotations

import os
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from mailbox_manager.app import create_main_window
from mailbox_manager.config import AppPaths
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.services.update_service import (
    InstallMode,
    ReleaseAsset,
    ReleaseInfo,
    StagedUpdate,
    UpdateInfo,
)
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import SettingsRepository
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


class FakeUpdateService:
    current_version = "0.3.0"

    def __init__(self) -> None:
        self.created_with: StagedUpdate | None = None
        self.launched_plan: object | None = None
        self.check_result: UpdateInfo | None = None

    def check_for_update(self) -> UpdateInfo | None:
        return self.check_result

    def discard_staged_update(self, staged: StagedUpdate) -> None:
        self.created_with = staged

    def create_installer_plan(self, staged: StagedUpdate) -> object:
        self.created_with = staged
        return object()

    def launch_installer(self, plan: object) -> None:
        self.launched_plan = plan


class BlockingInstallService(FakeUpdateService):
    def __init__(self) -> None:
        super().__init__()
        self.install_started = threading.Event()
        self.allow_install = threading.Event()

    def create_installer_plan(self, staged: StagedUpdate) -> object:
        self.install_started.set()
        if not self.allow_install.wait(timeout=5):
            raise TimeoutError("test installer was not released")
        return super().create_installer_plan(staged)


def _window(qtbot, tmp_path: Path) -> tuple[MainWindow, SettingsRepository]:
    database = Database(tmp_path / "update-gui.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"U" * 32))
    settings = SettingsRepository(database)
    window = MainWindow(
        accounts,
        MessageRepository(database),
        settings=settings,
    )
    window._update_service = FakeUpdateService()  # type: ignore[assignment]
    window.check_updates_action.setEnabled(True)
    qtbot.addWidget(window)
    window.show()
    return window, settings


def _update_info(mode: InstallMode = InstallMode.ONEFILE) -> UpdateInfo:
    filename = f"MailDesk-v0.4.0-windows-x64-{mode.value}.zip"
    asset = None
    if mode is not InstallMode.SOURCE:
        asset = ReleaseAsset(
            name=filename,
            download_url=f"https://github.com/17sho/MailDesk/releases/download/v0.4.0/{filename}",
            size=2048,
            digest="sha256:" + "a" * 64,
        )
    release = ReleaseInfo(
        version="0.4.0",
        tag_name="v0.4.0",
        name="MailDesk v0.4.0",
        notes="## 新功能\n\n- 后台更新",
        page_url="https://github.com/17sho/MailDesk/releases/tag/v0.4.0",
        published_at="2026-07-15T00:00:00Z",
        assets=(asset,) if asset is not None else (),
    )
    return UpdateInfo(
        current_version="0.3.0",
        release=release,
        install_mode=mode,
        asset=asset,
        checksum_asset=None,
    )


def test_available_update_shows_toolbar_button_and_popup(qtbot, tmp_path) -> None:
    window, _settings = _window(qtbot, tmp_path)

    window._on_update_check_result(_update_info(), None)

    assert window.update_tool_button.isVisible()
    assert window.update_tool_button.text() == "更新"
    assert window._update_dialog is not None
    assert window._update_dialog.isVisible()
    assert window._update_dialog.latest_version == "0.4.0"


def test_application_composition_enables_startup_update_checks(qtbot, tmp_path) -> None:
    root = tmp_path / "MailDesk"
    paths = AppPaths(
        root=root,
        database=root / "maildesk.db",
        key_file=root / "master.key.dpapi",
        logs=root / "logs",
        eml=root / "eml",
    )

    window = create_main_window(paths)
    qtbot.addWidget(window)
    window._startup_update_timer.stop()

    assert window._update_service is not None
    assert window._update_service.current_version == "0.4.1"
    assert window._update_service.updates_dir == paths.updates
    assert window.check_updates_action.isEnabled()


def test_skipped_version_suppresses_automatic_prompt(qtbot, tmp_path) -> None:
    window, settings = _window(qtbot, tmp_path)
    settings.set("skipped_update_version", "0.4.0")

    window._on_update_check_result(_update_info(), None)

    assert window.update_tool_button.isHidden()
    assert window._update_dialog is None


def test_skip_action_persists_version_and_hides_button(qtbot, tmp_path) -> None:
    window, settings = _window(qtbot, tmp_path)
    window._on_update_check_result(_update_info(), None)

    window._skip_update_version("v0.4.0")

    assert settings.get("skipped_update_version") == "0.4.0"
    assert window.update_tool_button.isHidden()


def test_background_progress_and_ready_state_update_toolbar(qtbot, tmp_path) -> None:
    window, _settings = _window(qtbot, tmp_path)
    update = _update_info()
    window._on_update_check_result(update, None)
    window._update_operation_id = "operation-1"
    window._update_download_identity = window._update_identity(update)

    window._on_update_download_progress("operation-1", 1024, 2048)

    assert window.update_tool_button.text() == "更新 50%"
    assert window.update_tool_button.property("state") == "downloading"

    staged = StagedUpdate(update, tmp_path / "stage", tmp_path / "stage" / "MailDesk.exe")
    window._on_update_download_result("operation-1", staged, None)

    assert window.update_tool_button.text() == "重启更新"
    assert window.update_tool_button.property("state") == "ready"
    assert window._update_dialog is not None
    assert window._update_dialog.primary_button.text() == "重启并安装"


def test_update_progress_button_remains_visible_in_compact_toolbar(qtbot, tmp_path) -> None:
    window, _settings = _window(qtbot, tmp_path)
    window.resize(1080, 680)
    window._set_update_button_state("downloading", 48)
    qtbot.wait(10)

    top_left = window.update_tool_button.mapTo(
        window.main_toolbar,
        window.update_tool_button.rect().topLeft(),
    )
    right_edge = top_left.x() + window.update_tool_button.width()

    assert window.update_toolbar_action.isVisible()
    assert window.update_tool_button.isVisible()
    assert window.update_tool_button.text() == "更新 48%"
    assert right_edge <= window.main_toolbar.width()


def test_install_requires_final_confirmation_then_launches_helper(
    qtbot, tmp_path, monkeypatch
) -> None:
    window, _settings = _window(qtbot, tmp_path)
    service = window._update_service
    assert isinstance(service, FakeUpdateService)
    update = _update_info()
    service.check_result = update
    staged = StagedUpdate(update, tmp_path / "stage", tmp_path / "stage" / "MailDesk.exe")
    window._update_info = update
    window._staged_update = staged
    window._update_download_identity = window._update_identity(update)
    window._show_update_dialog()
    quit_requested: list[bool] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(window, "request_quit", lambda: quit_requested.append(True))

    window._confirm_update_install("0.4.0")
    qtbot.waitUntil(lambda: service.launched_plan is not None, timeout=1500)
    qtbot.waitUntil(lambda: quit_requested == [True], timeout=1500)

    assert service.created_with is staged
    assert service.launched_plan is not None
    assert quit_requested == [True]


def test_install_file_verification_does_not_block_the_gui(
    qtbot, tmp_path, monkeypatch
) -> None:
    window, _settings = _window(qtbot, tmp_path)
    service = BlockingInstallService()
    window._update_service = service  # type: ignore[assignment]
    update = _update_info()
    service.check_result = update
    staged = StagedUpdate(update, tmp_path / "stage", tmp_path / "stage" / "MailDesk.exe")
    window._update_info = update
    window._staged_update = staged
    window._update_download_identity = window._update_identity(update)
    window._show_update_dialog()
    assert window._update_dialog is not None
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    quit_requested: list[bool] = []
    monkeypatch.setattr(window, "request_quit", lambda: quit_requested.append(True))

    window._confirm_update_install("0.4.0")
    qtbot.waitUntil(service.install_started.is_set, timeout=1500)
    gui_callback_ran: list[bool] = []
    QTimer.singleShot(0, lambda: gui_callback_ran.append(True))
    qtbot.waitUntil(lambda: bool(gui_callback_ran), timeout=500)

    assert window._update_install_worker is not None
    assert window._update_dialog.primary_button.text() == "正在准备安装…"
    assert "安装助手接管" in window._update_dialog.progress_detail_label.text()
    assert quit_requested == []

    service.allow_install.set()
    qtbot.waitUntil(lambda: service.launched_plan is not None, timeout=1500)
    qtbot.waitUntil(lambda: quit_requested == [True], timeout=1500)


def test_stale_download_result_cannot_replace_active_update(qtbot, tmp_path) -> None:
    window, _settings = _window(qtbot, tmp_path)
    old_update = _update_info()
    new_release = ReleaseInfo(
        version="0.5.0",
        tag_name="v0.5.0",
        name="MailDesk v0.5.0",
        notes="newer",
        page_url="https://github.com/17sho/MailDesk/releases/tag/v0.5.0",
        published_at=None,
        assets=(),
    )
    new_update = UpdateInfo(
        current_version="0.3.0",
        release=new_release,
        install_mode=InstallMode.SOURCE,
        asset=None,
        checksum_asset=None,
    )
    window._update_info = new_update
    window._update_operation_id = "new-operation"
    window._update_download_identity = window._update_identity(new_update)
    old_staged = StagedUpdate(
        old_update,
        tmp_path / "old-stage",
        tmp_path / "old-stage" / "MailDesk.exe",
    )

    window._on_update_download_result("old-operation", old_staged, None)

    assert window._staged_update is None
    assert window._update_info is new_update


def test_install_does_not_repeat_network_check_after_signed_download(
    qtbot, tmp_path, monkeypatch
) -> None:
    window, _settings = _window(qtbot, tmp_path)
    service = window._update_service
    assert isinstance(service, FakeUpdateService)
    update = _update_info()
    staged = StagedUpdate(
        update,
        tmp_path / "verified-stage",
        tmp_path / "verified-stage" / "MailDesk.exe",
    )
    window._update_info = update
    window._staged_update = staged
    window._update_download_identity = window._update_identity(update)
    window._show_update_dialog()
    service.check_result = None
    quit_requested: list[bool] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(window, "request_quit", lambda: quit_requested.append(True))

    window._confirm_update_install("0.4.0")
    qtbot.waitUntil(lambda: service.launched_plan is not None, timeout=1500)
    qtbot.waitUntil(lambda: quit_requested == [True], timeout=1500)

    assert service.created_with is staged
    assert service.launched_plan is not None
    assert window._staged_update is staged
