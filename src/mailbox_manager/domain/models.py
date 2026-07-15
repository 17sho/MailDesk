from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from mailbox_manager.domain.status import AccountStatus


class ProtocolType(StrEnum):
    IMAP = "imap"
    POP3 = "pop3"
    GRAPH = "graph"


class SecurityMode(StrEnum):
    SSL = "ssl"
    STARTTLS = "starttls"
    PLAIN = "plain"


class ProxyType(StrEnum):
    HTTP = "http"
    SOCKS5 = "socks5"


class PostAction(StrEnum):
    NONE = "none"
    MARK_READ = "mark_read"
    MOVE = "move"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class EmailAccount:
    email: str
    provider: str
    protocol: ProtocolType
    host: str = ""
    port: int = 0
    security: SecurityMode = SecurityMode.SSL
    username: str = ""
    secret: str = field(default="", repr=False)
    refresh_token: str = field(default="", repr=False)
    client_id: str = ""
    tenant: str = "common"
    oauth_provider: str = ""
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_security: SecurityMode = SecurityMode.SSL
    proxy_id: int | None = None
    web_auth_status: str = "not_configured"
    totp_secret: str = field(default="", repr=False)
    group_id: int | None = None
    tags: tuple[str, ...] = ()
    status: AccountStatus = AccountStatus.DISCONNECTED
    status_detail: str = ""
    last_fetch_at: datetime | None = None
    account_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.email or "@" not in self.email:
            raise ValueError("邮箱地址格式不正确")
        if self.protocol in {ProtocolType.IMAP, ProtocolType.POP3} and not self.host:
            raise ValueError("IMAP/POP3 账号必须配置服务器")
        if self.protocol in {ProtocolType.IMAP, ProtocolType.POP3} and not 1 <= self.port <= 65535:
            raise ValueError("端口必须在 1 到 65535 之间")
        if self.smtp_port and not 1 <= self.smtp_port <= 65535:
            raise ValueError("SMTP 端口必须在 1 到 65535 之间")


@dataclass(frozen=True, slots=True)
class MailFolder:
    name: str
    display_name: str = ""
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MailAttachment:
    """A MIME or provider attachment associated with a locally stored message.

    Repository list operations intentionally leave ``content`` as ``None``.  Callers that need
    to save or open an attachment should retrieve it by ``attachment_id`` through
    ``MessageRepository.get_attachment`` so message lists stay memory bounded.
    """

    filename: str
    content_type: str = "application/octet-stream"
    size: int = 0
    content_id: str = ""
    disposition: str = "attachment"
    provider_attachment_id: str = ""
    content: bytes | None = field(default=None, repr=False, compare=False)
    is_truncated: bool = False
    attachment_id: int | None = None
    message_id: int | None = None

    def __post_init__(self) -> None:
        if not self.filename.strip():
            raise ValueError("附件文件名不能为空")
        if self.size < 0:
            raise ValueError("附件大小不能为负数")
        if self.disposition not in {"attachment", "inline"}:
            raise ValueError("附件类型必须是 attachment 或 inline")

    @property
    def is_inline(self) -> bool:
        return self.disposition == "inline"


@dataclass(frozen=True, slots=True)
class MailMessage:
    provider_message_id: str
    folder: str
    transport_id: str = ""
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    recipients: tuple[str, ...] = ()
    catch_all_recipient: str = ""
    received_at: datetime | None = None
    text_body: str = ""
    html_body: str = field(default="", repr=False)
    web_html_body: str = field(default="", repr=False)
    matched_values: tuple[str, ...] = ()
    attachments: tuple[MailAttachment, ...] = ()
    raw_eml: bytes = field(default=b"", repr=False)
    eml_path: str = ""
    message_id: int | None = None
    account_id: int | None = None

    @property
    def sender_display(self) -> str:
        name = self.sender_name.strip()
        address = self.sender.strip()
        if name and address and name.casefold() != address.casefold():
            return f"{name} <{address}>"
        return name or address


@dataclass(frozen=True, slots=True)
class MessageSearchHit:
    account_email: str
    message: MailMessage


