"""
tests/api/test_shop.py
主流程测试：购买/出售正向场景

★ 核心修改：
- 工厂用户用 get_auth_headers 构造鉴权，不再拼用户名
- assert_state_equals 只传 db_check + player_id
- 去掉 autouse=True，显式依赖
- 统一 player_id 参数，不硬编码
"""
import allure

from tests.utils.assertions import assert_state_equals
from tests.utils.factories import (
    create_player,
    give_item_to_player,
    get_item_price,
    get_player_gold,
    get_backpack_count,
    get_order_count,
    get_auth_headers,
)


class TestBuyItem:
    """购买道具正向测试"""

    @allure.feature("购买功能")
    @allure.story("正常购买流程")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_buy_success(self, shop_api, db_check):
        """购买道具：接口 + 数据库双重断言"""
        player_id = 1
        item_id = 1
        quantity = 3

        # 初始状态
        before_gold = get_player_gold(db_check, player_id=player_id)
        before_backpack = get_backpack_count(db_check, player_id=player_id, item_id=item_id)
        before_orders = get_order_count(db_check, player_id=player_id)
        price = get_item_price(db_check, item_id=item_id)
        expected_cost = price * quantity

        # 执行购买
        result = shop_api.buy(item_id=item_id, quantity=quantity)
        assert result["status_code"] == 200
        data = result["data"]
        assert data["gold_remain"] == before_gold - expected_cost
        assert data["msg"] == "购买成功"

        # 组合断言
        assert_state_equals(
            db_check,
            expected_gold=before_gold - expected_cost,
            expected_orders=before_orders + 1,
            expected_bp_count=before_backpack + quantity,
            player_id=player_id,
            item_id=item_id,
        )

        # 订单详情验证
        order = db_check(
            "SELECT * FROM orders WHERE player_id=? ORDER BY order_id DESC LIMIT 1",
            (player_id,),
        )
        assert order["item_id"] == item_id
        assert order["quantity"] == quantity
        assert order["amount"] == expected_cost

    @allure.feature("购买功能")
    @allure.story("动态用户独立测试")
    def test_buy_with_factory_user(self, client, db_check):
        """工厂用户：金币刚好花完的精确边界"""
        # 创建全新用户，与 player1 完全隔离
        player_id, username = create_player(gold=300)
        headers = get_auth_headers(player_id)

        item_id = 1
        quantity = 3
        price = get_item_price(db_check, item_id=item_id)
        expected_cost = price * quantity

        # 用自定义 headers 直接实例化 ShopAPI
        from tests.api.shop_api import ShopAPI
        api = ShopAPI(client, headers)

        result = api.buy(item_id=item_id, quantity=quantity)
        assert result["status_code"] == 200
        data = result["data"]
        assert data["gold_remain"] == 0
        assert data["msg"] == "购买成功"

        # 组合断言
        assert_state_equals(
            db_check,
            expected_gold=0,
            expected_orders=1,
            expected_bp_count=quantity,
            player_id=player_id,
            item_id=item_id,
        )


class TestSellItem:
    """出售道具正向测试"""

    @allure.feature("出售功能")
    @allure.story("正常出售流程")
    @allure.severity(allure.severity_level.NORMAL)
    def test_sell_success(self, shop_api, db_check):
        """出售成功：金币增加，背包减少，订单生成"""
        player_id = 1
        item_id = 1
        sell_quantity = 3

        # 前置：直接塞道具（比调购买接口更快更稳定）
        give_item_to_player(player_id=player_id, item_id=item_id, count=5)

        # 初始状态
        before_gold = get_player_gold(db_check, player_id=player_id)
        before_backpack = get_backpack_count(db_check, player_id=player_id, item_id=item_id)
        before_sold_orders = get_order_count(db_check, player_id=player_id, status="sold")
        price = get_item_price(db_check, item_id=item_id)
        expected_income = price * sell_quantity

        # 执行出售
        result = shop_api.sell(item_id=item_id, quantity=sell_quantity)
        assert result["status_code"] == 200
        data = result["data"]
        assert data["gold_remain"] == before_gold + expected_income
        assert data["msg"] == "出售成功"

        # 组合断言
        assert_state_equals(
            db_check,
            expected_gold=before_gold + expected_income,
            expected_orders=before_sold_orders + 1,
            expected_bp_count=before_backpack - sell_quantity,
            player_id=player_id,
            item_id=item_id,
        )

        # 订单详情验证
        order = db_check(
            "SELECT * FROM orders WHERE player_id=? AND status='sold' ORDER BY order_id DESC LIMIT 1",
            (player_id,),
        )
        assert order["item_id"] == item_id
        assert order["quantity"] == sell_quantity
        assert order["amount"] == expected_income

    @allure.feature("出售功能")
    @allure.story("魔法药水出售测试")
    @allure.severity(allure.severity_level.NORMAL)
    def test_sell_magic_potion(self, shop_api, db_check):
        """出售魔法药水：验证不同道具的价格和数量"""
        player_id = 1
        item_id = 2  # 魔法药水
        sell_quantity = 2

        # 前置：给背包塞 2 瓶魔法药水
        give_item_to_player(player_id=player_id, item_id=item_id, count=sell_quantity)

        before_gold = get_player_gold(db_check, player_id=player_id)
        before_backpack = get_backpack_count(db_check, player_id=player_id, item_id=item_id)
        before_sold_orders = get_order_count(db_check, player_id=player_id, status="sold")
        price = get_item_price(db_check, item_id=item_id)
        expected_income = price * sell_quantity

        result = shop_api.sell(item_id=item_id, quantity=sell_quantity)
        assert result["status_code"] == 200
        data = result["data"]
        assert data["gold_remain"] == before_gold + expected_income

        # 组合断言
        assert_state_equals(
            db_check,
            expected_gold=before_gold + expected_income,
            expected_orders=before_sold_orders + 1,
            expected_bp_count=before_backpack - sell_quantity,
            player_id=player_id,
            item_id=item_id,
        )
