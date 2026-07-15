from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

DEFERRED_MIGRATION_MARKER = ".maildesk-migrated-to"


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    database: Path
    key_file: Path
    logs: Path
    eml: Path
    update_root: Path | None = None

    @property
    def updates(self) -> Path:
        """Private staging area used by the verified-release updater."""

        return self.update_root or self.root / "updates"

    @classmethod
    def for_current_user(
        cls,
        *,
        system: str | None = None,
        home: Path | None = None,
        executable_path: Path | None = None,
        frozen: bool | None = None,
    ) -> AppPaths:
        system = system or platform.system()
        home = Path.home() if home is None else Path(home)
        explicit_root = os.environ.get("MAILDESK_DATA_DIR")
        if explicit_root:
            root = Path(explicit_root).expanduser()
            update_root = root / "updates"
        else:
            is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
            if is_frozen:
                executable = Path(executable_path or sys.executable).resolve()
                container = _application_container(executable, system)
                root = container / "MailDesk Data"
                update_root = container / ".maildesk-update"
            else:
                root = legacy_data_root(system=system, home=home)
                update_root = root / "updates"
        key_name = "master.key.dpapi" if system == "Windows" else "master.key.keychain"
        return cls(
            root=root,
            database=root / "maildesk.db",
            key_file=root / key_name,
            logs=root / "logs",
            eml=root / "eml",
            update_root=update_root,
        )

    def ensure(self) -> None:
        for directory in (self.root, self.logs, self.eml, self.updates):
            directory.mkdir(parents=True, exist_ok=True)


def legacy_data_root(*, system: str, home: Path) -> Path:
    """Return the pre-portable MailDesk data directory for migration only."""

    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
        return base / "MailDesk"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "MailDesk"
    data_home = os.environ.get("XDG_DATA_HOME")
    return (Path(data_home) if data_home else home / ".local" / "share") / "MailDesk"


def migrate_legacy_data(
    paths: AppPaths,
    *,
    system: str | None = None,
    home: Path | None = None,
    defer_legacy_cleanup: bool = False,
) -> bool:
    """Atomically move known legacy user data beside the installed application.

    Update payloads and stale process locks are deliberately not migrated.  The old
    directory is removed only after the copied SQLite database passes ``quick_check``.
    """

    system = system or platform.system()
    home = Path.home() if home is None else Path(home)
    legacy = legacy_data_root(system=system, home=home).resolve()
    destination = paths.root.resolve()
    if legacy == destination or not legacy.is_dir():
        return False
    if paths.database.exists():
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.migrating-{uuid4().hex}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        for filename in ("maildesk.db", "master.key.dpapi", "master.key.keychain"):
            source = legacy / filename
            if source.is_file():
                shutil.copy2(source, temporary / filename)
        for directory_name in ("eml", "logs"):
            source = legacy / directory_name
            if source.is_dir():
                shutil.copytree(source, temporary / directory_name)
        migrated_database = temporary / "maildesk.db"
        if migrated_database.is_file():
            # sqlite3.Connection.__exit__ commits/rolls back but does not close the
            # native handle.  Windows refuses to rename the containing directory
            # while that handle is still open, so close it explicitly.
            with closing(sqlite3.connect(migrated_database)) as connection:
                result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or str(result[0]).casefold() != "ok":
                raise RuntimeError("旧版 MailDesk 数据库完整性校验失败")
        if destination.exists():
            if any(destination.iterdir()):
                raise RuntimeError("便携数据目录已存在且不为空，未自动覆盖")
            destination.rmdir()
        temporary.replace(destination)
        if defer_legacy_cleanup:
            (legacy / DEFERRED_MIGRATION_MARKER).write_text(
                str(destination), encoding="utf-8"
            )
        else:
            shutil.rmtree(legacy)
        return True
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def cleanup_deferred_legacy_data(
    paths: AppPaths,
    *,
    system: str | None = None,
    home: Path | None = None,
) -> bool:
    """Delete a legacy profile only when its migration marker targets these paths."""

    system = system or platform.system()
    home = Path.home() if home is None else Path(home)
    legacy = legacy_data_root(system=system, home=home).resolve()
    destination = paths.root.resolve()
    marker = legacy / DEFERRED_MIGRATION_MARKER
    if legacy == destination or not marker.is_file() or not paths.database.is_file():
        return False
    try:
        marked_destination = Path(marker.read_text(encoding="utf-8").strip()).resolve()
    except (OSError, ValueError):
        return False
    if marked_destination != destination:
        return False
    with closing(sqlite3.connect(paths.database)) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
    if result is None or str(result[0]).casefold() != "ok":
        raise RuntimeError("便携 MailDesk 数据库完整性校验失败，未清理旧数据")
    shutil.rmtree(legacy)
    return True


def _application_container(executable: Path, system: str) -> Path:
    if system == "Darwin":
        for parent in executable.parents:
            if parent.name.casefold().endswith(".app"):
                return parent.parent
        return executable.parent
    if system == "Windows" and (executable.parent / "_internal").is_dir():
        return executable.parent.parent
    return executable.parent
