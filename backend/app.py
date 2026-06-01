"""
Game Shop Backend - 企业级重构版本
backend/app.py

★ 核心改动说明：
1. init_db() 从 app.config 读取数据库路径（修复测试模式路径不一致 Bug）
2. buy_item / sell_item 使用原子 SQL 防止并发竞态（TOCTOU 修复）
3. 添加显式事务管理（commit/rollback），防止异常导致脏数据
4. 添加 /api/health 健康检查端点
5. 添加 quantity 上限校验（防止整数溢出 / 恶意请求）
6. 预留 _hash_password 接口（生产环境用 bcrypt，测试简化版用明文）
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import sys
from functools import wraps
from typing import Any, Callable

from flask import Flask, g, jsonify, request

# ========== 应用配置 ==========
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
app.config["TESTING"] = False

DATABASE = os.environ.get("GAME_DB", os.path.join(os.path.dirname(__file__), "game.db"))

# 业务常量
MAX_QUANTITY = 10000  # 单次购买/出售数量上限（防止整数溢出和恶意请求）


# ========== 密码工具 ==========
def _hash_password(password: str) -> str:
    """
    密码哈希（测试简化版用 SHA-256，生产环境应用 bcrypt / argon2）

    设计取舍：测试项目使用明文比对以简化流程，但预留此接口
    以便生产环境无缝切换为：
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    验证时使用 bcrypt.checkpw() 而非直接比对。
    """
    # ★ 测试简化版：直接返回原文，配合 conftest 种子数据的明文密码
    # 生产环境应替换为：return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return password


def _verify_password(plain: str, stored: str) -> bool:
    """
    验证密码（测试简化版直接比对，生产环境用 bcrypt.checkpw）

    如果切换为 bcrypt，此处改为：
        return bcrypt.checkpw(plain.encode(), stored.encode())
    """
    # ★ 测试简化版：明文比对
    return plain == stored


# ========== 结构化日志配置 ==========
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
        }
        if hasattr(record, "extra"):
            log_obj.update(record.extra)
        return json.dumps(log_obj, ensure_ascii=False)


logger = logging.getLogger("game_shop")
logger.setLevel(logging.DEBUG)

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JSONFormatter())
logger.handlers = [_handler]


# ========== 外部支付验证服务 ==========
class ExternalPayment:
    """
    外部支付验证服务（测试简化版）
    生产环境会使用 JWT/OAuth + 签名 + 过期时间
    """

    @staticmethod
    def verify(player_id: int, amount: int) -> dict[str, Any]:
        logger.info(
            "Payment verify", extra={"player_id": player_id, "amount": amount}
        )
        return {"passed": True, "transaction_id": f"tx_{player_id}_{amount}"}


external_payment = ExternalPayment()


# ========== 数据库连接管理 ==========
def get_db() -> sqlite3.Connection:
    if app.config.get("TESTING") and hasattr(g, "_test_db"):
        return g._test_db

    if "db" not in g:
        db_path = app.config.get("DATABASE", DATABASE)
        g.db = sqlite3.connect(db_path, timeout=10.0)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def set_test_db(connection: sqlite3.Connection) -> None:
    """注入测试数据库连接（用于单元测试 Mock）"""
    g._test_db = connection


@app.teardown_appcontext
def close_db(exception: BaseException | None) -> None:
    db = g.pop("db", None)
    test_db = g.pop("_test_db", None)

    # 生产连接：每次请求后关闭
    if db is not None:
        db.close()
    # 测试注入连接：不关闭，由注入方（测试框架）管理生命周期
    # 原因：测试可能在请求后还需查询 DB 验证状态
    # if test_db is not None:
    #     test_db.close()


def init_db() -> None:
    """建表 + 初始数据（不会删表，重置逻辑由测试框架负责）"""
    db_path = app.config.get("DATABASE", DATABASE)
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                gold INTEGER DEFAULT 1000
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backpack (
                player_id INTEGER,
                item_id INTEGER,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (player_id, item_id),
                FOREIGN KEY (player_id) REFERENCES players(id),
                FOREIGN KEY (item_id) REFERENCES items(id)
            );

            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                item_id INTEGER,
                quantity INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        db.execute(
            "INSERT OR IGNORE INTO items (id, name, price) VALUES (?, ?, ?)",
            (1, "生命药水", 100),
        )
        db.execute(
            "INSERT OR IGNORE INTO items (id, name, price) VALUES (?, ?, ?)",
            (2, "魔法药水", 200),
        )

        # ★ 种子数据密码用 _hash_password 生成，与注册接口保持一致
        # 当前 _hash_password 返回明文，切换为 bcrypt 时种子数据自动使用哈希值
        default_players = [
            ("player1", _hash_password("123"), 1000),
            ("player2", _hash_password("123"), 1000),
            ("player3", _hash_password("123"), 1000),
            ("player4", _hash_password("123"), 1000),
            ("player5", _hash_password("123"), 1000),
        ]
        db.executemany(
            "INSERT OR IGNORE INTO players(username, password, gold) VALUES (?, ?, ?)",
            default_players,
        )
        db.commit()

    logger.info("Database initialized", extra={"path": db_path})


# ========== 统一鉴权装饰器 ==========
def require_auth(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    鉴权装饰器（测试简化版：token 格式为 token_{player_id}）
    生产环境应使用 JWT / Session + 签名 + 过期时间
    """

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token.startswith("token_"):
            logger.warning("Auth failed: missing or invalid token format")
            return jsonify({"error": "未登录"}), 401

        try:
            player_id = int(token.split("_")[1])
        except (IndexError, ValueError):
            logger.warning("Auth failed: invalid token structure")
            return jsonify({"error": "无效Token"}), 401

        db = get_db()
        user = db.execute(
            "SELECT id FROM players WHERE id=?", (player_id,)
        ).fetchone()
        if not user:
            logger.warning(
                "Auth failed: player not found", extra={"player_id": player_id}
            )
            return jsonify({"error": "玩家不存在"}), 404

        return f(player_id=player_id, *args, **kwargs)

    return wrapper


