MailDesk v0.3.3 · Windows x64
================================

项目主页：https://github.com/17sho/MailDesk
版本页面：https://github.com/17sho/MailDesk/releases/tag/v0.3.3

系统要求
--------
- Windows 10/11 x64
- 可访问目标邮箱官方服务器的网络
- 仅管理你本人拥有或已经明确获授权的邮箱

两个下载包
----------
1. onefile：解压后直接运行 MailDesk.exe。
   文件少、携带方便，但首次启动需要释放 Qt 运行时，通常较慢。

2. onedir：保持 MailDesk 文件夹内容完整，运行 MailDesk\MailDesk.exe。
   启动更快，也更方便排查 Qt 插件问题，推荐日常使用。

首次运行
--------
应用数据会创建在：
%LOCALAPPDATA%\MailDesk

其中凭据字段使用 Windows DPAPI + Fernet 加密。邮件正文和附件不是全盘加密，
建议开启 BitLocker，并保护好 Windows 账号。

在线升级
--------
v0.3.0 是首个内置在线升级客户端的版本。v0.2.0 及更早版本需要先手动下载
并安装本版本；从 v0.3.0 开始，应用可在后台检查并下载后续正式版本。

v0.3.1 移除了安装助手对 Get-FileHash 的依赖，并强化了 PowerShell 7 与
Windows PowerShell 5 混合环境下的安装、健康回执和失败回滚兼容性。

v0.3.2 将最终文件完整性校验和安装助手接管移到后台线程，修复点击“重启并安装”
后界面看似无响应的问题；同时限制同一数据目录只运行一个 MailDesk 实例，避免多个
进程共同占用安装目录导致更新失败。

v0.3.3 将 macOS arm64/x64 与 Windows 放入同一正式版本和同一签名 Release，并为
macOS 增加后台下载、确认重启、MailDesk.app 原子替换、启动健康检查与失败回滚。

发现新版时，应用会弹出提示并在顶部显示“更新”按钮。下载不会阻塞正常操作，
客户端会先用内置 Ed25519 公钥验证官方签名清单，再核对版本、安装模式、文件名、
体积和 SHA-256。安装前还会复核 Release 未被撤回；只有明确确认后才会启动外部
更新助手。助手完成相邻路径预复制、完整性复核和原子切换，并等待新版启动健康
回执；启动失败会恢复备份并重新打开旧版。也可以跳过当前提示版本。

更新仅从项目官方 GitHub Release 的 HTTPS 地址下载，暂存于：
%LOCALAPPDATA%\MailDesk\updates

在线升级需要能够访问 GitHub，且当前 Windows 用户对软件所在目录具有写入权限。
源码开发模式不会自动覆盖源码目录。Ed25519 是 MailDesk 应用级发布签名，不等同于
Windows Authenticode 证书，因此 SmartScreen 仍可能显示“未知发布者”。

安全校验
--------
下载后可在 PowerShell 中校验：

Get-FileHash .\MailDesk-v0.3.3-windows-x64-onefile.zip -Algorithm SHA256
Get-FileHash .\MailDesk-v0.3.3-windows-x64-onedir.zip -Algorithm SHA256

将结果与 Release 中的 SHA256SUMS.txt 比对。

自动更新还要求 Release 同时包含：
MailDesk-update-manifest-v1.json
MailDesk-update-manifest-v1.sig

本版本未使用商业代码签名证书。Windows SmartScreen 或杀毒软件可能对新的
PyInstaller 程序显示未知发布者提示；请先核对 SHA256，并仅从项目官方 Release 下载。

许可证
------
MailDesk 自有代码使用 MIT License。压缩包中的 LICENSE、THIRD_PARTY_NOTICES.md
和 licenses 目录包含项目及第三方组件声明。

本软件按“原样”提供，不附带任何明示或默示担保。
