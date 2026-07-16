from __future__ import annotations

from build_macos import (
    macos_asset_basename,
    normalize_macos_arch,
    should_include_macos_qt_entry,
    should_include_macos_qt_payload,
)


def test_normalizes_supported_macos_architectures() -> None:
    assert normalize_macos_arch("x86_64") == "x64"
    assert normalize_macos_arch("AMD64") == "x64"
    assert normalize_macos_arch("arm64") == "arm64"
    assert normalize_macos_arch("aarch64") == "arm64"


def test_names_native_macos_release_assets() -> None:
    assert macos_asset_basename("1.2.3", "x86_64") == "MailDesk-v1.2.3-macos-x64"
    assert macos_asset_basename("1.2.3", "arm64") == "MailDesk-v1.2.3-macos-arm64"


def test_macos_payload_filter_drops_chromium_and_keeps_qt_widgets() -> None:
    assert not should_include_macos_qt_payload(
        "PySide6/Qt/lib/QtWebEngineCore.framework/Versions/A/QtWebEngineCore"
    )
    assert not should_include_macos_qt_payload(
        "PySide6/Qt/lib/QtQuick.framework/Versions/A/QtQuick"
    )
    assert should_include_macos_qt_payload("PySide6/Qt/lib/QtDBus.framework/Versions/A/QtDBus")
    assert not should_include_macos_qt_payload("PySide6/QtWebEngineWidgets.abi3.so")
    assert should_include_macos_qt_payload("PySide6/QtWidgets.abi3.so")
    assert not should_include_macos_qt_payload(
        "PySide6/Qt/lib/QtCharts.framework/Versions/A/QtCharts"
    )
    assert not should_include_macos_qt_payload("PySide6/QtCharts.abi3.so")
    assert not should_include_macos_qt_payload(
        "PySide6/Qt/lib/QtMultimedia.framework/Versions/A/QtMultimedia"
    )
    assert not should_include_macos_qt_payload("PySide6/Qt/lib/QtPdf.framework/Versions/A/QtPdf")
    assert not should_include_macos_qt_payload("PySide6/Qt3DCore.abi3.so")


def test_macos_payload_filter_checks_absolute_paths_and_symlink_targets() -> None:
    quick = "/opt/python/site-packages/PySide6/Qt/lib/QtQuick.framework/Versions/A/QtQuick"
    widgets = "/opt/python/site-packages/PySide6/Qt/lib/QtWidgets.framework/Versions/A/QtWidgets"

    assert not should_include_macos_qt_payload(quick)
    assert should_include_macos_qt_payload(widgets)
    assert not should_include_macos_qt_entry("QtQuick", quick)
    assert should_include_macos_qt_entry("QtWidgets", widgets)
