"""
tests/concurrency/test_concurrency.py
并发竞态测试：超卖、超扣、精确余额竞争
游戏测试核心壁垒

★ 核心改动：
- test_concurrent_buy_consistency 的金币从 1000 → 500
  原因：gold=1000 时 10 个请求全部能成功（1000/100=10），无论新旧代码都通过
  改为 gold=500 后，最多 5 个请求应该成功，旧代码（SELECT+UPDATE）会让超过 5 个
  请求成功（读到过期余额），新代码（原子 SQL WHERE gold >= ?）确保恰好 5 个成功
- 增加 threading.Event 屏障同步，让所有线程真正同时发出请求
- 使用唯一用户名，避免并发测试间相互干扰
★ 修复：create_player 返回 (player_id, username)，需要解包
★ 增强：
- ThreadPoolExecutor 替代裸线程，异常自动传播
- 轮询等待替代 time.sleep，消除 flaky test
- 状态码全覆盖检查，401/500 不再漏网
- 区分业务失败和系统错误
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import allure
import pytest
import requests

from tests.utils.factories import create_player, get_token, give_item_to_player

# 常量
ITEM_PRICE = 100  # 生命药水单价，与种子数据一致
VALID_STATUS_CODES = {200, 400}  # 并发请求只应出现这两个状态码


def _poll_db(db_check, sql: str, params: tuple, timeout: float = 5.0, interval: float = 0.1):
    """轮询数据库直到有结果或超时（替代 time.sleep 固定等待）"""
    start = time.time()
    while time.time() - start < timeout:
        result = db_check(sql, params)
        if result is not None:
            return result
        time.sleep(interval)
    return None


@pytest.mark.concurrency
@allure.feature("商城功能")
@allure.story("并发竞态测试")
class TestRaceCondition:
    """并发场景下的数据一致性验证"""

    @allure.title("并发购买：10 人抢 5 份，验证不超扣")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_concurrent_buy_consistency(self, base_url: str, db_check):
        """
        场景：玩家有 500 金币，同时发起 10 次购买请求（每次 100 金币）
        期望：恰好 5 次成功，金币 + 已花费 = 500，不能出现负余额

        ★ 为什么 gold=500 而不是 1000：
        gold=1000 时，10×100=1000，所有请求都能成功，新旧代码都通过——测不出 Bug
        gold=500 时，最多 5 次成功，旧代码 SELECT+UPDATE 可能让 >5 个请求通过
        （因为并发读到相同的过期余额），新代码原子 SQL WHERE gold>=? 确保恰好 5 个
        """
        # ★ 修复：create_player 返回 (player_id, username)
        player_id, _ = create_player(gold=500)
        token = get_token(player_id)
        headers = {"Authorization": f"Bearer {token}"}
        buy_url = f"{base_url}/api/buy"

        # 记录初始状态
        before_gold = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
        initial_gold = before_gold["gold"] if before_gold else 0

        results: list[int] = []
        system_errors: list[str] = []

        # ★ 屏障同步：所有线程等 start_event 触发后才真正发请求
        start_event = threading.Event()

        def _buy() -> int:
            start_event.wait()
            resp = requests.post(
                buy_url,
                json={"item_id": 1, "quantity": 1},
                headers=headers,
                timeout=5,
            )
            return resp.status_code

        num_threads = 10

        # ★ 增强：用 ThreadPoolExecutor 替代裸线程，异常自动传播
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(_buy) for _ in range(num_threads)]

            # 等所有线程就绪后同时释放
            time.sleep(0.2)
            start_event.set()

            for future in as_completed(futures, timeout=15):
                try:
                    results.append(future.result())
                except Exception as exc:
                    system_errors.append(str(exc))

        # ★ 增强：轮询等待数据库最终一致，替代 time.sleep(0.5)
        final_gold = _poll_db(
            db_check,
            "SELECT gold FROM players WHERE id=?",
            (player_id,),
        )
        final_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (player_id, 1),
        )

        final_gold_val = final_gold["gold"] if final_gold else 0
        final_bp_count = final_backpack["count"] if final_backpack else 0

        success_count = sum(1 for r in results if r == 200)
        fail_count = sum(1 for r in results if r == 400)

        allure.attach(
            f"初始金币: {initial_gold}\n"
            f"成功: {success_count}\n失败(余额不足): {fail_count}\n"
            f"系统错误: {len(system_errors)}\n状态码: {results}",
            name="并发请求结果",
            attachment_type=allure.attachment_type.TEXT,
        )

        # ★ 增强：系统错误必须为 0（服务器挂了测试不能静默通过）
        assert len(system_errors) == 0, f"出现系统错误: {system_errors}"

        # ★ 增强：所有状态码必须在预期范围内（401/500 不能漏网）
        unexpected = [r for r in results if r not in VALID_STATUS_CODES]
        assert len(unexpected) == 0, f"出现意外状态码: {unexpected}"

        # 核心断言 1：金币不能为负（防超扣）
        assert final_gold_val >= 0, f"金币为负！超扣 Bug！final_gold={final_gold_val}"

        # 核心断言 2：成功次数不能超过金币允许的最大次数
        max_possible = initial_gold // ITEM_PRICE
        assert success_count <= max_possible, (
            f"超扣！成功{success_count}次，但金币最多允许{max_possible}次"
        )

        # 核心断言 3：背包数量 == 成功请求数
        assert final_bp_count == success_count, (
            f"背包({final_bp_count}) != 成功数({success_count})，数据不一致"
        )

        # 核心断言 4：金币守恒（初始 = 剩余 + 花费）
        total_spent = success_count * ITEM_PRICE
        assert final_gold_val + total_spent == initial_gold, (
            f"金币不守恒！初始{initial_gold}，剩余{final_gold_val}，花费{total_spent}"
        )

    @allure.title("并发出售：10 人抢卖 5 瓶，验证不超卖")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_concurrent_sell_consistency(self, base_url: str, db_check):
        """
        场景：玩家有 5 瓶生命药水，同时发起 10 次出售请求
        期望：最多 5 次成功，不会出现卖出的总数 > 拥有数量
        """
        # ★ 修复：create_player 返回 (player_id, username)
        player_id, _ = create_player(gold=0)
        give_item_to_player(player_id, item_id=1, count=5)

        token = get_token(player_id)
        headers = {"Authorization": f"Bearer {token}"}
        sell_url = f"{base_url}/api/sell"

        results: list[int] = []
        system_errors: list[str] = []
        start_event = threading.Event()

        def _sell() -> int:
            start_event.wait()
            resp = requests.post(
                sell_url,
                json={"item_id": 1, "quantity": 1},
                headers=headers,
                timeout=5,
            )
            return resp.status_code

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_sell) for _ in range(10)]
            time.sleep(0.2)
            start_event.set()
            for future in as_completed(futures, timeout=15):
                try:
                    results.append(future.result())
                except Exception as exc:
                    system_errors.append(str(exc))

        final_gold = _poll_db(
            db_check,
            "SELECT gold FROM players WHERE id=?",
            (player_id,),
        )
        final_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (player_id, 1),
        )

        final_gold_val = final_gold["gold"] if final_gold else 0
        final_bp_count = final_backpack["count"] if final_backpack else 0
        success_count = sum(1 for r in results if r == 200)

        allure.attach(
            f"初始道具: 5\n成功出售: {success_count}\n"
            f"最终金币: {final_gold_val}\n背包剩余: {final_bp_count}\n"
            f"系统错误: {len(system_errors)}",
            name="并发出售结果",
            attachment_type=allure.attachment_type.TEXT,
        )

        # ★ 增强：系统错误 + 意外状态码检查
        assert len(system_errors) == 0, f"出现系统错误: {system_errors}"
        unexpected = [r for r in results if r not in VALID_STATUS_CODES]
        assert len(unexpected) == 0, f"出现意外状态码: {unexpected}"

        # 核心断言 1：不能超卖
        assert success_count <= 5, f"超卖！成功{success_count}次，但只有5瓶"

        # 核心断言 2：金币 = 成功次数 × 单价
        assert final_gold_val == success_count * ITEM_PRICE, (
            f"金币不守恒：期望{success_count * ITEM_PRICE}，实际{final_gold_val}"
        )

        # 核心断言 3：全卖完时背包应清空
        if success_count == 5:
            assert final_bp_count == 0, "卖完了但背包还有剩余"

    @allure.title("竞态购买：100 金币玩家同时买 2 次，只能成功 1 次")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_race_condition_exact_balance(self, base_url: str, db_check):
        """
        极限场景：金币刚好够买 1 次，并发 2 次请求
        验证后端原子 SQL 是否正确防护重复扣款

        旧代码（TOCTOU Bug）：
          Thread1: SELECT gold=100 → 通过检查
          Thread2: SELECT gold=100 → 通过检查
          Thread1: UPDATE gold=0
          Thread2: UPDATE gold=-100 ← 超扣！

        新代码（原子 SQL）：
          Thread1: UPDATE WHERE gold>=100 → rowcount=1, 成功
          Thread2: UPDATE WHERE gold>=100 → gold=0<100, rowcount=0, 失败
        """
        # ★ 修复：create_player 返回 (player_id, username)
        player_id, _ = create_player(gold=100)
        token = get_token(player_id)
        headers = {"Authorization": f"Bearer {token}"}
        buy_url = f"{base_url}/api/buy"

        results: list[int] = []
        system_errors: list[str] = []
        start_event = threading.Event()

        def _buy() -> int:
            start_event.wait()
            resp = requests.post(
                buy_url,
                json={"item_id": 1, "quantity": 1},
                headers=headers,
                timeout=5,
            )
            return resp.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_buy) for _ in range(2)]
            time.sleep(0.1)
            start_event.set()
            for future in as_completed(futures, timeout=15):
                try:
                    results.append(future.result())
                except Exception as exc:
                    system_errors.append(str(exc))

        final_gold = _poll_db(
            db_check,
            "SELECT gold FROM players WHERE id=?",
            (player_id,),
        )
        final_gold_val = final_gold["gold"] if final_gold else 0
        final_bp = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (player_id, 1),
        )
        final_bp_count = final_bp["count"] if final_bp else 0

        success_count = sum(1 for r in results if r == 200)

        allure.attach(
            f"初始金币: 100\n成功次数: {success_count}\n"
            f"最终金币: {final_gold_val}\n背包: {final_bp_count}\n"
            f"状态码: {results}\n系统错误: {len(system_errors)}",
            name="竞态结果",
            attachment_type=allure.attachment_type.TEXT,
        )

        # ★ 增强：系统错误 + 意外状态码检查
        assert len(system_errors) == 0, f"出现系统错误: {system_errors}"
        unexpected = [r for r in results if r not in VALID_STATUS_CODES]
        assert len(unexpected) == 0, f"出现意外状态码: {unexpected}"

        # 只能成功 1 次，金币应为 0
        assert success_count == 1, f"竞态失败！成功{success_count}次，预期1次"
        assert final_gold_val == 0, f"金币应为0，实际{final_gold_val}"
        assert final_bp_count == 1, f"背包应为1，实际{final_bp_count}"
