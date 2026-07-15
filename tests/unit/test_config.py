from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

from mailbox_manager.app import (
    acquire_instance_lock,
    report_update_health,
    schedule_startup_probe,
)
from mailbox_manager.config import (
    AppPaths,
    cleanup_deferred_legacy_data,
    migrate_legacy_data,
)


def test_app_paths_keep_runtime_data_outside_source_tree(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    paths = AppPaths.for_current_user(system="Windows", home=tmp_path)

    assert paths.root == tmp_path / "MailDesk"
    assert paths.database.parent == paths.root
    assert paths.key_file.name.endswith(".dpapi")
    assert paths.logs.parent == paths.root
    assert paths.updates == paths.root / "updates"


def test_frozen_onedir_keeps_data_and_updates_beside_program(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MAILDESK_DATA_DIR", raising=False)
    executable = tmp_path / "portable" / "MailDesk" / "MailDesk.exe"
    executable.parent.mkdir(parents=True)
    (executable.parent / "_internal").mkdir()
    executable.touch()

    paths = AppPaths.for_current_user(
        system="Windows",
        home=tmp_path,
        executable_path=executable,
        frozen=True,
    )

    assert paths.root == tmp_path / "portable" / "MailDesk Data"
    assert paths.updates == tmp_path / "portable" / ".maildesk-update"
    assert not paths.root.is_relative_to(executable.parent)


def test_frozen_onefile_keeps_data_beside_executable(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MAILDESK_DATA_DIR", raising=False)
    executable = tmp_path / "portable" / "MailDesk.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()

    paths = AppPaths.for_current_user(
        system="Windows",
        home=tmp_path,
        executable_path=executable,
        frozen=True,
    )

    assert paths.root == executable.parent / "MailDesk Data"
    assert paths.updates == executable.parent / ".maildesk-update"


def test_frozen_macos_keeps_data_beside_app_bundle(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MAILDESK_DATA_DIR", raising=False)
    executable = tmp_path / "Applications" / "MailDesk.app" / "Contents" / "MacOS" / "MailDesk"
    executable.parent.mkdir(parents=True)
    executable.touch()

    paths = AppPaths.for_current_user(
        system="Darwin",
        home=tmp_path,
        executable_path=executable,
        frozen=True,
    )

    assert paths.root == tmp_path / "Applications" / "MailDesk Data"
    assert paths.updates == tmp_path / "Applications" / ".maildesk-update"


def test_migrates_only_user_data_and_removes_legacy_updates(tmp_path, monkeypatch) -> None:
    import sqlite3
    from contextlib import closing

    legacy_base = tmp_path / "legacy-local"
    monkeypatch.setenv("LOCALAPPDATA", str(legacy_base))
    legacy = legacy_base / "MailDesk"
    legacy.mkdir(parents=True)
    with closing(sqlite3.connect(legacy / "maildesk.db")) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('kept')")
        connection.commit()
    (legacy / "master.key.dpapi").write_bytes(b"protected-key")
    (legacy / "eml").mkdir()
    (legacy / "eml" / "message.eml").write_text("message", encoding="utf-8")
    (legacy / "logs").mkdir()
    (legacy / "logs" / "app.log").write_text("old log", encoding="utf-8")
    (legacy / "updates").mkdir()
    (legacy / "updates" / "large.zip").write_bytes(b"not migrated")
    portable = tmp_path / "portable"
    paths = AppPaths(
        root=portable / "MailDesk Data",
        database=portable / "MailDesk Data" / "maildesk.db",
        key_file=portable / "MailDesk Data" / "master.key.dpapi",
        logs=portable / "MailDesk Data" / "logs",
        eml=portable / "MailDesk Data" / "eml",
        update_root=portable / ".maildesk-update",
    )

    assert migrate_legacy_data(paths, system="Windows", home=tmp_path) is True

    assert paths.database.is_file()
    assert paths.key_file.read_bytes() == b"protected-key"
    assert (paths.eml / "message.eml").is_file()
    assert not (paths.root / "updates").exists()
    assert not legacy.exists()


def test_defers_legacy_cleanup_until_old_updater_health_handoff_finishes(
    tmp_path, monkeypatch
) -> None:
    import sqlite3
    from contextlib import closing

    legacy_base = tmp_path / "legacy-local"
    monkeypatch.setenv("LOCALAPPDATA", str(legacy_base))
    legacy = legacy_base / "MailDesk"
    legacy.mkdir(parents=True)
    with closing(sqlite3.connect(legacy / "maildesk.db")) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.commit()
    portable = tmp_path / "portable"
    paths = AppPaths(
        root=portable / "MailDesk Data",
        database=portable / "MailDesk Data" / "maildesk.db",
        key_file=portable / "MailDesk Data" / "master.key.dpapi",
        logs=portable / "MailDesk Data" / "logs",
        eml=portable / "MailDesk Data" / "eml",
        update_root=portable / ".maildesk-update",
    )

    assert migrate_legacy_data(
        paths,
        system="Windows",
        home=tmp_path,
        defer_legacy_cleanup=True,
    )
    assert legacy.is_dir()
    assert cleanup_deferred_legacy_data(
        paths, system="Windows", home=tmp_path
    )
    assert not legacy.exists()


def test_update_health_accepts_one_legacy_updater_handoff(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "legacy-local"))
    portable = tmp_path / "portable"
    paths = AppPaths(
        root=portable / "MailDesk Data",
        database=portable / "MailDesk Data" / "maildesk.db",
        key_file=portable / "MailDesk Data" / "master.key.dpapi",
        logs=portable / "MailDesk Data" / "logs",
        eml=portable / "MailDesk Data" / "eml",
        update_root=portable / ".maildesk-update",
    )
    token = "c" * 32
    marker = tmp_path / "legacy-local" / "MailDesk" / "updates" / (".health-" + "d" * 32)
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_TOKEN", token)
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_FILE", str(marker))

    assert report_update_health(paths) is True
    assert marker.read_text(encoding="utf-8") == token


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