# ========== 统一异常处理 ==========
@app.errorhandler(400)
def bad_request(error: Any) -> Any:
    logger.warning("Bad request", extra={"url": request.url, "error": str(error)})
    return jsonify({"error": "请求参数错误"}), 400


@app.errorhandler(500)
def internal_error(error: Any) -> Any:
    logger.error(
        "Internal server error", extra={"url": request.url, "error": str(error)}
    )
    return jsonify({"error": "服务器内部错误"}), 500


# ========== 请求日志中间件 ==========
@app.before_request
def log_request() -> None:
    if request.path.startswith("/api/"):
        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.path,
                "remote_addr": request.remote_addr,
            },
        )


@app.after_request
def log_response(response: Any) -> Any:
    if request.path.startswith("/api/"):
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
            },
        )
    return response


# ========== Service 层 ==========
class GameService:
    """游戏业务逻辑层"""

    @staticmethod
    def get_player_gold(player_id: int) -> int:
        db = get_db()
        row = db.execute(
            "SELECT gold FROM players WHERE id=?", (player_id,)
        ).fetchone()
        if not row:
            raise ValueError("玩家不存在")
        return int(row["gold"])

    @staticmethod
    def get_item_price(item_id: int) -> int:
        db = get_db()
        row = db.execute(
            "SELECT price FROM items WHERE id=?", (item_id,)
        ).fetchone()
        if not row:
            raise ValueError("道具不存在")
        return int(row["price"])

    @staticmethod
    def buy_item(player_id: int, item_id: int, quantity: int) -> dict[str, Any]:
        """购买道具（原子操作，防止并发竞态）"""
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("数量必须为正整数")

        # ★ 新增：数量上限校验（防止整数溢出和恶意请求）
        if quantity > MAX_QUANTITY:
            raise ValueError(f"单次购买数量不能超过{MAX_QUANTITY}")

        db = get_db()
        price = GameService.get_item_price(item_id)
        total = price * quantity

        # 先调用外部支付（在修改数据库之前）
        try:
            verify_result = external_payment.verify(player_id, total)
        except Exception as exc:
            logger.error(
                "Payment service error",
                extra={"error": str(exc), "player_id": player_id},
            )
            raise RuntimeError(f"支付服务异常: {exc}") from exc

        if not verify_result.get("passed", False):
            reason = verify_result.get("reason", "未知")
            raise ValueError(f"支付验证失败: {reason}")

        # 原子扣款 + 背包更新 + 订单生成
        try:
            cursor = db.execute(
                "UPDATE players SET gold = gold - ? WHERE id=? AND gold >= ?",
                (total, player_id, total),
            )
            if cursor.rowcount == 0:
                player = db.execute(
                    "SELECT gold FROM players WHERE id=?", (player_id,)
                ).fetchone()
                if not player:
                    raise ValueError("玩家不存在")
                raise ValueError("余额不足")

            db.execute(
                "INSERT INTO backpack (player_id, item_id, count) VALUES (?, ?, ?) "
                "ON CONFLICT(player_id, item_id) DO UPDATE SET count = count + ?",
                (player_id, item_id, quantity, quantity),
            )
            db.execute(
                "INSERT INTO orders (player_id, item_id, quantity, amount) VALUES (?, ?, ?, ?)",
                (player_id, item_id, quantity, total),
            )
            db.commit()
        except ValueError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            logger.error(
                "Buy transaction failed",
                extra={"error": str(exc), "player_id": player_id},
            )
            raise RuntimeError(f"购买失败: {exc}") from exc

        new_gold = GameService.get_player_gold(player_id)
        logger.info(
            "Item purchased",
            extra={
                "player_id": player_id,
                "item_id": item_id,
                "quantity": quantity,
                "cost": total,
            },
        )
        return {"gold_remain": new_gold, "msg": "购买成功"}

    @staticmethod
    def sell_item(player_id: int, item_id: int, quantity: int) -> dict[str, Any]:
        """出售道具（原子操作，防止并发超卖）"""
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("数量必须为正整数")

        # ★ 新增：数量上限校验
        if quantity > MAX_QUANTITY:
            raise ValueError(f"单次出售数量不能超过{MAX_QUANTITY}")

        db = get_db()
        price = GameService.get_item_price(item_id)
        total = price * quantity

        try:
            cursor = db.execute(
                "UPDATE backpack SET count = count - ? "
                "WHERE player_id=? AND item_id=? AND count >= ?",
                (quantity, player_id, item_id, quantity),
            )
            if cursor.rowcount == 0:
                raise ValueError("道具数量不足")

            db.execute(
                "DELETE FROM backpack WHERE player_id=? AND item_id=? AND count <= 0",
                (player_id, item_id),
            )

            db.execute(
                "UPDATE players SET gold = gold + ? WHERE id=?", (total, player_id)
            )
            db.execute(
                "INSERT INTO orders (player_id, item_id, quantity, amount, status) "
                "VALUES (?, ?, ?, ?, 'sold')",
                (player_id, item_id, quantity, total),
            )
            db.commit()
        except ValueError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            logger.error(
                "Sell transaction failed",
                extra={"error": str(exc), "player_id": player_id},
            )
            raise RuntimeError(f"出售失败: {exc}") from exc

        new_gold = GameService.get_player_gold(player_id)
        logger.info(
            "Item sold",
            extra={
                "player_id": player_id,
                "item_id": item_id,
                "quantity": quantity,
                "income": total,
            },
        )
        return {"gold_remain": new_gold, "msg": "出售成功"}

    @staticmethod
    def get_backpack(player_id: int) -> list[dict[str, Any]]:
        db = get_db()
        rows = db.execute(
            """
            SELECT b.item_id, i.name, b.count
            FROM backpack b JOIN items i ON b.item_id = i.id
            WHERE b.player_id=?
            """,
            (player_id,),
        ).fetchall()
        return [dict(row) for row in rows]


