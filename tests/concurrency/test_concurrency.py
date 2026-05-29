"""
tests/concurrency/test_concurrency.py
并发竞态测试最终版：超卖、超扣、重复支付
游戏测试核心壁垒
"""
from __future__ import annotations

import threading
import time

import allure
import requests

from tests.utils.factories import create_player, get_token, give_item_to_player


@allure.feature("商城功能")
@allure.story("并发竞态测试")
class TestRaceCondition:
    """并发场景下的数据一致性验证"""

    @allure.title("并发购买：10 人同时购买，验证不超扣")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_concurrent_buy_consistency(self, base_url: str, db_check):
        """
        场景：玩家有 1000 金币，同时发起 10 次购买请求（每次买 1 瓶生命药水，100 金币）
        期望：最终金币 + 已花费 = 1000，不能出现负余额
        """
        player_id = create_player("concurrent_buyer", gold=1000)
        token = get_token(player_id)
        headers = {"Authorization": f"Bearer {token}"}
        buy_url = f"{base_url}/api/buy"

        results = []
        errors = []

        def _buy():
            try:
                resp = requests.post(
                    buy_url,
                    json={"item_id": 1, "quantity": 1},
                    headers=headers,
                    timeout=5,
                )
                results.append(resp.status_code)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=_buy) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(0.5)

        success_count = sum(1 for r in results if r == 200)
        fail_count = len(results) - success_count

        allure.attach(
            f"成功: {success_count}\n失败: {fail_count}\n异常: {len(errors)}\n"
            f"状态码: {results}",
            name="并发请求结果",
            attachment_type=allure.attachment_type.TEXT,
        )

        final_gold = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
        final_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (player_id, 1),
        )

        final_gold_val = final_gold["gold"] if final_gold else 0
        final_bp_count = final_backpack["count"] if final_backpack else 0

        # 核心断言 1：金币不能为负
        assert final_gold_val >= 0, f"金币为负！超扣 Bug！final_gold={final_gold_val}"

        # 核心断言 2：背包数量 == 成功请求数
        assert final_bp_count == success_count, (
            f"背包({final_bp_count}) != 成功数({success_count})，可能超卖或丢失"
        )

        # 核心断言 3：金币 + 花费 == 初始金币
        total_spent = success_count * 100
        assert final_gold_val + total_spent == 1000, (
            f"金币不一致！初始1000，最终{final_gold_val}，花费{total_spent}"
        )

    @allure.title("并发出售：验证不出售超过拥有的数量")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_concurrent_sell_consistency(self, base_url: str, db_check):
        """
        场景：玩家有 5 瓶生命药水，同时发起 10 次出售请求
        期望：最多 5 次成功
        """
        player_id = create_player("concurrent_seller", gold=0)
        give_item_to_player(player_id, item_id=1, count=5)

        token = get_token(player_id)
        headers = {"Authorization": f"Bearer {token}"}
        sell_url = f"{base_url}/api/sell"

        results = []

        def _sell():
            try:
                resp = requests.post(
                    sell_url,
                    json={"item_id": 1, "quantity": 1},
                    headers=headers,
                    timeout=5,
                )
                results.append(resp.status_code)
            except Exception:
                results.append(-1)

        threads = [threading.Thread(target=_sell) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(0.5)

        success_count = sum(1 for r in results if r == 200)

        final_gold = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
        final_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (player_id, 1),
        )

        final_gold_val = final_gold["gold"] if final_gold else 0
        final_bp_count = final_backpack["count"] if final_backpack else 0

        allure.attach(
            f"成功出售: {success_count}\n最终金币: {final_gold_val}\n背包剩余: {final_bp_count}",
            name="并发出售结果",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert success_count <= 5, f"超卖！成功{success_count}次，但只有5瓶"
        assert final_gold_val == success_count * 100
        if success_count == 5:
            assert final_bp_count == 0, "卖完了但背包还有剩余"

    @allure.title("竞态购买：100金币玩家同时买2次，只能成功1次")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_race_condition_exact_balance(self, base_url: str, db_check):
        """
        极限场景：金币刚好够买1次，并发2次请求
        验证后端是否有行级锁保护，防止重复扣款
        """
        player_id = create_player("race_exact", gold=100)
        token = get_token(player_id)
        headers = {"Authorization": f"Bearer {token}"}
        buy_url = f"{base_url}/api/buy"

        results = []

        def _buy():
            try:
                resp = requests.post(
                    buy_url,
                    json={"item_id": 1, "quantity": 1},
                    headers=headers,
                    timeout=5,
                )
                results.append(resp.status_code)
            except Exception:
                results.append(-1)

        # 同时发2个请求
        t1 = threading.Thread(target=_buy)
        t2 = threading.Thread(target=_buy)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        time.sleep(0.3)

        success_count = sum(1 for r in results if r == 200)
        final_gold = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
        final_gold_val = final_gold["gold"] if final_gold else 0
        final_bp = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (player_id, 1),
        )
        final_bp_count = final_bp["count"] if final_bp else 0

        allure.attach(
            f"成功次数: {success_count}\n最终金币: {final_gold_val}\n背包: {final_bp_count}\n"
            f"状态码: {results}",
            name="竞态结果",
            attachment_type=allure.attachment_type.TEXT,
        )

        # 只能成功1次，金币应为0
        assert success_count == 1, f"竞态失败！成功{success_count}次，预期1次"
        assert final_gold_val == 0, f"金币应为0，实际{final_gold_val}"
        assert final_bp_count == 1, f"背包应为1，实际{final_bp_count}"