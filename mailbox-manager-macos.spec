from __future__ import annotations

import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

from build import should_include_qt_payload
from build_macos import should_include_macos_qt_entry

ROOT = Path(SPECPATH)
with (ROOT / "pyproject.toml").open("rb") as stream:
    VERSION = str(tomllib.load(stream)["project"]["version"])

datas = collect_data_files("certifi")
datas.append(
    (
        str(ROOT / "src" / "mailbox_manager" / "assets" / "app.svg"),
        "mailbox_manager/assets",
    )
)
hiddenimports = ["keyring.backends.macOS", "socks", "socksio"]

analysis = Analysis(
    [str(ROOT / "src" / "mailbox_manager" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "_brotli",
        "brotli",
        "h2",
        "hpack",
        "hyperframe",
        "outcome",
        "sortedcontainers",
        "tkinter",
        "trio",
        "pytest",
        "_pytest",
        "pytestqt",
        "pygments",
        "wsproto",
        "win32crypt",
        "zstandard",
    ],
    noarchive=False,
    optimize=1,
)
analysis.binaries = [
    entry
    for entry in analysis.binaries
    if should_include_qt_payload(entry[0])
    and should_include_macos_qt_entry(entry[0], entry[1])
]
analysis.datas = [
    entry
    for entry in analysis.datas
    if should_include_qt_payload(entry[0])
    and should_include_macos_qt_entry(entry[0], entry[1])
]
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MailDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
bundle_files = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="MailDesk",
)
application = BUNDLE(
    bundle_files,
    name="MailDesk.app",
    icon=str(ROOT / "assets" / "app.icns"),
    bundle_identifier="com.maildesk.app",
    info_plist={
        "CFBundleDisplayName": "MailDesk",
        "CFBundleName": "MailDesk",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    },
)
