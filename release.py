from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import platform
import re
import shutil
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
DEFAULT_OUTPUT = ROOT / "artifacts" / "releases"

RUNTIME_DISTRIBUTIONS = (
    "PySide6",
    "PySide6-Essentials",
    "PySide6-Addons",
    "shiboken6",
    "cryptography",
    "httpx",
    "httpcore",
    "certifi",
    "PyOTP",
    "PySocks",
    "socksio",
    "pywin32",
    "anyio",
    "sniffio",
    "h11",
    "idna",
    "cffi",
    "pycparser",
    "typing_extensions",
    "Brotli",
    "zstandard",
    "attrs",
    "outcome",
    "sortedcontainers",
    "trio",
    "wsproto",
    "packaging",
    "setuptools",
)

COMMON_RELEASE_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "RELEASE_README.txt",
)


def project_version(root: Path = ROOT) -> str:
    with (root / "pyproject.toml").open("rb") as stream:
        value = str(tomllib.load(stream)["project"]["version"])
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError(f"不支持的项目版本号：{value}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_license_file(path: PurePosixPath) -> bool:
    lowered_parts = {part.casefold() for part in path.parts}
    lowered_name = path.name.casefold()
    return bool(
        lowered_parts.intersection({"license", "licenses", "license_files"})
        or lowered_name.startswith(("license", "copying", "notice"))
    )


def collect_distribution_licenses(target: Path) -> int:
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for requested_name in RUNTIME_DISTRIBUTIONS:
        try:
            distribution = importlib.metadata.distribution(requested_name)
        except importlib.metadata.PackageNotFoundError:
            continue
        package_name = re.sub(
            r"[^A-Za-z0-9_.-]+", "-", distribution.metadata["Name"] or requested_name
        )
        package_root = target / f"{package_name}-{distribution.version}"
        used_names: set[str] = set()
        for entry in distribution.files or ():
            entry_path = PurePosixPath(str(entry).replace("\\", "/"))
            if not _is_license_file(entry_path):
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file():
                continue
            candidate = entry_path.name
            counter = 2
            while candidate.casefold() in used_names:
                candidate = f"{entry_path.stem}-{counter}{entry_path.suffix}"
                counter += 1
            used_names.add(candidate.casefold())
            package_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, package_root / candidate)
            copied += 1
    if not copied:
        raise RuntimeError("没有从构建环境收集到第三方许可证")
    return copied


def _embedded_version(path: Path) -> tuple[int, int, int, int]:
    if platform.system() != "Windows":
        raise RuntimeError("Windows 版本资源只能在 Windows 上验证")
    import win32api  # type: ignore[import-not-found]

    info = win32api.GetFileVersionInfo(str(path), "\\")
    ms = int(info["FileVersionMS"])
    ls = int(info["FileVersionLS"])
    return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def _iter_directory_files(directory: Path):
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            yield path, path.relative_to(directory)


def _write_archive(
    target: Path, entries: list[tuple[Path, PurePosixPath]]
) -> None:
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(
        temporary,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        for source, archive_path in entries:
            archive.write(source, archive_path.as_posix())
    temporary.replace(target)


def build_release_archives(
    *, root: Path = ROOT, output: Path = DEFAULT_OUTPUT, version: str | None = None
) -> tuple[Path, Path, Path]:
    version = version or project_version(root)
    expected_version = (*map(int, version.split(".")), 0)
    onefile_exe = root / "dist" / "MailDesk.exe"
    onedir_root = root / "dist" / "MailDesk"
    onedir_exe = onedir_root / "MailDesk.exe"
    for executable in (onefile_exe, onedir_exe):
        if not executable.is_file():
            raise FileNotFoundError(f"缺少构建产物：{executable}")
        actual_version = _embedded_version(executable)
        if actual_version != expected_version:
            raise RuntimeError(
                f"{executable.name} 版本资源为 {actual_version}，期望 {expected_version}"
            )

    output.mkdir(parents=True, exist_ok=True)
    onefile_name = f"MailDesk-v{version}-windows-x64-onefile"
    onedir_name = f"MailDesk-v{version}-windows-x64-onedir"
    onefile_zip = output / f"{onefile_name}.zip"
    onedir_zip = output / f"{onedir_name}.zip"

    with tempfile.TemporaryDirectory(prefix="maildesk-release-licenses-") as temp:
        licenses = Path(temp) / "python-packages"
        collect_distribution_licenses(licenses)
        common_entries: list[tuple[Path, PurePosixPath]] = []
        for filename in COMMON_RELEASE_FILES:
            common_entries.append((root / filename, PurePosixPath(filename)))
        for filename in ("GPL-3.0.txt", "LGPL-3.0.txt", "PYTHON-3.12.txt"):
            common_entries.append(
                (root / "legal" / filename, PurePosixPath("licenses") / filename)
            )
        for source, relative in _iter_directory_files(licenses):
            common_entries.append(
                (
                    source,
                    PurePosixPath("licenses/python-packages")
                    / PurePosixPath(relative.as_posix()),
                )
            )

        onefile_prefix = PurePosixPath(onefile_name)
        onefile_entries = [
            (onefile_exe, onefile_prefix / "MailDesk.exe"),
            *[
                (source, onefile_prefix / archive_path)
                for source, archive_path in common_entries
            ],
        ]
        _write_archive(onefile_zip, onefile_entries)

        onedir_prefix = PurePosixPath(onedir_name)
        onedir_entries = [
            (
                source,
                onedir_prefix / "MailDesk" / PurePosixPath(relative.as_posix()),
            )
            for source, relative in _iter_directory_files(onedir_root)
        ]
        onedir_entries.extend(
            (source, onedir_prefix / archive_path)
            for source, archive_path in common_entries
        )
        _write_archive(onedir_zip, onedir_entries)

    checksum_file = output / "SHA256SUMS.txt"
    checksum_file.write_text(
        "".join(
            f"{sha256_file(path)}  {path.name}\n"
            for path in (onefile_zip, onedir_zip)
        ),
        encoding="utf-8",
        newline="\n",
    )
    return onefile_zip, onedir_zip, checksum_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Package versioned MailDesk Windows release archives"
    )
    parser.add_argument("--version", help="必须与 pyproject.toml 一致")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    detected = project_version()
    if arguments.version and arguments.version != detected:
        parser.error(f"--version {arguments.version} 与项目版本 {detected} 不一致")
    archives = build_release_archives(
        output=arguments.output, version=arguments.version or detected
    )
    for path in archives:
        print(f"发布文件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
