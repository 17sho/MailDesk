from __future__ import annotations

import zipfile
from pathlib import Path

import release


def test_build_release_archives_names_and_versions_windows_packages(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    (root / "dist" / "MailDesk" / "_internal").mkdir(parents=True)
    (root / "legal").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "maildesk"\nversion = "0.2.0"\n', encoding="utf-8"
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

    monkeypatch.setattr(release, "_embedded_version", lambda _path: (0, 2, 0, 0))

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

    assert onefile_zip.name == "MailDesk-v0.2.0-windows-x64-onefile.zip"
    assert onedir_zip.name == "MailDesk-v0.2.0-windows-x64-onedir.zip"
    with zipfile.ZipFile(onefile_zip) as archive:
        names = set(archive.namelist())
        assert "MailDesk-v0.2.0-windows-x64-onefile/MailDesk.exe" in names
        assert (
            "MailDesk-v0.2.0-windows-x64-onefile/"
            "licenses/python-packages/example-1.0/LICENSE"
        ) in names
    with zipfile.ZipFile(onedir_zip) as archive:
        names = set(archive.namelist())
        assert "MailDesk-v0.2.0-windows-x64-onedir/MailDesk/MailDesk.exe" in names
        assert (
            "MailDesk-v0.2.0-windows-x64-onedir/"
            "MailDesk/_internal/runtime.dll"
        ) in names
    checksum_text = checksums.read_text(encoding="utf-8")
    assert f"{release.sha256_file(onefile_zip)}  {onefile_zip.name}" in checksum_text
    assert f"{release.sha256_file(onedir_zip)}  {onedir_zip.name}" in checksum_text
