from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import release
from mailbox_manager.services.update_service import (
    SIGNED_MANIFEST_ASSET_NAME,
    SIGNED_MANIFEST_SIGNATURE_NAME,
    TRUSTED_UPDATE_PUBLIC_KEY_B64,
)


def test_build_release_archives_names_and_versions_windows_packages(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    (root / "dist" / "MailDesk" / "_internal").mkdir(parents=True)
    (root / "legal").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "maildesk"\nversion = "0.3.0"\n', encoding="utf-8"
    )
    (root / "dist" / "MailDesk.exe").write_bytes(b"onefile")
    (root / "dist" / "MailDesk" / "MailDesk.exe").write_bytes(b"onedir")
    (root / "dist" / "MailDesk" / "_internal" / "runtime.dll").write_bytes(
        b"runtime"
    )
    for filename in release.COMMON_RELEASE_FILES:
        (root / filename).write_text(filename, encoding="utf-8")
    for filename in ("GPL-3.0.txt", "LGPL-3.0.txt", "PYTHON-3.12.txt"):
        (root / "legal" / filename).write_text(filename, encoding="utf-8")

    monkeypatch.setattr(release, "_embedded_version", lambda _path: (0, 3, 0, 0))

    def fake_collect(target: Path) -> int:
        package = target / "example-1.0"
        package.mkdir(parents=True)
        (package / "LICENSE").write_text("example license", encoding="utf-8")
        return 1

    monkeypatch.setattr(release, "collect_distribution_licenses", fake_collect)
    output = tmp_path / "output"

    onefile_zip, onedir_zip, checksums = release.build_release_archives(
        root=root, output=output
    )

    assert onefile_zip.name == "MailDesk-v0.3.0-windows-x64-onefile.zip"
    assert onedir_zip.name == "MailDesk-v0.3.0-windows-x64-onedir.zip"
    with zipfile.ZipFile(onefile_zip) as archive:
        names = set(archive.namelist())
        assert "MailDesk-v0.3.0-windows-x64-onefile/MailDesk.exe" in names
        assert (
            "MailDesk-v0.3.0-windows-x64-onefile/"
            "licenses/python-packages/example-1.0/LICENSE"
        ) in names
    with zipfile.ZipFile(onedir_zip) as archive:
        names = set(archive.namelist())
        assert "MailDesk-v0.3.0-windows-x64-onedir/MailDesk/MailDesk.exe" in names
        assert (
            "MailDesk-v0.3.0-windows-x64-onedir/"
            "MailDesk/_internal/runtime.dll"
        ) in names
    checksum_text = checksums.read_text(encoding="utf-8")
    assert f"{release.sha256_file(onefile_zip)}  {onefile_zip.name}" in checksum_text
    assert f"{release.sha256_file(onedir_zip)}  {onedir_zip.name}" in checksum_text


def test_signed_update_manifest_binds_both_archives_and_verifies(tmp_path: Path) -> None:
    version = "0.3.0"
    onefile = tmp_path / f"MailDesk-v{version}-windows-x64-onefile.zip"
    onedir = tmp_path / f"MailDesk-v{version}-windows-x64-onedir.zip"
    onefile.write_bytes(b"onefile archive")
    onedir.write_bytes(b"onedir archive")
    private_key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "release-key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )

    manifest, signature = release.build_signed_update_manifest(
        (onefile, onedir),
        version=version,
        signing_key=key_path,
        output=tmp_path,
        expected_public_key=public_key,
    )

    private_key.public_key().verify(signature.read_bytes(), manifest.read_bytes())
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert payload["repository"] == "17sho/MailDesk"
    assert payload["version"] == version
    assert payload["assets"][onefile.name] == {
        "sha256": release.sha256_file(onefile),
        "size": onefile.stat().st_size,
    }
    assert payload["assets"][onedir.name]["sha256"] == release.sha256_file(
        onedir
    )
    assert manifest.name == SIGNED_MANIFEST_ASSET_NAME
    assert signature.name == SIGNED_MANIFEST_SIGNATURE_NAME
    assert release.TRUSTED_UPDATE_PUBLIC_KEY_B64 == TRUSTED_UPDATE_PUBLIC_KEY_B64


def test_signed_manifest_can_bind_synchronized_windows_and_macos_assets(
    tmp_path: Path,
) -> None:
    version = "0.3.3"
    names = (
        f"MailDesk-v{version}-windows-x64-onefile.zip",
        f"MailDesk-v{version}-windows-x64-onedir.zip",
        f"MailDesk-v{version}-macos-arm64.zip",
        f"MailDesk-v{version}-macos-x64.zip",
        f"MailDesk-v{version}-macos-arm64.dmg",
        f"MailDesk-v{version}-macos-x64.dmg",
    )
    assets = tuple(tmp_path / name for name in names)
    for asset in assets:
        asset.write_bytes(asset.name.encode("utf-8"))
    private_key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "release-key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )

    manifest, _signature = release.build_signed_update_manifest(
        assets,
        version=version,
        signing_key=key_path,
        output=tmp_path,
        expected_public_key=public_key,
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert set(payload["assets"]) == set(names)

    with pytest.raises(ValueError, match="同时包含 arm64 与 x64"):
        release.build_signed_update_manifest(
            assets[:3],
            version=version,
            signing_key=key_path,
            output=tmp_path,
            expected_public_key=public_key,
        )


def test_signed_manifest_rejects_private_key_that_clients_do_not_trust(
    tmp_path: Path,
) -> None:
    version = "0.3.0"
    archives = tuple(
        tmp_path / f"MailDesk-v{version}-windows-x64-{mode}.zip"
        for mode in ("onefile", "onedir")
    )
    for archive in archives:
        archive.write_bytes(archive.name.encode())
    private_key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "wrong-key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    with pytest.raises(RuntimeError, match="内置公钥不匹配"):
        release.build_signed_update_manifest(
            archives,
            version=version,
            signing_key=key_path,
            output=tmp_path,
            expected_public_key=b"P" * 32,
        )
