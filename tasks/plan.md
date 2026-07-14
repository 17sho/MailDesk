# Implementation Plan: MailDesk v0.1

## Overview

按 `SPEC.md` 构建 Windows 本地多邮箱管理工具。依赖顺序为：领域契约 → 安全存储/导入 → 协议与邮件解析 → 服务编排 → PySide6 GUI → 打包与文档。采用小型垂直切片，每个切片先写失败测试，再实现并运行对应验证。

## Architecture Decisions

- 使用 `src` 布局，领域模型与 Qt 解耦，核心逻辑可在无 GUI 环境测试。
- 使用同步 `imaplib`/`httpx` 客户端配合 `QThreadPool`；每个 worker 独立客户端，避免跨线程 socket 状态。
- 数据库通过 repository 暴露领域对象；秘密字段由 `CredentialCipher` 在存储边界加密。
- 随机 Fernet 主密钥由 Windows DPAPI 保护；非 Windows 仅允许显式测试后端，不提供不安全的生产回退。
- UI 使用 `QAbstractTableModel`，避免 `QTableWidget` 在大批量数据下的性能和状态同步问题。
- 外部 HTTP/IMAP 在测试中使用 fake transport/fake connection，不访问真实服务。

## Dependency Graph

```text
领域模型/错误/状态
├─ 安全存储 ── 账号仓储 ── 账号服务 ── GUI 表模型
├─ 智能导入 ──────────────┘
├─ 邮件解析 ── IMAP/Graph 客户端 ── FetchService ── GUI workers
└─ 导出/日志 ────────────────────────────────┘

GUI + 入口 + 资源 → PyInstaller spec/build.py → 构建验证
```

## Task List

### Phase 1: Foundation

- [x] Task 1: 工程骨架与领域契约
- [x] Task 2: DPAPI/Fernet 加密存储与 SQLite 仓储
- [x] Task 3: 智能导入、provider 自动配置和安全导出

### Checkpoint: Foundation

- [x] 核心单元/集成测试通过
- [x] 测试数据库中不存在明文秘密
- [x] ruff 静态检查通过

### Phase 2: Core Mail Flow

- [x] Task 4: MIME/验证码/Catch-All 邮件解析
- [x] Task 5: EmailClientBase、IMAP 与 Graph 客户端
- [x] Task 6: FetchService 编排、错误分类和审计日志

### Checkpoint: Core Flow

- [x] fake IMAP/HTTP 下端到端收件流程通过
- [x] 取消、超时、鉴权失败和分页上限有测试

### Phase 3: Desktop UI

- [x] Task 7: 账号表模型、导入预览与主窗口布局
- [x] Task 8: QThreadPool 并发 worker、开始/停止与实时状态
- [x] Task 9: 主题、托盘基础、TOTP/分组标签的安全扩展入口

### Checkpoint: Desktop

- [x] Qt offscreen 窗口启动测试通过
- [x] GUI 事件循环不被网络任务阻塞

### Phase 4: Ship

- [x] Task 10: build.py、PyInstaller spec、图标与依赖清单
- [x] Task 11: README、示例文件、完整测试/lint/构建验证

### Checkpoint: Complete

- [x] `SPEC.md` Definition of Done 逐项核对
- [x] onedir 构建成功，onefile 配置可用
- [x] 无真实秘密、无明文凭据、无危险默认行为

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Outlook 租户/Scope 差异 | 高 | tenant、scope 可配置；错误结构统一；测试 token 与 Graph 两阶段 |
| 邮件 MIME/编码复杂 | 高 | 标准库解析、大小上限、multipart 与 charset 单测 |
| DPAPI 导致跨设备不可迁移 | 中 | 文档说明；只导出非秘密元数据；未来提供用户口令保护的显式迁移包 |
| 批量网络阻塞 GUI | 高 | QThreadPool、每任务超时、协作取消、并发上限 |
| PyInstaller Qt 插件缺失 | 中 | collect_submodules/collect_data_files；onedir 作为发布前验证基线 |
| 导入启发式误判 | 中 | 预览确认、置信度/逐行错误、不静默持久化歧义行 |

## Verification Commands

```powershell
py -3.12 -m pytest -q
py -3.12 -m ruff check src tests build.py release.py
$env:QT_QPA_PLATFORM='offscreen'; py -3.12 -m pytest -q tests/gui
py -3.12 build.py --mode onedir --clean
```
