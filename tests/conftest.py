"""
tests/conftest.py
最终版：修复循环导入 + Playwright Trace + 统一配置
"""
from __future__ import annotations

import logging
import os
import socket
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Generator

import allure
import pytest
from playwright.sync_api import Browser, Page, sync_playwright
from werkzeug.serving import make_server

if TYPE_CHECKING:
    from flask import Flask

# 统一配置中心
from config import settings  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 强制绑定测试数据库
os.environ["GAME_DB"] = settings.game_db

import backend.app as backend_module  # noqa: E402


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
        f"Database: {settings.game_db}\nEnv: {settings.test_env}",
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
    db.execute("DELETE FROM players WHERE id > 5")

    db.execute(
        "UPDATE items SET name = CASE id WHEN 1 THEN '生命药水' WHEN 2 THEN '魔法药水' END, "
        "price = CASE id WHEN 1 THEN 100 WHEN 2 THEN 200 END "
        "WHERE id IN (1, 2)"
    )
    db.execute("UPDATE players SET gold = 1000, password = '123' WHERE id <= 5")

    db.execute(
        "INSERT OR IGNORE INTO items (id, name, price) VALUES (?, ?, ?)",
        (1, "生命药水", 100),
    )
    db.execute(
        "INSERT OR IGNORE INTO items (id, name, price) VALUES (?, ?, ?)",
        (2, "魔法药水", 200),
    )
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
# 数据库直查 Fixture
# ============================================================================
@pytest.fixture
def db_check(app: Flask) -> Callable[..., Any | None]:
    def _check(sql: str, params: tuple[Any, ...] = ()) -> Any | None:
        with app.app_context():
            db = backend_module.get_db()
            db.row_factory = sqlite3.Row
            cur = db.execute(sql, params)
            row = cur.fetchone()
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


@pytest.fixture
def auth_headers(client: Any) -> Callable[[str, str], dict[str, str]]:
    """动态登录任意用户"""

    def _login(username: str, password: str = "123") -> dict[str, str]:
        resp = client.post(
            "/api/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200, f"登录失败: {resp.get_json()}"
        token: str = resp.get_json()["token"]
        return {"Authorization": f"Bearer {token}"}

    return _login


@pytest.fixture
def unique_username() -> Callable[[], str]:
    import uuid

    counter = 0

    def _gen() -> str:
        nonlocal counter
        counter += 1
        return f"u_{uuid.uuid4().hex[:6]}_{counter}"

    return _gen


@pytest.fixture
def get_gold(client: Any, logged_headers: dict[str, str]) -> Callable[[], int]:
    def _get() -> int:
        resp = client.get("/api/gold", headers=logged_headers)
        data = resp.get_json()
        return data.get("gold", 0) if data else 0

    return _get


# ============================================================================
# 真实 HTTP 服务器（UI + 并发测试用）
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


# ============================================================================
# Playwright 浏览器 Fixture（增强 Trace 录制）
# ============================================================================
@pytest.fixture(scope="session")
def browser(request: pytest.FixtureRequest) -> Generator[Browser, None, None]:
    use_headed = request.config.getoption("--headed", default=False)
    headless_mode = False if use_headed else settings.headless

    with sync_playwright() as p:
        launcher = getattr(p, settings.browser_type)
        browser_instance = launcher.launch(headless=headless_mode)
        yield browser_instance
        browser_instance.close()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[Any]
) -> Generator[None, Any, None]:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture
def page(
        browser: Browser, base_url: str, request: pytest.FixtureRequest
) -> Generator[Page, None, None]:
    # 1. 创建上下文（只保留正确的参数）
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        record_video_dir="videos/",
    )

    # 2. 开启 Trace 录制（截图 + DOM快照 + 网络 + 控制台）
    context.tracing.start(screenshots=True, snapshots=True, sources=True)

    pg = context.new_page()
    yield pg

    # 3. 判断用例是否失败
    failed = False
    if hasattr(request.node, "rep_call"):
        failed = request.node.rep_call.failed

    # 4. 保存 Trace 文件
    trace_dir = Path("test-results") / request.node.name.replace(":", "_")
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / "trace.zip"

    context.tracing.stop(path=str(trace_path))

    # 5. 失败时截图 + 附加 Trace 到 Allure
    if failed:
        try:
            allure.attach(
                pg.screenshot(full_page=True),
                name="failure_screenshot",
                attachment_type=allure.attachment_type.PNG,
            )
        except Exception:
            pass

        try:
            if trace_path.exists():
                allure.attach.file(
                    str(trace_path),
                    name="playwright_trace",
                    attachment_type=allure.attachment_type.ZIP,
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
        f"Headless={settings.headless}\n"
        f"TestEnv={settings.test_env}\n"
        f"CI={os.environ.get('CI', 'false')}\n",
        encoding="utf-8",
    )


# ============================================================================
# API / Page Object Fixture（延迟导入，避免循环导入）
# ============================================================================
@pytest.fixture
def shop_api(client: Any, logged_headers: dict[str, str]) -> Any:
    from tests.api.shop_api import ShopAPI

    return ShopAPI(client, logged_headers)


@pytest.fixture
def shop_page(page: Page, base_url: str) -> Any:
    from tests.pages.shop_page import ShopPage

    return ShopPage(page, base_url)