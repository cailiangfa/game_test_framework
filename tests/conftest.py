"""
tests/conftest.py
最终版：修复循环导入 + Playwright Trace + 统一配置

★ 核心修改：
- _seed_database 使用 _hash_password("123")，与 app.py 密码逻辑保持一致
- 移除了未使用的 shop_api_with_user fixture，保持简洁
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

from config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import backend.app as backend_module
from backend.app import _hash_password  # ★ 导入密码哈希函数


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

    # ★ 修复 P0：使用 _hash_password 生成密码，与 app.py / register 接口保持一致
    # 如果 app.py 切换为 bcrypt，此处自动适配哈希值
    db.execute("UPDATE players SET gold = 1000, password = ? WHERE id <= 5", (_hash_password("123"),))

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
            (i, f"player{i}", _hash_password("123"), 1000),  # ★ 此处也用 _hash_password
        )
    db.commit()


@pytest.fixture(autouse=True)
def _reset_db(app: Flask) -> Generator[None, None, None]:
    """
    每个测试函数执行前重置数据库。
    """
    with app.app_context():
        db = backend_module.get_db()
        db.row_factory = sqlite3.Row
        _seed_database(db)
    yield


# ============================================================================
# Session 级清理（连带删除 WAL 文件）
# ============================================================================
@pytest.fixture(scope="session", autouse=True)
def _cleanup_session() -> Generator[None, None, None]:
    yield
    try:
        db_path = backend_module.app.config.get("DATABASE", settings.game_db)
        for suffix in ["", "-shm", "-wal"]:
            f = db_path + suffix
            if os.path.exists(f):
                os.remove(f)
                logging.info("Cleaned up test database file: %s", f)
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
def auth_headers(client: Any) -> Callable[[str, str], dict[str, str]]:
    """动态登录任意用户（通过 /api/login 获取 token）"""

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
def logged_headers(auth_headers) -> dict[str, str]:
    """默认登录 player1"""
    return auth_headers("player1", "123")


@pytest.fixture
def logged_headers_player2(auth_headers) -> dict[str, str]:
    """登录 player2"""
    return auth_headers("player2", "123")


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
# Playwright 浏览器 Fixture
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
    context = browser.new_context(
        base_url=base_url,
        viewport={"width": 1280, "height": 720},
        record_video_dir="videos/" if settings.headless else None,
    )

    if settings.trace:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)

    pg = context.new_page()
    yield pg

    failed = False
    if hasattr(request.node, "rep_call"):
        failed = request.node.rep_call.failed

    trace_dir = Path("test-results") / request.node.name.replace(":", "_")
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / "trace.zip"

    if settings.trace:
        context.tracing.stop(path=str(trace_path))

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
    allure_results_dir = Path("allure-results")
    allure_results_dir.mkdir(parents=True, exist_ok=True)
    env_file = allure_results_dir / "environment.properties"
    env_file.write_text(
        f"GameDB={settings.game_db}\n"
        f"Browser={settings.browser_type}\n"
        f"Headless={settings.headless}\n"
        f"Trace={settings.trace}\n"
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
def shop_page(page: Page) -> Any:
    from tests.pages.shop_page import ShopPage
    return ShopPage(page)
