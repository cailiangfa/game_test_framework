"""
tests/utils/factories.py
数据工厂 - 动态创建测试数据

★ 核心修改：
- create_player 返回 (player_id, username)，方便登录
- 新增 get_auth_headers，直接构造鉴权头（与后端 token_{player_id} 一致）
- 新增 get_item_price / get_player_gold / get_backpack_count / get_order_count
  统一返回 int，永不为 None
- 所有数据库操作统一使用 backend_module.get_db()
"""
from __future__ import annotations

import sqlite3

import backend.app as backend_module
from backend.app import _hash_password
from faker import Faker

faker = Faker("zh_CN")

_MAX_RETRIES = 3


def _get_app():
    return backend_module.app


# ==================== 创建型工厂 ====================

def create_player(
    username: str | None = None,
    password: str = "123",
    gold: int = 1000,
) -> tuple[int, str]:
    """
    创建测试用户，返回 (player_id, username)。

    - username 为空时自动用 Faker 生成
    - 密码使用 _hash_password 存储，与 app.py 一致
    - 用户名重复时自动重试（最多 3 次）
    """
    app = _get_app()

    for attempt in range(_MAX_RETRIES):
        if username is None or attempt > 0:
            actual_username = f"player_{faker.user_name()}_{faker.random_int(1000, 9999)}"
        else:
            actual_username = username

        try:
            with app.app_context():
                db = backend_module.get_db()
                db.execute(
                    "INSERT INTO players(username, password, gold) VALUES (?, ?, ?)",
                    (actual_username, _hash_password(password), gold),
                )
                db.commit()
                row = db.execute(
                    "SELECT id FROM players WHERE username=?", (actual_username,)
                ).fetchone()
                if row is None:
                    raise RuntimeError(f"创建用户失败: {actual_username}")
                return int(row["id"]), actual_username
        except sqlite3.IntegrityError:
            if attempt == _MAX_RETRIES - 1:
                raise RuntimeError(
                    f"创建用户失败：{_MAX_RETRIES} 次重试后用户名仍重复"
                ) from None
            continue

    raise RuntimeError("创建用户失败：未知错误")


def create_item(item_id: int, name: str | None = None, price: int = 100) -> None:
    """创建或覆盖道具"""
    if name is None:
        name = f"{faker.word()}药水"

    app = _get_app()
    with app.app_context():
        db = backend_module.get_db()
        db.execute(
            "INSERT OR REPLACE INTO items(id, name, price) VALUES (?, ?, ?)",
            (item_id, name, price),
        )
        db.commit()


def give_item_to_player(player_id: int, item_id: int, count: int = 1) -> None:
    """给玩家背包添加道具（支持重复调用叠加数量）"""
    app = _get_app()
    with app.app_context():
        db = backend_module.get_db()
        db.execute(
            "INSERT INTO backpack (player_id, item_id, count) VALUES (?, ?, ?) "
            "ON CONFLICT(player_id, item_id) DO UPDATE SET count = count + ?",
            (player_id, item_id, count, count),
        )
        db.commit()


def set_player_gold(player_id: int, gold: int) -> None:
    """直接设置玩家金币"""
    app = _get_app()
    with app.app_context():
        db = backend_module.get_db()
        db.execute("UPDATE players SET gold=? WHERE id=?", (gold, player_id))
        db.commit()


# ==================== 鉴权工具 ====================

def get_token(player_id: int) -> str:
    """构造测试 token（与后端 require_auth 的格式一致：token_{player_id}）"""
    return f"token_{player_id}"


def get_auth_headers(player_id: int) -> dict[str, str]:
    """直接构造鉴权 headers，无需走 /api/login（更快、更稳定）"""
    return {"Authorization": f"Bearer {get_token(player_id)}"}


# ==================== 查询型工厂 ====================

def get_item_price(db_check, *, item_id: int = 1) -> int:
    """查询道具价格，不存在返回 0"""
    row = db_check("SELECT price FROM items WHERE id=?", (item_id,))
    return int(row["price"]) if row else 0


def get_player_gold(db_check, *, player_id: int = 1) -> int:
    """查询玩家金币，不存在返回 0"""
    row = db_check("SELECT gold FROM players WHERE id=?", (player_id,))
    return int(row["gold"]) if row else 0


def get_backpack_count(db_check, *, player_id: int = 1, item_id: int = 1) -> int:
    """查询背包道具数量，不存在返回 0"""
    row = db_check(
        "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
        (player_id, item_id),
    )
    return int(row["count"]) if row else 0


def get_order_count(db_check, *, player_id: int = 1, status: str | None = None) -> int:
    """查询订单数量，status 为空则查全部"""
    if status:
        row = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=? AND status=?",
            (player_id, status),
        )
    else:
        row = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?",
            (player_id,),
        )
    return int(row["cnt"]) if row else 0


# ==================== 便捷工厂 ====================

def create_rich_player(gold: int = 10_000) -> tuple[int, str]:
    """创建土豪玩家"""
    return create_player(gold=gold)


def create_poor_player(gold: int = 0) -> tuple[int, str]:
    """创建穷玩家"""
    return create_player(gold=gold)
