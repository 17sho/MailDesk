from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

from mailbox_manager.app import (
    acquire_instance_lock,
    report_update_health,
    schedule_startup_probe,
)
from mailbox_manager.config import AppPaths


def test_app_paths_keep_runtime_data_outside_source_tree(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    paths = AppPaths.for_current_user(system="Windows", home=tmp_path)

    assert paths.root == tmp_path / "MailDesk"
    assert paths.database.parent == paths.root
    assert paths.key_file.name.endswith(".dpapi")
    assert paths.logs.parent == paths.root
    assert paths.updates == paths.root / "updates"


def test_macos_paths_use_application_support_and_keychain_marker(tmp_path) -> None:
    paths = AppPaths.for_current_user(system="Darwin", home=tmp_path)

    assert paths.root == tmp_path / "Library" / "Application Support" / "MailDesk"
    assert paths.key_file.name == "master.key.keychain"


def test_update_health_marker_is_restricted_to_update_staging(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = AppPaths.for_current_user()
    paths.ensure()
    token = "a" * 32
    marker = paths.updates / (".health-" + "b" * 32)
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_TOKEN", token)
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_FILE", str(marker))

    assert report_update_health(paths) is True
    assert marker.read_text(encoding="utf-8") == token
    assert "MAILDESK_UPDATE_HEALTH_TOKEN" not in os.environ

    outside = tmp_path / "outside-health"
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_TOKEN", token)
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_FILE", str(outside))
    with pytest.raises(ValueError, match="路径无效"):
        report_update_health(paths)
    assert not outside.exists()


def test_instance_lock_allows_only_one_process_per_data_directory(tmp_path) -> None:
    paths = AppPaths(
        root=tmp_path / "MailDesk",
        database=tmp_path / "MailDesk" / "maildesk.db",
        key_file=tmp_path / "MailDesk" / "master.key.dpapi",
        logs=tmp_path / "MailDesk" / "logs",
        eml=tmp_path / "MailDesk" / "eml",
    )

    first = acquire_instance_lock(paths)
    assert first is not None
    try:
        assert acquire_instance_lock(paths) is None
    finally:
        first.unlock()

    replacement = acquire_instance_lock(paths)
    assert replacement is not None
    replacement.unlock()


def test_webengine_startup_probe_exercises_reader_and_quits(monkeypatch) -> None:
    callbacks: list[tuple[int, object]] = []
    window = Mock()
    logger = Mock()
    monkeypatch.setenv("MAILDESK_STARTUP_PROBE", "webengine")
    monkeypatch.setattr(
        "mailbox_manager.app.QTimer.singleShot",
        lambda delay, callback: callbacks.append((delay, callback)),
    )

    assert schedule_startup_probe(window, logger) is True
    assert "MAILDESK_STARTUP_PROBE" not in os.environ
    assert callbacks[0][0] == 0

    callbacks[0][1]()  # type: ignore[operator]

    window.message_body.setPlainText.assert_called_once_with(
        "MailDesk packaged WebEngine probe"
    )
    logger.info.assert_called_once_with("MailDesk WebEngine startup probe passed")
    assert callbacks[1][0] == 250
    assert callbacks[1][1] == window.request_quit
