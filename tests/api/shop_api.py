"""
tests/api/shop_api.py
统一 API Client：FlaskClient 版

★ 核心修改：
- _request 统一处理 headers 合并，日志和真实请求一致
- buy / sell 支持 **kwargs 透传 headers，方便工厂用户覆盖
- Schema 校验失败时抛出异常，防止测试假通过
- get_gold 失败时抛异常，不吞错
★ 修复：FlaskClient 不支持 timeout 参数，移除
"""
from __future__ import annotations

import json
from typing import Any, Dict

import allure
from flask.testing import FlaskClient

from tests.schemas.shop import (
    BuyRequest,
    BuyResponse,
    GoldResponse,
    LoginRequest,
    SellRequest,
    SellResponse,
)


class ShopAPI:
    def __init__(
        self, client: FlaskClient, headers: Dict[str, str] | None = None
    ) -> None:
        self.client = client
        self.headers = headers or {}

    def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> tuple[Any, Any]:
        """统一请求封装：合并 headers + 失败时记录 Allure"""
        # ★ 关键修改：统一合并 headers，保证日志和真实请求一致
        override_headers = kwargs.pop("headers", {})
        final_headers = {**self.headers, **override_headers}

        # 日志脱敏
        safe_headers = {
            k: ("***" if k.lower() == "authorization" else v)
            for k, v in final_headers.items()
        }

        request_log = {
            "method": method.upper(),
            "path": path,
            "headers": safe_headers,
            "body": kwargs.get("json"),
        }

        try:
            # ★ 修复：FlaskClient 不支持 timeout，移除该参数
            resp = getattr(self.client, method.lower())(
                path, headers=final_headers, **kwargs
            )
        except Exception as exc:
            allure.attach(
                json.dumps(
                    {"error": str(exc), "request": request_log},
                    ensure_ascii=False,
                    indent=2,
                ),
                name="request_failed",
                attachment_type=allure.attachment_type.JSON,
            )
            raise

        resp_data = resp.get_json(silent=True)
        if resp_data is None and resp.data:
            try:
                resp_data = resp.data.decode("utf-8")
            except Exception:
                resp_data = str(resp.data)

        if resp.status_code >= 400:
            allure.attach(
                json.dumps(request_log, ensure_ascii=False, indent=2),
                name="failed_request",
                attachment_type=allure.attachment_type.JSON,
            )
            allure.attach(
                json.dumps(
                    {"status_code": resp.status_code, "data": resp_data},
                    ensure_ascii=False,
                    indent=2,
                ),
                name="failed_response",
                attachment_type=allure.attachment_type.JSON,
            )

        return resp, resp_data

    # ---------- 基础操作（带 Pydantic 校验）----------

    @allure.step("登录: username={username}")
    def login(self, username: str, password: str) -> dict[str, Any]:
        payload = LoginRequest(username=username, password=password).model_dump()
        resp, data = self._request("post", "/api/login", json=payload)
        return {"status_code": resp.status_code, "data": data}

    @allure.step("获取金币")
    def get_gold(self, **kwargs) -> int:
        resp, data = self._request("get", "/api/gold", **kwargs)
        if resp.status_code != 200:
            raise AssertionError(f"获取金币失败: status={resp.status_code}, data={data}")

        if not isinstance(data, dict):
            raise AssertionError(f"金币接口返回非 dict: {data}")

        try:
            validated = GoldResponse.model_validate(data)
            return validated.gold
        except Exception as e:
            allure.attach(
                json.dumps(
                    {"error": str(e), "response_data": data},
                    ensure_ascii=False,
                    indent=2,
                ),
                name="gold_schema_error",
                attachment_type=allure.attachment_type.JSON,
            )
            raise AssertionError(f"金币响应 Schema 校验失败: {e}") from e

    @allure.step("购买: item_id={item_id}, quantity={quantity}")
    def buy(self, item_id: int, quantity: int, **kwargs) -> dict[str, Any]:
        payload = BuyRequest(item_id=item_id, quantity=quantity).model_dump()
        resp, data = self._request("post", "/api/buy", json=payload, **kwargs)

        # ★ 修复 P0：200 响应但 Schema 校验失败时，直接抛异常，防止假通过
        if resp.status_code == 200 and isinstance(data, dict):
            try:
                BuyResponse.model_validate(data)
            except Exception as e:
                allure.attach(
                    json.dumps(
                        {
                            "error": str(e),
                            "response_data": data,
                            "schema": BuyResponse.model_json_schema(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    name="schema_validation_error",
                    attachment_type=allure.attachment_type.JSON,
                )
                raise AssertionError(f"200 响应不符合 BuyResponse Schema: {e}") from e

        return {"status_code": resp.status_code, "data": data}

    @allure.step("出售: item_id={item_id}, quantity={quantity}")
    def sell(self, item_id: int, quantity: int, **kwargs) -> dict[str, Any]:
        payload = SellRequest(item_id=item_id, quantity=quantity).model_dump()
        resp, data = self._request("post", "/api/sell", json=payload, **kwargs)

        # ★ 修复 P0：200 响应但 Schema 校验失败时，直接抛异常
        if resp.status_code == 200 and isinstance(data, dict):
            try:
                SellResponse.model_validate(data)
            except Exception as e:
                allure.attach(
                    json.dumps(
                        {
                            "error": str(e),
                            "response_data": data,
                            "schema": SellResponse.model_json_schema(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    name="schema_validation_error",
                    attachment_type=allure.attachment_type.JSON,
                )
                raise AssertionError(f"200 响应不符合 SellResponse Schema: {e}") from e

        return {"status_code": resp.status_code, "data": data}

    # ---------- 原始请求（绕过 Pydantic）----------

    @allure.step("原始购买请求: item_id={item_id}, quantity={quantity}")
    def buy_raw(self, item_id: int, quantity: int, **kwargs) -> dict[str, Any]:
        """不经过 Pydantic 校验，直接发请求，用于测试后端参数校验"""
        resp, data = self._request(
            "post",
            "/api/buy",
            json={"item_id": item_id, "quantity": quantity},
            **kwargs,
        )
        return {"status_code": resp.status_code, "data": data}

    @allure.step("原始出售请求: item_id={item_id}, quantity={quantity}")
    def sell_raw(self, item_id: int, quantity: int, **kwargs) -> dict[str, Any]:
        """不经过 Pydantic 校验，直接发请求"""
        resp, data = self._request(
            "post",
            "/api/sell",
            json={"item_id": item_id, "quantity": quantity},
            **kwargs,
        )
        return {"status_code": resp.status_code, "data": data}

    # ---------- Schema 严格校验版 ----------

    @allure.step("Schema校验购买: item_id={item_id}, quantity={quantity}")
    def buy_validated(self, item_id: int, quantity: int, **kwargs) -> BuyResponse:
        """严格校验版：后端返回字段不对直接抛异常，测试立刻失败"""
        result = self.buy(item_id, quantity, **kwargs)
        if result["status_code"] != 200:
            raise AssertionError(f"购买失败: {result['data']}")
        # buy() 内部已经校验过一次，这里再校验一次确保万无一失
        return BuyResponse.model_validate(result["data"])

    @allure.step("Schema校验出售: item_id={item_id}, quantity={quantity}")
    def sell_validated(self, item_id: int, quantity: int, **kwargs) -> SellResponse:
        result = self.sell(item_id, quantity, **kwargs)
        if result["status_code"] != 200:
            raise AssertionError(f"出售失败: {result['data']}")
        return SellResponse.model_validate(result["data"])
