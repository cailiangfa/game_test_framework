"""
并发竞态测试：验证购买/出售在并发场景下的数据一致性
这是游戏测试的核心关注点：超卖、超扣、重复支付
"""

from __future__ import annotations

import threading
import time

import allure
import requests

from tests.utils.factories import create_player, get_token


@allure.feature("商城功能")
@allure.story("并发竞态测试")
class TestRaceCondition:
    """并发场景下的数据一致性验证"""

    @allure.title("并发购买：10 人同时购买，验证不超扣/不超卖")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_concurrent_buy_consistency(self, base_url: str, db_check):
        """
        场景：玩家有 1000 金币，同时发起 10 次购买请求（每次买 1 瓶生命药水，100 金币）
        期望：只有 10 次请求中的前 10 瓶能成功（金币够），或者因为锁机制只成功部分
        关键：最终金币 + 已花费 = 初始金币（1000），不能出现负余额
        """
        # 创建独立玩家，避免干扰其他测试
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

        # 10 个线程同时购买
        threads = [threading.Thread(target=_buy) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 等待 SQLite WAL 写入完成（给后端一点时间落盘）
        time.sleep(0.5)

        # 统计结果
        success_count = sum(1 for r in results if r == 200)
        fail_count = len(results) - success_count

        allure.attach(
            f"成功: {success_count}\n失败: {fail_count}\n异常: {len(errors)}\n"
            f"详细状态码: {results}",
            name="并发请求结果",
            attachment_type=allure.attachment_type.TEXT,
        )

        # 数据库断言：最终金币必须 >= 0，且背包数量 == 成功次数
        final_gold = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
        final_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (player_id, 1),
        )

        final_gold_val = final_gold["gold"] if final_gold else 0
        final_bp_count = final_backpack["count"] if final_backpack else 0

        allure.attach(
            f"最终金币: {final_gold_val}\n背包数量: {final_bp_count}",
            name="数据库最终状态",
            attachment_type=allure.attachment_type.TEXT,
        )

        # 核心断言 1：金币不能为负（超扣是致命 Bug）
        assert final_gold_val >= 0, f"金币为负！超扣 Bug！final_gold={final_gold_val}"

        # 核心断言 2：背包数量 == 成功请求数（不能多给道具）
        assert final_bp_count == success_count, (
            f"背包数量({final_bp_count}) != 成功请求数({success_count})，"
            f"可能超卖或丢失"
        )

        # 核心断言 3：金币 + 花费 == 初始金币（1000）
        total_spent = success_count * 100  # 生命药水 100 金币
        assert final_gold_val + total_spent == 1000, (
            f"金币不一致！初始1000，最终{final_gold_val}，花费{total_spent}，"
            f"差额={1000 - final_gold_val - total_spent}"
        )

        # 记录：如果成功次数 > 10，说明没有锁保护（预期会失败，用来展示 Bug）
        if success_count > 10:
            allure.attach(
                "警告：并发购买成功次数超过预期，后端缺少行级锁保护",
                name="竞态条件发现",
                attachment_type=allure.attachment_type.TEXT,
            )

    @allure.title("并发出售：验证不出售超过拥有的数量")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_concurrent_sell_consistency(self, base_url: str, db_check):
        """
        场景：玩家有 5 瓶生命药水，同时发起 10 次出售请求（每次卖 1 瓶）
        期望：只有 5 次成功，金币增加 500，背包清零
        """
        # 创建玩家并直接给 5 瓶药水
        player_id = create_player("concurrent_seller", gold=0)
        from tests.utils.factories import give_item_to_player

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
            f"成功出售: {success_count}\n最终金币: {final_gold_val}\n"
            f"背包剩余: {final_bp_count}",
            name="并发出售结果",
            attachment_type=allure.attachment_type.TEXT,
        )

        # 断言：不能超卖（成功次数 <= 5）
        assert success_count <= 5, f"超卖！成功{success_count}次，但只有5瓶"

        # 断言：金币 = 成功次数 * 100
        assert final_gold_val == success_count * 100

        # 断言：如果卖完了，背包应该为空或 count=0
        if success_count == 5:
            assert final_bp_count == 0, "卖完了但背包还有剩余"
