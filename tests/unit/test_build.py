from __future__ import annotations

from pathlib import Path

import pytest

from build import ensure_icon, should_include_qt_payload, validate_mode
from build_macos import macos_asset_basename, normalize_macos_arch


def test_ensure_icon_renders_windows_ico_from_svg(tmp_path) -> None:
    source = tmp_path / "app.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        '<rect width="64" height="64" fill="#176b87"/></svg>',
        encoding="utf-8",
    )
    target = tmp_path / "app.ico"

    ensure_icon(source, target)

    assert target.read_bytes().startswith(b"\x00\x00\x01\x00")


def test_validate_mode_accepts_only_supported_pyinstaller_modes() -> None:
    assert validate_mode("onefile") == "onefile"
    assert validate_mode("onedir") == "onedir"


def test_windows_build_excludes_unused_qml_payload_and_keeps_webengine() -> None:
    assert not should_include_qt_payload(
        "PySide6/qml/QtQuick/Controls/FluentWinUI3/dark/images/very-long-name.png"
    )
    assert should_include_qt_payload("PySide6/QtWebEngineWidgets.pyd")
    assert should_include_qt_payload("PySide6/resources/qtwebengine_resources.pak")


def test_macos_release_names_normalize_native_architectures() -> None:
    assert normalize_macos_arch("arm64") == "arm64"
    assert normalize_macos_arch("x86_64") == "x64"
    assert macos_asset_basename("0.3.1", "arm64") == "MailDesk-v0.3.1-macos-arm64"
    assert macos_asset_basename("0.3.1", "x86_64") == "MailDesk-v0.3.1-macos-x64"
    with pytest.raises(ValueError, match="不支持"):
        normalize_macos_arch("ppc64")


def test_macos_spec_builds_an_app_bundle_with_keychain_backend() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = (root / "mailbox-manager-macos.spec").read_text(encoding="utf-8")

    assert "application = BUNDLE(" in spec
    assert 'bundle_identifier="com.maildesk.app"' in spec
    assert '"keyring.backends.macOS"' in spec
    assert '"LSMinimumSystemVersion": "13.0"' in spec


def test_pyinstaller_spec_embeds_release_version_resource() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = (root / "mailbox-manager.spec").read_text(encoding="utf-8")
    version_info = (root / "assets" / "version_info.txt").read_text(
        encoding="utf-8"
    )

    assert 'version=str(ROOT / "assets" / "version_info.txt")' in spec
    assert "filevers=(0, 3, 3, 0)" in version_info
    assert "prodvers=(0, 3, 3, 0)" in version_info
    assert "StringStruct(u'FileVersion', u'0.3.3.0')" in version_info
    assert "StringStruct(u'ProductVersion', u'0.3.3.0')" in version_info
