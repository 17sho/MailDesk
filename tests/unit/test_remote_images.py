from __future__ import annotations

import httpx

from mailbox_manager.mail import remote_images


def test_remote_image_url_policy_rejects_private_protocol_credentials_and_controls(
    monkeypatch,
) -> None:
    assert remote_images._is_safe_url("http://127.0.0.1/image.png") is False
    assert remote_images._is_safe_url("http://localhost/image.png") is False
    assert remote_images._is_safe_url("file:///C:/secret.png") is False
    assert remote_images._is_safe_url("https://user:password@example.com/image.png") is False
    assert remote_images._is_safe_url("https://example.com:99999/image.png") is False
    assert remote_images._is_safe_url("https://example.com/image.png\nInjected: value") is False

    monkeypatch.setattr(remote_images, "_is_public_host", lambda hostname: True)
    assert remote_images._is_safe_url("https://images.example.com/image.png") is True


def test_remote_image_download_still_enforces_stream_size(monkeypatch) -> None:
    monkeypatch.setattr(remote_images, "MAX_REMOTE_IMAGE_SIZE", 4)
    monkeypatch.setattr(remote_images, "_is_safe_url", lambda url: True)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=b"12345",
            request=request,
        )
    )
    with httpx.Client(transport=transport) as client:
        result = remote_images._download_image(client, "https://images.example.com/image.png")

    assert result is None


def test_remote_image_redirect_is_revalidated_against_ssrf(monkeypatch) -> None:
    monkeypatch.setattr(
        remote_images,
        "_is_public_host",
        lambda hostname: hostname == "public.example",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private.png"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = remote_images._download_image(client, "https://public.example/image.png")

    assert result is None


def test_remote_image_uses_file_signature_when_server_mime_is_wrong(monkeypatch) -> None:
    monkeypatch.setattr(remote_images, "_is_safe_url", lambda url: True)
    png = b"\x89PNG\r\n\x1a\n" + b"payload"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/octet-stream"},
            content=png,
            request=request,
        )
    )
    with httpx.Client(transport=transport) as client:
        result = remote_images._download_image(
            client, "https://images.example.com/no-extension"
        )

    assert result == ("image/png", png)
