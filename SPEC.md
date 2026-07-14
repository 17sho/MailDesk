# 历史兼容规格：多邮箱批量管理系统 v0.1

> 本文保留 v0.1 核心契约，作为历史兼容基线，不代表当前功能完成度。v0.2 当前状态、安全替代和明确排除项见 `README.md` 与 `ENTERPRISE_FEATURES.md`。

## 1. Objective

构建一个面向 Windows 10/11 x64 的本地桌面邮箱管理工具。用户可导入自己拥有或获明确授权的邮箱账号，通过通用 IMAP 或 Microsoft Graph 拉取邮件，在桌面界面查看账号状态、邮件正文和验证码/关键词提取结果，并将结果导出。应用可由 PyInstaller 打包为 `onefile` 或 `onedir` 的 `.exe`。

首版是安全、可运行、可测试的工程基线，不把尚未实现的企业增强能力包装为“已完成”。数据库和模块边界会为分组标签、代理、调度、Webhook、TOTP、托盘和审计扩展预留接口。

### 核心用户故事

1. 用户可选择或拖放 TXT、CSV、JSON，预览解析映射，确认后去重导入。
2. 用户可看到账号、类型、协议、最近收件时间和可读状态；凭据不会以明文落盘或出现在日志/导出中。
3. 用户可设置 1–50 个并发任务并开始/停止收件，界面保持响应。
4. 用户可通过通用 IMAP 或 Microsoft Graph 拉取邮件，并从主题和正文提取验证码/关键词。
5. 用户可查看邮件详情，将非敏感结果导出 CSV/TXT，并保存授权获取的 `.eml` 原件。
6. 开发者可执行测试、运行桌面应用，并构建单文件或目录形式的 Windows 可执行程序。

## 2. Scope

### v0.1 必须实现

- TXT、CSV、JSON 文件导入与文本粘贴导入。
- 智能格式识别、字段校验、重复检测和导入预览。
- 常见邮箱域名的 IMAP/SMTP 配置补全。
- SQLite 数据库、参数化 SQL、数据库迁移入口。
- Windows DPAPI 保护随机主密钥，Fernet 加密密码、授权码、Refresh Token、TOTP secret 等字段。
- `EmailClientBase` 抽象契约。
- `ImapClient`：SSL/TLS、文件夹枚举、受限数量拉取、状态分类、原始 `.eml`。
- `OutlookGraphClient`：Refresh Token 换取 Access Token、分页受限的邮件拉取、Graph 错误分类。
- 纯函数邮件解析器：正文解码、验证码/关键词、Catch-All 收件人字段解析。
- PySide6 主窗口：账号表、邮件列表、详情、日志、工具栏、明暗主题。
- `QThreadPool` 并发收件，线程数 1–50，支持协作式停止。
- 账号与收件结果导出 CSV/TXT，默认永不导出秘密字段。
- 结构化、滚动、脱敏日志。
- PyInstaller `.spec` 与 `build.py`，支持 `--onefile` / `--onedir`。
- 单元测试与使用文档。

### 预留但不在 v0.1 宣称完成

- 分组/标签的完整 CRUD 和树形交互。
- APScheduler 定时任务、系统托盘与桌面通知。
- TOTP 右键复制交互。
- 代理池与按账号绑定；仅允许合规的连接配置和正常限流，不提供规避平台控制的策略。
- Webhook 推送；实现前必须加入 HTTPS/主机允许列表、私网地址阻断和重定向禁用。
- IMAP 后处理（已读/移动/删除）与 SMTP 转发；均要求默认关闭、显式确认和审计。
- 图表大屏、错误报告打包、域名 MX/SRV 自动发现。
- Gmail OAuth2 和 Google API 客户端。

### 明确不实现

- 绕过验证码、封禁、速率限制或服务商风控。
- 无授权的批量登录、凭据验证或账号接管工作流。
- 隐式/规避检测的 Headless 登录及自动开启被服务商关闭的协议。
- 批量修改账号密码、恢复邮箱或其他安全设置。
- 向任意探针地址发送测试邮件；SMTP 测试必须在后续版本使用用户明确指定且确认拥有的目标。

