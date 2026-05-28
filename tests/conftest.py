"""
企业级 Pytest Fixture 体系 - CI 修复版
修复点：
1. db_check 显式转 dict，避免 sqlite3.Row 在 CI 中的兼容问题
2. _seed_database 防御性补全 players/items，防止数据缺失
3. 强制 GAME_DB 环境变量，避免路径漂移
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Generator

import allure
import pytest
import sqlite3
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
from pydantic_settings import BaseSettings, SettingsConfigDict
from werkzeug.serving import make_server

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 强制绑定测试数据库路径，防止被 .env 或系统环境覆盖
TEST_DB_PATH = str(PROJECT_ROOT / "tests" / "test.db")
os.environ["GAME_DB"] = TEST_DB_PATH

import backend.app as backend_module  # noqa: E402


# ============================================================================
# 配置中心
# ============================================================================
class TestConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    game_db: str = TEST_DB_PATH
    host: str = "127.0.0.1"
    headless: bool = True
    browser_type: str = "chromium"


settings = TestConfig()


# ============================================================================
# Session 级：应用实例
# ============================================================================
@pytest.fixture(scope="session")
def app() -> Generator[Flask, None, None]:
    app_instance = backend_module.app
    app_instance.config.update(
        {
            "TESTING": True,
            "DATABASE": settings.game_db,
        }
    )
    backend_module.init_db()
    allure.attach(
        f"Database: {settings.game_db}\nTesting Mode: True",
        name="Test Environment",
        attachment_type=allure.attachment_type.TEXT,
    )
    yield app_instance


# ============================================================================
# Function 级：数据库重置
# ============================================================================
def _seed_database(db: sqlite3.Connection) -> None:
    """重置数据库到标准种子状态"""
    db.execute("DELETE FROM orders")
    db.execute("DELETE FROM backpack")
    db.execute("UPDATE players SET gold = 1000")

    # 防御性：确保道具存在
    db.execute(
        "INSERT OR IGNORE INTO items (id, name, price) VALUES (?, ?, ?)",
        (1, "生命药水", 100),
    )
    db.execute(
        "INSERT OR IGNORE INTO items (id, name, price) VALUES (?, ?, ?)",
        (2, "魔法药水", 200),
    )

    # 防御性：确保 5 个测试玩家存在（init_db 理论上已创建，这里兜底）
    for i in range(1, 6):
        db.execute(
            "INSERT OR IGNORE INTO players (id, username, password, gold) VALUES (?, ?, ?, ?)",
            (i, f"player{i}", "123", 1000),
        )
    db.commit()


@pytest.fixture(autouse=True)
def _reset_db(app: Flask) -> Generator[None, None, None]:
    """每个测试函数执行前重置数据库"""
    with app.app_context():
        db = backend_module.get_db()
        db.row_factory = sqlite3.Row
        _seed_database(db)
    yield


# ============================================================================
# Session 级清理
# ============================================================================
@pytest.fixture(scope="session", autouse=True)
def _cleanup_session() -> Generator[None, None, None]:
    yield
    try:
        if os.path.exists(settings.game_db):
            os.remove(settings.game_db)
            logging.info("Cleaned up test database: %s", settings.game_db)
    except OSError as exc:
        logging.warning("Failed to remove test db: %s", exc)


# ============================================================================
# 数据库直查 Fixture（修复：显式转 dict）
# ============================================================================
@pytest.fixture
def db_check(app: Flask) -> Callable[..., Any | None]:
    def _check(sql: str, params: tuple[Any, ...] = ()) -> Any | None:
        with app.app_context():
            db = backend_module.get_db()
            db.row_factory = sqlite3.Row
            cur = db.execute(sql, params)
            row = cur.fetchone()
            # 显式转 dict，避免 CI 中 sqlite3.Row 行为不一致
            return dict(row) if row else None
    return _check


@pytest.fixture
def db_exec(app: Flask) -> Callable[..., None]:
    def _exec(sql: str, params: tuple[Any, ...] = ()) -> None:
        with app.app_context():
            db = backend_module.get_db()
            db.execute(sql, params)
            db.commit()
    return _exec


# ============================================================================
# Flask 测试客户端
# ============================================================================
@pytest.fixture
def client(app: Flask) -> Generator[Any, None, None]:
    with app.test_client() as test_client:
        yield test_client


# ============================================================================
# 登录态 headers
# ============================================================================
@pytest.fixture
def logged_headers(client: Any) -> dict[str, str]:
    resp = client.post(
        "/api/login",
        json={"username": "player1", "password": "123"},
    )
    assert resp.status_code == 200, f"登录失败: {resp.get_json()}"
    token: str = resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def logged_headers_player2(client: Any) -> dict[str, str]:
    resp = client.post(
        "/api/login",
        json={"username": "player2", "password": "123"},
    )
    assert resp.status_code == 200
    token: str = resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# 快捷查金币
# ============================================================================
@pytest.fixture
def get_gold(client: Any, logged_headers: dict[str, str]) -> Callable[[], int]:
    def _get() -> int:
        resp = client.get("/api/gold", headers=logged_headers)
        data = resp.get_json()
        return data.get("gold", 0) if data else 0
    return _get


# ============================================================================
# Playwright 浏览器 Fixture
# ============================================================================
def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 10.0, interval: float = 0.1) -> None:
    import urllib.error
    import urllib.request

    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except urllib.error.HTTPError:
            return
        except urllib.error.URLError:
            time.sleep(interval)
    raise RuntimeError(f"Server failed to start within {timeout}s: {url}")


@pytest.fixture(scope="session")
def base_url(app: Flask) -> Generator[str, None, None]:
    port = _get_free_port()
    server = make_server(settings.host, port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://{settings.host}:{port}"
    _wait_for_server(url)

    yield url

    server.shutdown()


@pytest.fixture(scope="session")
def browser() -> Generator[Browser, None, None]:
    with sync_playwright() as p:
        launcher = getattr(p, settings.browser_type)
        browser_instance = launcher.launch(headless=settings.headless)
        yield browser_instance
        browser_instance.close()


# ============================================================================
# pytest hook：失败自动截图
# ============================================================================
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Generator[None, Any, None]:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture
def page(browser: Browser, base_url: str, request: pytest.FixtureRequest) -> Generator[Page, None, None]:
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    pg = context.new_page()
    yield pg

    failed = False
    if hasattr(request.node, "rep_call"):
        failed = request.node.rep_call.failed

    if failed:
        try:
            allure.attach(
                pg.screenshot(full_page=True),
                name="failure_screenshot",
                attachment_type=allure.attachment_type.PNG,
            )
        except Exception:
            pass

    context.close()


# ============================================================================
# Allure 环境信息
# ============================================================================
def pytest_sessionstart(session: pytest.Session) -> None:
    env_file = Path(settings.game_db).parent / "environment.properties"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(
        f"GameDB={settings.game_db}\n"
        f"Browser={settings.browser_type}\n"
        f"Headless={settings.headless}\n",
        encoding="utf-8",
    )


# ============================================================================
# API / Page Object Fixture
# ============================================================================
from tests.api.shop_api import ShopAPI  # noqa: E402


@pytest.fixture
def shop_api(client: Any, logged_headers: dict[str, str]) -> ShopAPI:
    return ShopAPI(client, logged_headers)


from tests.pages.shop_page import ShopPage  # noqa: E402


@pytest.fixture
def shop_page(page: Page, base_url: str) -> ShopPage:
    return ShopPage(page, base_url)