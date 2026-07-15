from __future__ import annotations

import poplib
import socket
import ssl
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace

from mailbox_manager.domain.models import (
    ConnectionResult,
    EmailAccount,
    FetchRequest,
    FetchResult,
    MailFolder,
    PostAction,
    ProxyConfig,
)
from mailbox_manager.domain.status import AccountStatus
from mailbox_manager.mail.parser import parse_email_message
from mailbox_manager.protocols.base import EmailClientBase
from mailbox_manager.protocols.proxy_socket import create_proxy_socket

PopConnection = poplib.POP3 | poplib.POP3_SSL
ConnectionFactory = Callable[..., PopConnection]


class Pop3Client(EmailClientBase):
    def __init__(
        self,
        account: EmailAccount,
        *,
        timeout: float = 20.0,
        connection_factory: ConnectionFactory | None = None,
        proxy: ProxyConfig | None = None,
    ) -> None:
        self._account = account
        self._timeout = timeout
        self._factory = connection_factory
        self._connection: PopConnection | None = None
        self._proxy = proxy

    def _connect(self) -> PopConnection:
        if self._connection is not None:
            return self._connection
        factory = self._factory
        if factory is None and self._proxy is not None:
            connection = _proxy_pop_connection(
                self._account.host,
                self._account.port,
                self._account.security.value == "ssl",
                self._proxy,
                self._timeout,
            )
            factory = None
        else:
            connection = None
        if factory is None and connection is None:
            factory = (
                poplib.POP3_SSL
                if self._account.security.value == "ssl"
                else poplib.POP3
            )
        if connection is None:
            connection = factory(
                self._account.host, self._account.port, timeout=self._timeout
            )
        if self._account.security.value == "starttls":
            connection.stls(context=ssl.create_default_context())
        connection.user(self._account.username or self._account.email)
        connection.pass_(self._account.secret)
        self._connection = connection
        return connection

    def test_connection(self) -> ConnectionResult:
        try:
            self._connect().stat()
            return ConnectionResult(AccountStatus.SUCCESS, "POP3 连接成功")
        except Exception as exc:
            status, detail = _classify_pop_error(exc)
            return ConnectionResult(status, detail)

    def list_folders(self) -> list[MailFolder]:
        return [MailFolder("INBOX", "INBOX")]

    def fetch_messages(self, request: FetchRequest) -> FetchResult:
        messages = []
        try:
            connection = self._connect()
            count, _size = connection.stat()
            identifiers = _pop_transport_ids(connection, count)
            candidates = [
                (number, transport_id)
                for number, transport_id in reversed(identifiers)
                if ("INBOX", transport_id) not in request.known_transport_ids
            ]
            if not request.unlimited:
                candidates = candidates[: request.max_messages]
            for number, transport_id in candidates:
                _status, lines, _octets = connection.retr(number)
                raw = b"\r\n".join(lines) + b"\r\n"
                message = replace(
                    parse_email_message(
                        raw,
                        folder="INBOX",
                        keywords=request.keywords,
                        custom_pattern=request.custom_pattern,
                    ),
                    transport_id=transport_id,
                )
                if not request.include_raw:
                    message = replace(message, raw_eml=b"")
                messages.append(message)
                if (
                    message.matched_values
                    and request.post_action is PostAction.DELETE
                    and request.confirmed_actions
                ):
                    connection.dele(number)
            return FetchResult(AccountStatus.SUCCESS, tuple(messages), "POP3 收取完成")
        except Exception as exc:
            status, detail = _classify_pop_error(exc)
            return FetchResult(status, tuple(messages), detail)

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            with suppress(poplib.error_proto, OSError):
                connection.quit()


def _pop_transport_ids(connection: PopConnection, count: int) -> list[tuple[int, str]]:
    """Prefer stable POP3 UIDL values and fall back to session message numbers."""

    try:
        _status, rows, _octets = connection.uidl()
        parsed: list[tuple[int, str]] = []
        for row in rows:
            parts = row.decode("ascii", errors="ignore").split()
            if len(parts) >= 2 and parts[0].isdigit() and parts[1]:
                parsed.append((int(parts[0]), parts[1]))
        if parsed:
            return parsed
    except (AttributeError, OSError, poplib.error_proto):
        pass
    return [(number, str(number)) for number in range(1, count + 1)]


def _classify_pop_error(exc: Exception) -> tuple[AccountStatus, str]:
    if isinstance(exc, poplib.error_proto):
        return AccountStatus.AUTH_FAILED, "POP3 鉴权失败，请检查授权码"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return AccountStatus.TIMEOUT, "POP3 连接超时"
    if isinstance(exc, (OSError, ssl.SSLError)):
        return AccountStatus.NETWORK_ERROR, "无法连接 POP3 服务器"
    return AccountStatus.UNKNOWN_ERROR, "POP3 收件发生未知错误"


def _proxy_pop_connection(
    host: str,
    port: int,
    use_ssl: bool,
    proxy: ProxyConfig,
    timeout: float,
) -> PopConnection:
    class ProxyPop(poplib.POP3):
        def _create_socket(self, socket_timeout):
            return create_proxy_socket(proxy, (self.host, self.port), socket_timeout)

    class ProxyPopSsl(poplib.POP3_SSL):
        def _create_socket(self, socket_timeout):
            raw = create_proxy_socket(proxy, (self.host, self.port), socket_timeout)
            return self.context.wrap_socket(raw, server_hostname=self.host)

    implementation = ProxyPopSsl if use_ssl else ProxyPop
    return implementation(host, port, timeout=timeout)
