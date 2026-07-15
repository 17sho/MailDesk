from __future__ import annotations

from build_macos import (
    macos_asset_basename,
    normalize_macos_arch,
    repair_qtwebengine_framework_destination,
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


def test_repairs_flattened_qtwebengine_framework_resources() -> None:
    broken = (
        "PySide6/Qt/lib/QtWebEngineCore.framework/Versions/Resources/"
        "Resources/icudtl.dat"
    )

    assert repair_qtwebengine_framework_destination(broken) == (
        "PySide6/Qt/lib/QtWebEngineCore.framework/Versions/A/Resources/icudtl.dat"
    )


def test_repairs_flattened_qtwebengine_framework_helper() -> None:
    broken = (
        "PySide6/Qt/lib/QtWebEngineCore.framework/Versions/Resources/Helpers/"
        "QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess"
    )

    assert repair_qtwebengine_framework_destination(broken) == (
        "PySide6/Qt/lib/QtWebEngineCore.framework/Versions/A/Helpers/"
        "QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess"
    )


def test_leaves_other_framework_destinations_unchanged() -> None:
    destination = "PySide6/Qt/lib/QtCore.framework/Versions/A/QtCore"

    assert repair_qtwebengine_framework_destination(destination) == destination


def test_macos_payload_filter_keeps_reader_frameworks_and_drops_large_extras() -> None:
    assert should_include_macos_qt_payload(
        "PySide6/Qt/lib/QtWebEngineCore.framework/Versions/A/QtWebEngineCore"
    )
    assert should_include_macos_qt_payload(
        "PySide6/Qt/lib/QtQuick.framework/Versions/A/QtQuick"
    )
    assert should_include_macos_qt_payload("PySide6/QtWebEngineWidgets.abi3.so")
    assert not should_include_macos_qt_payload(
        "PySide6/Qt/lib/QtMultimedia.framework/Versions/A/QtMultimedia"
    )
    assert not should_include_macos_qt_payload(
        "PySide6/Qt/lib/QtPdf.framework/Versions/A/QtPdf"
    )
    assert not should_include_macos_qt_payload("PySide6/Qt3DCore.abi3.so")
