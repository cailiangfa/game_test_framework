"""
tests/performance/locustfile.py
性能测试最终版：自动启动后端 + 修复 Locust 2.x API
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from locust import HttpUser, between, events, task

# 自动启动后端服务（如果还没跑）
_backend_process = None


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    global _backend_process
    # 检查后端是否已在运行
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:5000/", timeout=1)
        print("[Locust] 后端服务已运行")
    except Exception:
        print("[Locust] 启动后端服务...")
        project_root = Path(__file__).resolve().parent.parent.parent
        _backend_process = subprocess.Popen(
            [sys.executable, str(project_root / "backend" / "app.py")],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # 等待后端启动
        for _ in range(30):
            time.sleep(0.5)
            try:
                urllib.request.urlopen("http://127.0.0.1:5000/", timeout=1)
                print("[Locust] 后端启动成功")
                break
            except Exception:
                pass


@events.quitting.add_listener
def on_locust_quitting(environment, **kwargs):
    global _backend_process
    if _backend_process:
        print("[Locust] 关闭后端服务...")
        _backend_process.terminate()
        _backend_process.wait()


class GameShopUser(HttpUser):
    wait_time = between(1, 3)
    host = "http://127.0.0.1:5000"

    def on_start(self):
        """每个用户开始时登录"""
        with self.client.post(
            "/api/login",
            json={"username": "player1", "password": "123"},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("token", "")
                resp.success()
            else:
                resp.failure(f"登录失败: {resp.status_code}")

    @task(3)
    def buy_item(self):
        with self.client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 1},
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"购买失败: {resp.status_code} - {resp.text}")

    @task(1)
    def get_gold(self):
        with self.client.get(
            "/api/gold",
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"查金币失败: {resp.status_code}")

    @task(1)
    def get_backpack(self):
        with self.client.get(
            "/api/backpack",
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"查背包失败: {resp.status_code}")