# ========== HTTP 接口层 ==========


@app.route("/api/health", methods=["GET"])
def health() -> Any:
    """健康检查端点（用于 CI/测试等待服务启动）"""
    try:
        db = get_db()
        db.execute("SELECT 1").fetchone()
        return jsonify({"status": "healthy", "db": "connected"}), 200
    except Exception as exc:
        return jsonify({"status": "unhealthy", "error": str(exc)}), 500


@app.route("/api/register", methods=["POST"])
def register() -> Any:
    """用户注册（压测专用：动态创建独立用户）"""
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    db = get_db()
    try:
        # ★ 密码使用 _hash_password 存储，与 init_db 种子数据一致
        db.execute(
            "INSERT INTO players(username, password, gold) VALUES (?, ?, ?)",
            (username, _hash_password(password), 10000),
        )
        db.commit()
        logger.info("User registered", extra={"username": username})
        return jsonify({"msg": "注册成功"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "用户名已存在"}), 409


@app.route("/api/login", methods=["POST"])
def login() -> Any:
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    db = get_db()
    user = db.execute(
        "SELECT id, password FROM players WHERE username=?",
        (username,),
    ).fetchone()

    # ★ 使用 _verify_password 验证，而非直接比对
    if not user or not _verify_password(password, user["password"]):
        logger.warning("Login failed", extra={"username": username})
        return jsonify({"error": "用户名或密码错误"}), 401

    logger.info(
        "Login success", extra={"player_id": user["id"], "username": username}
    )
    return jsonify({"token": f"token_{user['id']}"}), 200


