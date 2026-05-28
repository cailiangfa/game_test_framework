"""
商城页面 Page Object
- 封装所有元素定位策略
- 封装页面业务操作（买/卖/查金币）
- 封装等待逻辑，测试脚本只调业务方法
"""

from __future__ import annotations

import json
from typing import Any, Callable

import allure
from playwright.sync_api import Page


class ShopPage:
    """游戏商城页面封装"""

    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

    # ---------- 元素定位器（集中管理，一处修改全局生效）----------
    _TITLE = "h1"
    _GOLD_AMOUNT = "#gold-amount"
    _ERROR_MESSAGE = "#message"

    @staticmethod
    def _quantity_input(item_id: int) -> str:
        return f"#quantity-{item_id}"

    @staticmethod
    def _buy_button(item_id: int) -> str:
        """
        定位策略：先找到包含对应 quantity input 的 div，再找里面的 button。
        避免两个"购买"按钮文字相同导致误点。
        """
        return f"div:has({ShopPage._quantity_input(item_id)}) button"

    # ---------- 页面导航 ----------
    @allure.step("打开商城页面")
    def open(self) -> "ShopPage":
        self.page.goto(f"{self.base_url}/shop")
        return self

    # ---------- 等待 ----------
    @allure.step("等待页面加载完成")
    def wait_for_load(self) -> "ShopPage":
        self.page.wait_for_selector(self._TITLE, state="visible")
        self._wait_gold_loaded()
        return self

    def _wait_gold_loaded(self) -> None:
        """等待金币从'加载中...'变为具体数值"""
        self.page.wait_for_function(
            "document.getElementById('gold-amount').textContent !== '加载中...'"
        )

    # ---------- 查询 ----------
    @allure.step("获取页面标题")
    def get_title(self) -> str:
        return self.page.inner_text(self._TITLE)

    @allure.step("获取当前金币数")
    def get_gold(self) -> int:
        self._wait_gold_loaded()
        text = self.page.inner_text(self._GOLD_AMOUNT)
        return int(text)

    @allure.step("获取错误提示文本")
    def get_error_message(self) -> str:
        self.page.wait_for_function(
            "document.getElementById('message').textContent !== ''"
        )
        return self.page.inner_text(self._ERROR_MESSAGE)

    # ---------- 操作 ----------
    @allure.step("设置 item_id={item_id} 的购买数量为 {quantity}")
    def set_quantity(self, item_id: int, quantity: int) -> "ShopPage":
        self.page.fill(self._quantity_input(item_id), str(quantity))
        return self

    @allure.step("点击 item_id={item_id} 的购买按钮")
    def click_buy(self, item_id: int) -> "ShopPage":
        self.page.click(self._buy_button(item_id))
        return self

    # ---------- 拦截 / Mock ----------
    @allure.step("拦截 /api/buy 请求")
    def intercept_buy(self, handler: Callable[..., Any]) -> "ShopPage":
        self.page.route("**/api/buy", handler)
        return self

    # ---------- 组合业务方法（测试脚本直接调这个）----------
    @allure.step("购买道具 item_id={item_id}, quantity={quantity}")
    def buy(self, item_id: int, quantity: int, expect_gold_change: bool = True) -> "ShopPage":
        """一站式购买：设置数量 -> 点击购买 -> 可选等待金币刷新"""
        if expect_gold_change:
            before = self.get_gold()

        self.set_quantity(item_id, quantity).click_buy(item_id)

        if expect_gold_change:
            # 购买成功场景：等金币变化
            self.page.wait_for_function(
                f"document.getElementById('gold-amount').textContent !== '{before}'",
                timeout=5000
            )

        return self

    # ---------- 截图（失败排查）----------
    @allure.step("截取当前页面")
    def screenshot(self, name: str = "screenshot") -> bytes:
        return self.page.screenshot(full_page=True)