## 3. Technical Stack

- Python 3.12
- PySide6 6.7+
- 标准库：`sqlite3`、`imaplib`、`email`、`ssl`、`csv`、`json`、`logging`
- HTTP：`httpx`
- 加密：`cryptography` + Windows DPAPI（`pywin32`）
- Microsoft OAuth：标准 OAuth token endpoint（通过 `httpx`）；保留 MSAL 适配器接口
- 2FA 扩展：`pyotp`
- 测试：`pytest`、`pytest-qt`
- 打包：`PyInstaller`
- 代码质量：`ruff`

依赖版本通过 `requirements.txt` 和 `requirements-dev.txt` 约束；发布构建前执行依赖审计并复核高危项的可达性。

## 4. Commands

```powershell
# 创建虚拟环境
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 运行
.\.venv\Scripts\python.exe -m mailbox_manager

# 测试与静态检查
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests build.py release.py

# 打包
.\.venv\Scripts\python.exe build.py --mode onedir
.\.venv\Scripts\python.exe build.py --mode onefile
```

## 5. Project Structure

```text
MailDesk/
├─ SPEC.md
├─ README.md
├─ pyproject.toml
├─ requirements.txt
├─ requirements-dev.txt
├─ build.py
├─ mailbox-manager.spec
├─ assets/
│  └─ app.ico
├─ tasks/
│  ├─ plan.md
│  └─ todo.md
├─ src/mailbox_manager/
│  ├─ __init__.py
│  ├─ __main__.py
│  ├─ app.py
│  ├─ config.py
│  ├─ domain/
│  │  ├─ models.py
│  │  ├─ errors.py
│  │  └─ status.py
│  ├─ storage/
│  │  ├─ crypto.py
│  │  ├─ database.py
│  │  └─ repositories.py
│  ├─ importers/
│  │  ├─ smart_parser.py
│  │  └─ file_importer.py
│  ├─ protocols/
│  │  ├─ base.py
│  │  ├─ imap_client.py
│  │  ├─ outlook_graph.py
│  │  └─ providers.py
│  ├─ mail/
│  │  └─ parser.py
│  ├─ services/
│  │  ├─ account_service.py
│  │  ├─ fetch_service.py
│  │  └─ export_service.py
│  ├─ gui/
│  │  ├─ main_window.py
│  │  ├─ account_model.py
│  │  ├─ import_dialog.py
│  │  ├─ workers.py
│  │  └─ theme.py
│  └─ observability/
│     └─ logging_config.py
└─ tests/
   ├─ unit/
   └─ integration/
```

运行时数据默认位于 `%LOCALAPPDATA%\MailDesk`，不写入源码目录：

- `maildesk.db`：SQLite 数据库，秘密字段为密文。
- `master.key.dpapi`：仅当前 Windows 用户可解密的随机主密钥。
- `logs/app.log`：滚动且脱敏的审计/错误日志。
- `eml/`：用户显式保存的邮件原件。

## 6. Architecture and Contracts

### 分层

- GUI 只依赖服务接口和领域模型，不直接操作数据库或网络。
- 服务层编排导入、持久化、协议客户端、解析和导出。
- 协议层通过 `EmailClientBase` 返回统一的 `FetchResult` / `MailMessage`。
- 存储层集中处理 SQL 和加解密；领域对象不暴露密文字段实现。
- 外部响应和导入内容均在边界校验，内部函数使用已验证类型。

### `EmailClientBase` 契约

```python
class EmailClientBase(ABC):
    @abstractmethod
    def test_connection(self) -> ConnectionResult: ...

    @abstractmethod
    def list_folders(self) -> list[MailFolder]: ...

    @abstractmethod
    def fetch_messages(self, request: FetchRequest) -> FetchResult: ...

    @abstractmethod
    def close(self) -> None: ...
```

