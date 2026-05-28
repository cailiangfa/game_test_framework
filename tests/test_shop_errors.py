"""
异常测试用例：鉴权 / 参数校验 / 业务规则
适配修复后的 conftest.py（数据重置方案 + ShopAPI 封装层）
"""

from __future__ import annotations

import allure
import pytest

from tests.api.shop_api import ShopAPI
from tests.utils.assertions import assert_backpack_unchanged, assert_data_unchanged


# ============================================================================
# 鉴权异常
# ============================================================================
@allure.feature("商城功能")
@allure.story("异常场景")
class TestAuthErrors:
    """未登录 / Token 异常"""

    @allure.title("未登录购买：返回 401")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_without_token(self, client):
        with allure.step("Step 1: 不带 Authorization 调用购买"):
            resp = client.post("/api/buy", json={"item_id": 1, "quantity": 1})
            assert resp.status_code == 401
            assert "未登录" in resp.get_json()["error"]

    @allure.title("Token 格式非法：返回 401")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_invalid_token_format(self, client):
        with allure.step("Step 1: 发送格式错误但结构合法的 Token"):
            resp = client.post(
                "/api/buy",
                json={"item_id": 1, "quantity": 1},
                headers={"Authorization": "Bearer token_abc"},
            )
            assert resp.status_code == 401
            assert "无效Token" in resp.get_json()["error"]

    @allure.title("Token 中玩家 ID 不存在：返回 404")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_player_not_exist(self, client):
        with allure.step("Step 1: 使用不存在的 player_id=999"):
            resp = client.post(
                "/api/buy",
                json={"item_id": 1, "quantity": 1},
                headers={"Authorization": "Bearer token_999"},
            )
            assert resp.status_code == 404
            assert "玩家不存在" in resp.get_json()["error"]


# ============================================================================
# 业务规则异常
# ============================================================================
@allure.feature("商城功能")
@allure.story("异常场景")
class TestBusinessErrors:
    """余额不足 / 道具不存在 / 背包不足"""

    @allure.title("余额不足购买：返回 400，数据无脏写")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_insufficient_gold(self, shop_api: ShopAPI, db_check):
        with allure.step("Step 1: 记录购买前状态"):
            before_gold = shop_api.get_gold()
            before_orders = db_check(
                "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
            )["cnt"]
            allure.attach(
                f"金币: {before_gold}\n订单: {before_orders}",
                name="购买前状态",
                attachment_type=allure.attachment_type.TEXT,
            )

        with allure.step("Step 2: 尝试购买 999 瓶（远超余额）"):
            result = shop_api.buy(item_id=1, quantity=999)
            assert result["status_code"] == 400
            assert "余额不足" in result["data"]["error"]

        with allure.step("Step 3: 验证数据未脏写"):
            assert_data_unchanged(
                shop_api.get_gold,
                db_check,
                expected_gold=before_gold,
                expected_orders=before_orders,
            )

    @allure.title("购买不存在的道具：返回 400")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_item_not_exist(self, shop_api: ShopAPI):
        with allure.step("Step 1: 尝试购买 item_id=999"):
            result = shop_api.buy(item_id=999, quantity=1)
            assert result["status_code"] == 400
            assert "不存在" in result["data"]["error"]

    @allure.title("出售背包数量不足：返回 400，数据无脏写")
    @allure.severity(allure.severity_level.NORMAL)
    def test_sell_insufficient_items(self, shop_api: ShopAPI, db_check):
        with allure.step("Step 0: 前置 - 购买 2 瓶生命药水"):
            buy_result = shop_api.buy(item_id=1, quantity=2)
            assert buy_result["status_code"] == 200, f"前置购买失败: {buy_result['data']}"

        with allure.step("Step 1: 记录出售前状态"):
            before_gold = shop_api.get_gold()
            before_bp = db_check(
                "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
                (1, 1),
            )
            before_count = before_bp["count"] if before_bp else 0
            before_orders = db_check(
                "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
            )["cnt"]

        with allure.step("Step 2: 尝试出售 5 瓶（只有 2 瓶）"):
            result = shop_api.sell(item_id=1, quantity=5)
            assert result["status_code"] == 400
            assert "不足" in result["data"]["error"]

        with allure.step("Step 3: 验证数据未脏写"):
            assert_data_unchanged(
                shop_api.get_gold,
                db_check,
                expected_gold=before_gold,
                expected_orders=before_orders,
            )
            assert_backpack_unchanged(
                db_check,
                expected_count=before_count,
            )

    @allure.title("出售从未拥有的道具：返回 400")
    @allure.severity(allure.severity_level.NORMAL)
    def test_sell_item_not_in_backpack(self, shop_api: ShopAPI):
        with allure.step("Step 1: 尝试出售从未购买的 item_id=2"):
            result = shop_api.sell(item_id=2, quantity=1)
            assert result["status_code"] == 400
            assert "不足" in result["data"]["error"]


