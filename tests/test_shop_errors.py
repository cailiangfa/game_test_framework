import pytest
import allure

class TestBuyErrors:
    """购买接口异常测试"""

    # ---- 鉴权类 ----
    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_without_token(self, client):
        """未登录：不发Authorization，应返回401"""
        resp = client.post('/api/buy', json={'item_id': 1, 'quantity': 1})
        assert resp.status_code == 401
        assert '未登录' in resp.get_json()['error']

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_invalid_token_format(self, client):
        """无效Token：格式对但内容非法(token_abc)，触发ValueError，应返回401"""
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 1},
                           headers={'Authorization': 'Bearer token_abc'})
        assert resp.status_code == 401
        assert '无效Token' in resp.get_json()['error']

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_player_not_exist(self, client):
        """Token中玩家ID不存在(token_999)，应返回404"""
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 1},
                           headers={'Authorization': 'Bearer token_999'})
        assert resp.status_code == 404
        assert '玩家不存在' in resp.get_json()['error']

    # ---- 业务类 ----

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_insufficient_gold(self, client, logged_headers, db_check, get_gold):
        """余额不足：应返回400，且数据不变"""
        before_gold = get_gold()
        before_orders = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
        )['cnt']

        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 999},
                           headers=logged_headers)

        assert resp.status_code == 400
        assert '余额不足' in resp.get_json()['error']

        # 关键断言：数据不应有任何变化
        after_gold = get_gold()
        assert after_gold == before_gold

        after_orders = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
        )['cnt']
        assert after_orders == before_orders

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_item_not_exist(self, client, logged_headers):
        """道具不存在：应返回404"""
        resp = client.post('/api/buy',
                           json={'item_id': 999, 'quantity': 1},
                           headers=logged_headers)
        assert resp.status_code == 404
        assert '不存在' in resp.get_json()['error']

    # ---- 参数校验类 ----

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_zero_quantity(self, client, logged_headers):
        """数量为0：应返回400"""
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 0},
                           headers=logged_headers)
        assert resp.status_code == 400
        assert '正整数' in resp.get_json()['error']

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_negative_quantity(self, client, logged_headers):
        """数量为负数：应返回400"""
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': -5},
                           headers=logged_headers)
        assert resp.status_code == 400
        assert '正整数' in resp.get_json()['error']

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_float_quantity(self, client, logged_headers):
        """数量为浮点数：应返回400"""
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 1.5},
                           headers=logged_headers)
        assert resp.status_code == 400
        assert '正整数' in resp.get_json()['error']

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_missing_item_id(self, client, logged_headers):
        """缺少必填字段item_id：当前返回404道具不存在（接口设计待优化）"""
        resp = client.post('/api/buy',
                           json={'quantity': 1},
                           headers=logged_headers)
        # app.py 中 data.get('item_id') 返回 None，查不到道具 → 404
        assert resp.status_code == 404

    @allure.feature("购买功能")
    @allure.story("购买异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_buy_empty_body(self, client, logged_headers):
        """请求体为空：不发JSON，应不报500"""
        resp = client.post('/api/buy',
                           headers=logged_headers,
                           content_type='application/json')
        # get_json(silent=True) or {} 生效，不会500
        assert resp.status_code in (400, 401, 404)


class TestSellErrors:
    """出售接口异常测试"""

    @allure.feature("购买功能")
    @allure.story("销售异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_sell_insufficient_items(self, client, logged_headers, db_check, get_gold):
        """背包有道具但数量不足：先买2瓶再卖5瓶，应返回400"""
        # 前置：买2瓶生命药水
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 2},
                           headers=logged_headers)
        assert resp.status_code == 200, f"前置购买失败: {resp.get_json()}"

        before_gold = get_gold()
        before_orders = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
        )['cnt']

        # 尝试卖5瓶（只有2瓶）
        resp = client.post('/api/sell',
                           json={'item_id': 1, 'quantity': 5},
                           headers=logged_headers)

        assert resp.status_code == 400
        assert '不足' in resp.get_json()['error']

        # 数据不应有任何变化
        after_gold = get_gold()
        assert after_gold == before_gold

        after_orders = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
        )['cnt']
        assert after_orders == before_orders

    @allure.feature("购买功能")
    @allure.story("销售异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_sell_item_not_in_backpack(self, client, logged_headers):
        """出售从未拥有的道具：背包里根本没有，应返回400"""
        resp = client.post('/api/sell',
                           json={'item_id': 2, 'quantity': 1},
                           headers=logged_headers)
        assert resp.status_code == 400
        assert '不足' in resp.get_json()['error']

    @allure.feature("购买功能")
    @allure.story("销售异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_sell_without_token(self, client):
        """未登录出售：应返回401"""
        resp = client.post('/api/sell', json={'item_id': 1, 'quantity': 1})
        assert resp.status_code == 401

    @allure.feature("购买功能")
    @allure.story("销售异常场景")
    @allure.severity(allure.severity_level.MINOR)
    def test_sell_negative_quantity(self, client, logged_headers):
        """出售数量为负数：应返回400（防刷道具）"""
        # 先买1瓶，确保背包有东西
        client.post('/api/buy', json={'item_id': 1, 'quantity': 1},
                    headers=logged_headers)

        resp = client.post('/api/sell',
                           json={'item_id': 1, 'quantity': -1},
                           headers=logged_headers)
        assert resp.status_code == 400
        assert '正整数' in resp.get_json()['error']
