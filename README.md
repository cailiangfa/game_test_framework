
# 游戏商城自动化测试框架

![CI](https://github.com/cailiangfa/game_test_framework/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> 从零搭建的 Flask 游戏商城后端及配套全栈自动化测试体系，覆盖接口测试、UI 测试、性能测试，集成 Mock、数据驱动、数据库隔离、CI/CD 等工程化能力。

**核心特点**：不是"写脚本"，而是设计了一套可维护的测试工程体系——包括数据隔离策略、Mock 架构、Allure 报告结构、CI/CD 流水线。

---

## 技术栈
| 层级 | 技术 |
|:---|:---|
| 被测系统 | Flask + SQLite |
| 测试框架 | Pytest + Allure |
| 接口测试 | Flask test_client + 数据库双重校验 |
| UI 测试 | Playwright（网络拦截 + 自动登录） |
| 性能测试 | Locust |
| Mock | pytest-mock（模块级实例替换） |
| 数据驱动 | JSON + `@pytest.mark.parametrize` |
| CI/CD | GitHub Actions |
| 容器化 | Docker |

---

## 项目结构
```text
game_test_framework/
├── backend/
│   └── app.py              # 被测系统（购买/出售/支付验证）
├── tests/
│   ├── conftest.py         # 全局 Fixture（数据库/登录/浏览器）
│   ├── test_shop.py        # 正向流程（购买/出售）
│   ├── test_shop_errors.py # 异常场景（14 个用例）
│   ├── test_buy_ddt.py     # 数据驱动购买
│   ├── test_mock.py        # Mock 支付验证
│   ├── test_ui.py          # Playwright UI 测试
│   ├── locustfile.py       # 性能压测
│   └── data/
│       └── buy_data.json   # DDT 数据源
├── .github/workflows/
│   └── ci.yml              # CI/CD 流水线
├── Dockerfile
└── requirements.txt


```

---

## 测试覆盖

| 类型 | 用例数 | 核心验证点 |
|:---|:---|:---|
| 正向流程 | 2 | 购买扣金币、出售加金币、数据库一致性 |
| 异常场景 | 14 | 鉴权/参数校验/余额不足/道具不存在 |
| 数据驱动 | 4 | JSON 加载多组 `(item_id, quantity)` |
| Mock 测试 | 3 | 支付成功/失败/超时，验证业务兜底 |
| UI 测试 | 3 | 页面渲染、购买交互、接口拦截模拟 |
| **合计** | **26** | **全部通过** |

---

## 设计亮点

### 1. 数据库隔离策略
- **Session 级**：`init_db()` 建表 + 种子数据，只执行一次
- **Function 级**：`_reset_data` 清空业务数据 + 重置金币，不走 DROP（快）
- **Playwright 级**：独立 `page` Fixture，每个 UI 用例新浏览器上下文

### 2. Mock 架构设计
被测系统的 `ExternalPayment` 是**模块级实例**：
```python
external_payment = ExternalPayment()  # 可被 pytest-mock 替换
```

测试端直接 patch `backend.app.external_payment.verify`，无需改业务代码。

3. UI 拦截测试
用 Playwright `page.route` 拦截 `/api/buy`，强制返回 400，验证前端错误提示渲染——不依赖真实后端状态。

4. Allure 报告踩坑记录

> 使用 `allure generate + open` 会导致 Behaviors 页面 404，原因是静态生成不支持前端路由。

解决方案：使用 `allure serve` 或 PyCharm Allure 插件的 Serve 功能。

---

快速开始

环境准备

```bash
# 1. 克隆项目
git clone https://github.com/cailiangfa/game_test_framework.git
cd game_test_framework

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. 安装依赖
pip install -r requirements.txt
playwright install chromium
```

运行测试

```bash
# 全部测试
pytest tests/ -v

# 只看接口
pytest tests/test_shop.py tests/test_shop_errors.py -v

# 只看 UI（有头模式调试用）
pytest tests/test_ui.py -v --headed
```

生成 Allure 报告

```bash
pytest tests/ -v --alluredir=allure-results

# ✅ 推荐方式 A：命令行 serve（allure-commandline >= 2.29）
allure serve allure-results

# ✅ 推荐方式 B：PyCharm Allure 插件
# 右键 allure-results 文件夹 → Allure → Serve
```

> ❌ 不推荐：`allure generate + open`（Behaviors 页面 404）

性能测试

```bash
# 终端 1：启动 Flask 服务
python -c "import backend.app as b; b.init_db(); b.app.run(port=5000)"

# 终端 2：启动 Locust
locust -f tests/locustfile.py --host=http://127.0.0.1:5000
# 浏览器访问 http://localhost:8089，设置并发用户数和压测时长
```

---

CI/CD 集成

GitHub Actions 流水线（`.github/workflows/ci.yml`）：
1. 每次 push 自动安装依赖
2. 运行全部 26 个用例
3. 生成 Allure 报告并上传为 Artifact
4. 性能测试（可选，nightly 触发）

```yaml
# 关键步骤示意
- name: Run tests
  run: pytest tests/ -v --alluredir=allure-results

- name: Upload Allure results
  uses: actions/upload-artifact@v4
  with:
    name: allure-results
    path: allure-results
```

---

关键依赖版本

```
pytest==8.2.0
allure-pytest==2.16.0
playwright==1.44.0
pytest-mock==3.14.0
locust==2.28.0
Flask==3.0.3
Werkzeug==3.0.3
```

> 版本锁定原因：allure-pytest 2.16 + allure-commandline 2.29+ 才能稳定支持 Behaviors 页面。

---

面试 FAQ（建议背诵）

Q：数据库怎么保证测试隔离？

A：Session 级建表，Function 级重置数据。用 `DELETE + UPDATE` 代替 `DROP TABLE`，速度提升 10 倍+。

Q：Mock 怎么设计的？

A：业务代码里 `external_payment` 是模块级实例，测试用 `mocker.patch` 替换方法，验证三种场景：成功、失败、超时。

Q：Allure 报告遇到过什么问题？

A：`generate + open` 导致 Behaviors 404，原因是静态生成不支持前端路由。改用 `serve` 或 PyCharm 插件解决。

Q：性能测试怎么做的？

A：Locust 模拟真实用户行为，权重设计：查金币(3) > 购买(2) > 出售(1)。注意 400 业务拒绝不算服务器错误，但报告里会单独标记。

---

后续优化方向

- [ ] 接入 `pytest-xdist` 并行执行（需解决数据库并发写入）
- [ ] 补充契约测试（Pact 验证前后端接口契约）
- [ ] Allure TestOps 云端版（用例管理 + 需求追溯）
- [ ] 混沌工程（随机 kill 支付服务，验证熔断降级）

---

License
MIT