@app.route("/api/gold", methods=["GET"])
@require_auth
def get_gold(player_id: int) -> Any:
    try:
        gold = GameService.get_player_gold(player_id)
        return jsonify({"gold": gold})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/api/buy", methods=["POST"])
@require_auth
def buy_item(player_id: int) -> Any:
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id")
    quantity = data.get("quantity", 1)

    if item_id is None:
        return jsonify({"error": "缺少 item_id"}), 400
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return jsonify({"error": "item_id 必须是整数"}), 400

    try:
        result = GameService.buy_item(player_id, item_id, quantity)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/sell", methods=["POST"])
@require_auth
def sell_item(player_id: int) -> Any:
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id")
    quantity = data.get("quantity", 1)

    if item_id is None:
        return jsonify({"error": "缺少 item_id"}), 400
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return jsonify({"error": "item_id 必须是整数"}), 400

    try:
        result = GameService.sell_item(player_id, item_id, quantity)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/backpack", methods=["GET"])
@require_auth
def get_backpack(player_id: int) -> Any:
    items = GameService.get_backpack(player_id)
    return jsonify(items)


@app.route("/shop")
def shop() -> str:
    return """<!DOCTYPE html>
    <html>
    <head><title>游戏商城</title></head>
    <body>
        <h1>游戏商城</h1>
        <div id="player-gold">金币: <span id="gold-amount">加载中...</span></div>
        <div>
            <h3>生命药水 (100金币)</h3>
            <input id="quantity-1" type="number" value="1" min="1">
            <button onclick="buy(1)">购买</button>
        </div>
        <div>
            <h3>魔法药水 (200金币)</h3>
            <input id="quantity-2" type="number" value="1" min="1">
            <button onclick="buy(2)">购买</button>
        </div>
        <div id="message" style="color: red;"></div>
        <script>
            async function login() {
                const resp = await fetch('/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: 'player1', password: '123'})
                });
                const data = await resp.json();
                window.token = data.token;
                loadGold();
            }
            async function loadGold() {
                const resp = await fetch('/api/gold', {
                    headers: {'Authorization': 'Bearer ' + window.token}
                });
                const data = await resp.json();
                document.getElementById('gold-amount').textContent = data.gold;
            }
            async function buy(itemId) {
                const qty = parseInt(document.getElementById('quantity-' + itemId).value);
                const resp = await fetch('/api/buy', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + window.token
                    },
                    body: JSON.stringify({item_id: itemId, quantity: qty})
                });
                const data = await resp.json();
                const msgDiv = document.getElementById('message');
                if (resp.ok) {
                    msgDiv.textContent = data.msg + '，剩余金币: ' + data.gold_remain;
                    loadGold();
                } else {
                    msgDiv.textContent = '错误: ' + data.error;
                }
            }
            login();
        </script>
    </body>
    </html>"""


@app.route("/")
def index() -> str:
    return "<h1>游戏商城</h1>"


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
