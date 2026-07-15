from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mailbox_manager.services.update_service import (
    CHECKSUM_ASSET_NAME,
    SIGNED_MANIFEST_ASSET_NAME,
    SIGNED_MANIFEST_SIGNATURE_NAME,
    DownloadedUpdate,
    InstallMode,
    ReleaseAsset,
    ReleaseInfo,
    StagedUpdate,
    UpdateCancelledError,
    UpdateError,
    UpdateInfo,
    UpdateSecurityError,
    UpdateService,
    compare_versions,
    consume_install_result,
    detect_install_mode,
    is_newer_version,
    parse_github_release,
    validate_trusted_github_url,
)

REPOSITORY = "17sho/MailDesk"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
_TEST_SIGNING_KEY = Ed25519PrivateKey.from_private_bytes(b"S" * 32)
_TEST_PUBLIC_KEY = _TEST_SIGNING_KEY.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw,
)
_SIGNED_FIXTURES: dict[str, bytes] = {}


@pytest.fixture(scope="module")
def packaged_update_health_probe(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if os.name != "nt":
        pytest.skip("PyInstaller update probe is Windows-only")
    root = tmp_path_factory.mktemp("packaged-update-health-probe")
    script = root / "probe.py"
    script.write_text(
        "import os\n"
        "import time\n"
        "from pathlib import Path\n"
        "token = os.environ.get('MAILDESK_UPDATE_HEALTH_TOKEN', '')\n"
        "target = os.environ.get('MAILDESK_UPDATE_HEALTH_FILE', '')\n"
        "if not token or not target:\n"
        "    raise SystemExit(7)\n"
        "marker = Path(target)\n"
        "marker.write_text(token, encoding='utf-8')\n"
        "deadline = time.monotonic() + 10\n"
        "while marker.exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.1)\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile",
            "--name",
            "MailDesk",
            "--distpath",
            str(root / "dist"),
            "--workpath",
            str(root / "work"),
            "--specpath",
            str(root),
            "--log-level",
            "ERROR",
            str(script),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    executable = root / "dist" / "MailDesk.exe"
    if completed.returncode != 0 or not executable.is_file():
        diagnostics = "\n".join(
            output.strip() for output in (completed.stdout, completed.stderr) if output
        )
        raise AssertionError(f"Unable to package update probe: {diagnostics}")
    return executable


def _asset_url(name: str) -> str:
    return f"https://github.com/{REPOSITORY}/releases/download/v0.3.0/{name}"


def _release_payload(
    archive: bytes,
    *,
    version: str = "0.3.0",
    mode: InstallMode = InstallMode.ONEFILE,
    digest: str | None | object = ...,  # type: ignore[assignment]
    include_checksums: bool = True,
) -> dict[str, object]:
    archive_name = f"MailDesk-v{version}-windows-x64-{mode.value}.zip"
    if digest is ...:
        digest = f"sha256:{hashlib.sha256(archive).hexdigest()}"
    assets: list[dict[str, object]] = [
        {
            "name": archive_name,
            "browser_download_url": _asset_url(archive_name).replace(
                "v0.3.0", f"v{version}"
            ),
            "size": len(archive),
            "digest": digest,
        }
    ]
    if include_checksums:
        checksums = (
            f"{hashlib.sha256(archive).hexdigest()}  {archive_name}\n".encode()
        )
        assets.append(
            {
                "name": CHECKSUM_ASSET_NAME,
                "browser_download_url": _asset_url(CHECKSUM_ASSET_NAME).replace(
                    "v0.3.0", f"v{version}"
                ),
                "size": len(checksums),
                "digest": None,
            }
        )
    manifest = json.dumps(
        {
            "schema": 1,
            "repository": REPOSITORY,
            "version": version,
            "assets": {
                archive_name: {
                    "sha256": hashlib.sha256(archive).hexdigest(),
                    "size": len(archive),
                }
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = _TEST_SIGNING_KEY.sign(manifest)
    for name, content in (
        (SIGNED_MANIFEST_ASSET_NAME, manifest),
        (SIGNED_MANIFEST_SIGNATURE_NAME, signature),
    ):
        url = _asset_url(name).replace("v0.3.0", f"v{version}")
        _SIGNED_FIXTURES[url] = content
        assets.append(
            {
                "name": name,
                "browser_download_url": url,
                "size": len(content),
                "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
            }
        )
    return {
        "draft": False,
        "prerelease": False,
        "tag_name": f"v{version}",
        "name": f"MailDesk {version}",
        "body": "## Changes\n\n- Safe updater",
        "html_url": f"https://github.com/{REPOSITORY}/releases/tag/v{version}",
        "published_at": "2026-07-15T00:00:00Z",
        "assets": assets,
    }


def _zip_payload(mode: InstallMode, *, version: str = "0.3.0") -> bytes:
    stream = io.BytesIO()
    prefix = f"MailDesk-v{version}-windows-x64-{mode.value}"
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if mode is InstallMode.ONEFILE:
            archive.writestr(f"{prefix}/MailDesk.exe", b"new onefile executable")
        else:
            archive.writestr(f"{prefix}/MailDesk/MailDesk.exe", b"new onedir executable")
            archive.writestr(f"{prefix}/MailDesk/_internal/runtime.dll", b"runtime")
        archive.writestr(f"{prefix}/LICENSE", b"MIT")
    return stream.getvalue()


def _json_response(request: httpx.Request, payload: object) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        request=request,
    )


def _service(
    tmp_path: Path,
    handler,
    *,
    mode: InstallMode = InstallMode.ONEFILE,
    **limits,
) -> UpdateService:
    def signed_fixture_transport(request: httpx.Request) -> httpx.Response:
        content = _SIGNED_FIXTURES.get(str(request.url))
        if content is not None:
            return httpx.Response(
                200,
                content=content,
                headers={"content-length": str(len(content))},
                request=request,
            )
        return handler(request)

    return UpdateService(
        current_version="0.2.0",
        updates_dir=tmp_path / "updates",
        install_mode=mode,
        trusted_public_key=_TEST_PUBLIC_KEY,
        transport=httpx.MockTransport(signed_fixture_transport),
        **limits,
    )


def _static_update(mode: InstallMode, archive: bytes) -> UpdateInfo:
    version = "0.3.0"
    name = f"MailDesk-v{version}-windows-x64-{mode.value}.zip"
    asset = ReleaseAsset(
        name=name,
        download_url=_asset_url(name),
        size=len(archive),
        digest=f"sha256:{hashlib.sha256(archive).hexdigest()}",
    )
    release = ReleaseInfo(
        version=version,
        tag_name=f"v{version}",
        name=f"MailDesk {version}",
        notes="notes",
        page_url=f"https://github.com/{REPOSITORY}/releases/tag/v{version}",
        published_at=None,
        assets=(asset,),
    )
    return UpdateInfo(
        current_version="0.2.0",
        release=release,
        install_mode=mode,
        asset=asset,
        checksum_asset=None,
        expected_sha256=hashlib.sha256(archive).hexdigest(),
        expected_size=len(archive),
    )


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("0.3.0", "0.2.9", 1),
        ("v1.0.0", "1.0.0+build.9", 0),
        ("1.0.0-alpha", "1.0.0-alpha.1", -1),
        ("1.0.0-alpha.1", "1.0.0-alpha.beta", -1),
        ("1.0.0-beta.11", "1.0.0-rc.1", -1),
        ("1.0.0-rc.1", "1.0.0", -1),
    ],
)
def test_semantic_version_precedence(left: str, right: str, expected: int) -> None:
    assert compare_versions(left, right) == expected
    assert is_newer_version(left, right) is (expected > 0)


@pytest.mark.parametrize("version", ["1", "1.2", "01.2.3", "1.2.3-01", "latest"])
def test_semantic_version_rejects_invalid_values(version: str) -> None:
    with pytest.raises(ValueError):
        compare_versions(version, "1.0.0")


def test_detects_source_onefile_and_onedir_modes() -> None:
    assert detect_install_mode(frozen=False, meipass="ignored") is InstallMode.SOURCE
    assert detect_install_mode(frozen=True, meipass=r"C:\Temp\_MEI123") is InstallMode.ONEFILE
    assert detect_install_mode(frozen=True, meipass=r"C:\MailDesk\_internal") is InstallMode.ONEDIR


def test_parse_release_rejects_drafts_prereleases_and_duplicate_assets() -> None:
    archive = b"archive"
    draft = _release_payload(archive)
    draft["draft"] = True
    with pytest.raises(UpdateError, match="正式发行"):
        parse_github_release(draft)

    prerelease = _release_payload(archive, version="0.3.0-beta.1")
    with pytest.raises(UpdateError, match="正式发行"):
        parse_github_release(prerelease)

    duplicate = _release_payload(archive)
    duplicate["assets"] = [*duplicate["assets"], duplicate["assets"][0]]  # type: ignore[index]
    with pytest.raises(UpdateError, match="重复文件"):
        parse_github_release(duplicate)


def test_check_update_uses_exact_mode_asset_and_source_never_selects_installer(
    tmp_path: Path,
) -> None:
    archive = _zip_payload(InstallMode.ONEFILE)
    payload = _release_payload(archive)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == API_URL
        return _json_response(request, payload)

    onefile = _service(tmp_path, handler).check_for_update()
    assert onefile is not None
    assert onefile.install_supported
    assert onefile.asset is not None
    assert onefile.asset.name == "MailDesk-v0.3.0-windows-x64-onefile.zip"

    source = _service(tmp_path, handler, mode=InstallMode.SOURCE).check_for_update()
    assert source is not None
    assert source.install_mode is InstallMode.SOURCE
    assert source.asset is None
    assert not source.install_supported


def test_check_update_returns_none_when_latest_is_not_newer(tmp_path: Path) -> None:
    payload = _release_payload(b"archive", version="0.2.0")

    service = _service(
        tmp_path,
        lambda request: _json_response(request, payload),
    )

    assert service.check_for_update() is None


def test_update_check_requires_valid_offline_publisher_signature(tmp_path: Path) -> None:
    archive = _zip_payload(InstallMode.ONEFILE)
    payload = _release_payload(archive)
    signature_url = _asset_url(SIGNED_MANIFEST_SIGNATURE_NAME)
    original_signature = _SIGNED_FIXTURES[signature_url]
    _SIGNED_FIXTURES[signature_url] = b"X" * 64

    try:
        service = _service(
            tmp_path,
            lambda request: _json_response(request, payload),
        )
        with pytest.raises(UpdateSecurityError, match="发布者签名"):
            service.check_for_update()
    finally:
        _SIGNED_FIXTURES[signature_url] = original_signature

    payload_without_signature = _release_payload(archive)
    payload_without_signature["assets"] = [
        asset
        for asset in payload_without_signature["assets"]  # type: ignore[index]
        if asset["name"] != SIGNED_MANIFEST_SIGNATURE_NAME
    ]
    unsigned_service = _service(
        tmp_path,
        lambda request: _json_response(request, payload_without_signature),
    )
    with pytest.raises(UpdateSecurityError, match=r"缺少.*发布签名"):
        unsigned_service.check_for_update()


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/17sho/MailDesk/releases/download/file.zip",
        "https://example.com/file.zip",
        "https://user:secret@github.com/file.zip",
        "https://github.com:444/file.zip",
    ],
)
def test_rejects_untrusted_update_urls(url: str) -> None:
    with pytest.raises(UpdateSecurityError):
        validate_trusted_github_url(url)


