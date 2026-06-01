"""
tests/pages/shop_page.py
商城页面 Page Object
- 封装所有元素定位策略（Locator 模式）
- 封装页面业务操作（买/卖/查金币）
- 封装等待逻辑，测试脚本只调业务方法
★ 优化：base_url 由 Playwright context 管理，ShopPage 不再接收 base_url 参数
"""

from __future__ import annotations

from typing import Any, Callable

import allure
from playwright.sync_api import Locator, Page


class ShopPage:
    """游戏商城页面封装"""

    def __init__(self, page: Page) -> None:
        self.page = page

        # ---- Locator 集中管理（推荐写法，自带自动等待）----
        self.title: Locator = page.locator("h1")
        self.gold_amount: Locator = page.locator("#gold-amount")
        self.error_message: Locator = page.locator("#message")

    def _quantity_input(self, item_id: int) -> Locator:
        return self.page.locator(f"#quantity-{item_id}")

    def _buy_button(self, item_id: int) -> Locator:
        """
        定位策略：先找到包含对应 quantity input 的 div，再找里面的 button。
        避免两个"购买"按钮文字相同导致误点。
        """
        return self.page.locator(f"div:has(#quantity-{item_id}) button")

    # ---------- 页面导航 ----------
    @allure.step("打开商城页面")
    def open(self) -> "ShopPage":
        # ★ base_url 已在 Playwright context 里设置，只需传路径
        self.page.goto("/shop")
        return self

    # ---------- 等待 ----------
    @allure.step("等待页面加载完成")
    def wait_for_load(self) -> "ShopPage":
        self.title.wait_for(state="visible")
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
        return self.title.inner_text()

    @allure.step("获取当前金币数")
    def get_gold(self) -> int:
        self._wait_gold_loaded()
        text = self.gold_amount.inner_text()
        return int(text)

    @allure.step("获取错误提示文本")
    def get_error_message(self) -> str:
        self.page.wait_for_function(
            "document.getElementById('message').textContent !== ''"
        )
        return self.error_message.inner_text()

    # ---------- 操作 ----------
    @allure.step("设置 item_id={item_id} 的购买数量为 {quantity}")
    def set_quantity(self, item_id: int, quantity: int) -> "ShopPage":
        self._quantity_input(item_id).fill(str(quantity))
        return self

    @allure.step("点击 item_id={item_id} 的购买按钮")
    def click_buy(self, item_id: int) -> "ShopPage":
        self._buy_button(item_id).click()
        return self

    # ---------- 拦截 / Mock ----------
    @allure.step("拦截 API 请求: {pattern}")
    def intercept_api(self, pattern: str, handler: Callable[..., Any]) -> "ShopPage":
        """通用拦截方法，可拦截任意 API 路径"""
        self.page.route(pattern, handler)
        return self

    # ---------- 组合业务方法（测试脚本直接调这个）----------
    @allure.step("购买道具 item_id={item_id}, quantity={quantity}")
    def buy(
        self, item_id: int, quantity: int, expect_gold_change: bool = True
    ) -> "ShopPage":
        """一站式购买：设置数量 -> 点击购买 -> 可选等待金币刷新"""
        if expect_gold_change:
            before = self.get_gold()

        self.set_quantity(item_id, quantity).click_buy(item_id)

        if expect_gold_change:
            self.page.wait_for_function(
                f"document.getElementById('gold-amount').textContent !== '{before}'",
                timeout=5000,
            )

        return self

    # ---------- 截图（失败排查）----------
    @allure.step("截取当前页面")
    def screenshot(self, name: str = "screenshot") -> bytes:
        return self.page.screenshot(full_page=True)
