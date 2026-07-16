MailDesk v0.4.0 · Windows x64
================================

项目主页：https://github.com/17sho/MailDesk
版本页面：https://github.com/17sho/MailDesk/releases/tag/v0.4.0

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
应用数据会创建在软件同级：
MailDesk Data

更新下载和安装事务会创建在同级：
.maildesk-update

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

Windows v0.3.9 文件夹版若提示“自动更新已回滚”，请彻底退出 MailDesk，下载
MailDesk-v0.4.0-hotfix-windows-x64-onedir.zip，只用其中的 MailDesk 程序文件夹覆盖
旧程序文件夹，并保留同级 MailDesk Data。Release 中 5.5 KB 的
MailDesk-v0.3.9-onedir-update-launcher.exe 只用于安全启动旧版、复测原始升级按钮；
它不安装根治代码。hotfix 版已修复工作目录继承问题，并在失败后清理无用暂存副本。

v0.3.3 将 macOS arm64/x64 与 Windows 放入同一正式版本和同一签名 Release，并为
macOS 增加后台下载、确认重启、MailDesk.app 原子替换、启动健康检查与失败回滚。

v0.3.4 增加单个 HTTP/SOCKS5 代理的可视化添加与默认代理设置，并在系统设置中加入
手动检查更新入口。IMAP 收件改为每批最多下载 25 封，降低代理和海外网络下的等待时间；
遇到不兼容批量 FETCH 的服务端会自动逐封回退。

v0.3.5 增加可记忆的关闭窗口选择，可最小化到托盘或完全退出，也可在设置中恢复每次
询问。Windows 包移除未使用的 Qt 3D、PDF、Multimedia、虚拟键盘及 QML 调试资源，
同时保留 HTML 邮件、内嵌图片和远程图片所需的 QtWebEngine。

v0.3.6 修复确认“重启并安装”后停在原界面的问题。确认后不再重复联网复核 Release，
而是立即校验已经通过发布签名与 SHA-256 验证的本地文件并启动安装助手，同时记录
清晰的接管阶段日志。旧版本若仍无法重启，请手动覆盖安装 v0.3.6 一次。

v0.3.7 在邮件列表和阅读器中分别显示发件人名称与邮箱；系统设置新增全局字体、字号
和字重，并完善深色菜单、提示框及文件选择器。IMAP 连接与命令使用分级超时，下载
正文发生瞬时超时时会安全重连一次，并明确提示具体超时阶段。

v0.3.8 修复 macOS 安装包中 QtWebEngine Helper 与 Resources 目录错误导致打开邮件
阅读器时直接退出的问题，并将实际初始化邮件阅读器加入 macOS 发布前检查。

v0.3.9 将账号、邮件、设置、密钥和日志改为保存在程序同级 MailDesk Data；更新包
固定保存在同盘 .maildesk-update，更新程序目录时不会碰用户数据。更新安装使用独立
线程，真实测试覆盖 onedir 替换、重启、健康回执和数据保留。IMAP、POP3、Graph
保存传输 ID 后只收新邮件，远程图片并发自动加载；macOS 包移除未使用 Qt Framework。

v0.4.0 将关闭窗口选择改为紧凑、自适应卡片，修复大字号下的裁切、过度放大和工具栏
文字发虚。工作台图表改为轻量原生绘制，并从双平台包中移除 QtCharts、未使用的
HTTP/2/异步后端和可选压缩解码器；HTML 邮件、图片、代理和加密功能保持不变。

发现新版时，应用会弹出提示并在顶部显示“更新”按钮。下载不会阻塞正常操作，
客户端会先用内置 Ed25519 公钥验证官方签名清单，再核对版本、安装模式、文件名、
体积和 SHA-256。只有明确确认后才会复核本地逐文件摘要并启动外部更新助手，不再
依赖第二次 GitHub 网络请求。助手完成相邻路径预复制、完整性复核和原子切换，并等待新版启动健康
回执；启动失败会恢复备份并重新打开旧版。也可以跳过当前提示版本。

更新仅从项目官方 GitHub Release 的 HTTPS 地址下载，暂存于软件同级：
.maildesk-update

在线升级需要能够访问 GitHub，且当前 Windows 用户对软件所在目录具有写入权限。
源码开发模式不会自动覆盖源码目录。Ed25519 是 MailDesk 应用级发布签名，不等同于
Windows Authenticode 证书，因此 SmartScreen 仍可能显示“未知发布者”。

安全校验
--------
下载后可在 PowerShell 中校验：

Get-FileHash .\MailDesk-v0.4.0-windows-x64-onefile.zip -Algorithm SHA256
Get-FileHash .\MailDesk-v0.4.0-windows-x64-onedir.zip -Algorithm SHA256

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
