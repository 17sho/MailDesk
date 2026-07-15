# MailDesk v0.3.3

这是 Windows 与 macOS 首次完全同步的正式版本。两个平台使用同一个版本号、同一个正式 GitHub Release，以及同一份离线 Ed25519 签名更新清单。

## 本次更新

- macOS Apple Silicon (`arm64`) 与 Intel (`x64`) 不再单独标记为预发行版。
- macOS 支持应用内后台下载、安装前再次确认、自动退出并重启。
- macOS 更新助手会在同一磁盘预复制新版 `MailDesk.app`，原子切换后等待启动健康回执；新版无法正常启动时自动恢复旧版。
- macOS 自动更新会校验发布者签名、SHA-256、文件体积、应用版本、Bundle ID、最低系统版本、Mach-O 架构、可执行权限及 Framework 相对符号链接。
- Windows 继续提供 `onefile` 与推荐的 `onedir` 两种 x64 包，并保留 v0.3.2 的后台安装握手、单实例保护与失败回滚修复。
- `SHA256SUMS.txt` 和签名清单统一覆盖 Windows/macOS 的全部正式发行资产。

## 下载选择

- Windows 日常使用：`MailDesk-v0.3.3-windows-x64-onedir.zip`
- Windows 单文件：`MailDesk-v0.3.3-windows-x64-onefile.zip`
- Apple Silicon Mac：`MailDesk-v0.3.3-macos-arm64.dmg`
- Intel Mac：`MailDesk-v0.3.3-macos-x64.dmg`

macOS ZIP 主要供应用内自动升级，也可以手动解压。macOS 包当前没有 Apple Developer ID 签名和公证，首次打开可能需要在 Finder 中 Control-点击应用并选择“打开”。

在线升级不需要登录 GitHub，但必须能够访问 GitHub，且应用所在目录需要当前用户具备写入权限。
