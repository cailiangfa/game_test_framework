"""
tests/api/test_shop_errors.py
异常场景测试：鉴权失败、业务异常、参数校验
所有故意传错误参数的调用都用 buy_raw / sell_raw（绕过 Pydantic 前端校验）
★ 优化：所有异常用例均增加数据完整性验证（防脏写）
★ 重构：assert_all_unchanged → assert_state_equals，_snapshot 统一走 db_check
★ 修复：shop_api.request_raw 不存在，改用 client 直接请求
"""
from __future__ import annotations

import allure
import pytest

from tests.utils.assertions import assert_state_equals


# ---------- 辅助函数 ----------
def _snapshot(db_check, player_id: int = 1, item_id: int = 1) -> dict:
    """快照玩家当前状态，用于异常后比对（统一走 db_check，与 assert_state_equals 数据源一致）"""
    row = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
    return {
        "gold": int(row["gold"]) if row else 0,
        "orders": db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (player_id,)
        )["cnt"],
        "bp_count": (
            db_check(
                "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
                (player_id, item_id),
            )
            or {}
        ).get("count", 0),
    }


# ========== 鉴权异常 ==========
@pytest.mark.api
@allure.feature("异常场景")
@allure.story("鉴权失败")
class TestAuthErrors:
    """鉴权异常：无 token / 无效 token / 玩家不存在"""

    def test_buy_without_token(self, client):
        resp = client.post("/api/buy", json={"item_id": 1, "quantity": 1})
        assert resp.status_code == 401
        assert "未登录" in resp.get_json()["error"]

    def test_buy_invalid_token_format(self, client):
        resp = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 1},
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert resp.status_code == 401
        assert "未登录" in resp.get_json()["error"]

    def test_buy_player_not_exist(self, client):
        resp = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 1},
            headers={"Authorization": "Bearer token_99999"},
        )
        assert resp.status_code == 404
        assert "玩家不存在" in resp.get_json()["error"]


# ========== 业务异常 ==========
@pytest.mark.api
@allure.feature("异常场景")
@allure.story("业务异常")
class TestBusinessErrors:
    """业务异常：余额不足、道具不存在、背包数量不足"""

    @allure.title("购买失败：金币不足，数据不能被脏写")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_buy_insufficient_gold(self, shop_api, db_check):
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=1, quantity=999)
        assert result["status_code"] == 400
        assert "余额不足" in result["data"]["error"]

        # ★ 核心验证：异常后数据绝对不变
        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("购买失败：道具不存在，数据不能被脏写")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_buy_item_not_exist(self, shop_api, db_check):
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=999, quantity=1)
        assert result["status_code"] in [400, 404]
        error_msg = result["data"].get("error", "")
        assert any(
            keyword in error_msg for keyword in ["不存在", "道具", "item"]
        ), f"unexpected error: {error_msg}"

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("出售失败：背包数量不足，数据不能被脏写")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_sell_insufficient_items(self, shop_api, db_check):
        before = _snapshot(db_check)

        result = shop_api.sell_raw(item_id=1, quantity=999)
        assert result["status_code"] == 400
        assert "道具数量不足" in result["data"]["error"]

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("出售失败：道具不存在，数据不能被脏写")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_sell_item_not_in_backpack(self, shop_api, db_check):
        before = _snapshot(db_check, item_id=999)

        result = shop_api.sell_raw(item_id=999, quantity=1)
        assert result["status_code"] == 400
        assert "道具不存在" in result["data"]["error"]

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=0,
            item_id=999,
        )


# ========== 参数校验异常 ==========
@pytest.mark.api
@allure.feature("异常场景")
@allure.story("参数校验")
class TestValidationErrors:
    """参数校验异常（绕过 Pydantic，直接测后端校验）"""

    @allure.title("购买数量为0：参数校验 + 数据不变")
    def test_buy_zero_quantity(self, shop_api, db_check):
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=1, quantity=0)
        assert result["status_code"] == 400
        assert "正整数" in result["data"]["error"]

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("购买数量为负数：参数校验 + 数据不变")
    def test_buy_negative_quantity(self, shop_api, db_check):
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=1, quantity=-5)
        assert result["status_code"] == 400
        assert "正整数" in result["data"]["error"]

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("购买数量为浮点数：参数校验 + 数据不变")
    def test_buy_float_quantity(self, shop_api, db_check):
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=1, quantity=1.5)
        assert result["status_code"] == 400
        assert "正整数" in result["data"]["error"]

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("购买 item_id 为 None：参数校验 + 数据不变")
    def test_buy_missing_item_id(self, shop_api, db_check):
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=None, quantity=1)
        assert result["status_code"] == 400
        assert "item_id" in result["data"]["error"]

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("购买空请求体：参数校验 + 数据不变")
    def test_buy_empty_body(self, client, db_check):
        """★ 修复：client.post 需要带 Authorization，否则先被 401 拦截"""
        before = _snapshot(db_check)

        resp = client.post(
            "/api/buy",
            json={},
            headers={"Authorization": "Bearer token_1"},
        )
        assert resp.status_code == 400
        assert "item_id" in resp.get_json()["error"]

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("出售数量为负数：参数校验 + 数据不变")
    def test_sell_negative_quantity(self, shop_api, db_check):
        before = _snapshot(db_check)

        result = shop_api.sell_raw(item_id=1, quantity=-1)
        assert result["status_code"] == 400
        assert "正整数" in result["data"]["error"]

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("出售未登录：鉴权失败")
    def test_sell_without_token(self, client):
        resp = client.post("/api/sell", json={"item_id": 1, "quantity": 1})
        assert resp.status_code == 401
        assert "未登录" in resp.get_json()["error"]
