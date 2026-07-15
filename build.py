from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent
SVG_ICON = ROOT / "src" / "mailbox_manager" / "assets" / "app.svg"
ICO_ICON = ROOT / "assets" / "app.ico"
SPEC_FILE = ROOT / "mailbox-manager.spec"
WEBENGINE_LOCALES = frozenset(
    {"en-gb.pak", "en-us.pak", "zh-cn.pak", "zh-tw.pak"}
)


def should_include_qt_payload(destination: str) -> bool:
    """Drop QtWebEngine development/debug payloads that the reader never uses."""

    normalized = destination.replace("\\", "/").casefold()
    filename = normalized.rsplit("/", 1)[-1]
    # MailDesk uses Qt Widgets, Qt Charts and QtWebEngineWidgets, not Qt Quick.
    # Besides adding hundreds of megabytes, the QML style image hierarchy can
    # exceed Windows MAX_PATH inside the verified updater staging directory.
    if "pyside6/qml/" in normalized:
        return False
    if "pyside6/resources/" in normalized and (
        ".debug." in filename
        or filename.startswith("qtwebengine_devtools_resources")
    ):
        return False
    if "pyside6/translations/qtwebengine_locales/" in normalized:
        return filename in WEBENGINE_LOCALES
    return True


def validate_mode(value: str) -> str:
    if value not in {"onefile", "onedir"}:
        raise ValueError("mode 必须是 onefile 或 onedir")
    return value


def ensure_icon(source: Path = SVG_ICON, target: Path = ICO_ICON) -> None:
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError(f"无法读取 SVG 图标：{source}")
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(target), "ICO"):
        raise RuntimeError("当前 Qt 环境无法生成 Windows ICO 图标")


def build(
    mode: str,
    *,
    clean: bool = False,
    dist_path: Path | None = None,
    work_path: Path | None = None,
) -> None:
    mode = validate_mode(mode)
    ensure_icon()
    environment = os.environ.copy()
    environment["MAILDESK_BUILD_MODE"] = mode
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm"]
    if clean:
        command.append("--clean")
    if dist_path is not None:
        command.extend(("--distpath", str(dist_path.resolve())))
    if work_path is not None:
        command.extend(("--workpath", str((work_path / mode).resolve())))
    command.append(str(SPEC_FILE))
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    output_root = dist_path.resolve() if dist_path is not None else ROOT / "dist"
    output = output_root / ("MailDesk.exe" if mode == "onefile" else "MailDesk")
    print(f"构建完成：{output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MailDesk for Windows with PyInstaller")
    parser.add_argument("--mode", choices=("onefile", "onedir"), default="onedir")
    parser.add_argument("--clean", action="store_true", help="清理 PyInstaller 缓存后构建")
    parser.add_argument("--dist-path", type=Path, help="自定义构建输出目录")
    parser.add_argument("--work-path", type=Path, help="自定义 PyInstaller 临时目录")
    arguments = parser.parse_args()
    try:
        build(
            arguments.mode,
            clean=arguments.clean,
            dist_path=arguments.dist_path,
            work_path=arguments.work_path,
        )
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
