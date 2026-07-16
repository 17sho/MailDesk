from __future__ import annotations

import argparse
import base64
import os
import platform
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate_protected_key(output: Path) -> str:
    if platform.system() != "Windows":
        raise RuntimeError("DPAPI 发布密钥只能在 Windows 上生成")
    if output.exists():
        raise FileExistsError(f"拒绝覆盖现有发布密钥：{output}")

    import win32crypt

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    protected = win32crypt.CryptProtectData(
        private_pem,
        "MailDesk Ed25519 release signing key",
        None,
        None,
        None,
        0x1,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(protected)
    except Exception:
        output.unlink(missing_ok=True)
        raise

    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public_key).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a DPAPI-protected MailDesk Ed25519 release key"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(r"D:\secure\maildesk-release-signing-ed25519.pem.dpapi"),
    )
    arguments = parser.parse_args()
    public_key = generate_protected_key(arguments.output.resolve())
    print(f"已生成 DPAPI 发布密钥：{arguments.output.resolve()}")
    print(f"更新签名公钥（Base64）：{public_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
