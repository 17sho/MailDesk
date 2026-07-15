from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(parent_id, name)
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    provider TEXT NOT NULL,
    protocol TEXT NOT NULL,
    host TEXT NOT NULL DEFAULT '',
    port INTEGER NOT NULL DEFAULT 0 CHECK(port BETWEEN 0 AND 65535),
    security TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    secret_ciphertext TEXT NOT NULL DEFAULT '',
    refresh_token_ciphertext TEXT NOT NULL DEFAULT '',
    client_id TEXT NOT NULL DEFAULT '',
    tenant TEXT NOT NULL DEFAULT 'common',
    totp_ciphertext TEXT NOT NULL DEFAULT '',
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    status_detail TEXT NOT NULL DEFAULT '',
    last_fetch_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(email, protocol)
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#64748b'
);
CREATE TABLE IF NOT EXISTS account_tags (
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY(account_id, tag_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    provider_message_id TEXT NOT NULL,
    transport_id TEXT NOT NULL DEFAULT '',
    folder TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    sender TEXT NOT NULL DEFAULT '',
    sender_name TEXT NOT NULL DEFAULT '',
    recipients_json TEXT NOT NULL DEFAULT '[]',
    catch_all_recipient TEXT NOT NULL DEFAULT '',
    received_at TEXT,
    text_body TEXT NOT NULL DEFAULT '',
    html_body TEXT NOT NULL DEFAULT '',
    web_html_body TEXT NOT NULL DEFAULT '',
    matched_values_json TEXT NOT NULL DEFAULT '[]',
    eml_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(account_id, provider_message_id, folder)
);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    provider_attachment_id TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes INTEGER NOT NULL DEFAULT 0 CHECK(size_bytes >= 0),
    content_id TEXT NOT NULL DEFAULT '',
    disposition TEXT NOT NULL DEFAULT 'attachment',
    content_blob BLOB,
    is_truncated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(message_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_attachments_message_id ON attachments(message_id);
CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    requested_count INTEGER NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    action TEXT NOT NULL,
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    outcome TEXT NOT NULL,
    detail_redacted TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    proxy_type TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL CHECK(port BETWEEN 1 AND 65535),
    username TEXT NOT NULL DEFAULT '',
    password_ciphertext TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(proxy_type, host, port, username)
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    interval_minutes INTEGER NOT NULL CHECK(interval_minutes BETWEEN 1 AND 10080),
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_schedules_group
ON schedules(COALESCE(group_id, -1));
CREATE TABLE IF NOT EXISTS webhooks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    secret_ciphertext TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS automation_rules (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    pattern TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'none',
    target_folder TEXT NOT NULL DEFAULT '',
    webhook_id INTEGER REFERENCES webhooks(id) ON DELETE SET NULL,
    forward_to TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""

ACCOUNT_COLUMNS: dict[str, str] = {
    "provider": "TEXT NOT NULL DEFAULT 'custom'",
    "protocol": "TEXT NOT NULL DEFAULT 'imap'",
    "host": "TEXT NOT NULL DEFAULT ''",
    "port": "INTEGER NOT NULL DEFAULT 0",
    "security": "TEXT NOT NULL DEFAULT 'ssl'",
    "username": "TEXT NOT NULL DEFAULT ''",
    "secret_ciphertext": "TEXT NOT NULL DEFAULT ''",
    "refresh_token_ciphertext": "TEXT NOT NULL DEFAULT ''",
    "client_id": "TEXT NOT NULL DEFAULT ''",
    "tenant": "TEXT NOT NULL DEFAULT 'common'",
    "oauth_provider": "TEXT NOT NULL DEFAULT ''",
    "smtp_host": "TEXT NOT NULL DEFAULT ''",
    "smtp_port": "INTEGER NOT NULL DEFAULT 0",
    "smtp_security": "TEXT NOT NULL DEFAULT 'ssl'",
    "proxy_id": "INTEGER REFERENCES proxies(id) ON DELETE SET NULL",
    "web_auth_status": "TEXT NOT NULL DEFAULT 'not_configured'",
    "totp_ciphertext": "TEXT NOT NULL DEFAULT ''",
    "group_id": "INTEGER REFERENCES groups(id) ON DELETE SET NULL",
    "status": "TEXT NOT NULL DEFAULT 'disconnected'",
    "status_detail": "TEXT NOT NULL DEFAULT ''",
    "last_fetch_at": "TEXT",
    "created_at": "TEXT NOT NULL DEFAULT ''",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}

MESSAGE_COLUMNS: dict[str, str] = {
    "transport_id": "TEXT NOT NULL DEFAULT ''",
    "sender_name": "TEXT NOT NULL DEFAULT ''",
    "html_body": "TEXT NOT NULL DEFAULT ''",
    "web_html_body": "TEXT NOT NULL DEFAULT ''",
}

PROXY_COLUMNS: dict[str, str] = {
    "name": "TEXT NOT NULL DEFAULT ''",
    "is_default": "INTEGER NOT NULL DEFAULT 0",
}


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            existing = {
                row["name"] for row in connection.execute("PRAGMA table_info(accounts)")
            }
            for name, definition in ACCOUNT_COLUMNS.items():
                if name not in existing:
                    connection.execute(f'ALTER TABLE accounts ADD COLUMN "{name}" {definition}')
            message_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(messages)")
            }
            for name, definition in MESSAGE_COLUMNS.items():
                if name not in message_columns:
                    connection.execute(f'ALTER TABLE messages ADD COLUMN "{name}" {definition}')
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_transport "
                "ON messages(account_id, folder, transport_id)"
            )
            proxy_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(proxies)")
            }
            for name, definition in PROXY_COLUMNS.items():
                if name not in proxy_columns:
                    connection.execute(f'ALTER TABLE proxies ADD COLUMN "{name}" {definition}')
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_proxies_default ON proxies(is_default DESC, id)"
            )
            connection.execute("PRAGMA user_version = 8")
