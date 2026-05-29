"""
性能测试基线配置
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceBaseline:
    """
    性能基线

    注意：SQLite + Flask 单线程模式下，不要设太高的并发期望。
    这里的基线是为了"发现回归"，不是"对标生产数据库"。
    """

    # 响应时间（SQLite 本地文件，预期较快）
    p95_ms: int = 300  # SQLite 合理上限
    max_ms: int = 2000  # 容忍偶尔锁等待
    error_rate_pct: float = 1.0

    # 吞吐量（SQLite 写锁限制，单节点很难超过 50 RPS）
    rps_min: int = 20
    rps_target: int = 50

    # 错误率
    error_rate_pct: float = 1.0
    business_reject_rate_pct: float = 15.0  # 余额不足/道具不足，业务允许

    # 并发（SQLite 建议不超过 50 并发写）
    concurrent_users: int = 50
    spawn_rate: int = 5
    duration_sec: int = 180

    # 资源
    cpu_pct_max: float = 80.0
    memory_pct_max: float = 85.0


@dataclass(frozen=True)
class StepLoadProfile:
    """阶梯加压：适配 SQLite 的保守策略"""

    steps: list[tuple[int, int]] = None

    def __post_init__(self):
        if self.steps is None:
            # 保守阶梯：5→20→50，观察拐点
            object.__setattr__(
                self, 'steps',
                [(5, 60), (20, 60), (50, 120)]
            )


def get_baseline(env: str | None = None) -> PerformanceBaseline:
    env = env or os.getenv("PERF_ENV", "local")

    baselines = {
        "local": PerformanceBaseline(
            p95_ms=200,
            error_rate_pct=5.0,
            concurrent_users=20,
            duration_sec=60,
        ),
        "ci": PerformanceBaseline(
            p95_ms=100,
            error_rate_pct=1.0,
            concurrent_users=50,
            duration_sec=180,
        ),
    }

    return baselines.get(env, baselines["local"])


# 商品池
ITEMS_POOL = [
    {"item_id": 1, "name": "生命药水", "price": 100, "weight": 60},
    {"item_id": 2, "name": "魔法药水", "price": 200, "weight": 40},
]

ITEM_WEIGHTS = [item["weight"] for item in ITEMS_POOL]
ITEM_IDS = [item["item_id"] for item in ITEMS_POOL]