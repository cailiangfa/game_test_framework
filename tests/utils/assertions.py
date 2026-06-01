"""
tests/utils/assertions.py
公共断言工具：供多个测试模块复用

★ 核心修改：
- 移除 get_gold 函数参数，统一用 db_check + player_id 查库
- 所有函数只依赖 db_check，职责单一
"""
from __future__ import annotations

from typing import Any, Callable

import allure


@allure.step("验证金币和订单数（防脏写）")
def assert_data_unchanged(
    db_check: Callable[..., Any | None],
    *,
    expected_gold: int,
    expected_orders: int,
    player_id: int = 1,
) -> None:
    """断言：金币和订单数等于预期值"""
    row = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
    after_gold = int(row["gold"]) if row else 0

    order_row = db_check(
        "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (player_id,)
    )
    after_orders = int(order_row["cnt"]) if order_row else 0

    assert after_gold == expected_gold, (
        f"金币不符: 实际={after_gold}, 期望={expected_gold}"
    )
    assert after_orders == expected_orders, (
        f"订单数不符: 实际={after_orders}, 期望={expected_orders}"
    )


@allure.step("验证背包数量（防脏写）")
def assert_backpack_unchanged(
    db_check: Callable[..., Any | None],
    *,
    expected_count: int,
    player_id: int = 1,
    item_id: int = 1,
) -> None:
    """断言：背包数量等于预期值"""
    row = db_check(
        "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
        (player_id, item_id),
    )
    actual = int(row["count"]) if row else 0
    assert actual == expected_count, (
        f"背包数量不符: 实际={actual}, 期望={expected_count}"
    )


@allure.step("验证完整数据状态（金币+订单+背包）")
def assert_state_equals(
    db_check: Callable[..., Any | None],
    *,
    expected_gold: int,
    expected_orders: int,
    expected_bp_count: int,
    player_id: int = 1,
    item_id: int = 1,
) -> None:
    """组合断言：金币 + 订单 + 背包数量都等于预期"""
    assert_data_unchanged(
        db_check,
        expected_gold=expected_gold,
        expected_orders=expected_orders,
        player_id=player_id,
    )
    assert_backpack_unchanged(
        db_check,
        expected_count=expected_bp_count,
        player_id=player_id,
        item_id=item_id,
    )


@allure.step("验证玩家存在")
def assert_player_exists(
    db_check: Callable[..., Any | None],
    *,
    player_id: int = 1,
) -> None:
    player = db_check("SELECT id FROM players WHERE id=?", (player_id,))
    assert player is not None, f"玩家 {player_id} 不存在"


@allure.step("验证玩家不存在")
def assert_player_not_exists(
    db_check: Callable[..., Any | None],
    *,
    player_id: int = 1,
) -> None:
    player = db_check("SELECT id FROM players WHERE id=?", (player_id,))
    assert player is None, f"玩家 {player_id} 不应存在"
