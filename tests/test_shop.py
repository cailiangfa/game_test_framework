import pytest
import allure

class TestBuyItem:
    """购买道具正向测试"""

    @allure.feature("购买功能")  # 功能模块：购买
    @allure.story("正常购买流程")  # 故事线：正常购买
    @allure.severity(allure.severity_level.CRITICAL)  # 严重程度：核心功能
    def test_buy_success(self, client, logged_headers, db_check, get_gold):
        """购买道具：接口 + 数据库双重断言"""
        before_gold = get_gold()
        before_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (1, 1)
        )
        before_orders = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?",
            (1,)
        )['cnt']

        item_id = 1
        quantity = 3
        # 优化：动态从数据库获取价格，消除隐式耦合
        item = db_check("SELECT price FROM items WHERE id=?", (item_id,))
        price = item['price']

        resp = client.post('/api/buy',
                           json={'item_id': item_id, 'quantity': quantity},
                           headers=logged_headers)

        # 接口断言
        assert resp.status_code == 200, f"接口失败: {resp.get_json()}"
        data = resp.get_json()
        expected_cost = price * quantity
        assert data['gold_remain'] == before_gold - expected_cost
        assert data['msg'] == '购买成功'

        # 数据库断言 - 金币
        after_gold = get_gold()
        assert after_gold == before_gold - expected_cost

        # 数据库断言 - 背包
        after_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (1, 1)
        )
        assert after_backpack is not None, "购买后背包记录不应为空"
        expected_count = (before_backpack['count'] if before_backpack else 0) + quantity
        assert after_backpack['count'] == expected_count

        # 数据库断言 - 订单
        after_orders = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?",
            (1,)
        )['cnt']
        assert after_orders == before_orders + 1

        # 订单详情验证
        order = db_check(
            "SELECT * FROM orders WHERE player_id=? ORDER BY order_id DESC LIMIT 1",
            (1,)
        )
        assert order['item_id'] == item_id
        assert order['quantity'] == quantity
        assert order['amount'] == price * quantity


class TestSellItem:
    """出售道具正向测试"""

    @pytest.fixture(autouse=True)
    def setup_for_sell(self, client, logged_headers):
        """前置：买 5 瓶生命药水"""
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 5},
                           headers=logged_headers)
        assert resp.status_code == 200, f"前置购买失败: {resp.get_json()}"

    @allure.feature("支付功能")  # 功能模块：支付
    @allure.story("测试模拟支付")  # 故事线：模拟支付场景
    @allure.severity(allure.severity_level.NORMAL)  # 严重程度：普通
    def test_sell_success(self, client, logged_headers, db_check, get_gold):
        """出售成功：金币增加，背包减少，订单生成"""
        before_gold = get_gold()
        before_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (1, 1)
        )
        # 优化：空值保护，给出清晰的错误提示
        assert before_backpack is not None, "前置数据异常：背包中没有 item_id=1"
        before_count = before_backpack['count']

        before_sold_orders = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=? AND status='sold'",
            (1,)
        )['cnt']

        sell_quantity = 3
        # 优化：动态获取价格
        item = db_check("SELECT price FROM items WHERE id=?", (1,))
        expected_income = item['price'] * sell_quantity

        resp = client.post('/api/sell',
                           json={'item_id': 1, 'quantity': sell_quantity},
                           headers=logged_headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['gold_remain'] == before_gold + expected_income
        assert data['msg'] == '出售成功'

        # 数据库断言 - 金币
        after_gold = get_gold()
        assert after_gold == before_gold + expected_income

        # 数据库断言 - 背包
        after_backpack = db_check(
            "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
            (1, 1)
        )
        # 如果卖完还有剩
        assert after_backpack['count'] == before_count - sell_quantity

        # 数据库断言 - 订单
        after_sold_orders = db_check(
            "SELECT COUNT(*) as cnt FROM orders WHERE player_id=? AND status='sold'",
            (1,)
        )['cnt']
        assert after_sold_orders == before_sold_orders + 1
