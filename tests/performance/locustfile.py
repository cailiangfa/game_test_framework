"""
工程级 Locust 压测脚本
适配后端：SQLite + Flask 单线程，有注册接口
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path

from locust import HttpUser, between, events, task
from locust.runners import MasterRunner

from tests.performance.config import (ITEM_IDS, ITEM_WEIGHTS, StepLoadProfile,
                                      get_baseline)

BASELINE = get_baseline()


# ============ 阶梯加压 ============
class StepLoadShape:
    profile = StepLoadProfile()

    def tick(self):
        run_time = self.get_run_time()
        elapsed = 0
        for users, duration in self.profile.steps:
            if run_time < elapsed + duration:
                return (users, BASELINE.spawn_rate)
            elapsed += duration
        return None


# ============ 基线判定 ============
@events.request.add_listener
def on_request(
    request_type,
    name,
    response_time,
    response_length,
    response,
    context,
    exception,
    **kwargs,
):
    if response_time > BASELINE.max_ms and response is not None:
        response.failure(f"绝对超时: {response_time}ms > {BASELINE.max_ms}ms")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    if isinstance(environment.runner, MasterRunner):
        return

    stats = environment.runner.stats
    total = stats.total

    p95 = total.get_response_time_percentile(0.95)
    error_rate = (
        (total.num_failures / total.num_requests * 100) if total.num_requests else 0
    )

    passed = error_rate <= BASELINE.error_rate_pct and p95 <= BASELINE.p95_ms

    print("\n" + "=" * 60)
    print("性能基线判定")
    print("=" * 60)
    print(f"总请求: {total.num_requests} | 失败: {total.num_failures}")
    print(f"错误率: {error_rate:.2f}% (基线 ≤{BASELINE.error_rate_pct}%)")
    print(f"P95: {p95:.0f}ms (基线 ≤{BASELINE.p95_ms}ms)")
    print(f"结果: {'✅ PASS' if passed else '❌ FAIL'}")
    print("=" * 60)

    # 写入报告
    Path("locust-reports").mkdir(exist_ok=True)
    with open("locust-reports/baseline.json", "w") as f:
        json.dump(
            {
                "passed": passed,
                "total_requests": total.num_requests,
                "error_rate_pct": round(error_rate, 2),
                "p95_ms": round(p95, 2),
            },
            f,
            indent=2,
        )


# ============ 用户模型 ============
class GameShopUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """每个虚拟用户：注册 → 登录 → 拿到独立 token"""
        # 生成唯一用户名，避免冲突
        self.username = f"perf_{uuid.uuid4().hex[:8]}"
        self.password = "perf123"

        # 注册（忽略已存在错误）
        self.client.post(
            "/api/register",
            json={"username": self.username, "password": self.password},
            catch_response=True,
        )

        # 登录
        resp = self.client.post(
            "/api/login",
            json={
                "username": self.username,
                "password": self.password,
            },
        )

        if resp.status_code == 200:
            self.token = resp.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = None

    def _check_ready(self) -> bool:
        return self.token is not None

    def _random_item(self) -> int:
        return random.choices(ITEM_IDS, weights=ITEM_WEIGHTS, k=1)[0]

    def _assert_ok(self, resp, required_keys: list[str] | None = None):
        """通用响应校验"""
        if resp.status_code != 200:
            return False

        try:
            data = resp.json()
        except json.JSONDecodeError:
            resp.failure("Invalid JSON")
            return False

        if "error" in data:
            resp.failure(f"Business error: {data['error']}")
            return False

        if required_keys:
            for key in required_keys:
                if key not in data:
                    resp.failure(f"Missing key: {key}")
                    return False

        return True

    @task(3)
    def check_gold(self):
        if not self._check_ready():
            return

        with self.client.get(
            "/api/gold", headers=self.headers, catch_response=True
        ) as resp:
            if self._assert_ok(resp, ["gold"]):
                resp.success()

    @task(2)
    def buy_item(self):
        if not self._check_ready():
            return

        item_id = self._random_item()

        with self.client.post(
            "/api/buy",
            json={"item_id": item_id, "quantity": 1},
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 400:
                # 业务拒绝：余额不足等，不算系统错误
                resp.success()
            elif self._assert_ok(resp, ["gold_remain", "msg"]):
                resp.success()

    @task(1)
    def sell_item(self):
        if not self._check_ready():
            return

        item_id = self._random_item()

        with self.client.post(
            "/api/sell",
            json={"item_id": item_id, "quantity": 1},
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 400:
                resp.success()
            elif self._assert_ok(resp, ["gold_remain", "msg"]):
                resp.success()
