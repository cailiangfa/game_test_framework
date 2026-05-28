"""
公共断言工具：供多个测试模块复用
"""

from __future__ import annotations

from typing import Any, Callable

import allure


@allure.step("验证数据未脏写：金币={expected_gold}, 订单={expected_orders}")
def assert_data_unchanged(
    get_gold: Callable[[], int],
    db_check: Callable[..., Any | None],
    *,
    expected_gold: int,
    expected_orders: int,
    player_id: int = 1,
) -> None:
    """断言：金币和订单数在异常后不应变化（防止脏写）"""
    after_gold = get_gold()
    after_orders = db_check(
        "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (player_id,)
    )["cnt"]

    assert after_gold == expected_gold, f"异常后金币不应变化: {after_gold} != {expected_gold}"
    assert after_orders == expected_orders, f"异常后订单数不应变化: {after_orders} != {expected_orders}"


@allure.step("验证背包数量未变化")  # ← 去掉 f-string，避免 KeyError
def assert_backpack_unchanged(
    db_check: Callable[..., Any | None],
    *,
    expected_count: int,
    player_id: int = 1,
    item_id: int = 1,
) -> None:
    """断言：背包数量在异常后不应变化"""
    after_bp = db_check(
        "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
        (player_id, item_id),
    )
    actual = after_bp["count"] if after_bp else 0
    assert actual == expected_count, f"异常后背包数量不应变化: {actual} != {expected_count}"

    def assert_data_unchanged(get_gold_fn, db_check_fn, expected_gold, expected_orders):
        """验证金币和订单数未发生变化（防止脏写）"""
        actual_gold = get_gold_fn()
        actual_orders = db_check_fn(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
        )["cnt"]
        assert actual_gold == expected_gold, f"金币被脏写: {actual_gold} != {expected_gold}"
        assert actual_orders == expected_orders, f"订单数被脏写: {actual_orders} != {expected_orders}"

    def assert_backpack_unchanged(db_check_fn, expected_count):
        """验证背包道具数量未发生变化（防止脏写）"""
        actual_bp = db_check_fn(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (1, 1),
        )
        actual_count = actual_bp["count"] if actual_bp else 0
        assert actual_count == expected_count, f"背包数量被脏写: {actual_count} != {expected_count}"