# 参与贡献

感谢你愿意改进 MailDesk。项目欢迎缺陷修复、可访问性改进、邮件兼容性增强、测试、文档和本地化贡献。

## 开始之前

- 仅使用你拥有或明确获授权管理的测试邮箱。
- 不要在 Issue、日志、截图、测试数据或提交中包含真实密码、授权码、Refresh Token、TOTP 密钥、Cookie 或邮件正文。
- 不接受绕过验证码、封禁、Rate Limit、服务商风控，或批量接管/修改账号安全设置的实现。
- 涉及删除、移动、发件、转发或 Webhook 的改动必须保持默认安全、用户显式确认和可审计。

## 本地开发

项目面向 Windows 10/11，使用 Python 3.12：

```powershell
git clone https://github.com/17sho/MailDesk.git
cd MailDesk
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m mailbox_manager
```

提交前运行：

```powershell
py -3.12 -m ruff check src tests build.py release.py
py -3.12 -m pytest -q
```

测试必须使用临时数据库和 fake/mock 网络客户端，不应连接真实邮箱或外部 Webhook。

## 提交 Issue

请先搜索现有 Issue。缺陷报告应包含：

- Windows、Python 与 MailDesk 版本；
- 可复现的最小步骤；
- 预期行为与实际行为；
- 已脱敏的日志或截图；
- 是否可以稳定复现。

安全漏洞请按 [SECURITY.md](SECURITY.md) 私下报告，不要创建公开 Issue。

## Pull Request

1. 从 `main` 创建聚焦单一问题的分支。
2. 为行为变更补充或更新测试。
3. 保持 UI 文案、错误分类和安全默认值一致。
4. 更新相关 README、规格或企业功能矩阵。
5. 确认 Ruff 和完整测试通过。

PR 描述应说明改动目的、主要实现、验证方式、UI 截图（如适用）以及潜在安全影响。
