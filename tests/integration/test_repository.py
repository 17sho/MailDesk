from __future__ import annotations

import sqlite3

from mailbox_manager.domain.models import (
    EmailAccount,
    MailAttachment,
    MailMessage,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


def test_account_repository_encrypts_secrets_and_deduplicates(tmp_path) -> None:
    database_path = tmp_path / "maildesk.db"
    database = Database(database_path)
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"B" * 32)
    repository = AccountRepository(database, cipher)
    account = EmailAccount(
        email="Owner@Example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="Owner@Example.com",
        secret="plain-password",
        refresh_token="refresh-secret",
    )

    first = repository.add_many([account])
    second = repository.add_many([account])
    loaded = repository.list_all()

    assert first.inserted == 1
    assert second.duplicates == 1
    assert loaded[0].email == "owner@example.com"
    assert loaded[0].secret == "plain-password"
    raw_database = database_path.read_bytes()
    assert b"plain-password" not in raw_database
    assert b"refresh-secret" not in raw_database


def test_reimport_repairs_misclassified_outlook_oauth_account(tmp_path) -> None:
    database = Database(tmp_path / "repair.db")
    database.initialize()
    repository = AccountRepository(database, CredentialCipher.from_raw_key(b"R" * 32))
    client_id = "00000000-0000-0000-0000-000000000001"
    repository.add_many(
        [
            EmailAccount(
                email="owner@outlook.com",
                provider="Outlook",
                protocol=ProtocolType.IMAP,
                host="outlook.office365.com",
                port=993,
                security=SecurityMode.SSL,
                secret=client_id,
            )
        ]
    )
    original_id = repository.list_all()[0].account_id

    result = repository.add_many(
        [
            EmailAccount(
                email="owner@outlook.com",
                provider="outlook",
                protocol=ProtocolType.GRAPH,
                refresh_token="valid-refresh-token",
                client_id=client_id,
                oauth_provider="microsoft",
            )
        ]
    )

    loaded = repository.list_all()
    assert result.updated == 1
    assert result.inserted == 0
    assert len(loaded) == 1
    assert loaded[0].account_id == original_id
    assert loaded[0].protocol is ProtocolType.GRAPH
    assert loaded[0].refresh_token == "valid-refresh-token"
    assert loaded[0].secret == ""


def test_database_creates_enterprise_extension_tables(tmp_path) -> None:
    database = Database(tmp_path / "schema.db")
    database.initialize()

    with sqlite3.connect(database.path) as connection:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert {"accounts", "groups", "tags", "account_tags", "messages", "audit_events"} <= names


