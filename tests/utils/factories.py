"""
数据工厂 - 动态创建测试数据，替代写死的 JSON 和固定用户
"""
from __future__ import annotations

import backend.app as backend_module


def _get_app():
    """获取 Flask 应用实例（用于创建应用上下文）"""
    return backend_module.app


def create_player(username: str, password: str = "123", gold: int = 1000) -> int:
    """创建测试用户，返回 player_id"""
    app = _get_app()
    with app.app_context():
        db = backend_module.get_db()
        db.execute(
            "INSERT INTO players(username, password, gold) VALUES (?, ?, ?)",
            (username, password, gold),
        )
        db.commit()
        row = db.execute("SELECT id FROM players WHERE username=?", (username,)).fetchone()
        if row is None:
            raise RuntimeError(f"创建用户失败: {username}")
        return int(row["id"])


def create_item(item_id: int, name: str, price: int) -> None:
    """创建或覆盖道具"""
    app = _get_app()
    with app.app_context():
        db = backend_module.get_db()
        db.execute(
            "INSERT OR REPLACE INTO items(id, name, price) VALUES (?, ?, ?)",
            (item_id, name, price),
        )
        db.commit()


def give_item_to_player(player_id: int, item_id: int, count: int = 1) -> None:
    """给玩家背包添加道具"""
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


def get_token(player_id: int) -> str:
    """获取测试 token（跳过登录接口，直接构造）"""
    return f"token_{player_id}"