# ============================================================================
# 参数校验异常
# ============================================================================
@allure.feature("商城功能")
@allure.story("异常场景")
class TestValidationErrors:
    """数量非法 / 字段缺失 / 空请求体"""

    @allure.title("购买数量为 0：返回 400")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_zero_quantity(self, shop_api: ShopAPI):
        with allure.step("Step 1: quantity=0"):
            result = shop_api.buy(item_id=1, quantity=0)
            assert result["status_code"] == 400
            assert "正整数" in result["data"]["error"]

    @allure.title("购买数量为负数：返回 400")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_negative_quantity(self, shop_api: ShopAPI):
        with allure.step("Step 1: quantity=-5"):
            result = shop_api.buy(item_id=1, quantity=-5)
            assert result["status_code"] == 400
            assert "正整数" in result["data"]["error"]

    @allure.title("购买数量为浮点数：返回 400")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_float_quantity(self, shop_api: ShopAPI):
        with allure.step("Step 1: quantity=1.5"):
            result = shop_api.buy(item_id=1, quantity=1.5)
            assert result["status_code"] == 400
            assert "正整数" in result["data"]["error"]

    @allure.title("缺少必填字段 item_id：返回 400")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_missing_item_id(self, shop_api: ShopAPI):
        with allure.step("Step 1: 请求体不含 item_id"):
            resp = shop_api.client.post(
                "/api/buy",
                json={"quantity": 1},
                headers=shop_api.headers,
            )
            assert resp.status_code == 400
            assert "缺少" in resp.get_json()["error"] or "item_id" in resp.get_json()["error"]

    @allure.title("请求体为空：不触发 500")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_empty_body(self, shop_api: ShopAPI):
        with allure.step("Step 1: 发送空 JSON 请求体"):
            resp = shop_api.client.post(
                "/api/buy",
                headers=shop_api.headers,
                content_type="application/json",
            )
            assert resp.status_code in (400, 401, 404)

    @allure.title("出售数量为负数：返回 400")
    @allure.severity(allure.severity_level.NORMAL)
    def test_sell_negative_quantity(self, shop_api: ShopAPI):
        with allure.step("Step 0: 前置 - 购买 1 瓶确保背包有货"):
            buy_result = shop_api.buy(item_id=1, quantity=1)
            assert buy_result["status_code"] == 200

        with allure.step("Step 1: quantity=-1"):
            result = shop_api.sell(item_id=1, quantity=-1)
            assert result["status_code"] == 400
            assert "正整数" in result["data"]["error"]

    @allure.title("未登录出售：返回 401")
    @allure.severity(allure.severity_level.NORMAL)
    def test_sell_without_token(self, client):
        with allure.step("Step 1: 不带 Authorization 调用出售"):
            resp = client.post("/api/sell", json={"item_id": 1, "quantity": 1})
            assert resp.status_code == 401