def test_message_repository_migrates_and_refreshes_html_body(tmp_path) -> None:
    database_path = tmp_path / "messages.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE accounts (id INTEGER PRIMARY KEY);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                provider_message_id TEXT NOT NULL,
                folder TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '', sender TEXT NOT NULL DEFAULT '',
                recipients_json TEXT NOT NULL DEFAULT '[]',
                catch_all_recipient TEXT NOT NULL DEFAULT '', received_at TEXT,
                text_body TEXT NOT NULL DEFAULT '',
                matched_values_json TEXT NOT NULL DEFAULT '[]',
                eml_path TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                UNIQUE(account_id, provider_message_id, folder)
            );
            """
        )
    database = Database(database_path)
    database.initialize()
    repository = MessageRepository(database)
    repository.add_many(
        1,
        (
            MailMessage(
                provider_message_id="same",
                folder="INBOX",
                text_body="旧正文",
            ),
        ),
    )
    inserted = repository.add_many(
        1,
        (
                MailMessage(
                    provider_message_id="same",
                    folder="INBOX",
                    text_body="新正文",
                    html_body="<p>新正文</p>",
                    web_html_body="<style>p{color:#123456}</style><p>新正文</p>",
                ),
        ),
    )

    loaded = repository.list_for_account(1)[0]
    assert inserted == 0
    assert loaded.text_body == "新正文"
    assert loaded.html_body == "<p>新正文</p>"
    assert "color:#123456" in loaded.web_html_body

    with sqlite3.connect(database_path) as connection:
        attachment_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'attachments'"
        ).fetchone()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert attachment_table == ("attachments",)
    assert version == 8


def test_message_repository_persists_and_searches_sender_name(tmp_path) -> None:
    database = Database(tmp_path / "sender-name.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"S" * 32))
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
    account_id = accounts.list_all()[0].account_id
    assert account_id is not None
    messages = MessageRepository(database)
    messages.add_many(
        account_id,
        (
            MailMessage(
                provider_message_id="named-sender",
                folder="INBOX",
                sender_name="Security Team",
                sender="security@example.com",
                subject="Notice",
            ),
        ),
    )

    loaded = messages.list_for_account(account_id)[0]
    hits = messages.search("Security Team")

    assert loaded.sender_name == "Security Team"
    assert loaded.sender_display == "Security Team <security@example.com>"
    assert [hit.message.provider_message_id for hit in hits] == ["named-sender"]


def test_message_repository_persists_attachment_and_loads_binary_on_demand(tmp_path) -> None:
    database = Database(tmp_path / "attachments.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"A" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="attachments@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    account_id = accounts.list_all()[0].account_id
    assert account_id is not None
    repository = MessageRepository(database)
    repository.add_many(
        account_id,
        (
            MailMessage(
                provider_message_id="with-attachment",
                folder="INBOX",
                attachments=(
                    MailAttachment(
                        filename="报告.txt",
                        content_type="text/plain",
                        size=12,
                        content=b"report bytes",
                    ),
                ),
            ),
        ),
    )

    loaded = repository.list_for_account(1)[0]

    assert len(loaded.attachments) == 1
    metadata = loaded.attachments[0]
    assert metadata.filename == "报告.txt"
    assert metadata.content is None
    assert metadata.attachment_id is not None
    full_attachment = repository.get_attachment(metadata.attachment_id)
    assert full_attachment is not None
    assert full_attachment.content == b"report bytes"
    assert repository.attachment_content(metadata.attachment_id) == b"report bytes"

    accounts.delete_many([account_id])

    assert repository.get_attachment(metadata.attachment_id) is None


def test_message_upsert_without_attachment_payload_preserves_existing_attachments(
    tmp_path,
) -> None:
    database = Database(tmp_path / "preserve-attachments.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"P" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="preserve@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    account_id = accounts.list_all()[0].account_id
    assert account_id is not None
    repository = MessageRepository(database)
    repository.add_many(
        account_id,
        (
            MailMessage(
                provider_message_id="same",
                folder="INBOX",
                attachments=(
                    MailAttachment(filename="original.bin", size=3, content=b"old"),
                ),
            ),
        ),
    )
    repository.add_many(
        account_id,
        (MailMessage(provider_message_id="same", folder="INBOX", subject="updated"),),
    )

    loaded = repository.list_for_account(account_id)[0]
    attachment_id = loaded.attachments[0].attachment_id
    assert loaded.subject == "updated"
    assert attachment_id is not None
    assert repository.attachment_content(attachment_id) == b"old"


def test_account_repository_batch_delete_cascades_local_relations(tmp_path) -> None:
    database = Database(tmp_path / "delete.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"Z" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="first@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            ),
            EmailAccount(
                email="second@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            ),
        ]
    )
    first, second = accounts.list_all()
    messages = MessageRepository(database)
    messages.add_many(
        first.account_id,
        (MailMessage(provider_message_id="mail", folder="INBOX", text_body="body"),),
    )

    deleted = accounts.delete_many([first.account_id])

    assert deleted == 1
    assert [account.account_id for account in accounts.list_all()] == [second.account_id]
    assert messages.list_for_account(first.account_id) == []


def test_refresh_token_rotation_is_encrypted_and_preserves_account(tmp_path) -> None:
    database = Database(tmp_path / "rotate-token.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"Y" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="owner@outlook.com",
                provider="outlook",
                protocol=ProtocolType.GRAPH,
                refresh_token="old-refresh",
                client_id="00000000-0000-0000-0000-000000000001",
            )
        ]
    )
    account = accounts.list_all()[0]

    accounts.update_refresh_token(account.account_id, "rotated-refresh-secret")

    loaded = accounts.get(account.account_id)
    assert loaded is not None
    assert loaded.refresh_token == "rotated-refresh-secret"
    assert loaded.status_detail == "Microsoft 权限已更新，等待重新连接"
    assert b"rotated-refresh-secret" not in database.path.read_bytes()


def test_message_search_supports_global_and_single_account_scope(tmp_path) -> None:
    database = Database(tmp_path / "search.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"Q" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="first@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            ),
            EmailAccount(
                email="second@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            ),
        ]
    )
    first, second = accounts.list_all()
    messages = MessageRepository(database)
    messages.add_many(
        first.account_id,
        (
            MailMessage(
                provider_message_id="first-mail",
                folder="INBOX",
                subject="Invoice Alpha",
                text_body="payment reference A-100",
            ),
        ),
    )
    messages.add_many(
        second.account_id,
        (
            MailMessage(
                provider_message_id="second-mail",
                folder="INBOX",
                subject="Invoice Beta",
                text_body="payment reference B-200",
            ),
        ),
    )

    global_hits = messages.search("Invoice")
    account_hits = messages.search("Invoice", account_id=first.account_id)

    assert {hit.account_email for hit in global_hits} == {
        "first@example.com",
        "second@example.com",
    }
    assert [hit.message.subject for hit in account_hits] == ["Invoice Alpha"]
