import random

from locust import HttpUser, between, task


class GameShopUser(HttpUser):
    """模拟玩家：登录 → 查金币 → 买道具 → 卖道具"""

    wait_time = between(1, 3)

    def on_start(self):
        """每个虚拟用户启动时登录一次，随机选择一个测试账号"""
        # 从 5 个测试账号中随机选一个，避免所有用户操作同一个玩家
        player_num = random.randint(1, 5)
        username = f"player{player_num}"

        resp = self.client.post(
            "/api/login", json={"username": username, "password": "123"}
        )

        if resp.status_code == 200:
            self.token = resp.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            # 登录失败：标记自身为无效用户，后续任务跳过
            self.token = None
            self.headers = None

    def _is_ready(self):
        """检查用户是否登录成功"""
        if self.token is None:
            return False
        return True

    @task(3)
    def check_gold(self):
        """查金币：高频操作"""
        if not self._is_ready():
            return

        with self.client.get(
            "/api/gold", headers=self.headers, catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"查金币失败: HTTP {resp.status_code}")

    @task(2)
    def buy_item(self):
        """买道具：中频操作"""
        if not self._is_ready():
            return

        with self.client.post(
            "/api/buy",
            json={"item_id": 1, "quantity": 1},
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 400:
                # 业务拒绝（余额不足等）：不算服务器性能问题，标记为成功
                # 压测关注的是"服务器能否正常响应"，而不是"业务是否允许"
                resp.success()
            else:
                resp.failure(f"购买异常: HTTP {resp.status_code}")

    @task(1)
    def sell_item(self):
        """卖道具：低频操作"""
        if not self._is_ready():
            return

        with self.client.post(
            "/api/sell",
            json={"item_id": 1, "quantity": 1},
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 400:
                # 业务拒绝（背包里没有道具等）：不算服务器性能问题
                resp.success()
            else:
                resp.failure(f"出售异常: HTTP {resp.status_code}")
