# MailDesk v0.2.0 第三方组件声明

MailDesk 自有代码使用 MIT License。Windows 可执行程序由 PyInstaller 构建，并会随包携带 Python 运行时、Qt/PySide6 组件以及下列 Python 依赖。第三方组件仍分别适用其原始许可证，本项目的 MIT License 不会取代这些条款。

## 主要运行时组件

| 组件 | 构建版本 | 许可证 |
|---|---:|---|
| Python | 3.12.5 | Python Software Foundation License |
| PySide6 / PySide6 Essentials / PySide6 Addons | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only / 商业许可 |
| Shiboken6 | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only / 商业许可 |
| Qt 6 / Qt WebEngine | 6.11.1 | 模块对应的 LGPL/GPL/商业许可；Qt WebEngine 还包含 Chromium 第三方组件 |
| cryptography | 43.0.1 | Apache-2.0 OR BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| httpcore | 1.0.9 | BSD-3-Clause |
| certifi | 2026.1.4 | MPL-2.0（Mozilla CA 证书包） |
| PyOTP | 2.10.0 | MIT |
| PySocks | 1.7.1 | BSD |
| socksio | 1.0.0 | MIT |
| pywin32 | 312 | PSF 及所含组件各自许可证 |
| anyio | 4.12.1 | MIT |
| sniffio | 1.3.1 | MIT OR Apache-2.0 |
| h11 | 0.16.0 | MIT |
| idna | 3.11 | BSD-3-Clause |
| cffi | 1.17.1 | MIT |
| pycparser | 2.22 | BSD-3-Clause |
| typing_extensions | 4.15.0 | PSF-2.0 |
| Brotli | 1.1.0 | MIT |
| zstandard | 0.23.0 | BSD |

发布脚本会从实际构建环境的 `*.dist-info` 元数据中收集可用的 LICENSE、COPYING 和 NOTICE 文件，并放入压缩包的 `licenses/python-packages/` 目录。GNU GPLv3、LGPLv3 与 Python 许可证全文也会随包提供。

## Qt / PySide6 特别说明

- MailDesk 不修改 Qt 或 PySide6 源码，并通过动态库使用 Qt。
- `onedir` 包中的 Qt DLL 保持为独立文件；`onefile` 会在启动时将相同动态库释放到临时目录。
- 用户可以出于调试、替换动态库或验证许可证合规性的目的检查和解包 PyInstaller 产物；本项目不会限制适用开源许可证允许的逆向工程。
- 对应源码与完整条款可从以下上游获取：
  - <https://code.qt.io/cgit/pyside/pyside-setup.git/?h=6.11.1>
  - <https://code.qt.io/cgit/qt/>
  - <https://www.qt.io/licensing/open-source-lgpl-obligations>
- Qt WebEngine 基于 Chromium。其第三方声明可在 Qt WebEngine 的 `chrome://credits` 页面及 Qt 源码的 Chromium 许可材料中查看。

## 许可证全文

- GNU GPL v3：`licenses/GPL-3.0.txt`
- GNU LGPL v3：`licenses/LGPL-3.0.txt`
- Python 3.12：`licenses/PYTHON-3.12.txt`
- MailDesk MIT：`LICENSE`

本文件用于提供发行包中的第三方归属信息，不构成法律意见。如发现遗漏，请通过仓库 Issue 或安全报告渠道反馈。
