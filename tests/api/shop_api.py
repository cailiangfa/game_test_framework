"""
API 业务封装层：把 HTTP 调用封装成业务方法。
测试脚本只调 api.buy()，不直接写 client.post('/api/buy', ...)
"""

from __future__ import annotations

from typing import Any

import allure
from flask.testing import FlaskClient


class ShopAPI:
    """游戏商城 API 封装：所有 HTTP 调用集中在这里"""

    def __init__(self, client: FlaskClient, headers: dict[str, str] | None = None) -> None:
        self.client = client
        self.headers = headers or {}

    # ---------- 认证 ----------
    @allure.step("登录: username={username}")
    def login(self, username: str, password: str) -> dict[str, Any]:
        resp = self.client.post(
            "/api/login",
            json={"username": username, "password": password},
        )
        return {
            "status_code": resp.status_code,
            "data": resp.get_json(),
        }

    # ---------- 查询 ----------
    @allure.step("查询金币")
    def get_gold(self) -> int:
        resp = self.client.get("/api/gold", headers=self.headers)
        return resp.get_json()["gold"]

    @allure.step("查询背包")
    def get_backpack(self) -> list[dict[str, Any]]:
        resp = self.client.get("/api/backpack", headers=self.headers)
        return resp.get_json()

    # ---------- 购买 ----------
    @allure.step("购买道具 item_id={item_id}, quantity={quantity}")
    def buy(self, item_id: int, quantity: int) -> dict[str, Any]:
        resp = self.client.post(
            "/api/buy",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
        )
        return {
            "status_code": resp.status_code,
            "data": resp.get_json(),
        }

    # ---------- 出售 ----------
    @allure.step("出售道具 item_id={item_id}, quantity={quantity}")
    def sell(self, item_id: int, quantity: int) -> dict[str, Any]:
        resp = self.client.post(
            "/api/sell",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
        )
        return {
            "status_code": resp.status_code,
            "data": resp.get_json(),
        }