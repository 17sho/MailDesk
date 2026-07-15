from __future__ import annotations

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    FetchResult,
    MailMessage,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


class FakeClient:
    def __init__(self, result: FetchResult) -> None:
        self.result = result
        self.closed = False
        self.request: FetchRequest | None = None

    def fetch_messages(self, request: FetchRequest) -> FetchResult:
        self.request = request
        return self.result

    def close(self) -> None:
        self.closed = True


def test_fetch_service_persists_messages_and_updates_account_status(tmp_path) -> None:
    database = Database(tmp_path / "maildesk.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"C" * 32)
    accounts = AccountRepository(database, cipher)
    account = EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="owner@example.com",
        secret="secret",
    )
    accounts.add_many([account])
    stored = accounts.list_all()[0]
    message = MailMessage(
        provider_message_id="mail-1",
        folder="INBOX",
        subject="验证码",
        matched_values=("123456",),
        text_body="验证码 123456",
    )
    client = FakeClient(FetchResult(AccountStatus.SUCCESS, (message,), "ok"))
    service = FetchService(accounts, MessageRepository(database), client_factory=lambda _a: client)

    result = service.fetch_account(stored, FetchRequest())

    assert result.status is AccountStatus.SUCCESS
    assert client.closed is True
    assert accounts.get(stored.account_id).status is AccountStatus.SUCCESS  # type: ignore[arg-type]
    assert MessageRepository(database).list_for_account(stored.account_id)[0].subject == "验证码"  # type: ignore[arg-type]


def test_fetch_service_passes_persisted_transport_ids_to_client(tmp_path) -> None:
    database = Database(tmp_path / "incremental.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"I" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="incremental@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    stored = accounts.list_all()[0]
    assert stored.account_id is not None
    messages = MessageRepository(database)
    messages.add_many(
        stored.account_id,
        (
            MailMessage(
                provider_message_id="provider-42",
                transport_id="42",
                folder="INBOX",
            ),
        ),
    )
    client = FakeClient(FetchResult(AccountStatus.SUCCESS))
    service = FetchService(accounts, messages, client_factory=lambda _account: client)

    service.fetch_account(stored, FetchRequest())

    assert client.request is not None
    assert client.request.known_transport_ids == frozenset({("INBOX", "42")})


def test_fetch_service_persists_failure_status_without_messages(tmp_path) -> None:
    database = Database(tmp_path / "maildesk.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"D" * 32)
    accounts = AccountRepository(database, cipher)
    accounts.add_many(
        [
            EmailAccount(
                email="owner@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                security=SecurityMode.SSL,
                username="owner@example.com",
                secret="secret",
            )
        ]
    )
    stored = accounts.list_all()[0]
    client = FakeClient(FetchResult(AccountStatus.AUTH_FAILED, detail="bad"))
    service = FetchService(accounts, MessageRepository(database), client_factory=lambda _a: client)

    service.fetch_account(stored, FetchRequest())

    assert accounts.get(stored.account_id).status is AccountStatus.AUTH_FAILED  # type: ignore[arg-type]


def test_fetch_service_converts_unexpected_client_error_to_visible_status(tmp_path) -> None:
    class RaisingClient:
        def fetch_messages(self, _request):
            raise RuntimeError("provider detail must not escape")

        def close(self) -> None:
            pass

    database = Database(tmp_path / "exception.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"X" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="owner@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    stored = accounts.list_all()[0]
    service = FetchService(
        accounts,
        MessageRepository(database),
        client_factory=lambda _account: RaisingClient(),
    )

    result = service.fetch_account(stored, FetchRequest())

    assert result.status is AccountStatus.UNKNOWN_ERROR
    assert "provider detail" not in result.detail
    assert accounts.get(stored.account_id).status is AccountStatus.UNKNOWN_ERROR  # type: ignore[arg-type]
