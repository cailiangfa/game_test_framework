# 游戏商城全链路自动化测试框架

基于 pytest + Playwright + Pydantic 的游戏商城系统质量保障框架，覆盖 API、UI、并发竞态测试。

## 技术架构

![架构图](docs/arch.png)

## 技术栈

| 层级 | 技术 |
|------|------|
| UI 自动化 | Playwright + Page Object |
| API 测试 | pytest + requests + Pydantic |
| 并发/竞态 | threading + 数据库事务断言 |
| 数据管理 | Faker + 数据工厂 + 事务回滚 |
| 报告 | Allure + Playwright Trace |
| CI/CD | GitHub Actions |

## 目录结构

```text
game_test_framework/
├── backend/          # 被测服务（Flask）
├── tests/
│   ├── api/          # 接口测试
│   ├── ui/           # UI 自动化
│   ├── concurrency/  # 并发竞态测试
│   ├── fixtures/     # pytest fixtures
│   └── utils/        # 测试工具
├── pages/            # Page Object 层
├── docs/             # 架构图、文档
└── ci/               # GitHub Actions 配置

## 在线报告
[查看最新 Allure 报告](https://cailiangfa.github.io/game_test_framework/)