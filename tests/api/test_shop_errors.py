"""
tests/api/test_shop_errors.py
异常场景测试：鉴权失败、业务异常、参数校验
所有故意传错误参数的调用都用 buy_raw / sell_raw（绕过 Pydantic 前端校验）
"""
from __future__ import annotations

import allure
import pytest


class TestAuthErrors:
    """鉴权异常"""

    @allure.feature("异常场景")
    @allure.story("鉴权失败")
    def test_buy_without_token(self, client):
        resp = client.post("/api/buy", json={"item_id": 1, "quantity": 1})
        assert resp.status_code == 401
        assert "未登录" in resp.get_json()["error"]

    @allure.feature("异常场景")
    @allure.story("鉴权失败")
    def test_buy_invalid_token_format(self, client):
        resp = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 1},
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert resp.status_code == 401
        # 后端 require_auth 对格式不对的 token 统一返回"未登录"
        assert "未登录" in resp.get_json()["error"]

    @allure.feature("异常场景")
    @allure.story("鉴权失败")
    def test_buy_player_not_exist(self, client):
        resp = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 1},
            headers={"Authorization": "Bearer token_99999"},
        )
        assert resp.status_code == 404
        assert "玩家不存在" in resp.get_json()["error"]


class TestBusinessErrors:
    """业务异常"""

    @allure.feature("异常场景")
    @allure.story("业务异常")
    def test_buy_insufficient_gold(self, shop_api):
        # 买 999 瓶生命药水（100*999=99900），金币不够
        result = shop_api.buy_raw(item_id=1, quantity=999)
        assert result["status_code"] == 400
        assert "余额不足" in result["data"]["error"]

    @allure.feature("异常场景")
    @allure.story("业务异常")
    def test_buy_item_not_exist(self, shop_api):
        # item_id=999 不存在
        result = shop_api.buy_raw(item_id=999, quantity=1)
        assert result["status_code"] in [400, 404]
        error_msg = result["data"].get("error", "")
        assert any(
            keyword in error_msg
            for keyword in ["不存在", "道具", "item"]
        ), f"unexpected error: {error_msg}"

    @allure.feature("异常场景")
    @allure.story("业务异常")
    def test_sell_insufficient_items(self, client, logged_headers):
        # 背包里没有 999 瓶
        resp = client.post(
            "/api/sell",
            json={"item_id": 1, "quantity": 999},
            headers=logged_headers,
        )
        assert resp.status_code == 400
        assert "道具数量不足" in resp.get_json()["error"]

    @allure.feature("异常场景")
    @allure.story("业务异常")
    def test_sell_item_not_in_backpack(self, client, logged_headers):
        # 卖一个不存在的道具（item_id=999）
        resp = client.post(
            "/api/sell",
            json={"item_id": 999, "quantity": 1},
            headers=logged_headers,
        )
        assert resp.status_code == 400
        # 后端 GameService.get_item_price 先查 items 表，发现 item_id=999 不存在
        # 所以返回"道具不存在"而不是"道具数量不足"
        assert "道具不存在" in resp.get_json()["error"]


class TestValidationErrors:
    """参数校验异常（绕过 Pydantic，直接测后端校验）"""

    @allure.feature("异常场景")
    @allure.story("参数校验")
    def test_buy_zero_quantity(self, shop_api):
        result = shop_api.buy_raw(item_id=1, quantity=0)
        assert result["status_code"] == 400
        assert "正整数" in result["data"]["error"]

    @allure.feature("异常场景")
    @allure.story("参数校验")
    def test_buy_negative_quantity(self, shop_api):
        result = shop_api.buy_raw(item_id=1, quantity=-5)
        assert result["status_code"] == 400
        assert "正整数" in result["data"]["error"]

    @allure.feature("异常场景")
    @allure.story("参数校验")
    def test_buy_float_quantity(self, shop_api):
        result = shop_api.buy_raw(item_id=1, quantity=1.5)
        assert result["status_code"] == 400

    @allure.feature("异常场景")
    @allure.story("参数校验")
    def test_buy_missing_item_id(self, shop_api):
        result = shop_api.buy_raw(item_id=None, quantity=1)
        assert result["status_code"] == 400
        assert "item_id" in result["data"]["error"]

    @allure.feature("异常场景")
    @allure.story("参数校验")
    def test_buy_empty_body(self, client, logged_headers):
        resp = client.post("/api/buy", json={}, headers=logged_headers)
        assert resp.status_code == 400
        assert "item_id" in resp.get_json()["error"]

    @allure.feature("异常场景")
    @allure.story("参数校验")
    def test_sell_negative_quantity(self, shop_api):
        result = shop_api.sell_raw(item_id=1, quantity=-1)
        assert result["status_code"] == 400
        assert "正整数" in result["data"]["error"]

    @allure.feature("异常场景")
    @allure.story("参数校验")
    def test_sell_without_token(self, client):
        resp = client.post("/api/sell", json={"item_id": 1, "quantity": 1})
        assert resp.status_code == 401
        assert "未登录" in resp.get_json()["error"]