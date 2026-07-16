from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent
SVG_ICON = ROOT / "src" / "mailbox_manager" / "assets" / "app.svg"
ICNS_ICON = ROOT / "assets" / "app.icns"
SPEC_FILE = ROOT / "mailbox-manager-macos.spec"

_ICON_SPECS = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)

_MACOS_QT_FRAMEWORKS = frozenset(
    {
        "qtcore",
        "qtdbus",
        "qtgui",
        "qtsvg",
        "qtwidgets",
    }
)
_MACOS_QT_BINDINGS = frozenset(
    {
        "qtcore",
        "qtgui",
        "qtsvg",
        "qtwidgets",
    }
)


def should_include_macos_qt_payload(destination: str) -> bool:
    """Keep only Qt frameworks and Python bindings required by MailDesk."""

    normalized = destination.replace("\\", "/").casefold()
    marker = "pyside6/"
    if marker not in normalized:
        return True
    normalized = marker + normalized.rsplit(marker, 1)[1]
    parts = normalized.split("/")
    for part in parts:
        if part.endswith(".framework"):
            return part.removesuffix(".framework") in _MACOS_QT_FRAMEWORKS
    filename = parts[-1]
    if filename.endswith((".abi3.so", ".so")) and filename.startswith("qt"):
        module = filename.split(".", 1)[0]
        return module in _MACOS_QT_BINDINGS
    return True


def should_include_macos_qt_entry(destination: str, source: str) -> bool:
    """Filter both sides of a PyInstaller entry, including macOS symlinks."""

    return should_include_macos_qt_payload(destination) and should_include_macos_qt_payload(source)


def normalize_macos_arch(machine: str) -> str:
    normalized = machine.casefold().strip()
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    if normalized in {"x86_64", "amd64"}:
        return "x64"
    raise ValueError(f"不支持的 macOS 架构：{machine}")


def macos_asset_basename(version: str, machine: str) -> str:
    return f"MailDesk-v{version}-macos-{normalize_macos_arch(machine)}"


def _render_icon(renderer: QSvgRenderer, target: Path, size: int) -> None:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    if not image.save(str(target), "PNG"):
        raise RuntimeError(f"无法生成 macOS 图标资源：{target.name}")


def ensure_icns(source: Path = SVG_ICON, target: Path = ICNS_ICON) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("ICNS 图标只能在 macOS 上生成")
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError(f"无法读取 SVG 图标：{source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="maildesk-icon-") as temporary:
        iconset = Path(temporary) / "MailDesk.iconset"
        iconset.mkdir()
        for filename, size in _ICON_SPECS:
            _render_icon(renderer, iconset / filename, size)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(target)],
            check=True,
        )
    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError("iconutil 未生成有效的 ICNS 图标")


def build(*, clean: bool = False) -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("macOS .app 必须在真实 macOS 环境中构建")
    ensure_icns()
    environment = os.environ.copy()
    environment["MAILDESK_MAC_ARCH"] = platform.machine()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm"]
    if clean:
        command.append("--clean")
    command.append(str(SPEC_FILE))
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    output = ROOT / "dist" / "MailDesk.app"
    if not (output / "Contents" / "MacOS" / "MailDesk").is_file():
        raise RuntimeError("PyInstaller 未生成有效的 MailDesk.app")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MailDesk.app on macOS")
    parser.add_argument("--clean", action="store_true", help="清理 PyInstaller 缓存后构建")
    arguments = parser.parse_args()
    try:
        output = build(clean=arguments.clean)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    print(f"构建完成：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
