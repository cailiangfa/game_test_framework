"""
tests/api/test_mock.py
Mock 外部支付验证服务测试
适配修复后的 conftest.py（backend_module 别名 + patch.object）
★ 优化：支付成功用例增加数据验证；失败/超时用例使用 assert_state_equals 简化
★ 重构：assert_all_unchanged → assert_state_equals，before_gold 统一走 db_check
"""
from __future__ import annotations

import allure
import pytest
from pytest_mock import MockerFixture

import backend.app as backend_module
from tests.api.shop_api import ShopAPI
from tests.utils.assertions import assert_state_equals


@pytest.mark.api
@allure.feature("支付功能")
@allure.story("Mock 外部支付")
class TestMockPayment:
    """Mock 外部支付验证服务"""

    @allure.title("支付验证成功：购买正常完成，验证调用参数 + 数据变更")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_payment_verify_success(self, shop_api: ShopAPI, mocker: MockerFixture, db_check):
        with allure.step("Step 1: 记录购买前状态"):
            before_gold = shop_api.get_gold()
            before_bp = db_check(
                "SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1)
            )
            before_bp_count = before_bp["count"] if before_bp else 0

        with allure.step("Step 2: Mock 外部支付返回通过"):
            mock_verify = mocker.patch.object(
                backend_module.external_payment,
                "verify",
                return_value={"passed": True, "transaction_id": "mock_tx_001"},
            )

        with allure.step("Step 3: 发起购买请求"):
            result = shop_api.buy(item_id=1, quantity=1)

        with allure.step("Step 4: 断言接口返回"):
            assert result["status_code"] == 200
            assert result["data"]["msg"] == "购买成功"

        with allure.step("Step 5: 行为验证 - 确认支付服务被正确调用"):
            mock_verify.assert_called_once_with(1, 100)
            allure.attach(
                "调用参数: player_id=1, amount=100\n调用次数: 1",
                name="Mock 行为验证",
                attachment_type=allure.attachment_type.TEXT,
            )

        with allure.step("Step 6: 数据验证 - 金币必须扣了，背包必须加了"):
            after_gold = shop_api.get_gold()
            assert after_gold == before_gold - 100, (
                f"金币应扣100: {before_gold} -> {after_gold}"
            )
            after_bp = db_check(
                "SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1)
            )
            after_bp_count = after_bp["count"] if after_bp else 0
            assert after_bp_count == before_bp_count + 1, (
                f"背包应+1: {before_bp_count} -> {after_bp_count}"
            )

    @allure.title("支付验证失败：返回 400，数据绝对不变")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_payment_verify_failed(
        self, shop_api: ShopAPI, mocker: MockerFixture, db_check
    ):
        with allure.step("Step 1: 记录购买前状态"):
            gold_row = db_check("SELECT gold FROM players WHERE id=?", (1,))
            before_gold = int(gold_row["gold"]) if gold_row else 0
            before_orders = db_check(
                "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
            )["cnt"]
            before_bp = db_check(
                "SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1)
            )
            before_bp_count = before_bp["count"] if before_bp else 0

        with allure.step("Step 2: Mock 外部支付返回失败"):
            mock_verify = mocker.patch.object(
                backend_module.external_payment,
                "verify",
                return_value={"passed": False, "reason": "信用评分不足"},
            )

        with allure.step("Step 3: 发起购买请求"):
            result = shop_api.buy(item_id=1, quantity=1)

        with allure.step("Step 4: 断言接口返回"):
            assert result["status_code"] == 400
            assert "支付验证失败" in result["data"]["error"]
            assert "信用评分不足" in result["data"]["error"]

        with allure.step("Step 5: 行为验证"):
            mock_verify.assert_called_once_with(1, 100)

        with allure.step("Step 6: 严格数据不变断言（服务拒绝，绝不能扣钱）"):
            assert_state_equals(
                db_check,
                expected_gold=before_gold,
                expected_orders=before_orders,
                expected_bp_count=before_bp_count,
            )

    @allure.title("支付服务超时：返回 500，数据绝对不变")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_payment_service_timeout(
        self, shop_api: ShopAPI, mocker: MockerFixture, db_check
    ):
        with allure.step("Step 1: 记录购买前状态"):
            gold_row = db_check("SELECT gold FROM players WHERE id=?", (1,))
            before_gold = int(gold_row["gold"]) if gold_row else 0
            before_orders = db_check(
                "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
            )["cnt"]
            before_bp = db_check(
                "SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1)
            )
            before_bp_count = before_bp["count"] if before_bp else 0

        with allure.step("Step 2: Mock 外部支付抛出连接超时异常"):
            mock_verify = mocker.patch.object(
                backend_module.external_payment,
                "verify",
                side_effect=ConnectionError("支付服务连接超时"),
            )

        with allure.step("Step 3: 发起购买请求"):
            result = shop_api.buy(item_id=1, quantity=1)

        with allure.step("Step 4: 断言接口返回"):
            assert result["status_code"] == 500
            assert "支付服务异常" in result["data"]["error"]
            assert "支付服务连接超时" in result["data"]["error"]

        with allure.step("Step 5: 行为验证"):
            mock_verify.assert_called_once_with(1, 100)

        with allure.step("Step 6: 严格数据不变断言（服务挂了绝不能扣钱）"):
            assert_state_equals(
                db_check,
                expected_gold=before_gold,
                expected_orders=before_orders,
                expected_bp_count=before_bp_count,
            )
