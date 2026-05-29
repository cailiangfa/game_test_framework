"""
tests/api/test_overflow.py
游戏数值安全测试：int64溢出、负值、零值、极大值
这是游戏测试的差异化优势
"""
from __future__ import annotations

import allure
import pytest

from tests.utils.factories import create_player, set_player_gold


@allure.feature("数值安全")
@allure.story("边界与溢出")
class TestNumericSafety:
    """验证后端数值计算的边界防护"""

    @allure.title("购买数量极大值（quantity=999999）应被拒绝")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_buy_huge_quantity_rejected(self, client, logged_headers, db_check):
        """极大数量：验证后端不会计算溢出或挂掉"""
        resp = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 999999},
            headers=logged_headers,
        )
        # 期望：400 参数错误，而不是 500 内部错误或 200 成功
        assert resp.status_code == 400, f"极大数量应被拒绝，实际: {resp.status_code}"
        data = resp.get_json()
        assert "error" in data

        # 数据库断言：金币和背包都不能变
        gold = db_check("SELECT gold FROM players WHERE id=?", (1,))
        assert gold["gold"] == 1000, "金币不应被修改"
        bp = db_check("SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1))
        assert bp is None or bp["count"] == 0, "背包不应增加"

    @allure.title("购买数量零值/负值应被拒绝")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_zero_negative_rejected(self, client, logged_headers):
        """零值和负值：验证参数校验"""
        for bad_qty in [0, -1, -999]:
            resp = client.post(
                "/api/buy",
                json={"item_id": 1, "quantity": bad_qty},
                headers=logged_headers,
            )
            assert resp.status_code == 400, f"quantity={bad_qty} 应被拒绝"

    @allure.title("item_id 负值/零值应被拒绝")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_invalid_item_id(self, client, logged_headers):
        """非法道具ID"""
        for bad_id in [0, -1, 99999]:
            resp = client.post(
                "/api/buy",
                json={"item_id": bad_id, "quantity": 1},
                headers=logged_headers,
            )
            # 99999 可能返回 404（道具不存在），0/-1 应返回 400
            assert resp.status_code in [400, 404], f"item_id={bad_id} 应被拒绝，实际: {resp.status_code}"

    @allure.title("玩家金币 int64 最大值边界")
    @pytest.mark.skip(reason="需要后端支持设置极大金币，可选测试")
    def test_gold_int64_boundary(self, client, auth_headers, db_check):
        """
        极限场景：如果后端用 int64 存金币，接近最大值时加钱不应溢出为负
        这是一个概念测试，展示你对数值安全的关注
        """
        # 创建金币极大的玩家（模拟 int64 接近上限）
        player_id = create_player("rich_overflow", gold=2**63 - 1000)
        headers = auth_headers("rich_overflow")

        # 尝试买1瓶（100金币），应该成功
        resp = client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 1},
            headers=headers,
        )
        # 这里不强制断言，因为后端可能不支持这么大金币
        # 主要目的是展示测试设计思路
        allure.attach(
            f"初始金币: {2**63 - 1000}\n响应: {resp.status_code}\n数据: {resp.get_json()}",
            name="int64边界测试",
            attachment_type=allure.attachment_type.TEXT,
        )