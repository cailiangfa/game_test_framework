"""
UI 自动化测试：Page Object 模式
适配修复后的 conftest.py（autouse 数据重置 + page fixture 自动截图）
"""

from __future__ import annotations

import json

import allure
import pytest

from tests.pages.shop_page import ShopPage


@allure.feature("UI 测试")
@allure.story("商城页面")
class TestShopPageLoad:
    """页面加载"""

    @allure.title("商城页面正常打开，显示标题和金币")
    @allure.severity(allure.severity_level.NORMAL)
    def test_shop_page_loads(self, shop_page: ShopPage):
        with allure.step("Step 1: 打开商城页面"):
            shop_page.open().wait_for_load()

        with allure.step("Step 2: 断言标题"):
            assert shop_page.get_title() == "游戏商城"

        with allure.step("Step 3: 断言初始金币"):
            gold = shop_page.get_gold()
            assert gold == 1000, f"初始金币应为 1000，实际: {gold}"


@allure.feature("UI 测试")
@allure.story("商城页面")
class TestShopBuyFlow:
    """购买流程"""

    @allure.title("购买 1 瓶生命药水，金币从 1000 变为 900")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_item_updates_gold(self, shop_page: ShopPage):
        with allure.step("Step 1: 打开页面并等待加载"):
            shop_page.open().wait_for_load()

        with allure.step("Step 2: 记录购买前金币"):
            before = shop_page.get_gold()
            assert before == 1000, f"初始金币异常: {before}"

        with allure.step("Step 3: 购买 1 瓶生命药水"):
            shop_page.buy(item_id=1, quantity=1)

        with allure.step("Step 4: 断言金币扣减"):
            after = shop_page.get_gold()
            assert after == 900, f"购买后金币应为 900，实际: {after}"


@allure.feature("UI 测试")
@allure.story("商城页面")
class TestShopErrorHandling:
    """错误处理"""

    @allure.title("拦截购买接口返回余额不足，页面正确显示错误提示")
    @allure.severity(allure.severity_level.NORMAL)
    def test_insufficient_gold_ui(self, shop_page: ShopPage):
        def mock_insufficient(route):
            route.fulfill(
                status=400,
                content_type="application/json",
                body=json.dumps({"error": "余额不足"}),
            )

        with allure.step("Step 1: 拦截 /api/buy 并打开页面"):
            shop_page.intercept_buy(mock_insufficient).open().wait_for_load()

        with allure.step("Step 2: 尝试购买 999 瓶"):
            shop_page.buy(item_id=1, quantity=999, expect_gold_change=False)

        with allure.step("Step 3: 断言错误提示"):
            error_text = shop_page.get_error_message()
            assert "余额不足" in error_text, f"错误提示异常: {error_text}"