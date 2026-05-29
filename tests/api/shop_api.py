from typing import Any
import allure
import json
from flask.testing import FlaskClient


class ShopAPI:
    def __init__(self, client: FlaskClient, headers: dict[str, str] | None = None) -> None:
        self.client = client
        self.headers = headers or {}

    def _request(self, method: str, path: str, **kwargs) -> tuple[Any, Any]:
        """统一请求封装：失败时自动记录请求/响应到 Allure"""
        # 脱敏：Authorization 值打码，避免 token 泄露到报告
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

        # 解析响应（silent=True 防止非 JSON 响应抛异常）
        resp_data = resp.get_json(silent=True)
        if resp_data is None and resp.data:
            resp_data = resp.data.decode("utf-8")

        # 状态码 >= 400 时，自动 attach 到 Allure（排查核心能力）
        if resp.status_code >= 400:
            allure.attach(
                json.dumps(request_log, ensure_ascii=False, indent=2),
                name="failed_request",
                attachment_type=allure.attachment_type.JSON,
            )
            allure.attach(
                json.dumps({
                    "status_code": resp.status_code,
                    "data": resp_data,
                    "headers": dict(resp.headers),
                }, ensure_ascii=False, indent=2),
                name="failed_response",
                attachment_type=allure.attachment_type.JSON,
            )

        return resp, resp_data

    @allure.step("登录: username={username}")
    def login(self, username: str, password: str) -> dict[str, Any]:
        resp, data = self._request("post", "/api/login", json={"username": username, "password": password})
        return {"status_code": resp.status_code, "data": data}

    @allure.step("获取金币")
    def get_gold(self) -> int:
        resp, data = self._request("get", "/api/gold", headers=self.headers)
        if resp.status_code == 200 and data:
            return data.get("gold", 0)
        return 0

    @allure.step("购买: item_id={item_id}, quantity={quantity}")
    def buy(self, item_id: int, quantity: int) -> dict[str, Any]:
        resp, data = self._request(
            "post",
            "/api/buy",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
        )
        return {"status_code": resp.status_code, "data": data}

    @allure.step("出售: item_id={item_id}, quantity={quantity}")
    def sell(self, item_id: int, quantity: int) -> dict[str, Any]:
        resp, data = self._request(
            "post",
            "/api/sell",
            json={"item_id": item_id, "quantity": quantity},
            headers=self.headers,
        )
        return {"status_code": resp.status_code, "data": data}