@dataclass(frozen=True, slots=True)
class FetchRequest:
    folders: tuple[str, ...] = ("INBOX",)
    max_messages: int = 20
    keywords: tuple[str, ...] = ("verification code", "验证码", "reset password")
    custom_pattern: str = ""
    include_raw: bool = True
    include_special_folders: bool = False
    post_action: PostAction = PostAction.NONE
    action_target_folder: str = ""
    confirmed_actions: bool = False
    # Provider transport identifiers already persisted for this account.  Folder
    # is part of the key because IMAP UIDs are only unique within one mailbox.
    known_transport_ids: frozenset[tuple[str, str]] = frozenset()

    def __post_init__(self) -> None:
        if self.max_messages < 0:
            raise ValueError("每次收取数量不能为负数；0 表示不限制")
        if not self.folders:
            raise ValueError("至少选择一个邮件文件夹")
        if len(self.custom_pattern) > 500:
            raise ValueError("自定义正则长度不能超过 500")
        if self.post_action is PostAction.MOVE and not self.action_target_folder.strip():
            raise ValueError("移动邮件必须指定目标文件夹")
        if self.post_action is not PostAction.NONE and not self.confirmed_actions:
            raise ValueError("邮件后处理必须由用户显式确认")

    @property
    def unlimited(self) -> bool:
        return self.max_messages == 0


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    status: AccountStatus
    detail: str = ""

    @property
    def is_success(self) -> bool:
        return self.status is AccountStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class FetchResult:
    status: AccountStatus
    messages: tuple[MailMessage, ...] = ()
    detail: str = ""

    @property
    def is_success(self) -> bool:
        return self.status is AccountStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class ImportPreviewRow:
    line_number: int
    account: EmailAccount | None
    confidence: str
    warnings: tuple[str, ...] = ()
    error: str = ""
    raw_masked: str = ""


@dataclass(frozen=True, slots=True)
class ImportPreview:
    rows: tuple[ImportPreviewRow, ...]

    @property
    def valid_accounts(self) -> tuple[EmailAccount, ...]:
        return tuple(row.account for row in self.rows if row.account is not None and not row.error)

    @property
    def error_count(self) -> int:
        return sum(bool(row.error) for row in self.rows)


@dataclass(frozen=True, slots=True)
class Group:
    name: str
    parent_id: int | None = None
    group_id: int | None = None


@dataclass(frozen=True, slots=True)
class Tag:
    name: str
    color: str = "#64748b"
    tag_id: int | None = None


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    proxy_type: ProxyType
    host: str
    port: int
    name: str = ""
    username: str = ""
    password: str = field(default="", repr=False)
    enabled: bool = True
    is_default: bool = False
    proxy_id: int | None = None

    def __post_init__(self) -> None:
        if not self.host or not 1 <= self.port <= 65535:
            raise ValueError("代理地址或端口不正确")
        if len(self.name.strip()) > 100:
            raise ValueError("代理名称不能超过 100 个字符")

    @property
    def identity(self) -> str:
        return f"{self.proxy_type.value}://{self.host}:{self.port}"

    @property
    def display_name(self) -> str:
        return self.name.strip() or self.identity


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    group_id: int | None
    interval_minutes: int
    enabled: bool = True
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    schedule_id: int | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.interval_minutes <= 10_080:
            raise ValueError("监控周期必须在 1 分钟到 7 天之间")


@dataclass(frozen=True, slots=True)
class WebhookConfig:
    name: str
    url: str
    secret: str = field(default="", repr=False)
    enabled: bool = True
    webhook_id: int | None = None


@dataclass(frozen=True, slots=True)
class AutomationRule:
    name: str
    pattern: str
    action: PostAction = PostAction.NONE
    target_folder: str = ""
    webhook_id: int | None = None
    forward_to: str = ""
    enabled: bool = True
    rule_id: int | None = None

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.pattern.strip() or len(self.pattern) > 500:
            raise ValueError("自动化规则名称或匹配表达式不正确")
        if self.action is PostAction.MOVE and not self.target_folder.strip():
            raise ValueError("移动规则必须指定目标文件夹")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    occurred_at: datetime
    action: str
    outcome: str
    detail_redacted: str = ""
    account_id: int | None = None
    event_id: int | None = None


@dataclass(frozen=True, slots=True)
class DashboardStats:
    status_counts: dict[AccountStatus, int]
    messages_per_hour: tuple[tuple[datetime, int], ...]


@dataclass(frozen=True, slots=True)
class DashboardOverview:
    total_accounts: int
    healthy_accounts: int
    abnormal_accounts: int
    total_messages: int
    special_folder_messages: int
    enabled_proxies: int


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    rule_id: str
    rule_name: str
    finding_type: str
    detail: str
