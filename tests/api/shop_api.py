from typing import Any
import allure
from flask.testing import FlaskClient


class ShopAPI:
    def __init__(self, client: FlaskClient, headers: dict[str, str] | None = None) -> None:
        self.client = client
        self.headers = headers or {}

    @allure.step("登录: username={username}")
    def login(self, username: str, password: str) -> dict[str, Any]:
        resp = self.client.post("/api/login", json={"username": username, "password": password})
        return {"status_code": resp.status_code, "data": resp.get_json()}

    @allure.step("获取金币")
    def get_gold(self) -> int:
        resp = self.client.get("/api/gold", headers=self.headers)
        if resp.status_code == 200:
            data = resp.get_json()
            return data.get("gold", 0) if data else 0
        return 0

    @allure.step("购买: item_id={item_id}, quantity={quantity}")
    def buy(self, item_id: int, quantity: int) -> dict[str, Any]:
        resp = self.client.post(
            "/api/buy",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
        )
        return {"status_code": resp.status_code, "data": resp.get_json()}

    @allure.step("出售: item_id={item_id}, quantity={quantity}")
    def sell(self, item_id: int, quantity: int) -> dict[str, Any]:
        resp = self.client.post(
            "/api/sell",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
        )
        return {"status_code": resp.status_code, "data": resp.get_json()}