def test_untrusted_redirect_is_rejected_before_request(tmp_path: Path) -> None:
    archive = _zip_payload(InstallMode.ONEFILE)
    payload = _release_payload(archive)
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if str(request.url) == API_URL:
            return _json_response(request, payload)
        return httpx.Response(
            302,
            headers={"location": "https://attacker.example/update.zip"},
            request=request,
        )

    service = _service(tmp_path, handler)
    update = service.check_for_update()
    assert update is not None
    with pytest.raises(UpdateSecurityError, match="受信任"):
        service.download_update(update)
    assert requested_hosts == ["api.github.com", "github.com"]


def test_download_follows_trusted_redirect_verifies_digest_and_reports_progress(
    tmp_path: Path,
) -> None:
    archive = _zip_payload(InstallMode.ONEFILE)
    payload = _release_payload(archive)
    asset_name = "MailDesk-v0.3.0-windows-x64-onefile.zip"
    progress: list[tuple[int, int | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == API_URL:
            return _json_response(request, payload)
        if request.url.host == "github.com":
            return httpx.Response(
                302,
                headers={
                    "location": f"https://release-assets.githubusercontent.com/{asset_name}"
                },
                request=request,
            )
        return httpx.Response(
            200,
            content=archive,
            headers={"content-length": str(len(archive))},
            request=request,
        )

    service = _service(tmp_path, handler)
    update = service.check_for_update()
    assert update is not None
    downloaded = service.download_update(
        update,
        progress=lambda done, total: progress.append((done, total)),
    )

    assert downloaded.archive_path.read_bytes() == archive
    assert downloaded.sha256 == hashlib.sha256(archive).hexdigest()
    assert progress[0] == (0, len(archive))
    assert progress[-1] == (len(archive), len(archive))
    assert not downloaded.archive_path.with_name(
        f"{downloaded.archive_path.name}.part"
    ).exists()


def test_signed_manifest_allows_release_without_github_digest(tmp_path: Path) -> None:
    archive = _zip_payload(InstallMode.ONEFILE)
    payload = _release_payload(archive, digest=None)
    archive_name = "MailDesk-v0.3.0-windows-x64-onefile.zip"
    checksum = f"{hashlib.sha256(archive).hexdigest()}  {archive_name}\n".encode()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == API_URL:
            return _json_response(request, payload)
        if request.url.path.endswith(CHECKSUM_ASSET_NAME):
            return httpx.Response(200, content=checksum, request=request)
        return httpx.Response(200, content=archive, request=request)

    service = _service(tmp_path, handler)
    update = service.check_for_update()
    assert update is not None

    downloaded = service.download_update(update)

    assert downloaded.archive_path.read_bytes() == archive


def test_mismatched_github_digest_is_rejected_and_cancellation_cleans_partial(
    tmp_path: Path,
) -> None:
    archive = _zip_payload(InstallMode.ONEFILE)
    payload = _release_payload(archive, digest=f"sha256:{'0' * 64}")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == API_URL:
            return _json_response(request, payload)
        return httpx.Response(200, content=archive, request=request)

    service = _service(tmp_path, handler)
    with pytest.raises(UpdateSecurityError, match="摘要与签名清单"):
        service.check_for_update()

    valid_payload = _release_payload(archive)

    def valid_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == API_URL:
            return _json_response(request, valid_payload)
        return httpx.Response(200, content=archive, request=request)

    service = _service(tmp_path, valid_handler)
    update = service.check_for_update()
    assert update is not None and update.asset is not None
    with pytest.raises(UpdateCancelledError):
        service.download_update(update, cancelled=lambda: True)
    assert list(service.updates_dir.glob("*.part")) == []


def test_update_transaction_lock_prevents_two_instances_sharing_staging(
    tmp_path: Path,
) -> None:
    archive = _zip_payload(InstallMode.ONEFILE)
    payload = _release_payload(archive)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == API_URL:
            return _json_response(request, payload)
        return httpx.Response(200, content=archive, request=request)

    first = _service(tmp_path, handler)
    second = _service(tmp_path, handler)
    first_update = first.check_for_update()
    second_update = second.check_for_update()
    assert first_update is not None and second_update is not None

    first_download = first.download_update(first_update)
    with pytest.raises(UpdateError, match="另一个 MailDesk 实例"):
        second.download_update(second_update)
    assert first_download.transaction_id

    first.release_update_lock()
    second_download = second.download_update(second_update)
    assert second_download.transaction_id != first_download.transaction_id
    second.release_update_lock()


def test_install_result_is_consumed_once_and_history_is_retained(tmp_path: Path) -> None:
    updates = tmp_path / "updates"
    updates.mkdir()
    result = updates / "install-result-operation.log"
    result.write_text("failed_and_rolled_back", encoding="utf-8-sig")

    assert consume_install_result(updates) == "failed_and_rolled_back"
    assert consume_install_result(updates) is None
    assert (updates / "install-result-operation.log.seen").is_file()


@pytest.mark.parametrize("mode", [InstallMode.ONEFILE, InstallMode.ONEDIR])
def test_stage_valid_release_layout(mode: InstallMode, tmp_path: Path) -> None:
    archive = _zip_payload(mode)
    archive_path = tmp_path / "release.zip"
    archive_path.write_bytes(archive)
    update = _static_update(mode, archive)
    service = _service(tmp_path, lambda request: None, mode=mode)

    staged = service.stage_update(
        DownloadedUpdate(
            update=update,
            archive_path=archive_path,
            sha256=hashlib.sha256(archive).hexdigest(),
        )
    )

    executable = (
        staged.source_path
        if mode is InstallMode.ONEFILE
        else staged.source_path / "MailDesk.exe"
    )
    assert executable.read_bytes().startswith(b"new")
    assert staged.staging_root.parent == service.updates_dir


@pytest.mark.parametrize(
    "malicious_name",
    [
        "../MailDesk.exe",
        "/MailDesk.exe",
        "C:/MailDesk.exe",
        "folder\\..\\MailDesk.exe",
    ],
)
def test_zip_path_traversal_and_windows_paths_are_rejected(
    malicious_name: str, tmp_path: Path
) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(malicious_name, b"malicious")
    payload = stream.getvalue()
    archive_path = tmp_path / "malicious.zip"
    archive_path.write_bytes(payload)
    update = _static_update(InstallMode.ONEFILE, payload)
    service = _service(tmp_path, lambda request: None)

    with pytest.raises(UpdateSecurityError):
        service.stage_update(
            DownloadedUpdate(
                update=update,
                archive_path=archive_path,
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )


def test_zip_symlinks_and_extraction_bombs_are_rejected(tmp_path: Path) -> None:
    stream = io.BytesIO()
    prefix = "MailDesk-v0.3.0-windows-x64-onefile"
    with zipfile.ZipFile(stream, "w") as archive:
        link = zipfile.ZipInfo(f"{prefix}/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "MailDesk.exe")
        archive.writestr(f"{prefix}/MailDesk.exe", b"valid executable")
    symlink_zip = stream.getvalue()
    symlink_path = tmp_path / "symlink.zip"
    symlink_path.write_bytes(symlink_zip)
    update = _static_update(InstallMode.ONEFILE, symlink_zip)
    service = _service(tmp_path, lambda request: None)
    with pytest.raises(UpdateSecurityError, match="链接"):
        service.stage_update(
            DownloadedUpdate(
                update=update,
                archive_path=symlink_path,
                sha256=hashlib.sha256(symlink_zip).hexdigest(),
            )
        )

    bomb = _zip_payload(InstallMode.ONEFILE)
    bomb_path = tmp_path / "bomb.zip"
    bomb_path.write_bytes(bomb)
    bomb_update = _static_update(InstallMode.ONEFILE, bomb)
    limited = _service(
        tmp_path / "limited",
        lambda request: None,
        max_extracted_bytes=5,
        max_extracted_file_bytes=5,
    )
    with pytest.raises(UpdateSecurityError, match="体积"):
        limited.stage_update(
            DownloadedUpdate(
                update=bomb_update,
                archive_path=bomb_path,
                sha256=hashlib.sha256(bomb).hexdigest(),
            )
        )


@pytest.mark.parametrize("mode", [InstallMode.ONEFILE, InstallMode.ONEDIR])
def test_installer_plan_waits_replaces_rolls_back_and_restarts(
    mode: InstallMode, tmp_path: Path
) -> None:
    archive = _zip_payload(mode)
    update = _static_update(mode, archive)
    service = _service(tmp_path / "service", lambda request: None, mode=mode)
    source_root = service.updates_dir / "staging with space"
    if mode is InstallMode.ONEFILE:
        source = source_root / "MailDesk.exe"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"new")
        current = tmp_path / "current app" / "MailDesk.exe"
    else:
        source = source_root / "MailDesk"
        (source / "_internal").mkdir(parents=True)
        (source / "MailDesk.exe").write_bytes(b"new")
        current = tmp_path / "current app" / "MailDesk" / "MailDesk.exe"
    current.parent.mkdir(parents=True)
    current.write_bytes(b"old")
    if mode is InstallMode.ONEDIR:
        (current.parent / "_internal").mkdir()
    staged = StagedUpdate(update=update, staging_root=source_root, source_path=source)

    plan = service.create_installer_plan(
        staged,
        executable_path=current,
        parent_pid=4321,
        powershell_executable="trusted-powershell.exe",
    )

    script = plan.script_path.read_text(encoding="utf-8-sig")
    assert "$ParentProcess.WaitForExit(120000)" in script
    assert "Set-Content -LiteralPath $ReadyPath" in script
    assert "New MailDesk process did not report healthy startup" in script
    assert "Move-Item -LiteralPath $IncomingPath -Destination $TargetPath" in script
    assert "Update staged file integrity check failed" in script
    assert "Move-Item -LiteralPath $TargetPath -Destination $BackupPath" in script
    assert "$OriginalMoved = $true" in script
    assert "if ($OriginalMoved)" in script
    assert "Remove-Item -LiteralPath $TargetPath" in script
    assert "Start-Process" in script
    assert plan.command[0] == "trusted-powershell.exe"
    assert plan.command[plan.command.index("-ParentPid") + 1] == "4321"
    assert plan.command[plan.command.index("-SourcePath") + 1] == str(source.resolve())
    assert plan.ready_path is not None
    assert plan.health_path is not None
    assert plan.content_manifest_path is not None
    assert len(plan.health_token) == 32
    expected_target = current if mode is InstallMode.ONEFILE else current.parent
    assert plan.target_path == expected_target.resolve()
    assert plan.restart_executable == (
        plan.target_path
        if mode is InstallMode.ONEFILE
        else plan.target_path / "MailDesk.exe"
    )


def test_installer_rejects_staging_inside_replaced_onedir(tmp_path: Path) -> None:
    archive = _zip_payload(InstallMode.ONEDIR)
    update = _static_update(InstallMode.ONEDIR, archive)
    current_root = tmp_path / "MailDesk"
    current = current_root / "MailDesk.exe"
    current_root.mkdir()
    current.write_bytes(b"old")
    source = current_root / "updates" / "staged" / "MailDesk"
    (source / "_internal").mkdir(parents=True)
    (source / "MailDesk.exe").write_bytes(b"new")
    (current_root / "_internal").mkdir()
    service = _service(current_root, lambda request: None, mode=InstallMode.ONEDIR)

    with pytest.raises(UpdateError, match="待替换"):
        service.create_installer_plan(
            StagedUpdate(update=update, staging_root=source.parent, source_path=source),
            executable_path=current,
        )


@pytest.mark.skipif(os.name != "nt", reason="PowerShell updater is Windows-only")
@pytest.mark.parametrize("healthy", [True, False], ids=["success", "rollback"])
def test_powershell_helper_replaces_or_rolls_back_real_temp_files(
    tmp_path: Path,
    healthy: bool,
    packaged_update_health_probe: Path,
) -> None:
    archive = _zip_payload(InstallMode.ONEFILE)
    update = _static_update(InstallMode.ONEFILE, archive)
    service = _service(tmp_path / "service", lambda request: None)
    staging = service.updates_dir / "带 空格 staging"
    staging.mkdir(parents=True)
    source = staging / "MailDesk.exe"
    system_directory = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
    source_executable = (
        packaged_update_health_probe if healthy else system_directory / "whoami.exe"
    )
    shutil.copy2(source_executable, source)
    expected_update = source.read_bytes()
    current = tmp_path / "当前 程序" / "MailDesk.exe"
    current.parent.mkdir(parents=True)
    system_executable = system_directory / "where.exe"
    shutil.copy2(system_executable, current)
    original = current.read_bytes()
    staged = StagedUpdate(update=update, staging_root=staging, source_path=source)
    parent = subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "Start-Sleep -Seconds 30",
        ]
    )
    try:
        plan = service.create_installer_plan(
            staged,
            executable_path=current,
            parent_pid=parent.pid,
        )
        helper = service.launch_installer(plan)
        assert plan.ready_path is not None
        assert (
            plan.ready_path.read_text(encoding="utf-8-sig").strip()
            == plan.health_token
        )
    finally:
        service.release_update_lock()
        if parent.poll() is None:
            parent.terminate()
        try:
            parent.wait(timeout=5)
        except subprocess.TimeoutExpired:
            parent.kill()
            parent.wait(timeout=5)
    return_code = helper.wait(timeout=150)

    assert return_code == (0 if healthy else 1)
    assert plan.result_path is not None
    if healthy:
        assert current.read_bytes() == expected_update
        assert plan.result_path.read_text(encoding="utf-8-sig").strip() == "success"
        assert not staging.exists()
    else:
        assert current.read_bytes() == original
        assert (
            plan.result_path.read_text(encoding="utf-8-sig").strip()
            == "failed_and_rolled_back"
        )
    assert not plan.backup_path.exists()
    assert plan.incoming_path is not None and not plan.incoming_path.exists()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell updater is Windows-only")
def test_powershell_helper_rolls_back_an_onedir_start_failure(tmp_path: Path) -> None:
    archive = _zip_payload(InstallMode.ONEDIR)
    update = _static_update(InstallMode.ONEDIR, archive)
    service = _service(
        tmp_path / "service",
        lambda request: None,
        mode=InstallMode.ONEDIR,
    )
    staging = service.updates_dir / "带 空格 onedir staging"
    source = staging / "MailDesk"
    (source / "_internal").mkdir(parents=True)
    (source / "MailDesk.exe").write_bytes(b"not a real executable")
    (source / "_internal" / "runtime.dll").write_bytes(b"new runtime")
    current = tmp_path / "当前 onedir" / "MailDesk.exe"
    (current.parent / "_internal").mkdir(parents=True)
    current.write_bytes(b"old executable")
    old_runtime = current.parent / "_internal" / "runtime.dll"
    old_runtime.write_bytes(b"old runtime")
    parent = subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "Start-Sleep -Milliseconds 250",
        ]
    )
    plan = service.create_installer_plan(
        StagedUpdate(update, staging, source),
        executable_path=current,
        parent_pid=parent.pid,
    )
    helper = service.launch_installer(plan)
    service.release_update_lock()

    assert helper.wait(timeout=30) == 1
    parent.wait(timeout=5)
    assert current.read_bytes() == b"old executable"
    assert old_runtime.read_bytes() == b"old runtime"
    assert not plan.backup_path.exists()
    assert plan.incoming_path is not None and not plan.incoming_path.exists()
