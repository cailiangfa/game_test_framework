import os
import sqlite3
from flask import Flask, request, jsonify, g

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev'

DATABASE = os.environ.get('GAME_DB', os.path.join(os.path.dirname(__file__), 'game.db'))

# ========== 外部支付验证服务（可被 Mock 拦截）==========
class ExternalPayment:
    """模拟：外部支付验证服务"""
    @staticmethod
    def verify(player_id, amount):
        """真实场景这会调用第三方支付API，这里默认返回通过"""
        return {"passed": True}

external_payment = ExternalPayment()

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db_dir = os.path.dirname(DATABASE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    with sqlite3.connect(DATABASE) as db:
        db.executescript("""
            DROP TABLE IF EXISTS players;
            DROP TABLE IF EXISTS items;
            DROP TABLE IF EXISTS backpack;
            DROP TABLE IF EXISTS orders;

            CREATE TABLE players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                gold INTEGER DEFAULT 1000
            );

            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price INTEGER NOT NULL
            );

            CREATE TABLE backpack (
                player_id INTEGER,
                item_id INTEGER,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (player_id, item_id),
                FOREIGN KEY (player_id) REFERENCES players(id),
                FOREIGN KEY (item_id) REFERENCES items(id)
            );

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                item_id INTEGER,
                quantity INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # ===== 插入初始道具 =====
        db.execute("INSERT OR IGNORE INTO items (id, name, price) VALUES (1, '生命药水', 100)")
        db.execute("INSERT OR IGNORE INTO items (id, name, price) VALUES (2, '魔法药水', 200)")

        # ===== 插入初始玩家 =====
        default_players = [
            ('player1', '123', 1000),
            ('player2', '123', 1000),
            ('player3', '123', 1000),
            ('player4', '123', 1000),
            ('player5', '123', 1000),
        ]
        for username, password, gold in default_players:
            db.execute(
                'INSERT OR IGNORE INTO players(username, password, gold) VALUES (?, ?, ?)',
                (username, password, gold)
            )

        db.commit()

# ========== 接口 ==========

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')
    db = get_db()
    user = db.execute(
        "SELECT * FROM players WHERE username=? AND password=?",
        (username, password)
    ).fetchone()
    if user:
        return jsonify({"token": f"token_{user['id']}"}), 200
    return jsonify({"error": "用户名或密码错误"}), 401

@app.route('/api/gold', methods=['GET'])
def get_gold():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token.startswith('token_'):
        return jsonify({"error": "未登录"}), 401
    try:
        player_id = int(token.split('_')[1])
    except (IndexError, ValueError):
        return jsonify({"error": "无效Token"}), 401

    db = get_db()
    user = db.execute("SELECT gold FROM players WHERE id=?", (player_id,)).fetchone()
    if not user:
        return jsonify({"error": "玩家不存在"}), 404
    return jsonify({"gold": user['gold']})

@app.route('/shop')
def shop():
    return """
    <!DOCTYPE html>
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
    </html>
    """


@app.route('/api/buy', methods=['POST'])  # 修复：加上中括号
def buy_item():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token.startswith('token_'):
        return jsonify({"error": "未登录"}), 401
    try:
        player_id = int(token.split('_')[1])  # 修复：加上中括号
    except (IndexError, ValueError):
        return jsonify({"error": "无效Token"}), 401

    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)

    if not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "数量必须为正整数"}), 400

    db = get_db()

    user = db.execute("SELECT gold FROM players WHERE id=?", (player_id,)).fetchone()
    if not user:
        return jsonify({"error": "玩家不存在"}), 404

    item = db.execute("SELECT price FROM items WHERE id=?", (item_id,)).fetchone()
    if not item:
        return jsonify({"error": "道具不存在"}), 404

    total_price = item['price'] * quantity  # 修复：加上中括号

    if user['gold'] < total_price:  # 修复：加上中括号
        return jsonify({"error": "余额不足"}), 400

    # ===== 调用外部支付验证（可被 Mock 拦截）=====
    # 优化：增加 try-except 兜底，防止外部服务异常导致接口 500 报错或事务中断
    try:
        verify_result = external_payment.verify(player_id, total_price)
        if not verify_result.get('passed', False):
            return jsonify({"error": f"支付验证失败: {verify_result.get('reason', '未知')}"}), 400
    except Exception as e:
        # 外部服务宕机、超时等异常，捕获后返回 500，保证接口不裸奔报错
        return jsonify({"error": f"支付服务异常: {str(e)}"}), 500

    # ===== 以下是原有的扣钱、加背包、生成订单逻辑 =====
    db.execute("UPDATE players SET gold = gold - ? WHERE id=?", (total_price, player_id))
    db.execute(
        "INSERT INTO backpack (player_id, item_id, count) VALUES (?, ?, ?) "
        "ON CONFLICT(player_id, item_id) DO UPDATE SET count = count + ?",
        (player_id, item_id, quantity, quantity)
    )
    db.execute(
        "INSERT INTO orders (player_id, item_id, quantity, amount) VALUES (?, ?, ?, ?)",
        (player_id, item_id, quantity, total_price)
    )
    db.commit()

    new_gold = db.execute("SELECT gold FROM players WHERE id=?", (player_id,)).fetchone()['gold'] # 修复：加上中括号
    return jsonify({"gold_remain": new_gold, "msg": "购买成功"}), 200



@app.route('/api/sell', methods=['POST'])
def sell_item():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token.startswith('token_'):
        return jsonify({"error": "未登录"}), 401
    try:
        player_id = int(token.split('_')[1])
    except (IndexError, ValueError):
        return jsonify({"error": "无效Token"}), 401

    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)

    if not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "数量必须为正整数"}), 400

    db = get_db()

    user = db.execute("SELECT gold FROM players WHERE id=?", (player_id,)).fetchone()
    if not user:
        return jsonify({"error": "玩家不存在"}), 404

    item = db.execute("SELECT price FROM items WHERE id=?", (item_id,)).fetchone()
    if not item:
        return jsonify({"error": "道具不存在"}), 404

    # ✅ 只有出售才需要检查背包里够不够
    backpack_row = db.execute(
        "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
        (player_id, item_id)
    ).fetchone()
    if not backpack_row or backpack_row['count'] < quantity:
        return jsonify({"error": "道具数量不足"}), 400

    total_income = item['price'] * quantity

    db.execute("UPDATE players SET gold = gold + ? WHERE id=?", (total_income, player_id))
    db.execute(
        "UPDATE backpack SET count = count - ? WHERE player_id=? AND item_id=?",
        (quantity, player_id, item_id)
    )
    db.execute(
        "DELETE FROM backpack WHERE player_id=? AND item_id=? AND count <= 0",
        (player_id, item_id)
    )
    db.execute(
        "INSERT INTO orders (player_id, item_id, quantity, amount, status) VALUES (?, ?, ?, ?, 'sold')",
        (player_id, item_id, quantity, total_income)
    )
    db.commit()

    new_gold = db.execute("SELECT gold FROM players WHERE id=?", (player_id,)).fetchone()['gold']
    return jsonify({"gold_remain": new_gold, "msg": "出售成功"}), 200


@app.route('/api/backpack', methods=['GET'])
def get_backpack():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token.startswith('token_'):
        return jsonify({"error": "未登录"}), 401
    try:
        player_id = int(token.split('_')[1])
    except (IndexError, ValueError):
        return jsonify({"error": "无效Token"}), 401

    db = get_db()
    items = db.execute("""
        SELECT b.item_id, i.name, b.count
        FROM backpack b JOIN items i ON b.item_id = i.id
        WHERE b.player_id=?
    """, (player_id,)).fetchall()
    return jsonify([dict(row) for row in items])

@app.route('/')
def index():
    return "<h1>游戏商城</h1>"

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)


def init_db():
    db_dir = os.path.dirname(DATABASE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        db.executescript("""
            DROP TABLE IF EXISTS players;
            DROP TABLE IF EXISTS items;
            DROP TABLE IF EXISTS backpack;
            DROP TABLE IF EXISTS orders;

            CREATE TABLE players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                gold INTEGER DEFAULT 1000
            );

            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price INTEGER NOT NULL
            );

            CREATE TABLE backpack (
                player_id INTEGER,
                item_id INTEGER,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (player_id, item_id),
                FOREIGN KEY (player_id) REFERENCES players(id),
                FOREIGN KEY (item_id) REFERENCES items(id)
            );

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                item_id INTEGER,
                quantity INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO players (id, username, password, gold) VALUES (1, 'player1', '123', 1000);
            INSERT INTO players (id, username, password, gold) VALUES (2, 'player2', '123', 1000);
            INSERT INTO players (id, username, password, gold) VALUES (3, 'player3', '123', 1000);
            INSERT INTO players (id, username, password, gold) VALUES (4, 'player4', '123', 1000);
            INSERT INTO players (id, username, password, gold) VALUES (5, 'player5', '123', 1000);
            INSERT INTO items (id, name, price) VALUES (1, '生命药水', 100);
            INSERT INTO items (id, name, price) VALUES (2, '魔法药水', 200);
        """)


# ========== 启动入口 ==========
if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

