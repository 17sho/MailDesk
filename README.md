# MailDesk

<div align="center">

**面向 Windows 与 macOS 的本地多邮箱管理工作台**

[![Version](https://img.shields.io/badge/version-0.3.3-2563eb.svg)](https://github.com/17sho/MailDesk/releases)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776ab.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078d4.svg?logo=windows11&logoColor=white)](https://github.com/17sho/MailDesk/releases)
[![macOS](https://img.shields.io/badge/macOS-13%2B-111111.svg?logo=apple&logoColor=white)](docs/MACOS.md)
[![GUI](https://img.shields.io/badge/GUI-PySide6-41cd52.svg?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![CI](https://github.com/17sho/MailDesk/actions/workflows/ci.yml/badge.svg)](https://github.com/17sho/MailDesk/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-f5c518.svg)](LICENSE)

[功能](#功能矩阵) · [快速开始](#快速开始) · [macOS](docs/MACOS.md) · [导入格式](#账号导入格式) · [安全](#数据安全) · [构建](#构建-windows-exe) · [贡献](#贡献)

</div>

MailDesk 是使用 Python 3.12 与 PySide6 编写的 Windows/macOS 桌面应用，用于集中管理用户本人拥有或已获得明确授权的邮箱。它将账号导入、协议连接、并发收件、本地检索、邮件阅读、内容提取、发件、分组调度与审计集中在一个本地工作台中。

当前仓库版本为 **0.3.3**。Windows 与 macOS 使用同一正式版本和同一个 GitHub Release。Windows 数据默认保存在 `%LOCALAPPDATA%\MailDesk`，macOS 数据保存在 `~/Library/Application Support/MailDesk`；密码、应用专用密码、Refresh Token、TOTP 密钥等凭据字段使用 Windows DPAPI 或 macOS 钥匙串保护的随机 Fernet 主密钥进行加密。

> [!IMPORTANT]
> MailDesk 仅适用于合法、获授权的邮箱管理与自动化场景。项目不提供验证码绕过、封禁规避、隐藏式网页登录、批量修改密码/恢复邮箱、规避 Rate Limit 或其他绕过服务商安全控制的能力。使用者必须遵守邮箱服务商条款、组织安全政策与适用法律。

## 界面预览

![MailDesk 工作台概览](docs/images/overview.png)

<details>
<summary>查看账号与邮件界面</summary>

![MailDesk 账号与邮件](docs/images/accounts.png)

</details>

截图使用 `example.org` / `example.net` 虚构账号和演示邮件生成，不包含真实凭据或私人邮件。

## 功能矩阵

以下矩阵以 v0.3.3 当前代码为准。

| 模块 | 支持情况 | 说明 |
|---|---:|---|
| 账号导入 | ✅ | TXT、CSV、JSON、文件拖放与任意文本粘贴；导入前提供字段映射/识别预览、校验与去重 |
| 账号管理 | ✅ | 多选、批量删除、状态筛选、搜索、多层分组、标签与状态着色 |
| 凭据存储 | ✅ | SQLite 持久化；随机 Fernet 主密钥由 Windows DPAPI 或 macOS 钥匙串保护 |
| 通用收件 | ✅ | IMAP、POP3，支持 SSL、STARTTLS、自定义主机和端口 |
| OAuth2 收件 | ✅ | Microsoft Graph；Microsoft/Google Refresh Token + Client ID 换取 Access Token 后使用 Graph 或 XOAUTH2 IMAP |
| 批量取件 | ✅ | `QThreadPool` 并发、1–50 并发配置、协作式停止、统一连接状态与错误分类 |
| 单账号取件 | ✅ | 可对指定账号立即收取，不必刷新全部账号 |
| 文件夹扫描 | ✅ | 指定文件夹及 Junk/Spam/Trash 等特殊文件夹识别与合并收取 |
| 邮件解析 | ✅ | MIME multipart、常见字符集、纯文本/HTML、内嵌资源、附件、远程图片控制与 EML 原件 |
| 内容提取 | ✅ | 4–8 位验证码、关键词、自定义正则，以及 `To` / `X-Original-To` Catch-All 收件地址 |
| 搜索与导出 | ✅ | 当前账号或全部本地邮件搜索；按自定义文本/链接模式筛选并复制或导出；账号状态 CSV/TXT |
| 邮件阅读器 | ✅ | HTML 正文、附件保存、链接复制、远程图片授权加载、按需正文翻译 |
| 邮件发送 | ✅ | SMTP 或 Microsoft Graph；单账号/多账号发件、To/CC/BCC、文本/HTML 正文与附件；批量发件要求显式确认 |
| 邮件后处理 | ✅ | 匹配后标记已读、移动或删除；有副作用的操作必须由用户显式启用并确认 |
| 自动化连接 | ✅ | HTTPS Webhook、HMAC-SHA256 签名、规则匹配、用户确认后的 EML 转发 |
| 调度与托盘 | ✅ | 按分组定时收件、系统托盘驻留与新邮件通知 |
| 工作台 | ✅ | 账号健康度、邮件趋势、异常账号入口、代理开关与可配置快捷操作 |
| 审计与诊断 | ✅ | 脱敏日志、审计事件与 ZIP 排查报告；Outlook 转发/重定向规则只读检查 |
| 在线升级 | ✅ | 后台检查正式版、Ed25519 发布签名与 SHA-256 校验、事务锁、健康启动回执及失败回滚 |
| Windows 打包 | ✅ | PyInstaller `onedir` 与 `onefile`，包含应用图标和所需 Qt/Windows 运行时收集逻辑 |
| macOS 打包 | ✅ | GitHub 原生 arm64/x64 Runner 构建 `.app`、DMG 与 ZIP；与 Windows 同版本正式发布，当前未做 Apple 公证 |

## 支持的协议与服务商

### 协议与认证方式

| 协议/方式 | 用途 | 认证说明 |
|---|---|---|
| IMAP | 收件、文件夹读取、邮件后处理 | 密码/授权码/应用专用密码，或 Microsoft/Google XOAUTH2 |
| POP3 | 基础收件 | 密码、授权码或应用专用密码；不提供 IMAP 文件夹语义 |
| SMTP | 发件、权限自检、确认后的转发 | 密码/授权码/应用专用密码，或 Microsoft/Google OAuth2 |
| Microsoft Graph | Outlook / Microsoft 365 收件、附件、发件与邮件动作 | 用户提供合法取得的 Client ID、Refresh Token 与 tenant；权限由原授权决定 |

通用 IMAP/POP3/SMTP 可以配置 SSL 或 STARTTLS。代码模型也保留明文连接兼容项，但不建议在不受信网络中使用未加密连接。

### 内置服务商配置

| 服务商/域名 | 自动补全 | 推荐凭据 |
|---|---:|---|
| QQ 邮箱、Foxmail | ✅ | 邮箱授权码 |
| 163、126、Yeah、88 邮箱 | ✅ | 客户端授权码 |
| 新浪邮箱 | ✅ | 服务商允许的客户端授权凭据 |
| Gmail / Google Workspace | ✅ | 应用专用密码，或 Google OAuth2 Client ID + Refresh Token |
| Outlook、Hotmail、Live、Microsoft 365 | ✅ | Microsoft OAuth2 Client ID + Refresh Token；可选择 Graph 或 OAuth2 IMAP |
| 企业邮箱、自建域名邮箱 | 手动/受限探测 | 自定义 IMAP/POP3/SMTP 主机、端口和加密方式 |

服务商可能要求先开启 IMAP/POP3/SMTP、启用两步验证、创建应用专用密码，或由组织管理员授予 OAuth 权限。MailDesk 不会替用户绕过这些设置，也不负责签发 Refresh Token。

自定义域名探测必须由用户显式启动，仅尝试 `imap.<domain>`、`mail.<domain>` 与常见 993/143 组合；它不是完整的 MX/SRV 自动发现。

## 快速开始

### 直接下载 Windows 版

在 [MailDesk v0.3.3 Release](https://github.com/17sho/MailDesk/releases/tag/v0.3.3) 下载带版本号的 Windows x64 压缩包：

| 文件 | 适用场景 |
|---|---|
| `MailDesk-v0.3.3-windows-x64-onefile.zip` | 解压后直接运行单个 `MailDesk.exe`，携带方便，首次启动较慢 |
| `MailDesk-v0.3.3-windows-x64-onedir.zip` | 保持目录完整并运行 `MailDesk\MailDesk.exe`，启动更快，推荐日常使用 |
| `MailDesk-update-manifest-v1.json` | 同时绑定版本、仓库、Windows/macOS 正式包名称、体积和 SHA-256 的更新清单 |
| `MailDesk-update-manifest-v1.sig` | 使用离线 Ed25519 发布私钥生成的清单签名 |
| `SHA256SUMS.txt` | 供人工核对全部发行文件的 SHA-256 校验值 |

压缩包内包含使用说明、MIT License、第三方组件声明及许可证文本。当前二进制没有商业代码签名，Windows SmartScreen 可能显示“未知发布者”；请只从本仓库 Release 下载并先核对 SHA-256。

### 下载 macOS 正式版

macOS 与 Windows 共用 [v0.3.3 正式 Release](https://github.com/17sho/MailDesk/releases/tag/v0.3.3)。Apple Silicon 下载 `MailDesk-v0.3.3-macos-arm64.dmg`，Intel Mac 下载 `MailDesk-v0.3.3-macos-x64.dmg`；ZIP 是应用内自动更新包。架构选择、钥匙串存储、Gatekeeper 首次打开步骤和限制见 [`docs/MACOS.md`](docs/MACOS.md)。

macOS 包目前没有 Apple Developer ID 签名和公证，首次打开需要在 Finder 中 Control-点击并选择“打开”，或在“系统设置 → 隐私与安全性”中确认。请只从项目官方 Release 下载。

### 在线升级

**v0.3.0 是首个内置在线升级客户端的版本。** v0.2.0 及更早版本无法自动升级到 v0.3.0，需要先从上方 Release 手动下载一次；安装 v0.3.0 后，应用即可检查并安装后续正式版本。

v0.3.1 进一步移除了安装助手对 `Get-FileHash` 的依赖，并隔离 PowerShell 7 与 Windows PowerShell 5 的模块环境差异，提升后台安装与失败回滚在不同 Windows 启动环境中的一致性。

v0.3.2 修复点击“重启并安装”后界面长时间无响应的问题：最终完整性校验和安装助手握手改为后台执行，并显示明确阶段状态；同时增加单实例锁，并移除会导致 Windows 更新暂存路径超过 `MAX_PATH` 的未使用 QML 资源。

v0.3.3 将 macOS 纳入与 Windows 相同的正式版本和签名 Release：客户端按 Apple Silicon/Intel 自动选择 ZIP，在后台下载，确认后替换当前 `MailDesk.app`，等待新版健康回执；启动失败会恢复旧 `.app` 并重新打开。Framework 相对符号链接、文件权限和 Mach-O 架构均在安装前验证。

- 应用启动后会在后台查询本仓库最新的非草稿、非预发布 Release；检查失败不会干扰启动。
- 发现新版本时会弹出提示，并在顶部显示“更新”按钮。可以查看版本说明、跳过当前版本或开始下载。
- 下载在后台进行，顶部按钮和更新窗口会显示进度，正常的邮箱管理操作不会因此阻塞。
- 客户端内置 Ed25519 发布公钥；只有清单签名有效，且版本、安装模式、文件名、体积和 SHA-256 全部匹配时才允许下载和安装。`SHA256SUMS.txt` 仍供用户手动核对，但不是自动执行的唯一信任来源。
- 下载完成后会安全解压并生成逐文件完整性清单；安装前会再次联网确认 Release 未被撤回、签名和资产均未变化，然后再次请求确认。
- 只有选择“重启并安装”才会启动外部更新助手。助手先确认接管，再在目标磁盘的相邻临时路径完成复制和校验，通过原子重命名切换 Windows `onefile` / `onedir` 或 macOS `.app`，并等待新版启动健康回执；启动失败会恢复备份并重新打开旧版。
- 更新事务使用跨进程文件锁，避免多个 MailDesk 实例争抢同一暂存区。临时更新文件和有限的安装结果记录保存在 `%LOCALAPPDATA%\MailDesk\updates` 或 `~/Library/Application Support/MailDesk/updates`。

在线升级不需要登录 GitHub，但需要能够访问 GitHub，且 MailDesk 所在目录需要当前用户具备写入权限。源码开发模式不会覆盖源码目录；开发者应通过 Git 拉取代码和重新安装依赖完成升级。应用级 Ed25519 签名用于验证 MailDesk Release，但不等同于 Windows Authenticode 或 Apple Developer ID 证书。

当前更新签名公钥（Base64 原始 Ed25519 公钥）为 `ZGx6G4ac2jh9UG+/NIEKLKKYTM8MdNt52IfHuNoiRts=`；客户端和 `release.py` 都会校验同一信任根。公钥可以公开，发布私钥绝不能进入仓库或发行包。

### 环境要求

- Windows 10/11，或 macOS 13 及以上版本
- Python 3.12 或更高的兼容 3.12 版本
- 可访问目标邮箱官方服务器的网络
- 对相关邮箱和 OAuth 应用具有合法管理权限

### 1. 获取代码

```powershell
git clone https://github.com/17sho/MailDesk.git
cd MailDesk
```

### 2. 创建虚拟环境并安装

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

如需运行测试、代码检查或构建 EXE，再安装开发依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 3. 启动应用

```powershell
.\.venv\Scripts\python.exe -m mailbox_manager
```

也可以在已激活虚拟环境后运行入口命令：

```powershell
maildesk
```

### 4. 基本使用流程

1. 在“添加邮箱”中选择服务商和认证方式，或打开“批量导入”。
2. 在导入预览中核对协议、服务器、端口和认证字段；只勾选确认无误的记录。
3. 在账号列表中勾选账号，执行单账号取件或批量取件。
4. 在邮件列表中阅读正文、查看附件、搜索邮件或提取验证码/关键词。
5. 按需在“系统设置”中配置文件夹、收取数量、代理、调度、翻译和自动化规则。

## 账号导入格式

导入文件最大 20 MiB，文本最多 100,000 行。支持 UTF-8、UTF-8 BOM，并兼容读取 GB18030。示例文件见 [`examples/accounts.txt`](examples/accounts.txt)。

### TXT 与粘贴文本

字段分隔格式支持：

```text
账号----密码或授权码----IMAP服务器----端口
账号----主密码占位----授权码或应用专用密码
账号----RefreshToken----ClientID
账号----密码占位----ClientID----RefreshToken
账号----密码或授权码----IMAP服务器----端口----TOTP密钥
```

示例：

```text
owner@example.org----APP_PASSWORD----imap.example.org----993
user@qq.com----IGNORED_MAIN_PASSWORD----AUTHORIZATION_CODE
owner@outlook.com----REFRESH_TOKEN----00000000-0000-0000-0000-000000000001
user@gmail.com----GOOGLE_REFRESH_TOKEN----123456789.apps.googleusercontent.com
```

- Microsoft Client ID 识别为 UUID；Google Client ID 识别为 `*.apps.googleusercontent.com`。
- OAuth 行会从 Client ID 相邻字段中识别 Refresh Token；带有密码占位的 OAuth 行不会保存该密码字段。
- 常见服务商的三字段格式优先使用第三字段作为授权码/应用专用密码。
- 任意文本模式会启发式识别邮箱及相邻凭据，所有结果仍须在预览页人工确认。
- 文本中发现代理只会给出提示；代理必须在代理设置中单独确认导入。

### CSV

CSV 支持逗号、分号、Tab 或竖线分隔，可使用中英文表头。常见字段包括：

```text
email / account / 账号 / 邮箱
password / secret / 授权码 / 应用专用密码
host / imap_server / 服务器
port / 端口
protocol / 协议
security / 加密方式
refresh_token / client_id / tenant / oauth_provider
smtp_host / smtp_port / smtp_security
totp_secret
```

无表头 CSV 会按位置转换为与 TXT 相同的字段顺序后解析。

### JSON

接受账号对象数组，或包含 `accounts` 数组的对象：

```json
{
  "accounts": [
    {
      "email": "owner@example.org",
      "password": "APP_PASSWORD",
      "protocol": "imap",
      "host": "imap.example.org",
      "port": 993,
      "security": "ssl",
      "smtp_host": "smtp.example.org",
      "smtp_port": 465,
      "smtp_security": "ssl"
    }
  ]
}
```

重新导入已存在账号时，变更后的连接配置会更新原记录，并保留其分组、标签和已收取邮件。

## 本地数据目录

Windows 首次运行会创建：

```text
%LOCALAPPDATA%\MailDesk\
├─ maildesk.db          # SQLite：账号、配置、邮件、附件、审计等
├─ master.key.dpapi     # 当前 Windows 用户 DPAPI 保护的随机主密钥
├─ logs\app.log         # 滚动、脱敏应用日志
├─ eml\                 # 按账号隔离保存的邮件原件
└─ updates\             # 已下载并校验的在线升级暂存文件
```

macOS 对应目录为 `~/Library/Application Support/MailDesk`，主密钥保存于当前用户钥匙串，数据目录中只保留 `master.key.keychain` 标记文件。

不要只复制 `maildesk.db`、`master.key.dpapi` 或 `master.key.keychain` 到其他电脑。DPAPI/钥匙串与创建密钥的系统用户绑定，迁移后通常无法解密凭据。迁移前应使用应用提供的非敏感导出，并在目标设备重新录入凭据。

## 数据安全

- **字段级加密**：密码、授权码、Refresh Token、TOTP 密钥、代理密码和 Webhook 密钥等敏感字段以密文写入 SQLite。
- **本机密钥保护**：Fernet 使用随机 32 字节主密钥；主密钥由当前 Windows 用户的 DPAPI 或当前 macOS 用户的钥匙串保护。
- **最小暴露**：Access Token 仅在协议客户端内存中使用，不写入导出文件或正常日志。
- **安全导出**：账号导出不包含密码或 Token，并对可能触发电子表格公式的 CSV 单元格进行转义。
- **日志脱敏**：取件、发件与诊断日志使用账号标识和结果分类，不应记录完整凭据。
- **Webhook 限制**：仅允许 HTTPS 和允许列表主机；阻止私网、回环及保留地址，禁止重定向，可选 HMAC-SHA256 签名。
- **远程内容控制**：阅读器对远程图片采用显式加载/配置控制，降低邮件跟踪像素和未知外部请求风险。
- **更新包校验**：在线升级仅接受官方 GitHub Release 的 HTTPS 资产，并验证离线 Ed25519 发布签名、版本/模式/体积及 SHA-256；校验失败不会执行替换。
- **副作用确认**：删除、移动、自动转发和批量发件等操作要求用户显式配置或确认。

DPAPI/钥匙串/Fernet 保护的是**凭据字段**，不是整个数据库。已收取的邮件正文、附件和一般元数据需要在本地展示与检索，因此不应视为全盘加密数据。建议启用 BitLocker 或 FileVault、系统账户保护与可靠的设备锁屏，并妥善控制 MailDesk 数据目录的访问权限。

邮件翻译是按需功能。触发翻译时，当前邮件正文会发送给界面标明的第三方翻译服务；账号密码、Refresh Token、附件和账号配置不会作为翻译负载发送。处理敏感邮件前请先评估组织的数据出境与隐私要求。

## 代理路由与合规节流

支持批量导入 HTTP 或 SOCKS5 代理：

```text
IP:Port
IP:Port:User:Pass
```

单次最多导入 10,000 条。代理用户名和密码必须成对提供，代理密码使用本机凭据密钥加密。

取件路由优先级固定如下：

1. **账号固定代理优先**：账号绑定的代理必须存在且处于启用状态；否则该账号任务失败，不会静默回退到本地网络。
2. **全局代理池**：账号未绑定固定代理且全局代理取件已开启时，在已启用代理中轮询选择一个路由。
3. **本地直连**：全局代理开关关闭，或全局开启但当前没有可用代理时，未绑定代理的账号使用本地网络。

当前代理路由覆盖 IMAP、POP3、Microsoft Graph 及收件所需的 OAuth Token 交换。不要假定 SMTP 发件一定经过上述取件代理路由。

节流按真实网络身份分别执行，可配置每个身份的最大并发数与账号启动随机间隔。该机制用于控制负载、减少误操作并尊重服务商限制；全局代理轮询不是规避风控或隐藏批量登录来源的工具。遇到 `429`、封禁或服务商限制时，应停止任务并按官方流程处理。

## 测试与代码检查

安装 `requirements-dev.txt` 后，在仓库根目录运行：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests build.py release.py
```

测试覆盖导入、加密仓储、协议错误分类、Graph/IMAP/POP3/SMTP、代理路由、取件/发件服务、Webhook、自动化、邮件解析、GUI 交互和构建脚本。测试使用临时数据库、协议替身与 HTTP Mock Transport，不需要在测试代码中放入真实邮箱凭据。

提交问题时请勿附带真实密码、授权码、Refresh Token、TOTP 密钥、代理口令或未脱敏邮件原件。贡献流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，漏洞报告方式见 [`SECURITY.md`](SECURITY.md)。

## 构建 Windows EXE

确保开发依赖已经安装，并优先完成测试。构建脚本会从 `src/mailbox_manager/assets/app.svg` 生成 `assets/app.ico`，再调用 [`mailbox-manager.spec`](mailbox-manager.spec)。

### 目录版（推荐用于排查和分发验证）

```powershell
.\.venv\Scripts\python.exe build.py --mode onedir --clean
```

输出：

```text
dist\MailDesk\MailDesk.exe
```

### 单文件版

```powershell
.\.venv\Scripts\python.exe build.py --mode onefile --clean
```

输出：

```text
dist\MailDesk.exe
```

`onefile` 首次启动时需要释放 Qt 运行时，通常比 `onedir` 慢。正式发布前应在干净的 Windows 10/11 环境中分别验证启动、主题切换、邮件正文渲染、网络协议和托盘功能；代码签名、杀毒软件信誉与安装器不由 PyInstaller 自动完成。

两个 EXE 都构建完成后，可使用离线 Ed25519 私钥生成带版本号、许可证、签名清单和 SHA-256 的发行文件。私钥必须保存在仓库之外，禁止提交、上传或写入 CI 日志：

```powershell
$env:MAILDESK_RELEASE_SIGNING_KEY = "D:\secure\maildesk-release-signing-ed25519.pem"
.\.venv\Scripts\python.exe release.py --version 0.3.3 `
  --extra-asset .\macos\MailDesk-v0.3.3-macos-arm64.zip `
  --extra-asset .\macos\MailDesk-v0.3.3-macos-x64.zip `
  --extra-asset .\macos\MailDesk-v0.3.3-macos-arm64.dmg `
  --extra-asset .\macos\MailDesk-v0.3.3-macos-x64.dmg
Remove-Item Env:MAILDESK_RELEASE_SIGNING_KEY
```

`release.py` 会拒绝与客户端内置公钥不匹配的私钥，避免发布客户端无法验证的更新。统一正式 Release 应同时发布两个 Windows ZIP、两个 macOS ZIP、两个 macOS DMG、`MailDesk-update-manifest-v1.json`、`MailDesk-update-manifest-v1.sig` 和 `SHA256SUMS.txt`。发布私钥一旦丢失，旧客户端无法自动信任新的签名根，必须通过手动升级完成密钥轮换，因此应制作离线加密备份。

输出位于 `artifacts\releases`。脚本会验证 EXE 的 Windows 版本资源，并从当前构建环境收集第三方 Python 包的许可证文件。

## 构建 macOS App

macOS 包必须在真实 macOS 环境构建。安装开发依赖后运行：

```bash
.venv/bin/python build_macos.py --clean
```

输出为 `dist/MailDesk.app`。GitHub 的 [`macos-release.yml`](.github/workflows/macos-release.yml) 会在 arm64 与 Intel Runner 上分别执行测试、构建、应用元数据与入口签名信息检查、隔离启动测试，并生成 DMG/ZIP。完整步骤见 [`docs/MACOS.md`](docs/MACOS.md)。

## 项目结构

```text
MailDesk/
├─ src/mailbox_manager/
│  ├─ gui/                 # PySide6 主窗口、对话框、工作台、阅读器与主题
│  ├─ protocols/           # IMAP、POP3、SMTP、Graph、OAuth2 与代理 Socket
│  ├─ importers/           # TXT/CSV/JSON 导入与智能字段解析
│  ├─ mail/                # MIME 解析、正文安全展示、远程图片与 Web 文档处理
│  ├─ services/            # 取件、发件、代理、调度、自动化、Webhook、审计等
│  ├─ storage/             # SQLite、DPAPI/钥匙串/Fernet 与仓储实现
│  ├─ domain/              # 数据模型、状态与领域错误
│  ├─ observability/       # 脱敏日志配置
│  ├─ app.py               # 依赖装配与应用启动
│  └─ __main__.py          # python -m mailbox_manager 入口
├─ tests/                  # unit、integration 与 GUI 测试
├─ examples/               # 脱敏导入示例
├─ legal/                  # GPL/LGPL/Python 许可证全文
├─ build.py                # PyInstaller 构建入口
├─ build_macos.py          # macOS ICNS 与 MailDesk.app 构建入口
├─ release.py              # 版本化 ZIP、第三方许可证和 SHA-256 生成
├─ THIRD_PARTY_NOTICES.md  # Windows 发行包第三方组件声明
├─ mailbox-manager.spec    # onefile/onedir 共用构建规格
├─ mailbox-manager-macos.spec # macOS .app 构建规格
├─ pyproject.toml          # 包元数据、依赖和工具配置
├─ SPEC.md                 # 产品与架构规格
└─ ENTERPRISE_FEATURES.md  # 企业功能与安全替代矩阵
```

## 已知限制与合规边界

- 生产凭据存储在 Windows 使用 DPAPI、在 macOS 使用当前用户钥匙串；macOS 是正式发布但目前未使用 Apple Developer ID 签名和公证。
- OAuth2 Client ID、Refresh Token 与所需权限必须通过服务商官方流程取得，MailDesk 不内置绕过式授权流程。
- 服务商可能禁用基础认证、IMAP、POP3 或 SMTP；实际可用性取决于账号设置、租户政策和服务商限制。
- 本地搜索只覆盖已经收取并保存到本机的邮件，不等同于服务商端的完整全文检索。
- “单次取件数量设为 0”表示不设应用层数量上限，仍受服务商分页、连接稳定性、磁盘与内存资源限制。
- 在线升级只跟踪 GitHub 上的正式 Release，不会自动安装草稿或预发布版本；无 GitHub 网络访问时可继续使用当前版本并手动升级。
- 邮件移动、删除、转发和批量发送可能产生不可逆影响，启用前应先使用测试账号验证规则。
- 自定义域名发现仅做少量常见候选探测，不执行隐藏浏览器登录、网页 DOM 抓信或自动开启协议。
- 项目不执行批量改密、恢复邮箱修改、账号接管、自动删除安全规则、验证码绕过、身份/IP 隐匿或服务商风控规避。

更详细的设计背景见 [`SPEC.md`](SPEC.md)，企业能力与安全替代见 [`ENTERPRISE_FEATURES.md`](ENTERPRISE_FEATURES.md)。

## 贡献

欢迎通过 [Issues](https://github.com/17sho/MailDesk/issues) 提交可复现缺陷或合规的功能建议，也欢迎提交 Pull Request。

建议流程：

1. Fork 仓库并从 `main` 创建主题分支。
2. 保持改动范围清晰，为行为变更补充测试。
3. 运行完整 `pytest` 与 `ruff` 检查。
4. 在 Pull Request 中说明使用场景、验证方式、安全影响和兼容性变化。

贡献代码不得包含真实邮箱凭据、个人邮件、规避服务商控制的实现或未经授权的自动化流程。提交前请先阅读本 README 的[合规边界](#已知限制与合规边界)。

## 安全问题报告

请不要在公开 Issue 中披露可利用漏洞或真实密钥。安全问题应通过 GitHub 的 [Private vulnerability reporting](https://github.com/17sho/MailDesk/security/advisories/new) 私下报告，并提供：

- 受影响版本与 Windows/Python 环境；
- 最小复现步骤和预期影响；
- 已做脱敏的日志或示例数据；
- 如已知，建议的缓解方案。

## License

MailDesk 使用 [MIT License](LICENSE) 开源。你可以在保留版权和许可声明的前提下使用、复制、修改、合并、发布和分发本项目。第三方依赖仍分别适用其各自的许可证。
