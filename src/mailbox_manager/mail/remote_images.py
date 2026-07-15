from __future__ import annotations

import ipaddress
import socket
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import httpx

from mailbox_manager.mail.parser import remote_image_urls, sanitize_email_html
from mailbox_manager.mail.web_document import (
    sanitize_email_web_source,
    web_remote_image_urls,
)

MAX_REMOTE_IMAGES = 20
MAX_REMOTE_IMAGE_SIZE = 3 * 1024 * 1024
MAX_REMOTE_TOTAL_SIZE = 12 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_REDIRECT_CODES = {301, 302, 303, 307, 308}
_CACHE_MAX_ITEMS = 64
_CACHE_MAX_BYTES = 24 * 1024 * 1024
_IMAGE_CACHE: OrderedDict[str, tuple[str, bytes]] = OrderedDict()
_IMAGE_CACHE_BYTES = 0
_IMAGE_CACHE_LOCK = threading.Lock()


def _is_public_host(hostname: str) -> bool:
    lowered = hostname.casefold().rstrip(".")
    if not lowered or lowered == "localhost" or lowered.endswith(".localhost"):
        return False
    try:
        addresses = [ipaddress.ip_address(lowered)]
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(lowered, None, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


def _is_safe_url(url: str) -> bool:
    if not url or len(url) > 4096 or any(ord(character) < 32 for character in url):
        return False
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme.casefold() in {"http", "https"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65535)
        and _is_public_host(parsed.hostname)
    )


def _download_image(client: httpx.Client, url: str) -> tuple[str, bytes] | None:
    current = url
    for _ in range(4):
        if not _is_safe_url(current):
            return None
        try:
            with client.stream("GET", current, headers={"Accept": "image/*"}) as response:
                if response.status_code in _REDIRECT_CODES:
                    location = response.headers.get("location", "")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    return None
                declared_length = response.headers.get("content-length", "")
                if declared_length.isdigit() and int(declared_length) > MAX_REMOTE_IMAGE_SIZE:
                    return None
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_REMOTE_IMAGE_SIZE:
                        return None
                    chunks.append(chunk)
                payload = b"".join(chunks)
                content_type = _sniff_image_content_type(payload)
                return (content_type, payload) if content_type else None
        except httpx.HTTPError:
            return None
    return None


def load_remote_images(html_body: str) -> tuple[str, int, int]:
    """Download bounded public images after an explicit user action.

    Returns rendered HTML, successfully loaded count, and total remote image count.
    """

    urls = remote_image_urls(html_body)
    images = _download_images(urls)
    rendered = sanitize_email_html(
        html_body,
        remote_images=images,
        remote_policy="embed",
    )
    return rendered, len(images), len(urls)


def _download_images(urls: tuple[str, ...]) -> dict[str, tuple[str, bytes]]:
    images: dict[str, tuple[str, bytes]] = {}
    total_size = 0
    candidates: list[str] = []
    for url in urls[:MAX_REMOTE_IMAGES]:
        cached = _cached_image(url)
        if cached is None:
            candidates.append(url)
            continue
        if total_size + len(cached[1]) > MAX_REMOTE_TOTAL_SIZE:
            return images
        images[url] = cached
        total_size += len(cached[1])
    with httpx.Client(
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=False,
        headers={"User-Agent": "MailDesk/1.0 (email image viewer)"},
    ) as client:
        # Four concurrent requests keep visual mail responsive without opening a
        # large connection burst to tracking/image hosts.
        for offset in range(0, len(candidates), 4):
            batch = candidates[offset : offset + 4]
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                downloaded_batch = list(
                    executor.map(lambda url: _download_image(client, url), batch)
                )
            for url, downloaded in zip(batch, downloaded_batch, strict=True):
                if downloaded is None:
                    continue
                _cache_image(url, downloaded)
                if total_size + len(downloaded[1]) > MAX_REMOTE_TOTAL_SIZE:
                    return images
                images[url] = downloaded
                total_size += len(downloaded[1])
    return images


def _sniff_image_content_type(payload: bytes) -> str:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _cached_image(url: str) -> tuple[str, bytes] | None:
    with _IMAGE_CACHE_LOCK:
        value = _IMAGE_CACHE.get(url)
        if value is not None:
            _IMAGE_CACHE.move_to_end(url)
        return value


def _cache_image(url: str, value: tuple[str, bytes]) -> None:
    global _IMAGE_CACHE_BYTES
    if len(value[1]) > _CACHE_MAX_BYTES:
        return
    with _IMAGE_CACHE_LOCK:
        previous = _IMAGE_CACHE.pop(url, None)
        if previous is not None:
            _IMAGE_CACHE_BYTES -= len(previous[1])
        _IMAGE_CACHE[url] = value
        _IMAGE_CACHE_BYTES += len(value[1])
        while (
            len(_IMAGE_CACHE) > _CACHE_MAX_ITEMS
            or _IMAGE_CACHE_BYTES > _CACHE_MAX_BYTES
        ):
            _old_url, old_value = _IMAGE_CACHE.popitem(last=False)
            _IMAGE_CACHE_BYTES -= len(old_value[1])


def load_remote_images_for_web(html_body: str) -> tuple[str, int, int]:
    """Download bounded public images and retain the email's safe visual layout."""

    urls = web_remote_image_urls(html_body)
    images = _download_images(urls)
    rendered = sanitize_email_web_source(
        html_body,
        remote_images=images,
        remote_policy="embed",
    )
    return rendered, len(images), len(urls)
