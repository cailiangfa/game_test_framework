"""
tests/api/shop_api.py
统一 API Client：FlaskClient 版（API 测试用，快）
增加 Pydantic Schema 校验层 + 原始请求方法（用于异常场景测试）
"""
from __future__ import annotations

import json
from typing import Any

import allure
from flask.testing import FlaskClient

from tests.schemas.shop import BuyRequest, BuyResponse, LoginRequest, LoginResponse, SellRequest, SellResponse


class ShopAPI:
    def __init__(
        self, client: FlaskClient, headers: dict[str, str] | None = None
    ) -> None:
        self.client = client
        self.headers = headers or {}

    def _request(self, method: str, path: str, **kwargs) -> tuple[Any, Any]:
        """统一请求封装：失败时自动记录到 Allure"""
        all_headers = {**self.headers, **kwargs.get("headers", {})}
        safe_headers = {
            k: ("***" if k.lower() == "authorization" else v)
            for k, v in all_headers.items()
        }

        request_log = {
            "method": method.upper(),
            "path": path,
            "headers": safe_headers,
            "body": kwargs.get("json"),
        }

        resp = getattr(self.client, method.lower())(path, **kwargs)
        resp_data = resp.get_json(silent=True)
        if resp_data is None and resp.data:
            resp_data = resp.data.decode("utf-8")

        if resp.status_code >= 400:
            allure.attach(
                json.dumps(request_log, ensure_ascii=False, indent=2),
                name="failed_request",
                attachment_type=allure.attachment_type.JSON,
            )
            allure.attach(
                json.dumps(
                    {
                        "status_code": resp.status_code,
                        "data": resp_data,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                name="failed_response",
                attachment_type=allure.attachment_type.JSON,
            )

        return resp, resp_data

    # ---------- 基础操作（带 Pydantic 校验，正常流程用）----------
    @allure.step("登录: username={username}")
    def login(self, username: str, password: str) -> dict[str, Any]:
        LoginRequest(username=username, password=password)
        resp, data = self._request(
            "post", "/api/login", json={"username": username, "password": password}
        )
        return {"status_code": resp.status_code, "data": data}

    @allure.step("获取金币")
    def get_gold(self) -> int:
        resp, data = self._request("get", "/api/gold", headers=self.headers)
        if resp.status_code == 200 and data:
            validated = BuyResponse.model_validate({"gold_remain": data.get("gold", 0), "msg": ""})
            return validated.gold_remain
        return 0

    @allure.step("购买: item_id={item_id}, quantity={quantity}")
    def buy(self, item_id: int, quantity: int) -> dict[str, Any]:
        BuyRequest(item_id=item_id, quantity=quantity)
        resp, data = self._request(
            "post",
            "/api/buy",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
        )
        if resp.status_code == 200 and isinstance(data, dict):
            try:
                BuyResponse.model_validate(data)
            except Exception as e:
                allure.attach(str(e), name="schema_validation_error")
        return {"status_code": resp.status_code, "data": data}

    @allure.step("出售: item_id={item_id}, quantity={quantity}")
    def sell(self, item_id: int, quantity: int) -> dict[str, Any]:
        SellRequest(item_id=item_id, quantity=quantity)
        resp, data = self._request(
            "post",
            "/api/sell",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
        )
        if resp.status_code == 200 and isinstance(data, dict):
            try:
                SellResponse.model_validate(data)
            except Exception as e:
                allure.attach(str(e), name="schema_validation_error")
        return {"status_code": resp.status_code, "data": data}

    # ---------- 原始请求（绕过 Pydantic，专门测后端校验用）----------
    @allure.step("原始购买请求（异常场景）: item_id={item_id}, quantity={quantity}")
    def buy_raw(self, item_id, quantity, **kwargs) -> dict[str, Any]:
        """不经过 Pydantic 校验，直接发请求，用于测试后端参数校验"""
        resp, data = self._request(
            "post",
            "/api/buy",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
            **kwargs
        )
        return {"status_code": resp.status_code, "data": data}

    @allure.step("原始出售请求（异常场景）: item_id={item_id}, quantity={quantity}")
    def sell_raw(self, item_id, quantity, **kwargs) -> dict[str, Any]:
        """不经过 Pydantic 校验，直接发请求"""
        resp, data = self._request(
            "post",
            "/api/sell",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
            **kwargs
        )
        return {"status_code": resp.status_code, "data": data}

    # ---------- Schema 严格校验版（面试亮点：防御式编程）----------
    @allure.step("Schema校验购买: item_id={item_id}, quantity={quantity}")
    def buy_validated(self, item_id: int, quantity: int) -> BuyResponse:
        """严格校验版：后端返回字段不对直接抛异常，测试立刻失败"""
        result = self.buy(item_id, quantity)
        if result["status_code"] != 200:
            raise AssertionError(f"购买失败: {result['data']}")
        return BuyResponse.model_validate(result["data"])

    @allure.step("Schema校验出售: item_id={item_id}, quantity={quantity}")
    def sell_validated(self, item_id: int, quantity: int) -> SellResponse:
        result = self.sell(item_id, quantity)
        if result["status_code"] != 200:
            raise AssertionError(f"出售失败: {result['data']}")
        return SellResponse.model_validate(result["data"])