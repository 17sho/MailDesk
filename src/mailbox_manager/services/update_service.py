from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import plistlib
import posixpath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DEFAULT_REPOSITORY = "17sho/MailDesk"
GITHUB_API_ROOT = "https://api.github.com"
CHECKSUM_ASSET_NAME = "SHA256SUMS.txt"
SIGNED_MANIFEST_ASSET_NAME = "MailDesk-update-manifest-v1.json"
SIGNED_MANIFEST_SIGNATURE_NAME = "MailDesk-update-manifest-v1.sig"
TRUSTED_UPDATE_PUBLIC_KEY_B64 = "ZGx6G4ac2jh9UG+/NIEKLKKYTM8MdNt52IfHuNoiRts="
TRUSTED_GITHUB_DOWNLOAD_HOSTS = frozenset(
    {
        "api.github.com",
        "github.com",
        "github-releases.githubusercontent.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_SEMVER_PATTERN = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_CHECKSUM_LINE_PATTERN = re.compile(
    r"^([0-9a-fA-F]{64})[ \t]+(?:\*| )?([^\r\n]+?)\s*$"
)
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "aux",
        "clock$",
        "con",
        "conin$",
        "conout$",
        "nul",
        "prn",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
)


class UpdateError(RuntimeError):
    """A user-displayable update failure."""


class UpdateNetworkError(UpdateError):
    """The update endpoint could not be reached or returned an invalid status."""


class UpdateSecurityError(UpdateError):
    """Downloaded update data failed a trust or integrity check."""


class UpdateCancelledError(UpdateError):
    """The caller cancelled a background update download."""


class InstallMode(StrEnum):
    SOURCE = "source"
    ONEFILE = "onefile"
    ONEDIR = "onedir"
    MACOS_APP = "macos-app"


@dataclass(frozen=True, slots=True)
class _SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease: tuple[int | str, ...] = ()
    build: str | None = None

    @classmethod
    def parse(cls, value: str) -> _SemanticVersion:
        match = _SEMVER_PATTERN.fullmatch(value.strip())
        if match is None:
            raise ValueError(f"无效的语义版本号：{value}")
        prerelease: list[int | str] = []
        for identifier in (match.group(4) or "").split("."):
            if not identifier:
                continue
            if identifier.isdigit():
                if len(identifier) > 1 and identifier.startswith("0"):
                    raise ValueError(f"无效的语义版本号：{value}")
                prerelease.append(int(identifier))
            else:
                prerelease.append(identifier)
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=tuple(prerelease),
            build=match.group(5),
        )

    @property
    def normalized(self) -> str:
        value = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            value += "-" + ".".join(str(item) for item in self.prerelease)
        if self.build:
            value += f"+{self.build}"
        return value

    def precedence_key(self) -> tuple[int, int, int]:
        return self.major, self.minor, self.patch


def compare_versions(left: str, right: str) -> int:
    """Compare SemVer precedence, ignoring build metadata as required by SemVer."""

    left_version = _SemanticVersion.parse(left)
    right_version = _SemanticVersion.parse(right)
    if left_version.precedence_key() != right_version.precedence_key():
        return -1 if left_version.precedence_key() < right_version.precedence_key() else 1
    left_pre = left_version.prerelease
    right_pre = right_version.prerelease
    if not left_pre and not right_pre:
        return 0
    if not left_pre:
        return 1
    if not right_pre:
        return -1
    for left_item, right_item in zip(left_pre, right_pre, strict=False):
        if left_item == right_item:
            continue
        if isinstance(left_item, int) and isinstance(right_item, str):
            return -1
        if isinstance(left_item, str) and isinstance(right_item, int):
            return 1
        return -1 if left_item < right_item else 1
    if len(left_pre) == len(right_pre):
        return 0
    return -1 if len(left_pre) < len(right_pre) else 1


def is_newer_version(candidate: str, current: str) -> bool:
    return compare_versions(candidate, current) > 0


def detect_install_mode(
    *,
    frozen: bool | None = None,
    meipass: str | os.PathLike[str] | None = None,
    platform_name: str | None = None,
    system_name: str | None = None,
    executable_path: str | os.PathLike[str] | None = None,
) -> InstallMode:
    """Detect a supported frozen install without importing PyInstaller."""

    runtime_platform = os.name if platform_name is None else platform_name
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not is_frozen:
        return InstallMode.SOURCE
    if runtime_platform == "nt":
        bundle_root = getattr(sys, "_MEIPASS", "") if meipass is None else meipass
        bundle_name = (
            str(bundle_root).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        )
        if bundle_name.casefold() == "_internal":
            return InstallMode.ONEDIR
        return InstallMode.ONEFILE

    runtime_system = platform.system() if system_name is None else system_name
    executable = Path(executable_path or sys.executable)
    if runtime_system == "Darwin" and _macos_app_bundle(executable) is not None:
        return InstallMode.MACOS_APP
    return InstallMode.SOURCE


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int
    digest: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    version: str
    tag_name: str
    name: str
    notes: str
    page_url: str
    published_at: str | None
    assets: tuple[ReleaseAsset, ...]

    def asset_named(self, name: str) -> ReleaseAsset | None:
        return next((asset for asset in self.assets if asset.name == name), None)


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    current_version: str
    release: ReleaseInfo
    install_mode: InstallMode
    asset: ReleaseAsset | None
    checksum_asset: ReleaseAsset | None
    manifest_asset: ReleaseAsset | None = None
    signature_asset: ReleaseAsset | None = None
    expected_sha256: str | None = None
    expected_size: int | None = None

    @property
    def install_supported(self) -> bool:
        return self.install_mode is not InstallMode.SOURCE and self.asset is not None


@dataclass(frozen=True, slots=True)
class DownloadedUpdate:
    update: UpdateInfo
    archive_path: Path
    sha256: str
    transaction_id: str = ""


@dataclass(frozen=True, slots=True)
class StagedUpdate:
    update: UpdateInfo
    staging_root: Path
    source_path: Path
    transaction_id: str = ""
    content_manifest_path: Path | None = None
    content_manifest_sha256: str = ""


@dataclass(frozen=True, slots=True)
class InstallerPlan:
    script_path: Path
    command: tuple[str, ...]
    source_path: Path
    target_path: Path
    backup_path: Path
    restart_executable: Path
    parent_pid: int
    lock_path: Path | None = None
    incoming_path: Path | None = None
    ready_path: Path | None = None
    health_path: Path | None = None
    result_path: Path | None = None
    cleanup_path: Path | None = None
    health_token: str = ""
    content_root: Path | None = None
    content_manifest_path: Path | None = None
    content_manifest_sha256: str = ""
    helper_manifest_path: Path | None = None
    helper_manifest_sha256: str = ""


@dataclass(frozen=True, slots=True)
class SignedManifestAsset:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SignedUpdateManifest:
    repository: str
    version: str
    assets: tuple[SignedManifestAsset, ...]

    def asset_named(self, name: str) -> SignedManifestAsset | None:
        return next((asset for asset in self.assets if asset.name == name), None)


ProgressCallback = Callable[[int, int | None], None]
CancelCallback = Callable[[], bool]


def _read_diagnostic_tail(*paths: Path | None) -> str:
    """Return a small, user-displayable tail from updater diagnostics."""

    for path in paths:
        if path is None or not path.is_file():
            continue
        try:
            with path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - 4096))
                text = stream.read(4096).decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            return "安装助手信息：" + " | ".join(lines[-6:])
    return ""


