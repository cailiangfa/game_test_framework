
# Game Shop Test Framework

> 面向 Flask 游戏商城的全栈自动化测试项目，覆盖 API、UI、性能、Mock 与 CI/CD。

## 技术栈

| 层级 | 工具 | 用途 |
|------|------|------|
| **后端** | Flask 3.1.3 + SQLite | 被测系统 |
| **API 测试** | Pytest + Requests | 正向/异常/数据驱动/Mock |
| **UI 测试** | Playwright | 端到端页面流程 |
| **性能测试** | Locust | 阶梯式加压 |
| **报告** | Allure + Coverage | 可视化报告 + 覆盖率门禁 |
| **CI/CD** | GitHub Actions | 多 Python 版本矩阵 |
| **容器化** | Docker 多阶段构建 | 最小化镜像 |

## 快速开始

```bash
# 克隆项目
git clone https://github.com/你的用户名/game_test_framework.git
cd game_test_framework

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 运行全部测试
pytest tests/ -v --alluredir=allure-results --cov=backend --cov-report=term
```

## 测试策略

```
┌─────────────────────────────────────────┐
│           测试金字塔                     │
├─────────────────────────────────────────┤
│  🟢 单元测试（Service 层）              │
├─────────────────────────────────────────┤
│  🟡 接口测试（API 层）                  │
│     test_shop.py       → 正向流程       │
│     test_shop_errors.py → 异常场景      │
│     test_buy_ddt.py    → 数据驱动       │
│     test_mock.py       → Mock 支付      │
├─────────────────────────────────────────┤
│  🔴 E2E 测试（UI 层）                   │
│     test_ui.py         → Playwright     │
├─────────────────────────────────────────┤
│  ⚫ 性能测试                            │
│     locustfile.py      → 阶梯加压       │
└─────────────────────────────────────────┘
```

## 核心设计亮点

### 1. 数据隔离：务实重置方案

> 每个测试用例前重置数据库到种子状态。尝试过事务回滚，但 Flask 每个请求上下文创建独立 SQLite 连接，需 mock `get_db()` 才能生效。项目中选择重置方案保证稳定性，同时了解回滚原理。

### 2. API 封装层

```python
# 以前
resp = client.post('/api/buy', json={'item_id': 1}, headers=headers)

# 现在
shop_api.buy(item_id=1, quantity=3)
```

### 3. Page Object 模式

```python
# 以前（定位歧义）
page.click("button:has-text('购买')")

# 现在（精确匹配）
ShopPage._buy_button(item_id=1)  # div:has(#quantity-1) button
```

## 性能测试

```bash
locust -f tests/performance/locustfile.py --host=http://127.0.0.1:5000 --headless -u 100 -r 10 --run-time 4m
```

| 指标 | 目标 |
|------|------|
| P95 响应 | ≤ 200ms |
| 错误率 | ≤ 1% |
| RPS | ≥ 50 |

## 许可证

MIT