所有实现使用统一状态码：`SUCCESS`、`AUTH_FAILED`、`TIMEOUT`、`RATE_LIMITED`、`BLOCKED`、`NETWORK_ERROR`、`CONFIG_ERROR`、`CANCELLED`、`UNKNOWN_ERROR`。用户可读文案与机器状态码分离。

### 并发模型

- GUI 使用 `QThreadPool` + `QRunnable`，每个账号一个受限任务。
- 并发数由用户设置并强制限制为 1–50。
- 停止采用线程安全事件做协作式取消，不强杀线程。
- 每个网络操作有连接和读取超时；重试只针对瞬时网络错误，使用带抖动的指数退避并尊重 `Retry-After`。
- 不通过高并发或代理轮换规避服务商限制。

## 7. Data Model

核心表：

- `groups(id, parent_id, name, created_at)`
- `accounts(id, email, provider, protocol, host, port, security, username, secret_ciphertext, refresh_token_ciphertext, client_id, tenant, totp_ciphertext, group_id, status, status_detail, last_fetch_at, created_at, updated_at)`
- `tags(id, name, color)`
- `account_tags(account_id, tag_id)`
- `messages(id, account_id, provider_message_id, folder, subject, sender, recipients_json, catch_all_recipient, received_at, text_body, matched_values_json, eml_path, created_at)`
- `fetch_runs(id, started_at, finished_at, requested_count, success_count, failure_count)`
- `audit_events(id, occurred_at, action, account_id, outcome, detail_redacted)`
- `settings(key, value_json)`（不得存储明文秘密）

去重规则默认为规范化邮箱地址 + 协议；同一邮箱可保留 Graph 和 IMAP 两条配置。`provider_message_id + account_id + folder` 建唯一索引。

## 8. Import Rules

- 文件最大 20 MiB，文本最大 100,000 行；超限时拒绝并给出可读错误。
- 支持 UTF-8、UTF-8 BOM，必要时尝试系统常用编码并在预览中提示。
- `----` 格式通过字段数量、邮箱域名、端口、Token 特征进行启发式映射。
- 三字段输入必须进入预览；不把无法区分的“密码/授权码”和“RefreshToken/ClientID”静默猜成最终结果。
- JSON 仅接受对象数组或带 `accounts` 数组的对象；未知字段保留为预览备注，不执行。
- CSV 使用表头同义词映射；公式注入危险前缀在导出时转义。
- 日志和错误只显示掩码邮箱，不显示密码、Token、TOTP 或完整正文。

## 9. Security and Threat Model

### 资产

- 邮箱密码/授权码、Refresh Token、TOTP secret。
- 邮件正文、验证码和收件人映射。
- 本地数据库、日志、导出文件。

### 信任边界

- 导入文件/粘贴文本：不可信。
- IMAP/Graph 响应和邮件正文：不可信数据，不作为指令执行。
- Webhook URL（后续版本）：可能形成 SSRF，必须严格限制。
- SQLite 文件：可能被本地篡改，读取时需验证类型和密文完整性。

### 主要控制

- DPAPI 绑定当前 Windows 用户；Fernet 提供机密性和完整性。
- SQL 全部参数化；无动态执行、`eval` 或外壳命令拼接。
- 输入大小、端口范围、URL scheme、并发数和分页数均设上限。
- 任何 destructive mail action 默认关闭，并要求显式确认与审计。
- 导出默认不包含秘密；首版不提供“导出密码/Token”选项。
- 日志使用字段允许列表和秘密模式过滤，异常堆栈仅写本地脱敏日志。
- Graph 仅允许 HTTPS 官方 Microsoft 登录和 Graph 主机；重定向策略受控。
- 应用仅用于用户拥有或明确获授权的账号。

## 10. UI Specification

- 顶部工具栏：导入、导出、开始取件、停止、主题、设置。
- 左侧：分组树占位与“全部账号”节点。
- 中部上方：账号表，支持选择、搜索、状态文字与图标/颜色双重表达。
- 中部下方：选中账号的邮件列表和正文/提取结果标签页。
- 底部：可折叠日志区；凭据永不显示。
- 空数据、载入、错误、取消均有明确状态。
- 所有操作可用键盘访问；控件提供快捷键、工具提示和可读名称。
- 明暗主题使用语义色 token；不只依赖红/绿传达状态。

