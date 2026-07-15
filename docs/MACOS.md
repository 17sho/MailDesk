# MailDesk macOS 版

MailDesk macOS 版由 GitHub 的真实 macOS Runner 构建，分别提供 Apple Silicon 与 Intel 包。macOS 与 Windows 使用同一个正式版本号、同一个 GitHub Release 和同一份 Ed25519 签名更新清单；它不是在 Windows 上交叉编译或简单改名得到的文件。

## 下载选择

- `arm64`：Apple Silicon，适用于 M1、M2、M3、M4、M5 等芯片。
- `x64`：Intel Mac。
- `.dmg`：推荐普通用户使用，打开后把 `MailDesk.app` 拖到“应用程序”。
- `.zip`：应用内在线升级使用，也可手动解压部署。

最低目标系统为 macOS 13。首次启动前请使用 Release 中的 `SHA256SUMS.txt` 核对下载文件。

## 首次打开与 Gatekeeper

当前项目没有 Apple Developer ID 证书，因此应用未进行 Apple 公证。macOS 可能提示“无法验证开发者”。这不代表 SHA-256 或 GitHub Release 签名失效，但系统无法确认商业开发者身份。

推荐操作：

1. 只从项目官方 GitHub Release 下载并核对 SHA-256。
2. 将 `MailDesk.app` 移到“应用程序”。
3. 在 Finder 中按住 Control 点击 MailDesk，选择“打开”，再确认一次“打开”。
4. 如果仍被阻止，进入“系统设置 → 隐私与安全性”，在安全提示下选择“仍要打开”。

不要从不明网盘、群文件或二次打包站下载。项目不会要求关闭系统完整性保护。

## 数据与凭据

- 数据目录：`MailDesk.app` 同级的 `MailDesk Data`
- 更新目录：`MailDesk.app` 同级的 `.maildesk-update`
- 数据库：`maildesk.db`
- 日志：`logs/`
- 原始邮件：`eml/`
- 随机 Fernet 主密钥存放在当前 macOS 用户的“钥匙串”中。
- 数据目录中的 `master.key.keychain` 只是钥匙串项目标记，不包含明文主密钥。

首次访问钥匙串时，macOS 可能请求当前用户确认。删除 MailDesk 的钥匙串项目后，已有加密凭据将无法恢复。

## 功能与在线升级

IMAP、POP3、SMTP、Microsoft Graph、OAuth2、邮件阅读器、附件、翻译、搜索、导入导出、分组、代理和批量任务使用与 Windows 版相同的核心代码。

从 v0.3.3 开始，macOS 与 Windows 同步跟踪 GitHub 上最新的正式 Release，不会安装草稿或预发布版本，也不要求登录 GitHub：

1. 客户端根据当前机器自动选择 `macos-arm64.zip` 或 `macos-x64.zip`。
2. ZIP 在后台下载；版本、文件名、体积和 SHA-256 必须与内置公钥验证通过的 Ed25519 清单一致。
3. 下载后安全解压 `.app`，验证 `Info.plist` 版本、Bundle ID、最低系统版本、Mach-O 架构、可执行权限，以及 Framework 相对符号链接没有逃出应用目录。
4. 只有用户确认“重启并安装”后，外部 macOS 更新助手才会等待 MailDesk 退出，在同一磁盘创建新版副本并原子替换当前 `MailDesk.app`。
5. 新版必须写入启动健康回执并持续运行；否则助手会恢复备份并重新打开旧版。

在线升级要求 GitHub 可访问，且 `MailDesk.app` 所在目录对当前用户可写。如果应用位于无写入权限的系统目录，客户端会保留当前版本并提示从 Release 下载对应 DMG 手动安装。更新暂存与结果记录位于应用同级 `.maildesk-update`，确保下载、预复制和原子替换始终在同一磁盘进行。

v0.3.9 首次启动会把旧 `~/Library/Application Support/MailDesk` 中的数据库、钥匙串标记、日志和 EML 安全迁移到 `MailDesk Data`。旧更新缓存不会迁移，数据库校验失败时也不会删除原数据。更新应用时只替换 `MailDesk.app`，不会替换或删除同级 `MailDesk Data`。

系统托盘在 macOS 中显示为菜单栏图标。

## 代码签名限制

当前正式包仍未使用 Apple Developer ID 证书，也未完成 Apple 公证。应用内 Ed25519 签名能确认下载内容由 MailDesk 的离线发布密钥签发，但不能代替 Gatekeeper 的开发者身份验证。首次安装或系统策略变化后，仍可能需要按上面的 Gatekeeper 步骤确认打开。

## 从源码构建

必须在真实 macOS 上构建：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python build_macos.py --clean
```

输出位置为 `dist/MailDesk.app`。构建脚本会生成 ICNS 图标，并由 PyInstaller 创建原生 `.app` 目录。
