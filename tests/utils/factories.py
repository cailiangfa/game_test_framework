"""
数据工厂 - 动态创建测试数据
最终版：增加 Faker 随机生成，告别写死数据
"""
from __future__ import annotations

import backend.app as backend_module
from faker import Faker

faker = Faker("zh_CN")  # 中文数据，游戏测试更真实


def _get_app():
    return backend_module.app


def create_player(username: str | None = None, password: str = "123", gold: int = 1000) -> int:
    """创建测试用户，返回 player_id。username 为空时自动生成"""
    if username is None:
        username = f"player_{faker.user_name()}_{faker.random_int(1000, 9999)}"

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


def create_item(item_id: int, name: str | None = None, price: int = 100) -> None:
    """创建或覆盖道具。name 为空时自动生成"""
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
    """直接设置玩家金币（用于边界测试）"""
    app = _get_app()
    with app.app_context():
        db = backend_module.get_db()
        db.execute("UPDATE players SET gold=? WHERE id=?", (gold, player_id))
        db.commit()


def get_token(player_id: int) -> str:
    """构造测试 token"""
    return f"token_{player_id}"


def create_rich_player(gold: int = 10_000) -> int:
    """创建土豪玩家（默认1万金币）"""
    return create_player(gold=gold)


def create_poor_player(gold: int = 0) -> int:
    """创建穷玩家（默认0金币）"""
    return create_player(gold=gold)