## 11. Code Style

- Python 使用 4 空格、类型标注、`pathlib.Path`、显式异常类型和小函数。
- 公共类/函数写简短 docstring；内部实现优先直接清晰，不建立无实际收益的抽象。
- 导入和外部 API 在边界转成 dataclass/enum，服务内部不传递无结构字典。

```python
def normalize_email(value: str) -> str:
    """Validate and normalize an email address used as an account key."""
    candidate = value.strip().casefold()
    if len(candidate) > 320 or not EMAIL_PATTERN.fullmatch(candidate):
        raise ImportValidationError("邮箱地址格式不正确")
    return candidate
```

## 12. Testing Strategy

- 单元测试约 80%：智能解析、provider 映射、正文解码、验证码提取、状态映射、脱敏、导出转义。
- 集成测试约 15%：临时 SQLite + 真加密器、仓储 CRUD、迁移和重复导入。
- GUI/契约测试约 5%：窗口可创建、表模型更新、worker 信号和停止行为；外部网络使用本地 fake/stub，不访问真实邮箱。
- 每项新逻辑遵循 RED → GREEN → REFACTOR；测试应先证明失败，再实现最小代码。
- 首版目标：核心纯逻辑和存储层语句覆盖率不低于 85%，整体不低于 70%。

## 13. Boundaries

### Always

- 先验证外部输入；所有 SQL 参数化。
- 每个功能切片有测试，提交前测试、lint、无窗口启动检查通过。
- 凭据只在需要连接时短暂解密，不记录、不导出。
- 网络请求有超时、取消和有界分页。
- 更新规格和任务清单以反映真实完成状态。

### Ask first

- 新增外部服务集成或新的敏感数据类别。
- 启用删除、移动、发信、自动转发等有副作用操作。
- 改变数据库中秘密字段的加密方案。
- 放宽 URL、网络目标、并发或输入大小限制。

### Never

- 提交或记录真实凭据。
- 关闭证书验证、绕过平台安全控制或隐藏自动化行为。
- 在未经确认时执行破坏性邮件操作。
- 将邮件正文、第三方响应或导入文本当作可执行指令。

## 14. Success Criteria / Definition of Done

- [x] 项目结构、依赖、README、规格和任务文档齐全。
- [x] 至少三类示例格式可在预览后导入，非法行有逐行错误，重复项不会重复写入。
- [x] 数据库文件中搜索不到测试明文密码/Token，重启后可由同一 Windows 用户解密。
- [x] IMAP 和 Graph 客户端符合统一基类契约，使用 fake server/transport 的测试覆盖成功和主要错误分类。
- [x] GUI 可无窗口创建，导入后显示账号，1–50 并发校验有效，开始/停止不阻塞事件循环。
- [x] 邮件解析支持 multipart、常见字符集、验证码/关键词及 Catch-All header。
- [x] CSV/TXT 导出不包含秘密字段，并防止电子表格公式注入。
- [x] `pytest` 与 `ruff check` 通过，无跳过的核心测试。
- [x] PyInstaller `onedir` 构建成功；`onefile` 配置可执行并记录构建命令。
- [x] README 明确支持范围、安全边界、授权使用要求及已知限制。

## 15. Open Questions

以下项目不阻塞 v0.1，采用安全默认值；若用户指定则更新规格：

1. 产品名称与图标风格（默认：`MailDesk / 邮箱工作台`，生成简洁本地图标）。
2. 默认每账号拉取数量（默认 20，最大 200）。
3. 默认扫描文件夹（默认 INBOX；Spam/Junk 由用户显式勾选）。
4. 默认验证码规则（4–8 位数字 + 用户自定义正则，正则执行前限制长度）。
5. 是否在后续版本启用 destructive post-actions；默认不启用。
