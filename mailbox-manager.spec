from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

from build import should_include_qt_payload

ROOT = Path(SPECPATH)
MODE = os.environ.get("MAILDESK_BUILD_MODE", "onedir")
if MODE not in {"onefile", "onedir"}:
    raise ValueError("MAILDESK_BUILD_MODE must be onefile or onedir")

datas = collect_data_files("certifi")
datas.append(
    (
        str(ROOT / "src" / "mailbox_manager" / "assets" / "app.svg"),
        "mailbox_manager/assets",
    )
)
hiddenimports = ["win32timezone", "socks", "socksio"]

analysis = Analysis(
    [str(ROOT / "src" / "mailbox_manager" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest", "pytestqt", "pygments"],
    noarchive=False,
    optimize=1,
)
analysis.binaries = [
    entry for entry in analysis.binaries if should_include_qt_payload(entry[0])
]
analysis.datas = [
    entry for entry in analysis.datas if should_include_qt_payload(entry[0])
]
pyz = PYZ(analysis.pure)
common = dict(
    name="MailDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ROOT / "assets" / "app.ico"),
    version=str(ROOT / "assets" / "version_info.txt"),
    uac_admin=False,
)

if MODE == "onefile":
    executable = EXE(
        pyz,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        **common,
    )
else:
    executable = EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        **common,
    )
    bundle = COLLECT(
        executable,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=True,
        name="MailDesk",
    )
