import pytest
import json
import allure

class TestShopUI:
    """商城页面 UI 自动化测试"""

    @allure.feature("UI 测试")  # 功能模块：UI 测试
    @allure.story("商店页面")   # 故事线：商店页面
    @allure.severity(allure.severity_level.NORMAL)  # 严重程度：普通
    def test_shop_page_loads(self, page, base_url, _reset_data):
        """验证商城页面能正常打开，显示标题和金币"""
        page.goto(f"{base_url}/shop")

        # 等待标题出现
        page.wait_for_selector("h1", state="visible")
        assert page.inner_text("h1") == "游戏商城"

        # 等待金币加载完成（不再是"加载中..."）
        page.wait_for_function(
            "document.getElementById('gold-amount').textContent !== '加载中...'"
        )
        assert page.inner_text("#gold-amount") == "1000"

    @allure.feature("UI 测试")  # 功能模块：UI 测试
    @allure.story("商店页面")   # 故事线：商店页面
    @allure.severity(allure.severity_level.NORMAL)  # 严重程度：普通
    def test_buy_item_updates_gold(self, page, base_url, _reset_data):
        """购买一瓶生命药水，金币从1000变为900"""
        page.goto(f"{base_url}/shop")

        # 等待金币加载
        page.wait_for_function(
            "document.getElementById('gold-amount').textContent !== '加载中...'"
        )

        # 确认初始金币
        before = int(page.inner_text("#gold-amount"))
        assert before == 1000

        # 购买1瓶生命药水
        page.fill("#quantity-1", "1")
        page.click("button:has-text('购买')")

        # 等待金币变化
        page.wait_for_function(
            "document.getElementById('gold-amount').textContent !== '1000'"
        )
        after = int(page.inner_text("#gold-amount"))
        assert after == 900  # 1000 - 100

    @allure.feature("UI 测试")  # 功能模块：UI 测试
    @allure.story("商店页面")   # 故事线：商店页面
    @allure.severity(allure.severity_level.NORMAL)  # 严重程度：普通
    def test_insufficient_gold_ui(self, page, base_url, _reset_data):
        """拦截购买接口返回余额不足，验证页面错误提示"""
        # 定义拦截逻辑：必须返回 400，否则前端会走成功分支！
        def mock_insufficient(route):
            route.fulfill(
                status=400,
                content_type="application/json",
                body=json.dumps({"error": "余额不足"})
            )

        # 拦截购买请求
        page.route("**/api/buy", mock_insufficient)

        page.goto(f"{base_url}/shop")
        page.wait_for_function(
            "document.getElementById('gold-amount').textContent !== '加载中...'"
        )

        # 尝试购买
        page.fill("#quantity-1", "999")
        page.click("button:has-text('购买')")

        # 等待错误信息出现
        page.wait_for_function(
            "document.getElementById('message').textContent !== ''"
        )
        error_text = page.inner_text("#message")
        assert "余额不足" in error_text