def consume_install_result(updates_dir: Path) -> str | None:
    """Return one unseen helper result while retaining a small diagnostic history."""

    root = Path(updates_dir)
    try:
        diagnostics = sorted(
            root.glob("updater-launch-*.log"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for obsolete in diagnostics[5:]:
            obsolete.unlink(missing_ok=True)
        pending = sorted(
            root.glob("install-result-*.log"),
            key=lambda path: path.stat().st_mtime_ns,
        )
    except OSError:
        return None
    if not pending:
        return None
    result_path = pending[-1]
    try:
        if result_path.stat().st_size > 4096:
            outcome = "invalid_result"
        else:
            outcome = result_path.read_text(encoding="utf-8-sig").strip()
        seen_path = result_path.with_name(f"{result_path.name}.seen")
        result_path.replace(seen_path)
        history = sorted(
            root.glob("install-result-*.log.seen"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for obsolete in history[5:]:
            obsolete.unlink(missing_ok=True)
        return outcome
    except OSError:
        return None


def validate_trusted_github_url(url: str) -> None:
    """Reject non-HTTPS, credential-bearing and non-GitHub update URLs."""

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UpdateSecurityError("更新地址无效") from exc
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or host not in TRUSTED_GITHUB_DOWNLOAD_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise UpdateSecurityError("更新地址不是受信任的 GitHub HTTPS 地址")


def _plain_asset_name(name: str) -> bool:
    return (
        bool(name)
        and Path(name).name == name
        and PurePosixPath(name).name == name
        and "/" not in name
        and "\\" not in name
        and "\x00" not in name
    )


def parse_github_release(
    payload: Mapping[str, Any], *, repository: str = DEFAULT_REPOSITORY
) -> ReleaseInfo:
    """Parse and validate GitHub's latest-release JSON response."""

    if payload.get("draft") is not False or payload.get("prerelease") is not False:
        raise UpdateError("GitHub 返回的不是正式发行版本")
    tag_name = payload.get("tag_name")
    if not isinstance(tag_name, str):
        raise UpdateError("GitHub 发行信息缺少版本号")
    try:
        parsed_version = _SemanticVersion.parse(tag_name)
    except ValueError as exc:
        raise UpdateError("GitHub 发行版本号格式无效") from exc
    if parsed_version.prerelease:
        raise UpdateError("GitHub 返回的不是正式发行版本")
    version = f"{parsed_version.major}.{parsed_version.minor}.{parsed_version.patch}"

    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list):
        raise UpdateError("GitHub 发行信息缺少下载文件")
    assets: list[ReleaseAsset] = []
    used_names: set[str] = set()
    for raw_asset in raw_assets:
        if not isinstance(raw_asset, Mapping):
            raise UpdateError("GitHub 发行文件信息无效")
        name = raw_asset.get("name")
        download_url = raw_asset.get("browser_download_url")
        size = raw_asset.get("size")
        digest = raw_asset.get("digest")
        if (
            not isinstance(name, str)
            or not _plain_asset_name(name)
            or not isinstance(download_url, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or (digest is not None and not isinstance(digest, str))
        ):
            raise UpdateError("GitHub 发行文件信息无效")
        validate_trusted_github_url(download_url)
        if name in used_names:
            raise UpdateError(f"GitHub 发行版本包含重复文件：{name}")
        used_names.add(name)
        assets.append(
            ReleaseAsset(
                name=name,
                download_url=download_url,
                size=size,
                digest=digest,
            )
        )

    default_page_url = f"https://github.com/{repository}/releases/tag/{tag_name}"
    page_url = payload.get("html_url")
    if not isinstance(page_url, str):
        page_url = default_page_url
    try:
        validate_trusted_github_url(page_url)
    except UpdateSecurityError:
        page_url = default_page_url
    name = payload.get("name")
    notes = payload.get("body")
    published_at = payload.get("published_at")
    return ReleaseInfo(
        version=version,
        tag_name=tag_name,
        name=name.strip() if isinstance(name, str) and name.strip() else tag_name,
        notes=notes if isinstance(notes, str) else "",
        page_url=page_url,
        published_at=published_at if isinstance(published_at, str) else None,
        assets=tuple(assets),
    )


class UpdateService:
    """Secure, synchronous update primitives intended to run inside GUI workers."""

    def __init__(
        self,
        *,
        current_version: str,
        updates_dir: Path,
        repository: str = DEFAULT_REPOSITORY,
        install_mode: InstallMode | str | None = None,
        machine: str | None = None,
        trusted_public_key: bytes | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 30.0,
        max_api_bytes: int = 2 * 1024 * 1024,
        max_checksum_bytes: int = 1024 * 1024,
        max_manifest_bytes: int = 1024 * 1024,
        max_signature_bytes: int = 4096,
        max_download_bytes: int = 2 * 1024 * 1024 * 1024,
        max_extracted_bytes: int = 4 * 1024 * 1024 * 1024,
        max_extracted_file_bytes: int = 2 * 1024 * 1024 * 1024,
        max_archive_entries: int = 30_000,
        max_compression_ratio: int = 1_000,
    ) -> None:
        try:
            _SemanticVersion.parse(current_version)
        except ValueError as exc:
            raise ValueError("current_version 必须是有效的语义版本号") from exc
        if not _REPOSITORY_PATTERN.fullmatch(repository):
            raise ValueError("repository 必须采用 owner/name 格式")
        positive_limits = (
            timeout_seconds,
            max_api_bytes,
            max_checksum_bytes,
            max_manifest_bytes,
            max_signature_bytes,
            max_download_bytes,
            max_extracted_bytes,
            max_extracted_file_bytes,
            max_archive_entries,
            max_compression_ratio,
        )
        if any(limit <= 0 for limit in positive_limits):
            raise ValueError("更新服务的超时和体积限制必须大于零")
        self.current_version = current_version
        self.updates_dir = Path(updates_dir)
        self.repository = repository
        self.install_mode = (
            detect_install_mode()
            if install_mode is None
            else InstallMode(install_mode)
        )
        self.machine = platform.machine() if machine is None else machine
        public_key = (
            base64.b64decode(TRUSTED_UPDATE_PUBLIC_KEY_B64, validate=True)
            if trusted_public_key is None
            else trusted_public_key
        )
        if len(public_key) != 32:
            raise ValueError("trusted_public_key 必须是 32 字节 Ed25519 公钥")
        self._trusted_public_key = bytes(public_key)
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._max_api_bytes = max_api_bytes
        self._max_checksum_bytes = max_checksum_bytes
        self._max_manifest_bytes = max_manifest_bytes
        self._max_signature_bytes = max_signature_bytes
        self._max_download_bytes = max_download_bytes
        self._max_extracted_bytes = max_extracted_bytes
        self._max_extracted_file_bytes = max_extracted_file_bytes
        self._max_archive_entries = max_archive_entries
        self._max_compression_ratio = max_compression_ratio
        self._transaction_lock_guard = threading.Lock()
        self._transaction_lock_stream: BinaryIO | None = None
        self._transaction_id: str | None = None

    @property
    def latest_release_url(self) -> str:
        return f"{GITHUB_API_ROOT}/repos/{self.repository}/releases/latest"

    @property
    def transaction_lock_path(self) -> Path:
        return self.updates_dir / ".update-transaction.lock"

    def _acquire_update_lock(self) -> str:
        with self._transaction_lock_guard:
            if self._transaction_lock_stream is not None:
                return self._transaction_id or ""
            self.updates_dir.mkdir(parents=True, exist_ok=True)
            stream = self.transaction_lock_path.open("a+b")
            try:
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as exc:
                stream.close()
                raise UpdateError("另一个 MailDesk 实例正在处理更新") from exc
            self._transaction_lock_stream = stream
            self._transaction_id = uuid4().hex
            return self._transaction_id

    def release_update_lock(self) -> None:
        with self._transaction_lock_guard:
            stream = self._transaction_lock_stream
            if stream is None:
                return
            try:
                with suppress(OSError):
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()
                self._transaction_lock_stream = None
                self._transaction_id = None

    def discard_staged_update(self, staged: StagedUpdate) -> None:
        root = staged.staging_root.resolve()
        updates_root = self.updates_dir.resolve()
        if (
            _is_relative_to(root, updates_root)
            and root != updates_root
            and root.name.startswith("staged-v")
            and root.is_dir()
            and not root.is_symlink()
        ):
            shutil.rmtree(root, ignore_errors=True)
        self.release_update_lock()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self._transport,
            timeout=httpx.Timeout(self._timeout_seconds, connect=10.0),
            follow_redirects=False,
            headers={
                "Accept": "application/vnd.github+json",
                "Accept-Encoding": "identity",
                "User-Agent": f"MailDesk/{self.current_version} updater",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def fetch_latest_release(self) -> ReleaseInfo:
        try:
            with self._client() as client:
                response = self._send_with_trusted_redirects(
                    client, self.latest_release_url
                )
                try:
                    if response.status_code != 200:
                        raise UpdateNetworkError("GitHub 更新服务暂时不可用")
                    content = self._read_limited(response, self._max_api_bytes)
                finally:
                    response.close()
            payload = json.loads(content)
        except (UpdateError, UpdateSecurityError):
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise UpdateNetworkError("无法连接 GitHub 更新服务") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateError("GitHub 更新服务返回了无法识别的数据") from exc
        if not isinstance(payload, Mapping):
            raise UpdateError("GitHub 更新服务返回了无法识别的数据")
        return parse_github_release(payload, repository=self.repository)

    def check_for_update(self) -> UpdateInfo | None:
        release = self.fetch_latest_release()
        if not is_newer_version(release.version, self.current_version):
            return None
        checksum_asset = release.asset_named(CHECKSUM_ASSET_NAME)
        manifest_asset = release.asset_named(SIGNED_MANIFEST_ASSET_NAME)
        signature_asset = release.asset_named(SIGNED_MANIFEST_SIGNATURE_NAME)
        if manifest_asset is None or signature_asset is None:
            raise UpdateSecurityError("新版本缺少 MailDesk 官方发布签名")
        try:
            with self._client() as client:
                manifest = self._fetch_signed_manifest(
                    client,
                    release,
                    manifest_asset,
                    signature_asset,
                )
        except UpdateError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise UpdateNetworkError("无法验证新版本的发布者签名") from exc

        asset: ReleaseAsset | None = None
        signed_asset: SignedManifestAsset | None = None
        if self.install_mode is not InstallMode.SOURCE:
            expected_name = self._expected_archive_name(release.version)
            asset = release.asset_named(expected_name)
            if asset is None:
                raise UpdateError(f"新版本缺少当前安装类型的文件：{expected_name}")
            if asset.size <= 0:
                raise UpdateSecurityError("新版本更新包体积无效")
            signed_asset = manifest.asset_named(expected_name)
            if signed_asset is None:
                raise UpdateSecurityError("签名清单未包含当前安装类型的更新包")
            if asset.size != signed_asset.size:
                raise UpdateSecurityError("更新包体积与签名清单不一致")
            if asset.digest:
                algorithm, separator, digest = asset.digest.partition(":")
                if (
                    separator != ":"
                    or algorithm.casefold() != "sha256"
                    or not _SHA256_PATTERN.fullmatch(digest)
                    or not hmac.compare_digest(
                        digest.casefold(), signed_asset.sha256
                    )
                ):
                    raise UpdateSecurityError("GitHub 更新摘要与签名清单不一致")
        return UpdateInfo(
            current_version=self.current_version,
            release=release,
            install_mode=self.install_mode,
            asset=asset,
            checksum_asset=checksum_asset,
            manifest_asset=manifest_asset,
            signature_asset=signature_asset,
            expected_sha256=signed_asset.sha256 if signed_asset else None,
            expected_size=signed_asset.size if signed_asset else None,
        )

    def _expected_archive_name(self, version: str) -> str:
        if self.install_mode in {InstallMode.ONEFILE, InstallMode.ONEDIR}:
            return (
                f"MailDesk-v{version}-windows-x64-"
                f"{self.install_mode.value}.zip"
            )
        if self.install_mode is InstallMode.MACOS_APP:
            arch = _normalize_macos_arch(self.machine)
            return f"MailDesk-v{version}-macos-{arch}.zip"
        raise UpdateError("源码运行模式没有可自动安装的更新包")

    def download_update(
        self,
        update: UpdateInfo,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> DownloadedUpdate:
        asset = update.asset
        if not update.install_supported or asset is None:
            raise UpdateError("源码运行模式不能自动覆盖安装，请前往发行页面下载")
        if update.install_mode is not self.install_mode:
            raise UpdateError("更新包类型与当前程序安装类型不一致")
        if asset.size > self._max_download_bytes:
            raise UpdateSecurityError("更新包超过允许的最大体积")
        transaction_id = self._acquire_update_lock()
        archive_suffix = Path(asset.name).suffix or ".zip"
        archive_stem = Path(asset.name).stem
        target = self.updates_dir / (
            f"{archive_stem}-{transaction_id}{archive_suffix}"
        )
        partial = target.with_name(f"{target.name}.part")
        partial.unlink(missing_ok=True)
        try:
            with self._client() as client:
                expected_sha256 = self._expected_sha256(client, update)
                actual_sha256 = self._download_asset(
                    client,
                    asset,
                    partial,
                    progress=progress,
                    cancelled=cancelled,
                )
            if not hmac.compare_digest(actual_sha256, expected_sha256):
                raise UpdateSecurityError("更新包 SHA-256 校验失败")
            partial.replace(target)
        except UpdateError:
            partial.unlink(missing_ok=True)
            self.release_update_lock()
            raise
        except (httpx.HTTPError, OSError) as exc:
            partial.unlink(missing_ok=True)
            self.release_update_lock()
            raise UpdateNetworkError("更新包下载失败") from exc
        except Exception:
            partial.unlink(missing_ok=True)
            self.release_update_lock()
            raise
        return DownloadedUpdate(
            update=update,
            archive_path=target,
            sha256=actual_sha256,
            transaction_id=transaction_id,
        )

    def stage_update(
        self,
        downloaded: DownloadedUpdate,
        *,
        cancelled: CancelCallback | None = None,
    ) -> StagedUpdate:
        if cancelled is not None and cancelled():
            self.release_update_lock()
            raise UpdateCancelledError("更新暂存已取消")
        update = downloaded.update
        if not update.install_supported or update.asset is None:
            raise UpdateError("当前更新不能自动安装")
        if update.install_mode is not self.install_mode:
            raise UpdateError("更新包类型与当前程序安装类型不一致")
        archive = downloaded.archive_path
        if not archive.is_file():
            raise UpdateError("已下载的更新包不存在")
        actual_digest = _sha256_file(archive)
        if not hmac.compare_digest(actual_digest, downloaded.sha256.casefold()):
            raise UpdateSecurityError("更新包在暂存前发生了变化")

        transaction_id = self._acquire_update_lock()
        if downloaded.transaction_id and downloaded.transaction_id != transaction_id:
            self.release_update_lock()
            raise UpdateError("更新下载事务与当前进程不一致")
        transaction_id = downloaded.transaction_id or transaction_id

        temporary_root: Path | None = None
        try:
            self.updates_dir.mkdir(parents=True, exist_ok=True)
            temporary_root = Path(
                tempfile.mkdtemp(prefix=".extract-", dir=self.updates_dir)
            )
            final_root = self.updates_dir / (
                f"staged-v{update.release.version}-{update.install_mode.value}-"
                f"{transaction_id}"
            )
            self._safe_extract_zip(
                archive,
                temporary_root,
                cancelled=cancelled,
                allow_symlinks=update.install_mode is InstallMode.MACOS_APP,
            )
            if update.install_mode is InstallMode.MACOS_APP:
                prefix = (
                    f"MailDesk-v{update.release.version}-macos-"
                    f"{_normalize_macos_arch(self.machine)}"
                )
                extracted_source = Path(prefix) / "MailDesk.app"
            else:
                prefix = (
                    f"MailDesk-v{update.release.version}-windows-x64-"
                    f"{update.install_mode.value}"
                )
                extracted_source = (
                    Path(prefix) / "MailDesk.exe"
                    if update.install_mode is InstallMode.ONEFILE
                    else Path(prefix) / "MailDesk"
                )
            source = temporary_root / extracted_source
            if update.install_mode is InstallMode.ONEFILE:
                expected_executable = source
            elif update.install_mode is InstallMode.ONEDIR:
                expected_executable = source / "MailDesk.exe"
            else:
                expected_executable = source / "Contents" / "MacOS" / "MailDesk"
            if not expected_executable.is_file():
                raise UpdateSecurityError("更新包缺少预期的 MailDesk 主程序")
            if update.install_mode is InstallMode.MACOS_APP:
                _validate_staged_macos_app(
                    source,
                    update.release.version,
                    _normalize_macos_arch(self.machine),
                )
            else:
                _validate_staged_windows_executable(
                    expected_executable,
                    update.release.version,
                )
            if (
                update.install_mode is InstallMode.ONEDIR
                and not (source / "_internal").is_dir()
            ):
                raise UpdateSecurityError("更新包缺少 onedir 运行时目录")
            # Normalize the install payload close to the staging root. Keeping
            # the long release archive prefix here pushes Qt QML resource paths
            # beyond legacy Windows MAX_PATH after the temporary directory is
            # renamed, making unchanged files appear to have disappeared.
            payload_root = temporary_root / "payload"
            if payload_root.exists():
                raise UpdateSecurityError("更新包包含冲突的暂存目录")
            if update.install_mode is InstallMode.ONEFILE:
                payload_root.mkdir()
                source.replace(payload_root / "MailDesk.exe")
                relative_source = Path("payload") / "MailDesk.exe"
            elif update.install_mode is InstallMode.MACOS_APP:
                payload_root.mkdir()
                source.replace(payload_root / "MailDesk.app")
                relative_source = Path("payload") / "MailDesk.app"
            else:
                source.replace(payload_root)
                relative_source = Path("payload")
            source = temporary_root / relative_source
            for child in tuple(temporary_root.iterdir()):
                if child == payload_root:
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            content_root = (
                source.parent
                if update.install_mode is InstallMode.ONEFILE
                else source
            )
            content_files = (
                (source,)
                if update.install_mode is InstallMode.ONEFILE
                else _staged_content_paths(source)
            )
            content_manifest = temporary_root / ".staged-files-v1.json"
            content_manifest_sha256 = _write_staged_content_manifest(
                content_root,
                content_files,
                content_manifest,
                cancelled=cancelled,
                allow_symlinks=update.install_mode is InstallMode.MACOS_APP,
            )
            if final_root.exists():
                if final_root.is_dir() and not final_root.is_symlink():
                    shutil.rmtree(final_root)
                else:
                    final_root.unlink()
            temporary_root.replace(final_root)
            with suppress(OSError):
                archive.unlink()
            return StagedUpdate(
                update=update,
                staging_root=final_root,
                source_path=final_root / relative_source,
                transaction_id=transaction_id,
                content_manifest_path=final_root / content_manifest.name,
                content_manifest_sha256=content_manifest_sha256,
            )
        except UpdateError:
            if temporary_root is not None:
                shutil.rmtree(temporary_root, ignore_errors=True)
            self.release_update_lock()
            raise
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as exc:
            if temporary_root is not None:
                shutil.rmtree(temporary_root, ignore_errors=True)
            self.release_update_lock()
            raise UpdateSecurityError("更新包不是有效且安全的 ZIP 文件") from exc

    def create_installer_plan(
        self,
        staged: StagedUpdate,
        *,
        executable_path: Path | None = None,
        parent_pid: int | None = None,
        powershell_executable: str | os.PathLike[str] | None = None,
    ) -> InstallerPlan:
        mode = staged.update.install_mode
        if mode is InstallMode.SOURCE:
            raise UpdateError("源码运行模式不能自动安装")
        if mode is not self.install_mode:
            raise UpdateError("更新包类型与当前程序安装类型不一致")
        executable = Path(executable_path or sys.executable).resolve()
        if not executable.is_file():
            raise UpdateError("找不到当前 MailDesk 可执行文件")
        staging_root = staged.staging_root.resolve()
        updates_root = self.updates_dir.resolve()
        if (
            staging_root == Path(staging_root.anchor)
            or not staging_root.is_dir()
            or not _is_relative_to(staging_root, updates_root)
        ):
            raise UpdateError("更新暂存目录不属于当前 MailDesk 更新事务")
        source = staged.source_path.resolve()
        if not _is_relative_to(source, staging_root):
            raise UpdateError("更新源文件不属于当前 MailDesk 更新事务")
        if mode is InstallMode.ONEFILE:
            expected_executable = source
        elif mode is InstallMode.ONEDIR:
            expected_executable = source / "MailDesk.exe"
        else:
            expected_executable = source / "Contents" / "MacOS" / "MailDesk"
        if not expected_executable.is_file():
            raise UpdateError("暂存区缺少新版 MailDesk 可执行文件")
        if mode is InstallMode.ONEDIR and not (source / "_internal").is_dir():
            raise UpdateError("暂存区缺少新版 onedir 运行时目录")
        content_root = source.parent if mode is InstallMode.ONEFILE else source
        content_manifest_path = (
            staged.content_manifest_path.resolve()
            if staged.content_manifest_path is not None
            else staging_root / ".staged-files-v1.json"
        )
        if not _is_relative_to(content_manifest_path, staging_root):
            raise UpdateError("更新完整性清单不属于当前 MailDesk 更新事务")
        content_manifest_sha256 = staged.content_manifest_sha256
        if staged.content_manifest_path is None and not content_manifest_sha256:
            content_files = (
                (source,)
                if mode is InstallMode.ONEFILE
                else _staged_content_paths(source)
            )
            content_manifest_sha256 = _write_staged_content_manifest(
                content_root,
                content_files,
                content_manifest_path,
                allow_symlinks=mode is InstallMode.MACOS_APP,
            )
        elif (
            not content_manifest_path.is_file()
            or not _SHA256_PATTERN.fullmatch(content_manifest_sha256)
            or not hmac.compare_digest(
                _sha256_file(content_manifest_path),
                content_manifest_sha256.casefold(),
            )
        ):
            raise UpdateSecurityError("更新暂存区完整性清单已被修改")
        _verify_staged_content_manifest(
            content_root,
            content_manifest_path,
            content_manifest_sha256,
        )

        if mode is InstallMode.ONEFILE:
            target = executable
            restart_executable = target
        elif mode is InstallMode.ONEDIR:
            target = executable.parent
            restart_executable = target / "MailDesk.exe"
        else:
            app_bundle = _macos_app_bundle(executable)
            if app_bundle is None:
                raise UpdateError("当前 macOS 程序不在有效的 MailDesk.app 中")
            target = app_bundle
            restart_executable = target / "Contents" / "MacOS" / "MailDesk"
        target = target.resolve()
        if mode is InstallMode.ONEDIR and (
            target == Path(target.anchor) or not (target / "_internal").is_dir()
        ):
            raise UpdateError("当前 onedir 程序目录结构无效，不能自动替换")
        if mode is InstallMode.MACOS_APP and (
            target == Path(target.anchor)
            or target.is_symlink()
            or not target.is_dir()
            or not os.access(target.parent, os.W_OK)
        ):
            raise UpdateError(
                "MailDesk.app 所在目录不可写，请从发行页面下载 DMG 手动安装"
            )
        if _is_relative_to(source, target):
            raise UpdateError("更新暂存区不能位于待替换的程序目录内")

        process_id = os.getpid() if parent_pid is None else parent_pid
        if process_id <= 0:
            raise ValueError("parent_pid 必须大于零")
        transaction_id = self._acquire_update_lock()
        if staged.transaction_id and staged.transaction_id != transaction_id:
            self.release_update_lock()
            raise UpdateError("更新暂存事务与当前进程不一致")
        backup = target.with_name(
            f".{target.name}.maildesk-backup-{staged.update.release.version}-{process_id}"
        )
        incoming = target.with_name(
            f".{target.name}.maildesk-incoming-"
            f"{staged.update.release.version}-{transaction_id}"
        )
        health_token = uuid4().hex
        ready_path = self.updates_dir / f".installer-ready-{transaction_id}"
        health_path = self.updates_dir / f".health-{transaction_id}"
        result_path = self.updates_dir / f"install-result-{transaction_id}.log"
        helper_manifest_path: Path | None = None
        helper_manifest_sha256 = ""
        script_suffix = ".sh" if mode is InstallMode.MACOS_APP else ".ps1"
        script_path = self.updates_dir / (
            f"install-v{staged.update.release.version}-{mode.value}-"
            f"{transaction_id}{script_suffix}"
        )
        try:
            self.updates_dir.mkdir(parents=True, exist_ok=True)
            for marker in (ready_path, health_path, result_path):
                marker.unlink(missing_ok=True)
            if mode is InstallMode.MACOS_APP:
                helper_manifest_path = self.updates_dir / (
                    f".macos-content-{transaction_id}.manifest"
                )
                helper_manifest_sha256 = _write_macos_helper_manifest(
                    content_root,
                    helper_manifest_path,
                )
                script_path.write_text(
                    _MACOS_INSTALLER_SCRIPT,
                    encoding="utf-8",
                    newline="\n",
                )
                script_path.chmod(0o700)
            else:
                script_path.write_text(
                    _POWERSHELL_INSTALLER_SCRIPT,
                    encoding="utf-8-sig",
                    newline="\r\n",
                )
        except OSError as exc:
            self.release_update_lock()
            raise UpdateError("无法创建更新安装脚本") from exc
        if mode is InstallMode.MACOS_APP:
            if helper_manifest_path is None:
                raise UpdateError("无法创建 macOS 更新完整性清单")
            command = (
                "/bin/zsh",
                str(script_path),
                str(process_id),
                str(source),
                str(target),
                str(backup),
                str(restart_executable),
                str(self.transaction_lock_path),
                str(incoming),
                str(ready_path),
                str(health_path),
                str(result_path),
                str(staging_root),
                health_token,
                str(content_root),
                str(helper_manifest_path),
                helper_manifest_sha256,
            )
        else:
            powershell = str(
                powershell_executable or _default_powershell_executable()
            )
            command = (
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-ParentPid",
                str(process_id),
                "-Mode",
                mode.value,
                "-SourcePath",
                str(source),
                "-TargetPath",
                str(target),
                "-BackupPath",
                str(backup),
                "-RestartExecutable",
                str(restart_executable),
                "-LockPath",
                str(self.transaction_lock_path),
                "-IncomingPath",
                str(incoming),
                "-ReadyPath",
                str(ready_path),
                "-HealthPath",
                str(health_path),
                "-ResultPath",
                str(result_path),
                "-CleanupPath",
                str(staging_root),
                "-HealthToken",
                health_token,
                "-ContentRoot",
                str(content_root),
                "-ContentManifestPath",
                str(content_manifest_path),
                "-ContentManifestSha256",
                content_manifest_sha256,
            )
        return InstallerPlan(
            script_path=script_path,
            command=command,
            source_path=source,
            target_path=target,
            backup_path=backup,
            restart_executable=restart_executable,
            parent_pid=process_id,
            lock_path=self.transaction_lock_path,
            incoming_path=incoming,
            ready_path=ready_path,
            health_path=health_path,
            result_path=result_path,
            cleanup_path=staging_root,
            health_token=health_token,
            content_root=content_root,
            content_manifest_path=content_manifest_path,
            content_manifest_sha256=content_manifest_sha256,
            helper_manifest_path=helper_manifest_path,
            helper_manifest_sha256=helper_manifest_sha256,
        )

    def launch_installer(self, plan: InstallerPlan) -> subprocess.Popen[bytes]:
        """Launch the external helper; the GUI should quit only after this succeeds."""

        creation_flags = 0
        if os.name == "nt":
            # PowerShell can silently exit without executing -File when started
            # with DETACHED_PROCESS.  CREATE_NO_WINDOW remains alive after the GUI
            # exits and is verified below through the ready-token handshake.
            creation_flags = subprocess.CREATE_NO_WINDOW
        environment = os.environ.copy()
        for key in tuple(environment):
            if key.casefold() == "psmodulepath":
                environment.pop(key, None)
        diagnostic_path = (
            plan.result_path.parent / f"updater-launch-{plan.health_token}.log"
            if plan.result_path is not None
            else plan.script_path.with_suffix(".launch.log")
        )
        diagnostic_stream: BinaryIO | None = None
        try:
            diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostic_path.write_text(
                "MailDesk updater hand-off\n"
                f"source={plan.source_path}\n"
                f"target={plan.target_path}\n",
                encoding="utf-8",
            )
            diagnostic_stream = diagnostic_path.open("ab", buffering=0)
            process = subprocess.Popen(
                plan.command,
                stdin=subprocess.DEVNULL,
                stdout=diagnostic_stream,
                stderr=subprocess.STDOUT,
                close_fds=True,
                creationflags=creation_flags,
                start_new_session=os.name != "nt",
                env=environment,
            )
        except OSError as exc:
            self.release_update_lock()
            raise UpdateError(
                f"无法启动更新安装程序。诊断日志：{diagnostic_path}"
            ) from exc
        finally:
            if diagnostic_stream is not None:
                diagnostic_stream.close()
        if plan.ready_path is None or not plan.health_token:
            return process
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            try:
                ready = plan.ready_path.read_text(encoding="utf-8-sig").strip()
            except OSError:
                ready = ""
            if hmac.compare_digest(ready, plan.health_token):
                return process
            if process.poll() is not None:
                break
            time.sleep(0.05)
        with suppress(OSError):
            process.terminate()
        self.release_update_lock()
        detail = _read_diagnostic_tail(plan.result_path, diagnostic_path)
        suffix = f"\n{detail}" if detail else ""
        raise UpdateError(
            "更新安装程序未能安全接管，当前版本将继续运行。"
            f"\n诊断日志：{diagnostic_path}{suffix}"
        )

    def _fetch_signed_manifest(
        self,
        client: httpx.Client,
        release: ReleaseInfo,
        manifest_asset: ReleaseAsset,
        signature_asset: ReleaseAsset,
    ) -> SignedUpdateManifest:
        if (
            manifest_asset.size <= 0
            or manifest_asset.size > self._max_manifest_bytes
            or signature_asset.size != 64
            or signature_asset.size > self._max_signature_bytes
        ):
            raise UpdateSecurityError("更新签名文件体积无效")
        manifest_bytes = self._download_small_release_asset(
            client,
            manifest_asset,
            self._max_manifest_bytes,
        )
        signature = self._download_small_release_asset(
            client,
            signature_asset,
            self._max_signature_bytes,
        )
        if len(signature) != 64:
            raise UpdateSecurityError("更新签名格式无效")
        try:
            Ed25519PublicKey.from_public_bytes(self._trusted_public_key).verify(
                signature,
                manifest_bytes,
            )
        except (InvalidSignature, ValueError) as exc:
            raise UpdateSecurityError("新版本未通过 MailDesk 发布者签名验证") from exc
        return _parse_signed_update_manifest(
            manifest_bytes,
            repository=self.repository,
            release_version=release.version,
        )

    def _download_small_release_asset(
        self,
        client: httpx.Client,
        asset: ReleaseAsset,
        limit: int,
    ) -> bytes:
        if asset.size <= 0 or asset.size > limit:
            raise UpdateSecurityError("更新签名文件体积无效")
        response = self._send_with_trusted_redirects(client, asset.download_url)
        try:
            if response.status_code != 200:
                raise UpdateNetworkError("无法下载更新签名文件")
            content = self._read_limited(response, limit)
        finally:
            response.close()
        if len(content) != asset.size:
            raise UpdateSecurityError("更新签名文件下载不完整")
        return content

    def _expected_sha256(
        self, client: httpx.Client, update: UpdateInfo
    ) -> str:
        del client
        asset = update.asset
        if asset is None:
            raise UpdateError("当前更新没有可下载文件")
        expected = update.expected_sha256
        if (
            expected is None
            or not _SHA256_PATTERN.fullmatch(expected)
            or update.expected_size != asset.size
        ):
            raise UpdateSecurityError("更新任务缺少有效的发布者签名清单")
        return expected.casefold()

    def _download_asset(
        self,
        client: httpx.Client,
        asset: ReleaseAsset,
        partial: Path,
        *,
        progress: ProgressCallback | None,
        cancelled: CancelCallback | None,
    ) -> str:
        if cancelled is not None and cancelled():
            raise UpdateCancelledError("更新下载已取消")
        response = self._send_with_trusted_redirects(client, asset.download_url)
        digest = hashlib.sha256()
        received = 0
        try:
            if response.status_code != 200:
                raise UpdateNetworkError("GitHub 更新文件暂时不可用")
            content_length = _content_length(response)
            if content_length is not None and content_length > self._max_download_bytes:
                raise UpdateSecurityError("更新包超过允许的最大体积")
            if asset.size and content_length is not None and content_length != asset.size:
                raise UpdateSecurityError("更新包下载体积与 GitHub 发行信息不一致")
            total = asset.size or content_length
            if progress is not None:
                progress(0, total)
            with partial.open("xb") as stream:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if cancelled is not None and cancelled():
                        raise UpdateCancelledError("更新下载已取消")
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > self._max_download_bytes:
                        raise UpdateSecurityError("更新包超过允许的最大体积")
                    if asset.size and received > asset.size:
                        raise UpdateSecurityError("更新包下载体积与 GitHub 发行信息不一致")
                    stream.write(chunk)
                    digest.update(chunk)
                    if progress is not None:
                        progress(received, total)
            if asset.size and received != asset.size:
                raise UpdateNetworkError("更新包下载不完整")
            if content_length is not None and received != content_length:
                raise UpdateNetworkError("更新包下载不完整")
        finally:
            response.close()
        return digest.hexdigest()

    def _safe_extract_zip(
        self,
        archive_path: Path,
        destination: Path,
        *,
        cancelled: CancelCallback | None = None,
        allow_symlinks: bool = False,
    ) -> None:
        destination_root = destination.resolve()
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > self._max_archive_entries:
                raise UpdateSecurityError("更新包内文件数量异常")
            planned: list[tuple[zipfile.ZipInfo, Path, bool, str | None]] = []
            normalized_names: set[str] = set()
            total_size = 0
            for info in entries:
                if cancelled is not None and cancelled():
                    raise UpdateCancelledError("更新暂存已取消")
                parts = _safe_zip_parts(info, allow_symlinks=allow_symlinks)
                unix_mode = info.external_attr >> 16
                is_symlink = stat.S_ISLNK(unix_mode)
                normalized_name = "/".join(part.casefold() for part in parts)
                if normalized_name in normalized_names:
                    raise UpdateSecurityError("更新包包含名称冲突的文件")
                normalized_names.add(normalized_name)
                total_size += info.file_size
                if info.file_size > self._max_extracted_file_bytes:
                    raise UpdateSecurityError("更新包内单个文件体积异常")
                if total_size > self._max_extracted_bytes:
                    raise UpdateSecurityError("更新包解压后体积异常")
                if (
                    (info.file_size and info.compress_size == 0)
                    or (
                        info.compress_size > 0
                        and info.file_size / info.compress_size
                        > self._max_compression_ratio
                    )
                ):
                    raise UpdateSecurityError("更新包压缩比例异常")
                target = destination_root.joinpath(*parts).resolve()
                if not _is_relative_to(target, destination_root):
                    raise UpdateSecurityError("更新包包含越界路径")
                link_target: str | None = None
                if is_symlink:
                    if info.file_size > 4096:
                        raise UpdateSecurityError("更新包中的符号链接目标过长")
                    raw_target = archive.read(info)
                    try:
                        link_target = raw_target.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise UpdateSecurityError("更新包中的符号链接目标无效") from exc
                    _validate_macos_symlink(parts, link_target)
                planned.append((info, target, is_symlink, link_target))

            extracted_size = 0
            for info, target, is_symlink, _link_target in planned:
                if cancelled is not None and cancelled():
                    raise UpdateCancelledError("更新暂存已取消")
                if is_symlink:
                    continue
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    if allow_symlinks:
                        target.chmod((info.external_attr >> 16) & 0o777 or 0o755)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                file_size = 0
                with archive.open(info, "r") as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        if cancelled is not None and cancelled():
                            raise UpdateCancelledError("更新暂存已取消")
                        file_size += len(chunk)
                        extracted_size += len(chunk)
                        if (
                            file_size > self._max_extracted_file_bytes
                            or extracted_size > self._max_extracted_bytes
                            or file_size > info.file_size
                        ):
                            raise UpdateSecurityError("更新包解压后体积异常")
                        output.write(chunk)
                if file_size != info.file_size:
                    raise UpdateSecurityError("更新包内文件长度无效")
                if allow_symlinks:
                    target.chmod((info.external_attr >> 16) & 0o777 or 0o644)

            for _info, target, is_symlink, link_target in planned:
                if not is_symlink:
                    continue
                if cancelled is not None and cancelled():
                    raise UpdateCancelledError("更新暂存已取消")
                if link_target is None:
                    raise UpdateSecurityError("更新包中的符号链接目标无效")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(link_target)

    @staticmethod
    def _send_with_trusted_redirects(
        client: httpx.Client, url: str, *, max_redirects: int = 5
    ) -> httpx.Response:
        current_url = url
        for redirect_count in range(max_redirects + 1):
            validate_trusted_github_url(current_url)
            request = client.build_request("GET", current_url)
            validate_trusted_github_url(str(request.url))
            response = client.send(request, stream=True)
            if response.status_code not in _REDIRECT_STATUS_CODES:
                return response
            location = response.headers.get("location")
            response.close()
            if not location:
                raise UpdateNetworkError("GitHub 更新服务返回了无效跳转")
            if redirect_count >= max_redirects:
                raise UpdateNetworkError("GitHub 更新服务跳转次数过多")
            current_url = urljoin(str(request.url), location)
        raise UpdateNetworkError("GitHub 更新服务跳转次数过多")

    @staticmethod
    def _read_limited(response: httpx.Response, limit: int) -> bytes:
        content_length = _content_length(response)
        if content_length is not None and content_length > limit:
            raise UpdateSecurityError("更新服务响应体积异常")
        content = bytearray()
        for chunk in response.iter_bytes(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > limit:
                raise UpdateSecurityError("更新服务响应体积异常")
        return bytes(content)


def _parse_signed_update_manifest(
    content: bytes,
    *,
    repository: str,
    release_version: str,
) -> SignedUpdateManifest:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        payload = json.loads(content, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise UpdateSecurityError("更新签名清单格式无效") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "repository",
        "version",
        "assets",
    }:
        raise UpdateSecurityError("更新签名清单结构无效")
    if payload["schema"] != 1 or payload["repository"] != repository:
        raise UpdateSecurityError("更新签名清单不属于当前 MailDesk 仓库")
    version = payload["version"]
    if not isinstance(version, str) or version != release_version:
        raise UpdateSecurityError("更新签名清单版本与 Release 不一致")
    try:
        parsed_version = _SemanticVersion.parse(version)
    except ValueError as exc:
        raise UpdateSecurityError("更新签名清单版本无效") from exc
    if parsed_version.prerelease or parsed_version.normalized != version:
        raise UpdateSecurityError("更新签名清单版本无效")

    raw_assets = payload["assets"]
    if not isinstance(raw_assets, dict) or not 1 <= len(raw_assets) <= 32:
        raise UpdateSecurityError("更新签名清单的文件列表无效")
    assets: list[SignedManifestAsset] = []
    for name, raw_asset in raw_assets.items():
        if not isinstance(name, str) or not _plain_asset_name(name):
            raise UpdateSecurityError("更新签名清单包含无效文件名")
        if not isinstance(raw_asset, dict) or set(raw_asset) != {"sha256", "size"}:
            raise UpdateSecurityError("更新签名清单包含无效文件信息")
        size = raw_asset["size"]
        digest = raw_asset["sha256"]
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
            or not isinstance(digest, str)
            or not _SHA256_PATTERN.fullmatch(digest)
        ):
            raise UpdateSecurityError("更新签名清单包含无效文件信息")
        assets.append(
            SignedManifestAsset(
                name=name,
                size=size,
                sha256=digest.casefold(),
            )
        )
    return SignedUpdateManifest(
        repository=repository,
        version=version,
        assets=tuple(assets),
    )


def _checksum_for_asset(checksum_text: str, asset_name: str) -> str:
    matches: list[str] = []
    for line in checksum_text.splitlines():
        match = _CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            continue
        if match.group(2) == asset_name:
            matches.append(match.group(1).casefold())
    if len(matches) != 1:
        raise UpdateSecurityError("SHA256SUMS.txt 未包含唯一的目标更新包摘要")
    return matches[0]


def _content_length(response: httpx.Response) -> int | None:
    raw_length = response.headers.get("content-length")
    if raw_length is None:
        return None
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise UpdateSecurityError("更新服务返回了无效的文件长度") from exc
    if length < 0:
        raise UpdateSecurityError("更新服务返回了无效的文件长度")
    return length


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_staged_windows_executable(path: Path, version: str) -> None:
    if os.name != "nt" or not bool(getattr(sys, "frozen", False)):
        return
    try:
        with path.open("rb") as stream:
            dos_header = stream.read(64)
            if len(dos_header) != 64 or dos_header[:2] != b"MZ":
                raise ValueError("missing DOS header")
            pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
            if pe_offset < 64 or pe_offset > 64 * 1024 * 1024:
                raise ValueError("invalid PE offset")
            stream.seek(pe_offset)
            pe_header = stream.read(6)
        if len(pe_header) != 6 or pe_header[:4] != b"PE\0\0":
            raise ValueError("missing PE header")
        if struct.unpack_from("<H", pe_header, 4)[0] != 0x8664:
            raise ValueError("not an x64 executable")
        import win32api  # type: ignore[import-not-found]

        info = win32api.GetFileVersionInfo(str(path), "\\")
        file_version_ms = int(info["FileVersionMS"])
        file_version_ls = int(info["FileVersionLS"])
        actual = (
            file_version_ms >> 16,
            file_version_ms & 0xFFFF,
            file_version_ls >> 16,
            file_version_ls & 0xFFFF,
        )
        expected = (*map(int, version.split(".")), 0)
        if actual != expected:
            raise ValueError("version mismatch")
    except (OSError, KeyError, TypeError, ValueError, struct.error) as exc:
        raise UpdateSecurityError(
            "更新包中的 MailDesk.exe 不是预期版本的 Windows x64 程序"
        ) from exc


def _normalize_macos_arch(machine: str) -> str:
    normalized = machine.casefold().strip()
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    if normalized in {"x86_64", "amd64", "x64"}:
        return "x64"
    raise UpdateError(f"当前 macOS 架构不支持自动更新：{machine}")


def _macos_app_bundle(executable: Path) -> Path | None:
    candidate = Path(executable)
    if candidate.name != "MailDesk" or candidate.parent.name != "MacOS":
        return None
    contents = candidate.parent.parent
    bundle = contents.parent
    if contents.name != "Contents" or bundle.suffix.casefold() != ".app":
        return None
    return bundle


def _validate_macos_symlink(parts: tuple[str, ...], target: str) -> None:
    if (
        not target
        or len(target.encode("utf-8")) > 4096
        or any(character in target for character in ("\x00", "\r", "\n", "\t", "\\"))
        or PurePosixPath(target).is_absolute()
    ):
        raise UpdateSecurityError("更新包中的符号链接目标无效")
    parent = posixpath.dirname("/".join(parts))
    normalized = posixpath.normpath(posixpath.join(parent, target))
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise UpdateSecurityError("更新包中的符号链接越界")


def _staged_content_paths(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for current_root, directories, filenames in os.walk(root, followlinks=False):
        current = Path(current_root)
        retained_directories: list[str] = []
        for name in directories:
            candidate = current / name
            if candidate.is_symlink():
                paths.append(candidate)
            elif candidate.is_dir():
                retained_directories.append(name)
            else:
                raise UpdateSecurityError("更新暂存区包含特殊文件")
        directories[:] = retained_directories
        for name in filenames:
            candidate = current / name
            if candidate.is_symlink() or candidate.is_file():
                paths.append(candidate)
            else:
                raise UpdateSecurityError("更新暂存区包含特殊文件")
    return tuple(paths)


def _macho_architectures(path: Path) -> frozenset[str]:
    data = path.read_bytes()[:4096]
    if len(data) < 8:
        raise ValueError("Mach-O header is truncated")
    magic = data[:4]
    thin_endian: str | None = None
    if magic in {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf"}:
        thin_endian = ">"
    elif magic in {b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"}:
        thin_endian = "<"
    if thin_endian is not None:
        cpu_type = struct.unpack_from(f"{thin_endian}I", data, 4)[0]
        return frozenset({_macho_cpu_name(cpu_type)})

    if magic not in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}:
        raise ValueError("not a Mach-O executable")
    endian = ">" if magic == b"\xca\xfe\xba\xbe" else "<"
    count = struct.unpack_from(f"{endian}I", data, 4)[0]
    if not 1 <= count <= 16 or len(data) < 8 + count * 20:
        raise ValueError("invalid fat Mach-O header")
    return frozenset(
        _macho_cpu_name(struct.unpack_from(f"{endian}I", data, 8 + index * 20)[0])
        for index in range(count)
    )


def _macho_cpu_name(cpu_type: int) -> str:
    if cpu_type == 0x0100000C:
        return "arm64"
    if cpu_type == 0x01000007:
        return "x64"
    raise ValueError(f"unsupported Mach-O CPU type: {cpu_type:#x}")


def _validate_staged_macos_app(app: Path, version: str, arch: str) -> None:
    executable = app / "Contents" / "MacOS" / "MailDesk"
    info_path = app / "Contents" / "Info.plist"
    try:
        if app.is_symlink() or not app.is_dir() or not info_path.is_file():
            raise ValueError("invalid app bundle")
        info = plistlib.loads(info_path.read_bytes())
        if not isinstance(info, dict):
            raise ValueError("invalid Info.plist")
        if info.get("CFBundleIdentifier") != "com.maildesk.app":
            raise ValueError("bundle identifier mismatch")
        if info.get("CFBundleShortVersionString") != version:
            raise ValueError("bundle version mismatch")
        minimum = str(info.get("LSMinimumSystemVersion", ""))
        if not re.fullmatch(r"\d+(?:\.\d+){1,2}", minimum):
            raise ValueError("minimum macOS version missing")
        if arch not in _macho_architectures(executable):
            raise ValueError("Mach-O architecture mismatch")
        if not executable.stat().st_mode & stat.S_IXUSR:
            raise ValueError("MailDesk entry point is not executable")
    except (OSError, TypeError, ValueError, plistlib.InvalidFileException) as exc:
        raise UpdateSecurityError(
            f"更新包中的 MailDesk.app 不是预期版本的 macOS {arch} 应用"
        ) from exc


def _write_staged_content_manifest(
    content_root: Path,
    files: tuple[Path, ...],
    manifest_path: Path,
    *,
    cancelled: CancelCallback | None = None,
    allow_symlinks: bool = False,
) -> str:
    entries: list[dict[str, object]] = []
    for path in sorted(files, key=lambda item: item.relative_to(content_root).as_posix()):
        if cancelled is not None and cancelled():
            raise UpdateCancelledError("更新暂存已取消")
        relative = path.relative_to(content_root).as_posix()
        if not relative or relative.startswith("../") or any(
            character in relative for character in ("\r", "\n", "\t", "\\")
        ):
            raise UpdateSecurityError("更新暂存区文件路径无效")
        if path.is_symlink():
            if not allow_symlinks:
                raise UpdateSecurityError("更新暂存区包含链接或特殊文件")
            target = os.readlink(path)
            _validate_macos_symlink(tuple(PurePosixPath(relative).parts), target)
            entries.append(
                {
                    "path": relative,
                    "target": target,
                    "type": "symlink",
                }
            )
            continue
        if not path.is_file():
            raise UpdateSecurityError("更新暂存区包含链接或特殊文件")
        entry: dict[str, object] = {
            "path": relative,
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        if allow_symlinks:
            entry["type"] = "file"
        entries.append(entry)
    if not entries:
        raise UpdateSecurityError("更新暂存区没有可安装文件")
    content = json.dumps(
        {"schema": 2 if allow_symlinks else 1, "files": entries},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest_path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _verify_staged_content_manifest(
    content_root: Path,
    manifest_path: Path,
    expected_sha256: str,
) -> None:
    try:
        content = manifest_path.read_bytes()
        if not hmac.compare_digest(
            hashlib.sha256(content).hexdigest(),
            expected_sha256.casefold(),
        ):
            raise ValueError("manifest hash mismatch")
        payload = json.loads(content)
        files = payload["files"]
        schema = payload.get("schema")
        if schema not in {1, 2} or not isinstance(files, list):
            raise ValueError("manifest schema")
        if not 1 <= len(files) <= 30_000:
            raise ValueError("manifest file count")
        root = content_root.resolve()
        used_paths: set[str] = set()
        manifest_paths: set[str] = set()
        for entry in files:
            if not isinstance(entry, dict):
                raise ValueError("manifest entry")
            relative = entry["path"]
            if (
                not isinstance(relative, str)
                or not relative
                or any(character in relative for character in ("\r", "\n", "\t", "\\"))
                or PurePosixPath(relative).is_absolute()
                or any(part in {"", ".", ".."} for part in PurePosixPath(relative).parts)
            ):
                raise ValueError("manifest entry value")
            normalized = relative.casefold()
            if normalized in used_paths:
                raise ValueError("duplicate manifest path")
            used_paths.add(normalized)
            candidate = root.joinpath(*PurePosixPath(relative).parts)
            manifest_paths.add(relative)
            entry_type = entry.get("type", "file")
            if schema == 1 and set(entry) != {"path", "sha256", "size"}:
                raise ValueError("manifest v1 entry")
            if entry_type == "file":
                if set(entry) not in (
                    {"path", "sha256", "size"},
                    {"path", "sha256", "size", "type"},
                ):
                    raise ValueError("manifest file entry")
                size = entry["size"]
                digest = entry["sha256"]
                if (
                    not isinstance(size, int)
                    or isinstance(size, bool)
                    or size < 0
                    or not isinstance(digest, str)
                    or not _SHA256_PATTERN.fullmatch(digest)
                    or candidate.is_symlink()
                    or not candidate.is_file()
                    or candidate.stat().st_size != size
                    or not hmac.compare_digest(_sha256_file(candidate), digest.casefold())
                ):
                    raise ValueError("staged content mismatch")
            elif schema == 2 and entry_type == "symlink":
                if set(entry) != {"path", "target", "type"}:
                    raise ValueError("manifest symlink entry")
                target = entry["target"]
                if not isinstance(target, str):
                    raise ValueError("manifest symlink target")
                _validate_macos_symlink(tuple(PurePosixPath(relative).parts), target)
                if not candidate.is_symlink() or os.readlink(candidate) != target:
                    raise ValueError("staged symlink mismatch")
            else:
                raise ValueError("manifest entry type")
        actual_paths = {
            path.relative_to(root).as_posix()
            for path in _staged_content_paths(root)
            if path.resolve() != manifest_path.resolve()
        }
        if actual_paths != manifest_paths:
            raise ValueError("staged content contains unlisted entries")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UpdateSecurityError("更新暂存文件已被修改，已阻止安装") from exc


def _write_macos_helper_manifest(content_root: Path, target: Path) -> str:
    lines: list[str] = []
    for path in sorted(
        _staged_content_paths(content_root),
        key=lambda item: item.relative_to(content_root).as_posix(),
    ):
        relative = path.relative_to(content_root).as_posix()
        if any(character in relative for character in ("\r", "\n", "\t", "\\")):
            raise UpdateSecurityError("macOS 更新文件路径无法安全交给安装助手")
        if path.is_symlink():
            link_target = os.readlink(path)
            _validate_macos_symlink(tuple(PurePosixPath(relative).parts), link_target)
            lines.append(f"L\t-\t-\t{relative}\t{link_target}\n")
        elif path.is_file():
            lines.append(
                f"F\t{_sha256_file(path)}\t{path.stat().st_size}\t{relative}\t\n"
            )
        else:
            raise UpdateSecurityError("macOS 更新暂存区包含特殊文件")
    if not lines:
        raise UpdateSecurityError("macOS 更新暂存区没有可安装文件")
    content = "".join(lines).encode("utf-8")
    target.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _safe_zip_parts(
    info: zipfile.ZipInfo, *, allow_symlinks: bool = False
) -> tuple[str, ...]:
    name = info.filename
    if not name or any(character in name for character in ("\x00", "\r", "\n", "\t", "\\")):
        raise UpdateSecurityError("更新包包含无效路径")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UpdateSecurityError("更新包包含越界路径")
    parts = tuple(path.parts)
    for part in parts:
        stem = part.split(".", 1)[0].casefold()
        if (
            ":" in part
            or part.endswith((" ", "."))
            or stem in _WINDOWS_RESERVED_NAMES
        ):
            raise UpdateSecurityError("更新包包含 Windows 不支持的路径")
    if info.flag_bits & 0x1:
        raise UpdateSecurityError("更新包包含加密文件")
    unix_mode = info.external_attr >> 16
    file_type = stat.S_IFMT(unix_mode)
    if stat.S_ISLNK(unix_mode) and not allow_symlinks:
        raise UpdateSecurityError("更新包包含链接或特殊文件")
    allowed_types = (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK)
    if file_type not in allowed_types:
        raise UpdateSecurityError("更新包包含链接或特殊文件")
    if unix_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
        raise UpdateSecurityError("更新包包含不安全的文件权限")
    if (info.is_dir() and file_type == stat.S_IFREG) or (
        not info.is_dir() and file_type == stat.S_IFDIR
    ):
        raise UpdateSecurityError("更新包文件类型与路径不一致")
    return parts


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _default_powershell_executable() -> str:
    system_root = os.environ.get("SYSTEMROOT")
    if system_root:
        candidate = (
            Path(system_root)
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        if candidate.is_file():
            return str(candidate)
    return "powershell.exe"


_MACOS_INSTALLER_SCRIPT = r'''#!/bin/zsh
set -u

ParentPid="$1"
SourcePath="$2"
TargetPath="$3"
BackupPath="$4"
RestartExecutable="$5"
LockPath="$6"
IncomingPath="$7"
ReadyPath="$8"
HealthPath="$9"
ResultPath="${10}"
CleanupPath="${11}"
HealthToken="${12}"
ContentRoot="${13}"
ContentManifestPath="${14}"
ContentManifestSha256="${15}"
HelperLock="${LockPath}.helper"
OriginalMoved=0
NewPid=""

write_result() {
    /usr/bin/printf '%s\n' "$1" > "$ResultPath" 2>/dev/null || true
}

cleanup_helper_lock() {
    /bin/rmdir "$HelperLock" 2>/dev/null || true
}

restart_old_version() {
    if [[ -x "$RestartExecutable" ]]; then
        "$RestartExecutable" >/dev/null 2>&1 &
    fi
}

rollback_update() {
    if [[ -n "$NewPid" ]] && /bin/kill -0 "$NewPid" 2>/dev/null; then
        /bin/kill -9 "$NewPid" 2>/dev/null || true
    fi
    if [[ -e "$IncomingPath" || -L "$IncomingPath" ]]; then
        /bin/rm -rf -- "$IncomingPath" 2>/dev/null || true
    fi
    if [[ "$OriginalMoved" == "1" ]]; then
        if [[ -e "$TargetPath" || -L "$TargetPath" ]]; then
            /bin/rm -rf -- "$TargetPath" 2>/dev/null || true
        fi
        if [[ -e "$BackupPath" ]]; then
            /bin/mv "$BackupPath" "$TargetPath" 2>/dev/null || true
        fi
    fi
}

fail_update() {
    local reason="${1//$'\n'/ }"
    reason="${reason//$'\r'/ }"
    rollback_update
    /usr/bin/printf 'failed_and_rolled_back\n%s\n' \
        "${reason[1,1024]}" > "$ResultPath" 2>/dev/null || true
    restart_old_version
    cleanup_helper_lock
    exit 1
}

validate_relative_path() {
    local value="$1"
    if [[ -z "$value" || "$value" == /* || "$value" == *\\* \
        || "$value" == *$'\n'* || "$value" == *$'\r'* || "$value" == *$'\t'* ]]; then
        return 1
    fi
    local -a segments
    segments=("${(@s:/:)value}")
    local segment
    for segment in "${segments[@]}"; do
        if [[ -z "$segment" || "$segment" == "." || "$segment" == ".." ]]; then
            return 1
        fi
    done
    return 0
}

validate_link_target() {
    local relative="$1"
    local target="$2"
    if [[ -z "$target" || "$target" == /* || "$target" == *\\* \
        || "$target" == *$'\n'* || "$target" == *$'\r'* || "$target" == *$'\t'* ]]; then
        return 1
    fi
    local combined="${relative:h}/$target"
    local -a segments
    segments=("${(@s:/:)combined}")
    local segment
    local -i depth=0
    for segment in "${segments[@]}"; do
        if [[ -z "$segment" || "$segment" == "." ]]; then
            continue
        fi
        if [[ "$segment" == ".." ]]; then
            (( depth -= 1 ))
            if (( depth < 0 )); then
                return 1
            fi
        else
            (( depth += 1 ))
        fi
    done
    (( depth > 0 ))
}

if ! /usr/bin/printf '%s' "$HealthToken" > "$ReadyPath"; then
    exit 3
fi

Deadline=$(( SECONDS + 120 ))
while /bin/kill -0 "$ParentPid" 2>/dev/null; do
    if (( SECONDS >= Deadline )); then
        write_result "parent_exit_timeout"
        exit 4
    fi
    /bin/sleep 0.1
done

if ! /bin/mkdir "$HelperLock" 2>/dev/null; then
    write_result "transaction_lock_failed"
    restart_old_version
    exit 2
fi
trap cleanup_helper_lock EXIT

TargetParent="${TargetPath:h}"
if [[ "$TargetPath" != *.app || "$SourcePath" != *.app \
    || "$ContentRoot" != "$SourcePath" \
    || "$RestartExecutable" != "$TargetPath/Contents/MacOS/MailDesk" \
    || "${BackupPath:h}" != "$TargetParent" \
    || "${IncomingPath:h}" != "$TargetParent" \
    || "$BackupPath" != "$TargetParent/.${TargetPath:t}.maildesk-backup-"* \
    || "$IncomingPath" != "$TargetParent/.${TargetPath:t}.maildesk-incoming-"* ]]; then
    fail_update "unsafe updater path"
fi

if [[ ! -d "$SourcePath" || -L "$SourcePath" \
    || ! -x "$SourcePath/Contents/MacOS/MailDesk" \
    || ! -f "$ContentManifestPath" || -L "$ContentManifestPath" ]]; then
    fail_update "staged macOS app is incomplete"
fi

ManifestHash="$(
    /usr/bin/shasum -a 256 "$ContentManifestPath" 2>/dev/null \
        | /usr/bin/awk '{print $1}'
)"
if [[ "$ManifestHash" != "$ContentManifestSha256" ]]; then
    fail_update "staged content manifest hash mismatch"
fi

EntryCount=0
while IFS=$'\t' read -r Kind Digest Size Relative LinkTarget \
    || [[ -n "$Kind$Digest$Size$Relative$LinkTarget" ]]; do
    if ! validate_relative_path "$Relative"; then
        fail_update "invalid staged content path"
    fi
    Candidate="$ContentRoot/$Relative"
    case "$Kind" in
        F)
            if [[ ! -f "$Candidate" || -L "$Candidate" || "$Size" != <-> ]]; then
                fail_update "staged file is missing"
            fi
            ActualSize="$(/usr/bin/stat -f '%z' "$Candidate" 2>/dev/null)"
            ActualHash="$(
                /usr/bin/shasum -a 256 "$Candidate" 2>/dev/null \
                    | /usr/bin/awk '{print $1}'
            )"
            if [[ "$ActualSize" != "$Size" || "$ActualHash" != "$Digest" ]]; then
                fail_update "staged file integrity check failed"
            fi
            ;;
        L)
            if [[ ! -L "$Candidate" ]] || ! validate_link_target "$Relative" "$LinkTarget"; then
                fail_update "staged symbolic link is invalid"
            fi
            ActualTarget="$(/usr/bin/readlink "$Candidate" 2>/dev/null)"
            if [[ "$ActualTarget" != "$LinkTarget" ]]; then
                fail_update "staged symbolic link changed"
            fi
            ;;
        *)
            fail_update "staged content manifest entry is invalid"
            ;;
    esac
    (( EntryCount += 1 ))
done < "$ContentManifestPath"

ActualCount="$(
    /usr/bin/find "$ContentRoot" \( -type f -o -type l \) -print \
        | /usr/bin/wc -l | /usr/bin/tr -d ' '
)"
SpecialEntry="$(/usr/bin/find "$ContentRoot" ! -type d ! -type f ! -type l -print -quit)"
if (( EntryCount < 1 )) || [[ "$ActualCount" != "$EntryCount" || -n "$SpecialEntry" ]]; then
    fail_update "staged content contains unlisted entries"
fi

if [[ -e "$IncomingPath" || -L "$IncomingPath" ]]; then
    /bin/rm -rf -- "$IncomingPath" || fail_update "cannot clean incoming app"
fi
if ! /usr/bin/ditto "$SourcePath" "$IncomingPath"; then
    fail_update "cannot copy incoming app"
fi
if [[ ! -x "$IncomingPath/Contents/MacOS/MailDesk" ]]; then
    fail_update "incoming app entry point is missing"
fi
if [[ -e "$BackupPath" || -L "$BackupPath" ]]; then
    /bin/rm -rf -- "$BackupPath" || fail_update "cannot clean previous backup"
fi
if ! /bin/mv "$TargetPath" "$BackupPath"; then
    fail_update "cannot back up current app"
fi
OriginalMoved=1
if ! /bin/mv "$IncomingPath" "$TargetPath"; then
    fail_update "cannot activate incoming app"
fi

MAILDESK_UPDATE_HEALTH_TOKEN="$HealthToken" \
MAILDESK_UPDATE_HEALTH_FILE="$HealthPath" \
    "$RestartExecutable" >/dev/null 2>&1 &
NewPid=$!
Deadline=$(( SECONDS + 120 ))
Healthy=0
while (( SECONDS < Deadline )); do
    if [[ -f "$HealthPath" ]] \
        && [[ "$(/bin/cat "$HealthPath" 2>/dev/null)" == "$HealthToken" ]]; then
        Healthy=1
        break
    fi
    if ! /bin/kill -0 "$NewPid" 2>/dev/null; then
        break
    fi
    /bin/sleep 0.25
done
if [[ "$Healthy" != "1" ]]; then
    fail_update "new MailDesk process did not report healthy startup"
fi
/bin/sleep 3
if ! /bin/kill -0 "$NewPid" 2>/dev/null; then
    fail_update "new MailDesk process exited during startup health check"
fi

write_result "success"
/bin/rm -rf -- "$BackupPath" "$CleanupPath" 2>/dev/null || true
/bin/rm -f -- "$HealthPath" "$ReadyPath" "$ContentManifestPath" 2>/dev/null || true
cleanup_helper_lock
exit 0
'''


_POWERSHELL_INSTALLER_SCRIPT = r'''param(
    [Parameter(Mandatory = $true)][int]$ParentPid,
    [Parameter(Mandatory = $true)][ValidateSet("onefile", "onedir")][string]$Mode,
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$TargetPath,
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [Parameter(Mandatory = $true)][string]$RestartExecutable,
    [Parameter(Mandatory = $true)][string]$LockPath,
    [Parameter(Mandatory = $true)][string]$IncomingPath,
    [Parameter(Mandatory = $true)][string]$ReadyPath,
    [Parameter(Mandatory = $true)][string]$HealthPath,
    [Parameter(Mandatory = $true)][string]$ResultPath,
    [Parameter(Mandatory = $true)][string]$CleanupPath,
    [Parameter(Mandatory = $true)][ValidatePattern("^[0-9a-f]{32}$")][string]$HealthToken,
    [Parameter(Mandatory = $true)][string]$ContentRoot,
    [Parameter(Mandatory = $true)][string]$ContentManifestPath,
    [Parameter(Mandatory = $true)][ValidatePattern("^[0-9a-f]{64}$")][string]$ContentManifestSha256
)

$ErrorActionPreference = "Stop"

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $Stream = [System.IO.File]::Open(
        $LiteralPath,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    $Hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $HashBytes = $Hasher.ComputeHash($Stream)
        return [System.BitConverter]::ToString($HashBytes).Replace("-", "").ToLowerInvariant()
    } finally {
        $Hasher.Dispose()
        $Stream.Dispose()
    }
}

try {
    Set-Content -LiteralPath $ReadyPath -Value $HealthToken -Encoding UTF8 -NoNewline
} catch {
    exit 3
}

try {
    $ParentProcess = Get-Process -Id $ParentPid -ErrorAction Stop
    if (-not $ParentProcess.WaitForExit(120000)) {
        Set-Content -LiteralPath $ResultPath -Value "parent_exit_timeout" -Encoding UTF8
        exit 4
    }
} catch {
    # The parent already exited between helper launch and process lookup.
}

try {
    $LockStream = [System.IO.File]::Open(
        $LockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch {
    Set-Content -LiteralPath $ResultPath -Value "transaction_lock_failed" -Encoding UTF8
    if (Test-Path -LiteralPath $RestartExecutable) {
        Start-Process `
            -FilePath $RestartExecutable `
            -WorkingDirectory (Split-Path -Parent $RestartExecutable)
    }
    exit 2
}

$HadOriginal = Test-Path -LiteralPath $TargetPath
$OriginalMoved = $false

try {
    $ManifestItem = Get-Item -LiteralPath $ContentManifestPath -Force
    if (($ManifestItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Update content manifest is a reparse point"
    }
    $ManifestHash = Get-Sha256Hex -LiteralPath $ContentManifestPath
    if ($ManifestHash -cne $ContentManifestSha256) {
        throw "Update content manifest hash mismatch"
    }
    $ContentManifest = Get-Content -LiteralPath $ContentManifestPath -Raw |
        ConvertFrom-Json
    if ($ContentManifest.schema -ne 1 -or $ContentManifest.files.Count -lt 1) {
        throw "Update content manifest format is invalid"
    }
    $NormalizedRoot = [System.IO.Path]::GetFullPath($ContentRoot).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    foreach ($FileEntry in $ContentManifest.files) {
        $RelativePath = [string]$FileEntry.path
        $Segments = $RelativePath.Split('/')
        if (
            [System.IO.Path]::IsPathRooted($RelativePath) -or
            $Segments.Count -lt 1 -or
            ($Segments | Where-Object { $_ -eq "" -or $_ -eq "." -or $_ -eq ".." }).Count -gt 0
        ) {
            throw "Update content manifest path is invalid"
        }
        $PlatformRelative = $Segments -join [System.IO.Path]::DirectorySeparatorChar
        $Candidate = [System.IO.Path]::GetFullPath(
            [System.IO.Path]::Combine($ContentRoot, $PlatformRelative)
        )
        if (-not $Candidate.StartsWith(
            $NormalizedRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Update content manifest path escapes staging"
        }
        $CandidateItem = Get-Item -LiteralPath $Candidate -Force
        $CandidateHash = Get-Sha256Hex -LiteralPath $Candidate
        if (
            $CandidateItem.PSIsContainer -or
            ($CandidateItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $CandidateItem.Length -ne [int64]$FileEntry.size -or
            $CandidateHash -cne [string]$FileEntry.sha256
        ) {
            throw "Update staged file integrity check failed"
        }
    }
    $SourceItem = Get-Item -LiteralPath $SourcePath -Force
    if (($SourceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Update source is a reparse point"
    }
    if ($Mode -eq "onedir") {
        $ReparseItem = Get-ChildItem -LiteralPath $SourcePath -Force -Recurse |
            Where-Object {
                ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            } |
            Select-Object -First 1
        if ($null -ne $ReparseItem) {
            throw "Update source contains a reparse point"
        }
    }
    if (Test-Path -LiteralPath $IncomingPath) {
        Remove-Item -LiteralPath $IncomingPath -Recurse -Force
    }
    if ($Mode -eq "onefile") {
        Copy-Item -LiteralPath $SourcePath -Destination $IncomingPath -Force
        if (-not (Test-Path -LiteralPath $IncomingPath -PathType Leaf)) {
            throw "Incoming onefile executable is missing"
        }
    } else {
        Copy-Item -LiteralPath $SourcePath -Destination $IncomingPath -Recurse -Force
        if (-not (Test-Path -LiteralPath (Join-Path $IncomingPath "MailDesk.exe") -PathType Leaf)) {
            throw "Incoming onedir executable is missing"
        }
        if (-not (Test-Path `
            -LiteralPath (Join-Path $IncomingPath "_internal") `
            -PathType Container
        )) {
            throw "Incoming onedir runtime is missing"
        }
    }
    if (Test-Path -LiteralPath $BackupPath) {
        Remove-Item -LiteralPath $BackupPath -Recurse -Force
    }
    if ($HadOriginal) {
        Move-Item -LiteralPath $TargetPath -Destination $BackupPath
        $OriginalMoved = $true
    }
    Move-Item -LiteralPath $IncomingPath -Destination $TargetPath
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $RestartExecutable
    $StartInfo.WorkingDirectory = Split-Path -Parent $RestartExecutable
    $StartInfo.UseShellExecute = $false
    $StartInfo.EnvironmentVariables["MAILDESK_UPDATE_HEALTH_TOKEN"] = $HealthToken
    $StartInfo.EnvironmentVariables["MAILDESK_UPDATE_HEALTH_FILE"] = $HealthPath
    $NewProcess = [System.Diagnostics.Process]::Start($StartInfo)
    if ($null -eq $NewProcess) {
        throw "Unable to start the new MailDesk process"
    }
    $Healthy = $false
    $Deadline = [DateTime]::UtcNow.AddSeconds(120)
    while ([DateTime]::UtcNow -lt $Deadline) {
        if (Test-Path -LiteralPath $HealthPath -PathType Leaf) {
            $HealthValue = (Get-Content -LiteralPath $HealthPath -Raw).Trim()
            if ($HealthValue -ceq $HealthToken) {
                $Healthy = $true
                break
            }
        }
        $NewProcess.Refresh()
        if ($NewProcess.HasExited) {
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $Healthy) {
        $NewProcess.Refresh()
        $ProcessExited = $NewProcess.HasExited
        $ExitCode = if ($ProcessExited) { [string]$NewProcess.ExitCode } else { "running" }
        $MarkerExists = Test-Path -LiteralPath $HealthPath -PathType Leaf
        if (-not $NewProcess.HasExited) {
            Stop-Process -Id $NewProcess.Id -Force -ErrorAction SilentlyContinue
        }
        throw (
            "New MailDesk process did not report healthy startup " +
            "(exited=$ProcessExited; exit_code=$ExitCode; marker_exists=$MarkerExists)"
        )
    }
    Start-Sleep -Seconds 3
    $NewProcess.Refresh()
    if ($NewProcess.HasExited) {
        throw "New MailDesk process exited during startup health check"
    }
    Set-Content -LiteralPath $ResultPath -Value "success" -Encoding UTF8
    try {
        if (Test-Path -LiteralPath $BackupPath) {
            Remove-Item -LiteralPath $BackupPath -Recurse -Force
        }
        if (Test-Path -LiteralPath $CleanupPath) {
            Remove-Item -LiteralPath $CleanupPath -Recurse -Force
        }
        Remove-Item -LiteralPath $HealthPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ReadyPath -Force -ErrorAction SilentlyContinue
    } catch {
        # Cleanup failure does not invalidate an otherwise healthy update.
    }
    $LockStream.Dispose()
    exit 0
} catch {
    $FailureReason = ([string]$_.Exception.Message -replace "[\r\n]+", " ").Trim()
    if ($FailureReason.Length -gt 1024) {
        $FailureReason = $FailureReason.Substring(0, 1024)
    }
    try {
        Remove-Item Env:MAILDESK_UPDATE_HEALTH_TOKEN -ErrorAction SilentlyContinue
        Remove-Item Env:MAILDESK_UPDATE_HEALTH_FILE -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $IncomingPath) {
            Remove-Item -LiteralPath $IncomingPath -Recurse -Force
        }
        if ($OriginalMoved) {
            if (Test-Path -LiteralPath $TargetPath) {
                Remove-Item -LiteralPath $TargetPath -Recurse -Force
            }
            if (Test-Path -LiteralPath $BackupPath) {
                Move-Item -LiteralPath $BackupPath -Destination $TargetPath
            }
        } elseif (-not $HadOriginal -and (Test-Path -LiteralPath $TargetPath)) {
            Remove-Item -LiteralPath $TargetPath -Recurse -Force
        }
        try {
            $FailureOutcome = "failed_and_rolled_back"
            if (-not [string]::IsNullOrWhiteSpace($FailureReason)) {
                $FailureOutcome += "`n" + $FailureReason
            }
            Set-Content `
                -LiteralPath $ResultPath `
                -Value $FailureOutcome `
                -Encoding UTF8
        } catch {
            # A diagnostic write failure must not prevent restarting the old version.
        }
        if (Test-Path -LiteralPath $RestartExecutable) {
            Start-Process `
                -FilePath $RestartExecutable `
                -WorkingDirectory (Split-Path -Parent $RestartExecutable)
        }
    } catch {
        # Preserve the original failure exit code even if rollback also fails.
    }
    try {
        if (-not (Test-Path -LiteralPath $ResultPath -PathType Leaf)) {
            Set-Content `
                -LiteralPath $ResultPath `
                -Value "failed_rollback_incomplete" `
                -Encoding UTF8
        }
    } catch {
        # The updater still exits with failure if diagnostics cannot be written.
    }
    $LockStream.Dispose()
    exit 1
}
'''
