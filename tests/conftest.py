import os
import sys
import pytest
from pathlib import Path

# ===== 路径配置 =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_DB_PATH = str(PROJECT_ROOT / 'tests' / 'test.db')

# 必须在导入 backend 之前设置，确保它连的是测试库
os.environ['GAME_DB'] = TEST_DB_PATH

sys.path.insert(0, str(PROJECT_ROOT))
import backend.app as backend


# ===== Session 级：建表 + 种子数据（只跑一次）=====
@pytest.fixture(scope="session")
def app():
    backend.app.config['TESTING'] = True
    # 整个测试会话只初始化一次数据库（建表+种子数据）
    backend.init_db()
    return backend.app


# ===== Function 级：重置业务数据（不删表，走 Flask 通道）=====
@pytest.fixture(autouse=True)
def _reset_data(app):
    """
    每个测试函数执行前，重置业务数据到初始状态。
    不 DROP 表，只 DELETE 数据 + 重置种子数据。
    走 Flask 的 app_context，保证和接口用同一个连接。
    """
    with app.app_context():
        db = backend.get_db()
        # 1. 清空业务数据（按外键依赖顺序，子表先清）
        db.execute("DELETE FROM orders")
        db.execute("DELETE FROM backpack")
        # 2. 重置玩家数据（不是删了再插，而是 UPDATE 回初始值）
        db.execute("UPDATE players SET gold = 1000 WHERE id = 1")
        # 3. 确保种子道具数据完整（防止有人误删）
        #    用 INSERT OR IGNORE 保证已有数据不会被重复插入
        db.execute("INSERT OR IGNORE INTO items (id, name, price) VALUES (1, '生命药水', 100)")
        db.execute("INSERT OR IGNORE INTO items (id, name, price) VALUES (2, '魔法药水', 200)")
        db.commit()
    yield
    # yield 之后无需额外清理，下次 _reset_data 会再次重置


# ===== Session 级清理：测试结束后删除临时数据库文件 =====
@pytest.fixture(scope="session", autouse=True)
def _cleanup_db():
    yield
    try:
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
    except OSError:
        pass


# ===== 数据库直查（走 Flask 通道，保证数据一致）=====
@pytest.fixture
def db_check(app):
    def _check(sql, params=()):
        with app.app_context():
            db = backend.get_db()
            cur = db.execute(sql, params)
            return cur.fetchone()
    return _check


# ===== 数据库写入（用于构造特殊测试数据）=====
@pytest.fixture
def db_exec(app):
    def _exec(sql, params=()):
        with app.app_context():
            db = backend.get_db()
            db.execute(sql, params)
            db.commit()
    return _exec


# ===== Flask 测试客户端 =====
@pytest.fixture
def client(app):
    with app.test_client() as client:
        yield client


# ===== 登录态 headers =====
@pytest.fixture
def logged_headers(client):
    resp = client.post('/api/login', json={'username': 'player1', 'password': '123'})
    assert resp.status_code == 200, f"登录失败: {resp.get_json()}"
    token = resp.get_json()['token']
    return {'Authorization': f'Bearer {token}'}


# ===== 快捷查金币（工厂模式）=====
@pytest.fixture
def get_gold(client, logged_headers):
    def _get():
        resp = client.get('/api/gold', headers=logged_headers)
        return resp.get_json()['gold']
    return _get

# ===== Playwright 浏览器 Fixture =====
import threading
import socket
import time
from playwright.sync_api import sync_playwright


def _get_free_port():
    """获取一个空闲端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url(app):
    """启动真实的 Flask 服务器，供 Playwright 通过 HTTP 访问"""
    from werkzeug.serving import make_server

    port = _get_free_port()
    server = make_server("127.0.0.1", port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)  # 等待服务器就绪

    yield f"http://127.0.0.1:{port}"

    server.shutdown()


@pytest.fixture(scope="session")
def browser():
    """整个测试会话只启动一次浏览器"""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser, base_url):
    """每个测试用例独立页面，保证隔离"""
    context = browser.new_context()
    pg = context.new_page()
    yield pg
    context.close()
