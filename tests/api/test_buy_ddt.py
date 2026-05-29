"""
数据驱动购买测试（DDT）- 最终确认版
适配修复后的 conftest.py + 新的 buy_data.json 格式
"""

from __future__ import annotations

import allure
import pytest

from tests.api.shop_api import ShopAPI
from tests.utils.data_loader import load_json_data


# ========== 辅助函数（必须在类定义之前）==========
def _build_test_id(case: dict) -> str:
    """生成可读性强的测试 ID"""
    return case.get("id") or f"item{case['item_id']}_qty{case['quantity']}"


def _get_item_price(db_check, item_id: int) -> int:
    """查询道具价格"""
    item = db_check("SELECT price FROM items WHERE id=?", (item_id,))
    assert item is not None, f"道具不存在: item_id={item_id}"
    return item["price"]


# ========== 测试类 ==========
@allure.feature("商城功能")
@allure.story("数据驱动购买")
class TestBuyDDT:
    """数据驱动购买正向测试"""

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(c, id=_build_test_id(c))
            for c in load_json_data("buy_data.json")
        ],
    )
    @allure.title("{case[id]}: {case[description]}")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_success_ddt(self, shop_api: ShopAPI, db_check, case: dict):
        """从 JSON 加载数据，验证购买功能"""

        item_id = case["item_id"]
        quantity = case["quantity"]

        with allure.step(f"Step 1: 获取道具 {item_id} 价格"):
            price = _get_item_price(db_check, item_id)
            expected_cost = price * quantity
            allure.attach(
                f"item_id={item_id}, price={price}, quantity={quantity}, cost={expected_cost}",
                name="购买参数",
                attachment_type=allure.attachment_type.TEXT,
            )

        with allure.step("Step 2: 记录购买前状态"):
            before_gold = shop_api.get_gold()
            before_bp = db_check(
                "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
                (1, item_id),
            )
            before_bp_count = before_bp["count"] if before_bp else 0
            before_orders = db_check(
                "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
            )["cnt"]

        with allure.step(f"Step 3: 执行购买 (item_id={item_id}, quantity={quantity})"):
            result = shop_api.buy(item_id=item_id, quantity=quantity)
            assert result["status_code"] == 200, f"购买失败: {result['data']}"
            assert result["data"]["msg"] == "购买成功"

        with allure.step("Step 4: 验证接口返回金币"):
            assert result["data"]["gold_remain"] == before_gold - expected_cost

        with allure.step("Step 5: 验证数据库状态"):
            after_gold = shop_api.get_gold()
            assert after_gold == before_gold - expected_cost, f"金币异常: {after_gold}"

            after_bp = db_check(
                "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
                (1, item_id),
            )
            assert after_bp is not None, "购买后背包记录丢失"
            assert after_bp["count"] == before_bp_count + quantity, "背包数量异常"

            after_orders = db_check(
                "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
            )["cnt"]
            assert after_orders == before_orders + 1, "订单未生成"

        with allure.step("Step 6: 验证 JSON 预期结果"):
            expected_gold_delta = case.get("expected_gold_delta")
            expected_bp_delta = case.get("expected_bp_delta")

            if expected_gold_delta is not None:
                actual_delta = shop_api.get_gold() - before_gold
                assert (
                    actual_delta == expected_gold_delta
                ), f"金币变化异常: 预期 {expected_gold_delta}, 实际 {actual_delta}"

            if expected_bp_delta is not None:
                final_bp = db_check(
                    "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
                    (1, item_id),
                )
                actual_delta = (final_bp["count"] if final_bp else 0) - before_bp_count
                assert (
                    actual_delta == expected_bp_delta
                ), f"背包变化异常: 预期 {expected_bp_delta}, 实际 {actual_delta}"
