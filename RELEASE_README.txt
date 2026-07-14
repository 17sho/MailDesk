MailDesk v0.2.0 · Windows x64
================================

项目主页：https://github.com/17sho/MailDesk
版本页面：https://github.com/17sho/MailDesk/releases/tag/v0.2.0

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

安全校验
--------
下载后可在 PowerShell 中校验：

Get-FileHash .\MailDesk-v0.2.0-windows-x64-onefile.zip -Algorithm SHA256
Get-FileHash .\MailDesk-v0.2.0-windows-x64-onedir.zip -Algorithm SHA256

将结果与 Release 中的 SHA256SUMS.txt 比对。

本版本未使用商业代码签名证书。Windows SmartScreen 或杀毒软件可能对新的
PyInstaller 程序显示未知发布者提示；请先核对 SHA256，并仅从项目官方 Release 下载。

许可证
------
MailDesk 自有代码使用 MIT License。压缩包中的 LICENSE、THIRD_PARTY_NOTICES.md
和 licenses 目录包含项目及第三方组件声明。

本软件按“原样”提供，不附带任何明示或默示担保。
