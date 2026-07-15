from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from mailbox_manager.domain.models import (
    EmailAccount,
    MailAttachment,
    MailMessage,
    MessageSearchHit,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.domain.status import AccountStatus
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


@dataclass(frozen=True, slots=True)
class AddResult:
    inserted: int = 0
    duplicates: int = 0
    updated: int = 0


class AccountRepository:
    def __init__(self, database: Database, cipher: CredentialCipher) -> None:
        self._database = database
        self._cipher = cipher

    def add_many(self, accounts: list[EmailAccount] | tuple[EmailAccount, ...]) -> AddResult:
        inserted = 0
        duplicates = 0
        updated = 0
        with self._database.connect() as connection:
            for original in accounts:
                account = replace(original, email=original.email.strip().casefold())
                now = _now()
                existing = connection.execute(
                    "SELECT * FROM accounts WHERE email = ? AND protocol = ?",
                    (account.email, account.protocol.value),
                ).fetchone()
                if existing is None and account.protocol is ProtocolType.GRAPH:
                    candidates = connection.execute(
                        "SELECT * FROM accounts WHERE email = ? AND protocol = ?",
                        (account.email, ProtocolType.IMAP.value),
                    ).fetchall()
                    existing = next(
                        (
                            row
                            for row in candidates
                            if str(row["provider"]).casefold() == "outlook"
                            and _is_uuid(self._cipher.decrypt_text(row["secret_ciphertext"]))
                        ),
                        None,
                    )
                if existing is not None:
                    if self._same_configuration(existing, account):
                        duplicates += 1
                    else:
                        self._update_configuration(connection, existing, account, now)
                        updated += 1
                    continue
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO accounts (
                        email, provider, protocol, host, port, security, username,
                        secret_ciphertext, refresh_token_ciphertext, client_id, tenant,
                        oauth_provider, smtp_host, smtp_port, smtp_security, proxy_id,
                        web_auth_status, totp_ciphertext, group_id, status, status_detail,
                        last_fetch_at, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        account.email,
                        account.provider,
                        account.protocol.value,
                        account.host,
                        account.port,
                        account.security.value,
                        account.username or account.email,
                        self._cipher.encrypt_text(account.secret),
                        self._cipher.encrypt_text(account.refresh_token),
                        account.client_id,
                        account.tenant,
                        account.oauth_provider,
                        account.smtp_host,
                        account.smtp_port,
                        account.smtp_security.value,
                        account.proxy_id,
                        account.web_auth_status,
                        self._cipher.encrypt_text(account.totp_secret),
                        account.group_id,
                        account.status.value,
                        account.status_detail,
                        account.last_fetch_at.isoformat() if account.last_fetch_at else None,
                        now,
                        now,
                    ),
                )
                if cursor.rowcount:
                    inserted += 1
                else:
                    duplicates += 1
        return AddResult(inserted=inserted, duplicates=duplicates, updated=updated)

    def _same_configuration(self, row: object, account: EmailAccount) -> bool:
        existing_totp = self._cipher.decrypt_text(row["totp_ciphertext"])  # type: ignore[index]
        expected_totp = account.totp_secret or existing_totp
        expected_group = (
            account.group_id if account.group_id is not None else row["group_id"]  # type: ignore[index]
        )
        expected_proxy = (
            account.proxy_id if account.proxy_id is not None else row["proxy_id"]  # type: ignore[index]
        )
        stored = (
            row["provider"],  # type: ignore[index]
            row["protocol"],  # type: ignore[index]
            row["host"],  # type: ignore[index]
            row["port"],  # type: ignore[index]
            row["security"],  # type: ignore[index]
            row["username"],  # type: ignore[index]
            self._cipher.decrypt_text(row["secret_ciphertext"]),  # type: ignore[index]
            self._cipher.decrypt_text(row["refresh_token_ciphertext"]),  # type: ignore[index]
            row["client_id"],  # type: ignore[index]
            row["tenant"],  # type: ignore[index]
            row["oauth_provider"],  # type: ignore[index]
            row["smtp_host"],  # type: ignore[index]
            row["smtp_port"],  # type: ignore[index]
            row["smtp_security"],  # type: ignore[index]
            row["proxy_id"],  # type: ignore[index]
            existing_totp,
            row["group_id"],  # type: ignore[index]
        )
        incoming = (
            account.provider,
            account.protocol.value,
            account.host,
            account.port,
            account.security.value,
            account.username or account.email,
            account.secret,
            account.refresh_token,
            account.client_id,
            account.tenant,
            account.oauth_provider,
            account.smtp_host,
            account.smtp_port,
            account.smtp_security.value,
            expected_proxy,
            expected_totp,
            expected_group,
        )
        return stored == incoming

    def _update_configuration(
        self, connection, row: object, account: EmailAccount, now: str
    ) -> None:
        existing_totp = self._cipher.decrypt_text(row["totp_ciphertext"])  # type: ignore[index]
        group_id = (
            account.group_id if account.group_id is not None else row["group_id"]  # type: ignore[index]
        )
        proxy_id = (
            account.proxy_id if account.proxy_id is not None else row["proxy_id"]  # type: ignore[index]
        )
        connection.execute(
            """
            UPDATE accounts SET
                provider = ?, protocol = ?, host = ?, port = ?, security = ?,
                username = ?, secret_ciphertext = ?, refresh_token_ciphertext = ?,
                client_id = ?, tenant = ?, oauth_provider = ?, smtp_host = ?,
                smtp_port = ?, smtp_security = ?, proxy_id = ?, web_auth_status = ?,
                totp_ciphertext = ?, group_id = ?, status = ?, status_detail = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                account.provider,
                account.protocol.value,
                account.host,
                account.port,
                account.security.value,
                account.username or account.email,
                self._cipher.encrypt_text(account.secret),
                self._cipher.encrypt_text(account.refresh_token),
                account.client_id,
                account.tenant,
                account.oauth_provider,
                account.smtp_host,
                account.smtp_port,
                account.smtp_security.value,
                proxy_id,
                account.web_auth_status,
                self._cipher.encrypt_text(account.totp_secret or existing_totp),
                group_id,
                AccountStatus.DISCONNECTED.value,
                "配置已更新，等待重新连接",
                now,
                row["id"],  # type: ignore[index]
            ),
        )

    def list_all(
        self,
        *,
        group_id: int | None = None,
        group_ids: list[int] | tuple[int, ...] | None = None,
        ungrouped: bool = False,
        query: str = "",
        tag_id: int | None = None,
    ) -> list[EmailAccount]:
        clauses: list[str] = []
        params: list[object] = []
        if ungrouped:
            clauses.append("a.group_id IS NULL")
        elif group_ids:
            placeholders = ",".join("?" for _ in group_ids)
            clauses.append(f"a.group_id IN ({placeholders})")
            params.extend(group_ids)
        elif group_id is not None:
            clauses.append("a.group_id = ?")
            params.append(group_id)
        if query.strip():
            clauses.append("(a.email LIKE ? OR a.provider LIKE ? OR a.status LIKE ?)")
            value = f"%{query.strip()}%"
            params.extend((value, value, value))
        if tag_id is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM account_tags at "
                "WHERE at.account_id = a.id AND at.tag_id = ?)"
            )
            params.append(tag_id)
        sql = (
            "SELECT a.*, COALESCE(GROUP_CONCAT(t.name, char(31)), '') AS tag_names "
            "FROM accounts a "
            "LEFT JOIN account_tags at_all ON at_all.account_id = a.id "
            "LEFT JOIN tags t ON t.id = at_all.tag_id"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " GROUP BY a.id ORDER BY a.id"
        with self._database.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._to_account(row) for row in rows]

    def get(self, account_id: int) -> EmailAccount | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
        return self._to_account(row) if row else None

    def update_status(self, account_id: int, status: AccountStatus, detail: str = "") -> None:
        last_fetch = _now() if status is AccountStatus.SUCCESS else None
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE accounts
                SET status = ?, status_detail = ?,
                    last_fetch_at = COALESCE(?, last_fetch_at), updated_at = ?
                WHERE id = ?
                """,
                (status.value, detail[:500], last_fetch, _now(), account_id),
            )

    def update_group(self, account_ids: list[int], group_id: int | None) -> None:
        if not account_ids:
            return
        placeholders = ",".join("?" for _ in account_ids)
        with self._database.connect() as connection:
            connection.execute(
                f"UPDATE accounts SET group_id = ?, updated_at = ? WHERE id IN ({placeholders})",
                (group_id, _now(), *account_ids),
            )

    def bind_proxy(self, account_ids: list[int], proxy_id: int | None) -> None:
        if not account_ids:
            return
        placeholders = ",".join("?" for _ in account_ids)
        with self._database.connect() as connection:
            connection.execute(
                f"UPDATE accounts SET proxy_id = ?, updated_at = ? WHERE id IN ({placeholders})",
                (proxy_id, _now(), *account_ids),
            )

    def delete_many(self, account_ids: list[int] | tuple[int, ...]) -> int:
        unique_ids = sorted({account_id for account_id in account_ids if account_id > 0})
        if not unique_ids:
            return 0
        placeholders = ",".join("?" for _ in unique_ids)
        with self._database.connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM accounts WHERE id IN ({placeholders})",
                unique_ids,
            )
        return max(0, cursor.rowcount)

    def update_refresh_token(self, account_id: int, refresh_token: str) -> None:
        if account_id <= 0 or not refresh_token:
            raise ValueError("账号或 Refresh Token 无效")
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE accounts
                SET refresh_token_ciphertext = ?, status = ?, status_detail = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    self._cipher.encrypt_text(refresh_token),
                    AccountStatus.DISCONNECTED.value,
                    "Microsoft 权限已更新，等待重新连接",
                    _now(),
                    account_id,
                ),
            )
        if not cursor.rowcount:
            raise ValueError("找不到需要更新的账号")

    def update_connection(
        self,
        account_id: int,
        *,
        host: str,
        port: int,
        security: SecurityMode,
        protocol: ProtocolType = ProtocolType.IMAP,
    ) -> None:
        if not host or not 1 <= port <= 65535:
            raise ValueError("服务器或端口不正确")
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE accounts
                SET host = ?, port = ?, security = ?, protocol = ?, updated_at = ?
                WHERE id = ?
                """,
                (host, port, security.value, protocol.value, _now(), account_id),
            )

    def _to_account(self, row: object) -> EmailAccount:
        row_keys = set(row.keys())  # type: ignore[attr-defined]
        tag_names = row["tag_names"] if "tag_names" in row_keys else ""  # type: ignore[index]
        return EmailAccount(
            account_id=row["id"],  # type: ignore[index]
            email=row["email"],  # type: ignore[index]
            provider=row["provider"],  # type: ignore[index]
            protocol=ProtocolType(row["protocol"]),  # type: ignore[index]
            host=row["host"],  # type: ignore[index]
            port=row["port"],  # type: ignore[index]
            security=SecurityMode(row["security"]),  # type: ignore[index]
            username=row["username"],  # type: ignore[index]
            secret=self._cipher.decrypt_text(row["secret_ciphertext"]),  # type: ignore[index]
            refresh_token=self._cipher.decrypt_text(row["refresh_token_ciphertext"]),  # type: ignore[index]
            client_id=row["client_id"],  # type: ignore[index]
            tenant=row["tenant"],  # type: ignore[index]
            oauth_provider=row["oauth_provider"],  # type: ignore[index]
            smtp_host=row["smtp_host"],  # type: ignore[index]
            smtp_port=row["smtp_port"],  # type: ignore[index]
            smtp_security=SecurityMode(row["smtp_security"]),  # type: ignore[index]
            proxy_id=row["proxy_id"],  # type: ignore[index]
            web_auth_status=row["web_auth_status"],  # type: ignore[index]
            totp_secret=self._cipher.decrypt_text(row["totp_ciphertext"]),  # type: ignore[index]
            group_id=row["group_id"],  # type: ignore[index]
            tags=tuple(tag_names.split("\x1f")) if tag_names else (),
            status=AccountStatus(row["status"]),  # type: ignore[index]
            status_detail=row["status_detail"],  # type: ignore[index]
            last_fetch_at=_parse_datetime(row["last_fetch_at"]),  # type: ignore[index]
            created_at=_parse_datetime(row["created_at"]),  # type: ignore[index]
            updated_at=_parse_datetime(row["updated_at"]),  # type: ignore[index]
        )


class MessageRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def add_many(self, account_id: int, messages: tuple[MailMessage, ...]) -> int:
        inserted = 0
        with self._database.connect() as connection:
            for message in messages:
                existing = connection.execute(
                    """
                    SELECT id FROM messages
                    WHERE account_id = ? AND provider_message_id = ? AND folder = ?
                    """,
                    (account_id, message.provider_message_id, message.folder),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO messages (
                        account_id, provider_message_id, transport_id, folder,
                        subject, sender, sender_name,
                        recipients_json, catch_all_recipient, received_at, text_body,
                        html_body, web_html_body, matched_values_json, eml_path, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, provider_message_id, folder) DO UPDATE SET
                        transport_id = CASE
                            WHEN excluded.transport_id <> '' THEN excluded.transport_id
                            ELSE messages.transport_id
                        END,
                        subject = excluded.subject,
                        sender = excluded.sender,
                        sender_name = excluded.sender_name,
                        recipients_json = excluded.recipients_json,
                        catch_all_recipient = excluded.catch_all_recipient,
                        received_at = excluded.received_at,
                        text_body = excluded.text_body,
                        html_body = CASE
                            WHEN excluded.html_body <> '' THEN excluded.html_body
                            ELSE messages.html_body
                        END,
                        web_html_body = CASE
                            WHEN excluded.web_html_body <> '' THEN excluded.web_html_body
                            ELSE messages.web_html_body
                        END,
                        matched_values_json = excluded.matched_values_json,
                        eml_path = CASE
                            WHEN excluded.eml_path <> '' THEN excluded.eml_path
                            ELSE messages.eml_path
                        END
                    """,
                    (
                        account_id,
                        message.provider_message_id,
                        message.transport_id,
                        message.folder,
                        message.subject[:2000],
                        message.sender,
                        message.sender_name[:500],
                        json.dumps(message.recipients, ensure_ascii=False),
                        message.catch_all_recipient,
                        message.received_at.isoformat() if message.received_at else None,
                        message.text_body[:500_000],
                        message.html_body[: 12 * 1024 * 1024],
                        message.web_html_body[: 12 * 1024 * 1024],
                        json.dumps(message.matched_values, ensure_ascii=False),
                        message.eml_path,
                        _now(),
                    ),
                )
                message_row = connection.execute(
                    """
                    SELECT id FROM messages
                    WHERE account_id = ? AND provider_message_id = ? AND folder = ?
                    """,
                    (account_id, message.provider_message_id, message.folder),
                ).fetchone()
                if message_row is not None and message.attachments:
                    self._replace_attachments(
                        connection,
                        int(message_row["id"]),
                        message.attachments,
                    )
                inserted += int(existing is None)
        return inserted

    def known_transport_ids(self, account_id: int) -> frozenset[tuple[str, str]]:
        """Return provider IDs used to avoid downloading cached messages again."""

        if account_id <= 0:
            return frozenset()
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT folder, transport_id FROM messages
                WHERE account_id = ? AND transport_id <> ''
                """,
                (account_id,),
            ).fetchall()
        return frozenset((str(row["folder"]), str(row["transport_id"])) for row in rows)

    def list_for_account(self, account_id: int, limit: int = 500) -> list[MailMessage]:
        bounded_limit = max(1, min(limit, 1000))
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE account_id = ?
                ORDER BY COALESCE(received_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                (account_id, bounded_limit),
            ).fetchall()
            attachments = self._attachments_for_messages(
                connection, [int(row["id"]) for row in rows]
            )
        return [self._to_message(row, attachments.get(int(row["id"]), ())) for row in rows]

    def get(self, message_id: int) -> MailMessage | None:
        if message_id <= 0:
            return None
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
            if row is None:
                return None
            attachments = self._attachments_for_messages(connection, [message_id])
        return self._to_message(row, attachments.get(message_id, ()))

    def list_attachments(
        self, message_id: int, *, include_content: bool = False
    ) -> list[MailAttachment]:
        if message_id <= 0:
            return []
        with self._database.connect() as connection:
            columns = "*" if include_content else self._attachment_metadata_columns()
            rows = connection.execute(
                f"""
                SELECT {columns} FROM attachments
                WHERE message_id = ? ORDER BY ordinal, id
                """,
                (message_id,),
            ).fetchall()
        return [self._to_attachment(row, include_content=include_content) for row in rows]

    def get_attachment(self, attachment_id: int) -> MailAttachment | None:
        """Load one attachment including its binary content on demand."""

        if attachment_id <= 0:
            return None
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
            ).fetchone()
        return self._to_attachment(row, include_content=True) if row else None

    def attachment_content(self, attachment_id: int) -> bytes | None:
        attachment = self.get_attachment(attachment_id)
        return attachment.content if attachment is not None else None

    def search(
        self,
        query: str,
        *,
        account_id: int | None = None,
        limit: int = 1000,
    ) -> list[MessageSearchHit]:
        value = query.strip()
        if not value:
            return []
        escaped = (
            value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        clauses = [
            "(m.subject LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "OR m.sender LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "OR m.sender_name LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "OR m.recipients_json LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "OR m.text_body LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "OR m.html_body LIKE ? ESCAPE '\\' COLLATE NOCASE)"
        ]
        params: list[object] = [pattern] * 6
        if account_id is not None:
            clauses.append("m.account_id = ?")
            params.append(account_id)
        params.append(max(1, min(limit, 5000)))
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT m.*, a.email AS account_email
                FROM messages m
                JOIN accounts a ON a.id = m.account_id
                WHERE """
                + " AND ".join(clauses)
                + """
                ORDER BY COALESCE(m.received_at, m.created_at) DESC, m.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            attachments = self._attachments_for_messages(
                connection, [int(row["id"]) for row in rows]
            )
        return [
            MessageSearchHit(
                account_email=row["account_email"],
                message=self._to_message(row, attachments.get(int(row["id"]), ())),
            )
            for row in rows
        ]

    def list_with_accounts(
        self,
        *,
        account_id: int | None = None,
        limit: int = 5000,
    ) -> list[MessageSearchHit]:
        params: list[object] = []
        where = ""
        if account_id is not None:
            where = "WHERE m.account_id = ?"
            params.append(account_id)
        params.append(max(1, min(limit, 10_000)))
        with self._database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT m.*, a.email AS account_email
                FROM messages m
                JOIN accounts a ON a.id = m.account_id
                {where}
                ORDER BY COALESCE(m.received_at, m.created_at) DESC, m.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            attachments = self._attachments_for_messages(
                connection, [int(row["id"]) for row in rows]
            )
        return [
            MessageSearchHit(
                account_email=row["account_email"],
                message=self._to_message(row, attachments.get(int(row["id"]), ())),
            )
            for row in rows
        ]

    @staticmethod
    def _replace_attachments(
        connection,
        message_id: int,
        attachments: tuple[MailAttachment, ...],
    ) -> None:
        for ordinal, attachment in enumerate(attachments):
            connection.execute(
                """
                INSERT INTO attachments (
                    message_id, ordinal, provider_attachment_id, filename, content_type,
                    size_bytes, content_id, disposition, content_blob, is_truncated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id, ordinal) DO UPDATE SET
                    provider_attachment_id = excluded.provider_attachment_id,
                    filename = excluded.filename,
                    content_type = excluded.content_type,
                    size_bytes = excluded.size_bytes,
                    content_id = excluded.content_id,
                    disposition = excluded.disposition,
                    content_blob = CASE
                        WHEN excluded.content_blob IS NOT NULL THEN excluded.content_blob
                        WHEN attachments.filename = excluded.filename
                             AND attachments.size_bytes = excluded.size_bytes
                        THEN attachments.content_blob
                        ELSE NULL
                    END,
                    is_truncated = excluded.is_truncated
                """,
                (
                    message_id,
                    ordinal,
                    attachment.provider_attachment_id,
                    attachment.filename,
                    attachment.content_type,
                    attachment.size,
                    attachment.content_id,
                    attachment.disposition,
                    attachment.content,
                    int(attachment.is_truncated),
                    _now(),
                ),
            )
        connection.execute(
            "DELETE FROM attachments WHERE message_id = ? AND ordinal >= ?",
            (message_id, len(attachments)),
        )

    @staticmethod
    def _attachment_metadata_columns() -> str:
        return (
            "id, message_id, ordinal, provider_attachment_id, filename, content_type, "
            "size_bytes, content_id, disposition, is_truncated"
        )

    @classmethod
    def _attachments_for_messages(
        cls, connection, message_ids: list[int]
    ) -> dict[int, tuple[MailAttachment, ...]]:
        if not message_ids:
            return {}
        placeholders = ",".join("?" for _ in message_ids)
        rows = connection.execute(
            f"""
            SELECT {cls._attachment_metadata_columns()} FROM attachments
            WHERE message_id IN ({placeholders})
            ORDER BY message_id, ordinal, id
            """,
            message_ids,
        ).fetchall()
        grouped: dict[int, list[MailAttachment]] = {}
        for row in rows:
            grouped.setdefault(int(row["message_id"]), []).append(
                cls._to_attachment(row, include_content=False)
            )
        return {message_id: tuple(values) for message_id, values in grouped.items()}

    @staticmethod
    def _to_attachment(row: object, *, include_content: bool) -> MailAttachment:
        return MailAttachment(
            attachment_id=row["id"],  # type: ignore[index]
            message_id=row["message_id"],  # type: ignore[index]
            provider_attachment_id=row["provider_attachment_id"],  # type: ignore[index]
            filename=row["filename"],  # type: ignore[index]
            content_type=row["content_type"],  # type: ignore[index]
            size=row["size_bytes"],  # type: ignore[index]
            content_id=row["content_id"],  # type: ignore[index]
            disposition=row["disposition"],  # type: ignore[index]
            content=row["content_blob"] if include_content else None,  # type: ignore[index]
            is_truncated=bool(row["is_truncated"]),  # type: ignore[index]
        )

    @staticmethod
    def _to_message(
        row: object, attachments: tuple[MailAttachment, ...] = ()
    ) -> MailMessage:
        row_keys = set(row.keys())  # type: ignore[attr-defined]
        return MailMessage(
            message_id=row["id"],  # type: ignore[index]
            account_id=row["account_id"],  # type: ignore[index]
            provider_message_id=row["provider_message_id"],  # type: ignore[index]
            folder=row["folder"],  # type: ignore[index]
            transport_id=(
                row["transport_id"] if "transport_id" in row_keys else ""  # type: ignore[index]
            ),
            subject=row["subject"],  # type: ignore[index]
            sender=row["sender"],  # type: ignore[index]
            sender_name=(
                row["sender_name"] if "sender_name" in row_keys else ""  # type: ignore[index]
            ),
            recipients=tuple(json.loads(row["recipients_json"])),  # type: ignore[index]
            catch_all_recipient=row["catch_all_recipient"],  # type: ignore[index]
            received_at=_parse_datetime(row["received_at"]),  # type: ignore[index]
            text_body=row["text_body"],  # type: ignore[index]
            html_body=row["html_body"],  # type: ignore[index]
            web_html_body=row["web_html_body"],  # type: ignore[index]
            matched_values=tuple(json.loads(row["matched_values_json"])),  # type: ignore[index]
            attachments=attachments,
            eml_path=row["eml_path"],  # type: ignore[index]
        )
