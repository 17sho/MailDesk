from __future__ import annotations

import sqlite3

from mailbox_manager.domain.models import (
    AutomationRule,
    Group,
    PostAction,
    ProxyConfig,
    ProxyType,
    ScheduleConfig,
    Tag,
    WebhookConfig,
)
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    AutomationRuleRepository,
    GroupRepository,
    ProxyRepository,
    ScheduleRepository,
    SettingsRepository,
    TagRepository,
    WebhookRepository,
)


def test_database_migrates_existing_v1_accounts_and_creates_enterprise_tables(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY, email TEXT NOT NULL)"
        )
        connection.execute("PRAGMA user_version = 1")

    database = Database(path)
    database.initialize()

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(accounts)")}
        message_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(messages)")
        }
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert {"smtp_host", "smtp_port", "oauth_provider", "proxy_id", "web_auth_status"} <= columns
    assert {"sender_name", "transport_id"} <= message_columns
    assert {"proxies", "schedules", "webhooks", "automation_rules"} <= tables
    assert version == 8


def test_group_and_tag_repositories_support_nested_assets(tmp_path) -> None:
    database = Database(tmp_path / "assets.db")
    database.initialize()
    groups = GroupRepository(database)
    tags = TagRepository(database)

    root_id = groups.create(Group(name="项目A"))
    child_id = groups.create(Group(name="渠道1", parent_id=root_id))
    tag_id = tags.create(Tag(name="重点", color="#0f766e"))

    assert [(item.name, item.parent_id) for item in groups.list_all()] == [
        ("项目A", None),
        ("渠道1", root_id),
    ]
    assert child_id > root_id
    assert tags.list_all()[0].tag_id == tag_id


def test_proxy_webhook_schedule_and_rule_secrets_are_encrypted(tmp_path) -> None:
    path = tmp_path / "enterprise.db"
    database = Database(path)
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"H" * 32)
    proxies = ProxyRepository(database, cipher)
    webhooks = WebhookRepository(database, cipher)
    schedules = ScheduleRepository(database)
    rules = AutomationRuleRepository(database)

    proxy_id = proxies.add(
        ProxyConfig(
            name="默认 SOCKS 节点",
            proxy_type=ProxyType.SOCKS5,
            host="127.0.0.1",
            port=1080,
            username="proxy-user",
            password="proxy-password",
            is_default=True,
        )
    )
    webhook_id = webhooks.add(
        WebhookConfig(name="业务回调", url="https://hooks.example.com/mail", secret="hook-secret")
    )
    schedule_id = schedules.upsert(ScheduleConfig(group_id=None, interval_minutes=5))
    rule_id = rules.add(
        AutomationRule(
            name="验证码标记已读",
            pattern="验证码",
            action=PostAction.MARK_READ,
            webhook_id=webhook_id,
        )
    )

    stored_proxy = proxies.get(proxy_id)
    assert stored_proxy is not None
    assert stored_proxy.password == "proxy-password"
    assert stored_proxy.display_name == "默认 SOCKS 节点"
    assert stored_proxy.is_default is True
    second_proxy_id = proxies.add(
        ProxyConfig(
            name="新的默认节点",
            proxy_type=ProxyType.HTTP,
            host="proxy.example.com",
            port=8080,
            is_default=True,
        )
    )
    ordered_proxies = proxies.list_all()
    assert ordered_proxies[0].proxy_id == second_proxy_id
    assert [item.is_default for item in ordered_proxies] == [True, False]
    assert webhooks.get(webhook_id).secret == "hook-secret"  # type: ignore[union-attr]
    assert schedules.list_all()[0].schedule_id == schedule_id
    assert rules.list_all()[0].rule_id == rule_id
    raw = path.read_bytes()
    assert b"proxy-password" not in raw
    assert b"hook-secret" not in raw


def test_settings_repository_round_trips_structured_values(tmp_path) -> None:
    database = Database(tmp_path / "settings.db")
    database.initialize()
    settings = SettingsRepository(database)

    settings.set("fetch", {"folders": ["INBOX", "Junk"], "concurrency": 8})

    assert settings.get("fetch")["concurrency"] == 8
    assert settings.get("missing", {"enabled": False}) == {"enabled": False}
