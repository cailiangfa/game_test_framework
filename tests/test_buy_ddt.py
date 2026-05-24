import json
import pytest
import allure
from pathlib import Path

# 基于当前文件位置计算绝对路径，不依赖工作目录
DATA_DIR = Path(__file__).resolve().parent / 'data'


def load_buy_data():
    """从 JSON 文件加载购买测试数据"""
    with open(DATA_DIR / 'buy_data.json', 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------- 带 Allure 步骤的辅助函数 ----------

@allure.step("获取道具 {item_id} 的当前价格")
def get_item_price(db_check, item_id):
    """查询道具价格，若不存在则断言失败"""
    item = db_check("SELECT price FROM items WHERE id=?", (item_id,))
    assert item is not None, f"道具不存在: {item_id}"
    return item['price']


@allure.step("记录购买前状态 (玩家 1, 道具 {item_id})")
def record_before_state(get_gold, db_check, item_id):
    """返回购买前的金币、背包数量和订单数"""
    before_gold = get_gold()
    before_backpack = db_check(
        "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
        (1, item_id)
    )
    before_orders = db_check(
        "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
    )['cnt']
    return before_gold, before_backpack, before_orders


@allure.step("执行购买: 道具 {item_id}, 数量 {quantity}")
def execute_buy(client, logged_headers, item_id, quantity):
    """发送购买请求并返回响应"""
    resp = client.post('/api/buy',
                       json={'item_id': item_id, 'quantity': quantity},
                       headers=logged_headers)
    return resp


@allure.step("验证购买后状态 (玩家 1, 道具 {item_id})")
def verify_after_state(get_gold, db_check, item_id, before_gold, before_backpack,
                       before_orders, price, quantity, resp):
    """执行所有接口与数据库断言"""
    # 接口断言
    assert resp.status_code == 200, f"购买失败: {resp.get_json()}"
    resp_data = resp.get_json()
    expected_cost = price * quantity
    assert resp_data['gold_remain'] == before_gold - expected_cost

    # 数据库断言 - 金币
    after_gold = get_gold()
    assert after_gold == before_gold - expected_cost

    # 数据库断言 - 背包
    after_backpack = db_check(
        "SELECT count FROM backpack WHERE player_id=? AND item_id=?",
        (1, item_id)
    )
    assert after_backpack is not None, "购买后背包记录异常丢失"
    expected_count = (before_backpack['count'] if before_backpack else 0) + quantity
    assert after_backpack['count'] == expected_count

    # 数据库断言 - 订单
    after_orders = db_check(
        "SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,)
    )['cnt']
    assert after_orders == before_orders + 1


# ---------- 测试类 ----------

class TestBuyDDT:
    """数据驱动购买正向测试"""

    @pytest.mark.parametrize("case", load_buy_data(),
                             ids=lambda c: f"item{c['item_id']}_qty{c['quantity']}")
    @allure.feature("购买功能")
    @allure.story("购买 DDT 数据驱动")
    @allure.severity(allure.severity_level.NORMAL)
    def test_buy_success_ddt(self, client, logged_headers, db_check, get_gold, case):
        """从 JSON 文件加载数据，验证购买功能"""
        item_id = case['item_id']
        quantity = case['quantity']

        # 步骤1：获取道具价格
        price = get_item_price(db_check, item_id)

        # 步骤2：记录购买前状态
        before_gold, before_backpack, before_orders = record_before_state(
            get_gold, db_check, item_id
        )

        # 步骤3：执行购买
        resp = execute_buy(client, logged_headers, item_id, quantity)

        # 步骤4：验证购买后状态
        verify_after_state(get_gold, db_check, item_id, before_gold, before_backpack,
                           before_orders, price, quantity, resp)