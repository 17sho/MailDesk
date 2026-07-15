from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
DEFAULT_OUTPUT = ROOT / "artifacts" / "releases"
DEFAULT_REPOSITORY = "17sho/MailDesk"
SIGNED_MANIFEST_ASSET_NAME = "MailDesk-update-manifest-v1.json"
SIGNED_MANIFEST_SIGNATURE_NAME = "MailDesk-update-manifest-v1.sig"
TRUSTED_UPDATE_PUBLIC_KEY_B64 = "ZGx6G4ac2jh9UG+/NIEKLKKYTM8MdNt52IfHuNoiRts="

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
    "keyring",
    "jaraco.classes",
    "jaraco.context",
    "jaraco.functools",
    "more-itertools",
    "backports.tarfile",
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


def write_checksum_file(paths: tuple[Path, ...], target: Path) -> Path:
    target.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in paths),
        encoding="utf-8",
        newline="\n",
    )
    return target


def build_signed_update_manifest(
    archives: tuple[Path, ...],
    *,
    version: str,
    signing_key: Path,
    output: Path,
    repository: str = DEFAULT_REPOSITORY,
    expected_public_key: bytes | None = None,
) -> tuple[Path, Path]:
    """Create the canonical update manifest and its raw Ed25519 signature."""

    required_names = {
        f"MailDesk-v{version}-windows-x64-onefile.zip",
        f"MailDesk-v{version}-windows-x64-onedir.zip",
    }
    macos_zip_names = {
        f"MailDesk-v{version}-macos-arm64.zip",
        f"MailDesk-v{version}-macos-x64.zip",
    }
    macos_dmg_names = {
        f"MailDesk-v{version}-macos-arm64.dmg",
        f"MailDesk-v{version}-macos-x64.dmg",
    }
    names = {path.name for path in archives}
    if len(names) != len(archives) or any(not path.is_file() for path in archives):
        raise ValueError("签名清单包含重复或不存在的发行文件")
    if not required_names.issubset(names):
        raise ValueError("签名清单必须包含当前版本的 onefile 与 onedir 压缩包")
    if not names.issubset(required_names | macos_zip_names | macos_dmg_names):
        raise ValueError("签名清单包含名称或版本不受支持的发行文件")
    if names.intersection(macos_zip_names) not in (set(), macos_zip_names):
        raise ValueError("macOS 自动更新 ZIP 必须同时包含 arm64 与 x64")
    if names.intersection(macos_dmg_names) not in (set(), macos_dmg_names):
        raise ValueError("macOS DMG 必须同时包含 arm64 与 x64")
    try:
        private_key = serialization.load_pem_private_key(
            signing_key.read_bytes(),
            password=None,
        )
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("无法读取 Ed25519 发布签名私钥") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise RuntimeError("发布签名私钥不是 Ed25519 密钥")
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    trusted_key = (
        base64.b64decode(TRUSTED_UPDATE_PUBLIC_KEY_B64, validate=True)
        if expected_public_key is None
        else expected_public_key
    )
    if public_key != trusted_key:
        raise RuntimeError("发布签名私钥与客户端内置公钥不匹配")

    payload = {
        "schema": 1,
        "repository": repository,
        "version": version,
        "assets": {
            path.name: {
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in sorted(archives, key=lambda item: item.name)
        },
    }
    manifest_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = private_key.sign(manifest_bytes)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / SIGNED_MANIFEST_ASSET_NAME
    signature_path = output / SIGNED_MANIFEST_SIGNATURE_NAME
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_signature = signature_path.with_suffix(signature_path.suffix + ".tmp")
    temporary_manifest.write_bytes(manifest_bytes)
    temporary_signature.write_bytes(signature)
    temporary_manifest.replace(manifest_path)
    temporary_signature.replace(signature_path)
    return manifest_path, signature_path


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
    *,
    root: Path = ROOT,
    output: Path = DEFAULT_OUTPUT,
    version: str | None = None,
    dist: Path | None = None,
) -> tuple[Path, Path, Path]:
    version = version or project_version(root)
    expected_version = (*map(int, version.split(".")), 0)
    dist_root = dist.resolve() if dist is not None else root / "dist"
    onefile_exe = dist_root / "MailDesk.exe"
    onedir_root = dist_root / "MailDesk"
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
    write_checksum_file((onefile_zip, onedir_zip), checksum_file)
    return onefile_zip, onedir_zip, checksum_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Package versioned MailDesk Windows release archives"
    )
    parser.add_argument("--version", help="必须与 pyproject.toml 一致")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dist", type=Path, help="包含 onefile 与 onedir 构建结果的目录")
    parser.add_argument(
        "--extra-asset",
        type=Path,
        action="append",
        default=[],
        help="加入同版本 macOS arm64/x64 ZIP 或 DMG；可重复指定",
    )
    parser.add_argument(
        "--signing-key",
        type=Path,
        default=(
            Path(os.environ["MAILDESK_RELEASE_SIGNING_KEY"])
            if os.environ.get("MAILDESK_RELEASE_SIGNING_KEY")
            else None
        ),
        help="Ed25519 发布签名私钥 PEM；也可设置 MAILDESK_RELEASE_SIGNING_KEY",
    )
    arguments = parser.parse_args()
    detected = project_version()
    if arguments.version and arguments.version != detected:
        parser.error(f"--version {arguments.version} 与项目版本 {detected} 不一致")
    if arguments.signing_key is None:
        parser.error("必须通过 --signing-key 提供离线 Ed25519 发布签名私钥")
    onefile_zip, onedir_zip, checksum_file = build_release_archives(
        output=arguments.output,
        version=arguments.version or detected,
        dist=arguments.dist,
    )
    release_assets = (onefile_zip, onedir_zip, *arguments.extra_asset)
    manifest, signature = build_signed_update_manifest(
        release_assets,
        version=arguments.version or detected,
        signing_key=arguments.signing_key,
        output=arguments.output,
    )
    write_checksum_file(
        (*release_assets, manifest, signature),
        checksum_file,
    )
    for path in (*release_assets, manifest, signature, checksum_file):
        print(f"发布文件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
