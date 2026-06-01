"""
tests/api/test_overflow.py
游戏数值安全测试：int64 溢出、负值、零值、极大值、MAX_QUANTITY 边界
这是游戏测试的差异化优势

★ 核心改动：
- 新增 MAX_QUANTITY 边界测试（10000 通过 / 10001 拒绝）
- 新增出售侧溢出测试（与购买对称）
- 验证具体错误信息，而非只检查 status_code
- 所有异常用例增加数据不变断言（防脏写）
★ 重构：assert_all_unchanged → assert_state_equals，升级为完整数据校验
★ 修复：create_player 返回 tuple，需要解包
"""
from __future__ import annotations

import allure
import pytest

from tests.utils.assertions import assert_state_equals
from tests.utils.factories import create_player, get_token


# ---------- 辅助函数 ----------
def _snapshot(db_check, player_id: int = 1, item_id: int = 1) -> dict:
    """快照玩家当前状态（统一走 db_check，与 assert_state_equals 数据源一致）"""
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


@pytest.mark.api
@allure.feature("数值安全")
@allure.story("边界与溢出")
class TestNumericSafety:
    """验证后端数值计算的边界防护"""

    # ========== 购买侧 ==========

    @allure.title("购买数量极大值（quantity=999999）应被拒绝")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_buy_huge_quantity_rejected(self, shop_api, db_check):
        """极大数量：验证后端不会计算溢出或挂掉"""
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=1, quantity=999999)
        assert result["status_code"] == 400, (
            f"极大数量应被拒绝，实际: {result['status_code']}"
        )
        # ★ 验证具体错误信息：应提示数量上限
        error_msg = result["data"].get("error", "")
        assert "数量" in error_msg or "超过" in error_msg, (
            f"错误信息应包含数量上限提示，实际: {error_msg}"
        )

        # 数据不变（金币 + 订单 + 背包完整校验）
        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("购买数量零值/负值应被拒绝: quantity={bad_qty}")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.parametrize(
        "bad_qty",
        [0, -1, -999],
        ids=["zero", "negative_one", "huge_negative"],
    )
    def test_buy_zero_negative_rejected(self, shop_api, db_check, bad_qty):
        """零值和负值：验证参数校验 + 数据不变"""
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=1, quantity=bad_qty)
        assert result["status_code"] == 400, f"quantity={bad_qty} 应被拒绝"

        error_msg = result["data"].get("error", "")
        assert "正整数" in error_msg, f"应提示'正整数'，实际: {error_msg}"

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("item_id 非法值应被拒绝: item_id={bad_id}")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.parametrize(
        "bad_id, expected_keyword",
        [(0, "不存在"), (-1, "不存在"), (99999, "不存在")],
        ids=["zero", "negative", "not_exist"],
    )
    def test_buy_invalid_item_id(self, shop_api, db_check, bad_id, expected_keyword):
        """非法道具 ID + 数据不变"""
        before = _snapshot(db_check)

        result = shop_api.buy_raw(item_id=bad_id, quantity=1)
        assert result["status_code"] == 400, (
            f"item_id={bad_id} 应返回 400，实际: {result['status_code']}"
        )

        error_msg = result["data"].get("error", "")
        assert expected_keyword in error_msg, (
            f"应包含'{expected_keyword}'，实际: {error_msg}"
        )

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("MAX_QUANTITY 边界：quantity=10000 成功，10001 拒绝")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_buy_max_quantity_boundary(self, client, db_check):
        """
        验证后端 MAX_QUANTITY=10000 的边界行为：
        - quantity=10000：如果金币足够，应该成功
        - quantity=10001：应该被拒绝（超过上限）
        """
        # ★ 修复：create_player 返回 (player_id, username)，需要解包
        player_id, _ = create_player(gold=2_000_000)
        token = get_token(player_id)
        headers = {"Authorization": f"Bearer {token}"}

        # quantity=10000 应该成功
        resp = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 10000},
            headers=headers,
        )
        assert resp.status_code == 200, (
            f"quantity=10000（MAX_QUANTITY）应成功，实际: {resp.status_code}"
        )
        data = resp.get_json()
        assert data["gold_remain"] == 2_000_000 - 10000 * 100

        # quantity=10001 应该被拒绝
        resp2 = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 10001},
            headers=headers,
        )
        assert resp2.status_code == 400, (
            f"quantity=10001 应被拒绝，实际: {resp2.status_code}"
        )
        error_msg = resp2.get_json().get("error", "")
        assert "数量" in error_msg or "超过" in error_msg, (
            f"应提示数量上限，实际: {error_msg}"
        )

        # ★ 10001 失败后，金币应保持 10000 成功购买后的状态
        gold_after = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
        assert int(gold_after["gold"]) == 2_000_000 - 10000 * 100, (
            "10001 失败不应影响金币"
        )

    # ========== 出售侧 ==========

    @allure.title("出售数量极大值（quantity=999999）应被拒绝")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_sell_huge_quantity_rejected(self, shop_api, db_check):
        """出售极大数量：应被拒绝，数据不变"""
        before = _snapshot(db_check)

        result = shop_api.sell_raw(item_id=1, quantity=999999)
        assert result["status_code"] == 400

        error_msg = result["data"].get("error", "")
        # 可能是"数量超过上限"或"道具数量不足"，两个都算通过
        assert any(
            kw in error_msg for kw in ["数量", "不足", "超过"]
        ), f"错误信息异常: {error_msg}"

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    @allure.title("出售数量零值/负值应被拒绝: quantity={bad_qty}")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.parametrize(
        "bad_qty",
        [0, -1, -999],
        ids=["zero", "negative_one", "huge_negative"],
    )
    def test_sell_zero_negative_rejected(self, shop_api, db_check, bad_qty):
        """出售零值/负值：参数校验 + 数据不变"""
        before = _snapshot(db_check)

        result = shop_api.sell_raw(item_id=1, quantity=bad_qty)
        assert result["status_code"] == 400

        error_msg = result["data"].get("error", "")
        assert "正整数" in error_msg, f"应提示'正整数'，实际: {error_msg}"

        assert_state_equals(
            db_check,
            expected_gold=before["gold"],
            expected_orders=before["orders"],
            expected_bp_count=before["bp_count"],
        )

    # ========== int64 边界（可选）==========

    @allure.title("玩家金币 int64 最大值边界")
    @pytest.mark.skip(reason="需要后端支持设置极大金币，可选测试")
    def test_gold_int64_boundary(self, client, db_check):
        """
        极限场景：如果后端用 int64 存金币，接近最大值时加钱不应溢出为负。
        注意：当前后端用 Python int（无限精度），不会真正溢出；
        如果迁移到 C/Java 后端，需要重新测试。
        """
        # ★ 修复：create_player 返回 (player_id, username)，需要解包
        player_id, _ = create_player("rich_overflow", gold=2**63 - 1000)
        token = get_token(player_id)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 1},
            headers=headers,
        )
        allure.attach(
            f"初始金币: {2**63 - 1000}\n响应: {resp.status_code}\n数据: {resp.get_json()}",
            name="int64边界测试",
            attachment_type=allure.attachment_type.TEXT,
        )
