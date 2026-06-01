
# 游戏商城自动化测试框架

[![CI](https://github.com/cailiangfa/game_test_framework/actions/workflows/ci.yml/badge.svg)](https://github.com/cailiangfa/game_test_framework/actions)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![Allure Report](https://img.shields.io/badge/report-Allure-brightgreen)](https://github.com/cailiangfa/game_test_framework/actions)

> 基于"游戏核心交易链路（登录→购买→出售→金币/背包校验）"搭建的自动化测试框架。  
> `backend/` 为自研 Mock 服务，框架与后端实现解耦，可替换为真实服务地址直接接入。

---

## 为什么做这个项目？

在游戏测试工作中，交易链路是最容易出现**数据事故**的地方：

- 购买/出售时金币计算错误，导致玩家资产异常；
- 并发购买/出售时出现超卖、超扣、重复支付等竞态问题；
- 接口返回成功，但数据库状态不一致（"接口说成功，钱没扣"）；
- UI 操作走完，后台数据没对上，线上才爆出来。

这个项目就是为了**系统化解决这些问题**：

1. 接口返回 + 数据库状态双重断言，确保"成功就是真成功"；
2. 并发竞态测试，模拟多玩家同时交易，验证原子性和隔离性；
3. 用 Pydantic 做 Schema 校验，接口字段变更能第一时间被发现；
4. UI 端到端 + API 接口 + 并发场景三层覆盖，从不同维度保障交易质量。

---

## 核心特性

| 特性 | 实现方式 | 解决的问题 |
|------|---------|-----------|
| **契约测试** | Pydantic Schema 校验 | 防止"接口 200 但字段缺失"导致的测试假通过 |
| **三层 API 封装** | `buy` / `buy_raw` / `buy_validated` | 一套代码覆盖常规流程、参数校验、严格契约三种场景 |
| **数据一致性断言** | 接口返回值 + 数据库直查双重校验 | 防止接口"撒谎"，确保金币/背包/订单状态真实落库 |
| **并发竞态测试** | threading + 独立用户隔离 | 验证超卖、超扣、重复支付等游戏核心风险 |
| **测试隔离** | Function 级数据库重置 + 工厂模式 | 用例之间零耦合，可任意顺序执行 |
| **工程化** | GitHub Actions + Allure + Codecov | 每次 push 自动运行测试并生成报告与覆盖率 |

---

## 项目结构

```text
game_test_framework/
├── .github/workflows/ci.yml      # CI/CD 流水线 (GitHub Actions)
├── backend/                       # 被测后端服务 (Flask + SQLite)
│   ├── app.py                     # 主应用入口
│   └── requirements.txt
├── tests/
│   ├── api/                       # API 接口测试
│   │   ├── shop_api.py            # API Client 封装 (Pydantic + Allure)
│   │   ├── test_shop.py           # 购买/出售主流程
│   │   ├── test_shop_errors.py    # 异常场景
│   │   ├── test_buy_ddt.py        # 数据驱动测试
│   │   ├── test_overflow.py       # 溢出/边界测试
│   │   └── test_mock.py           # Mock 测试
│   ├── ui/                        # UI 自动化 (Playwright)
│   │   └── test_ui.py
│   ├── pages/                     # Page Object 层
│   │   └── shop_page.py
│   ├── concurrency/               # 并发/竞态测试
│   │   └── test_concurrency.py
│   ├── performance/               # 性能压测 (Locust)
│   │   └── locustfile.py
│   ├── utils/                     # 测试工具库
│   │   ├── factories.py           # 数据工厂 (Faker)
│   │   ├── assertions.py          # 公共断言
│   │   └── data_loader.py
│   ├── schemas/                   # 数据契约 (Pydantic)
│   │   └── shop.py
│   ├── data/                      # 测试数据
│   │   └── buy_data.json
│   └── conftest.py                # Pytest 全局配置 / Fixture
├── pytest.ini                     # Pytest 配置
├── requirements.txt               # 项目依赖 (严格锁版本)
└── README.md
```

---

## 快速开始

### 环境要求

- Python 3.12+
- pip

### 安装

```bash
# 克隆项目
git clone https://github.com/cailiangfa/game_test_framework.git
cd game_test_framework

# 创建虚拟环境
python -m venv venv

# 激活环境 (macOS/Linux)
source venv/bin/activate
# 或 (Windows)
# venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器 (仅 UI 测试需要)
playwright install chromium
```

### 运行测试

```bash
# 运行全部测试
pytest

# 仅运行 API 测试
pytest tests/api -v

# 仅运行 UI 测试
pytest tests/ui -v

# 仅运行并发测试
pytest tests/concurrency -v

# 生成 Allure 报告
pytest --alluredir=./allure-results
allure serve allure-results
```

### 运行性能测试 (Locust)

```bash
# 启动后端服务 (终端 A)
python backend/app.py

# 启动 Locust (终端 B)
locust -f tests/performance/locustfile.py --host=http://127.0.0.1:5000
# 访问 http://localhost:8089 配置并发参数
```

---

## 测试报告

本项目集成 **Allure Report**，提供以下可视化能力：

- **测试用例分层**: Feature / Story / Severity 标记
- **失败追踪**: UI 测试失败自动截图 + Playwright Trace 录制
- **请求日志**: API 请求/响应自动附加到报告中
- **CI Artifact**: 每次运行生成独立报告包，保留 7 天

**本地查看报告:**
```bash
allure serve allure-results
```

---

## 设计决策 (面试 FAQ)

**Q: 为什么用 SQLite 而不是 Docker 起 MySQL?**

> 求职项目的第一原则是"clone 即跑"。SQLite 零配置，降低运行门槛，同时通过 `db_check` fixture 实现数据库直查断言，测试能力不打折。后续如需切换为 MySQL，只需修改 `config.py` 和 `init_db()`，对测试用例基本透明。

**Q: 为什么 API Client 里同时存在 `buy` / `buy_raw` / `buy_validated`?**

> 分层设计：
> - `buy_raw` 绕过 Pydantic，专门测后端参数校验；
> - `buy` 走常规流程，带 Schema 校验，用于主流程和回归；
> - `buy_validated` 在 200 响应时严格校验契约，一旦字段不符合规范立即让测试失败。
>
> 一套代码覆盖多种测试需求，避免重复封装。

**Q: 为什么数据工厂直接操作数据库，而不是调接口?**

> 测试前置条件应该尽可能稳定。
>
> `give_item_to_player` 直接 INSERT 比"先登录再购买"快一个数量级，且不受被测接口 bug 牵连，符合"测试隔离"原则。真实业务中，如果接口不稳定，前置条件会跟着一起抖动，测试就不稳了。

**Q: 并发测试怎么保证数据不冲突?**

> 使用 `create_player` 工厂为每个并发线程创建独立用户，配合 SQLite WAL 模式，实现线程级数据隔离。
>
> 未来如果切换为 MySQL，只需修改隔离级别配置，测试用例无需改动。

**Q: 为什么 README 里的 Allure 在线报告链接指向 Actions 而不是 GitHub Pages？**

> 当前项目优先保证"clone 下来就能跑"，GitHub Pages 自动化部署会增加复杂度和仓库体积。
>
> 先用 Actions Artifact 证明"CI 有报告"，等后续需要展示时再升级为 GitHub Pages。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| UI 自动化 | Playwright + Page Object |
| API 测试 | pytest + FlaskClient + Pydantic |
| 并发/竞态 | threading + 数据库事务断言 |
| 数据管理 | JSON DDT + 数据工厂 (Faker) |
| Schema 校验 | Pydantic v2 |
| 报告 | Allure + Playwright Trace |
| CI/CD | GitHub Actions |

---

## License

MIT License

> 本项目为个人学习作品，欢迎交流。如有问题请提 Issue。