# MailDesk v0.3.9｜稳定更新、便携数据与增量取件

本版本重点解决 Windows/macOS 在线更新不生效、用户数据写入系统盘、重复取件速度慢，以及 macOS 安装包体积过大的问题。

## 主要更新

- Windows 与 macOS 发行版现在会把用户数据保存在软件同级的 `MailDesk Data`，更新事务保存在同级 `.maildesk-update`。下载、预复制和程序替换始终位于用户选择的同一磁盘。
- 首次启动会安全迁移旧系统目录中的数据库、密钥标记、日志和可选 EML 文件；迁移前执行 SQLite 完整性校验，不会复制旧更新缓存。
- 更新检查、下载和安装接管使用独立线程池，慢速 IMAP 任务不会再阻塞“重启并安装”。
- Windows `onefile`、`onedir` 与 macOS `.app` 更新时只替换程序文件，同级 `MailDesk Data` 不会被删除，更新失败回滚也不会影响用户数据。
- 持久化保存 IMAP UID、POP3 UIDL 和 Microsoft Graph Message ID，后续刷新只下载未收取的新邮件，Graph 不再重复请求旧邮件附件。
- “立即取件”只检查当前账号最新的一封新邮件，不必刷新全部账号。
- 网络图片改为并发自动加载，并校验真实 PNG/JPEG/GIF/WebP 文件签名；使用有容量限制的内存缓存，重复打开邮件更快。
- 阅读完整 MIME/Graph 邮件不要求额外保存 EML 文件；“保存 EML 原件”改为可选设置，减少长期磁盘占用。
- macOS 构建移除未使用的 Qt 3D、Multimedia、PDF、Virtual Keyboard 等 Framework，同时保留 WebEngine 邮件阅读器所需运行时。

## 更新说明

旧版本仍可能把 v0.3.9 暂存到原系统数据目录。v0.3.9 首次启动时会先向旧安装助手写入健康回执，再迁移数据，避免安装助手误判启动失败并回滚；旧缓存会在下一次启动时安全清理。

如果当前旧版点击“重启并安装”仍完全没有反应，请从本页面手动下载并安装 v0.3.9 一次。安装 v0.3.9 后，后续版本将使用新的同盘更新链路。

## 下载选择

- Windows 日常使用推荐 `windows-x64-onedir.zip`，启动速度更快。
- Windows 便携使用可选择 `windows-x64-onefile.zip`。
- Apple Silicon（M1/M2/M3/M4/M5）请选择 `macos-arm64.dmg`。
- Intel Mac 请选择 `macos-x64.dmg`。
- macOS ZIP 主要用于应用内自动更新，也可以手动解压使用。

## 验证与兼容性

- Windows 本地完整测试：337 项通过，3 项跳过。
- macOS Intel 与 Apple Silicon 均在 GitHub 原生 Runner 完成测试、构建和 WebEngine 实际启动验证。
- 所有正式包均写入 `SHA256SUMS.txt`，并由统一 Ed25519 签名清单绑定版本、文件名、体积和 SHA-256。
- 本版本为 Windows/macOS 同步正式版，不是预发行版本。
- macOS 包暂未使用 Apple Developer ID 签名和公证，首次打开可能需要在 Finder 中按住 Control 点击应用并选择“打开”。
