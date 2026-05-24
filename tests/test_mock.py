import pytest
import allure

class TestMockPayment:
    """Mock 外部支付验证服务"""

    @allure.feature("支付功能")  # 功能模块：支付
    @allure.story("测试模拟支付")  # 故事线：模拟支付场景
    @allure.severity(allure.severity_level.NORMAL)  # 严重程度：普通
    def test_payment_verify_success(self, client, logged_headers, mocker, db_check):
        """模拟支付验证成功：购买正常完成，且验证调用行为"""
        # 1. Mock 外部服务，让它返回通过
        mock_verify = mocker.patch(
            'backend.app.external_payment.verify',
            return_value={"passed": True}
        )

        # 2. 发起请求
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 1},
                           headers=logged_headers)

        # 3. 接口断言
        assert resp.status_code == 200
        assert resp.get_json()['msg'] == '购买成功'

        # 4. 行为验证（核心！）：确认业务代码确实以正确的参数调了支付验证
        mock_verify.assert_called_once_with(1, 100)

    @allure.feature("支付功能")  # 功能模块：支付
    @allure.story("测试模拟支付")  # 故事线：模拟支付场景
    @allure.severity(allure.severity_level.NORMAL)  # 严重程度：普通
    def test_payment_verify_failed(self, client, logged_headers, mocker, db_check):
        """模拟支付验证失败：应返回400，且数据绝对不变"""
        # 1. 记录初始状态
        before_gold = 1000
        before_orders = db_check("SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,))['cnt']
        before_backpack = db_check("SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1))

        # 2. Mock 外部服务，让它返回不通过
        mock_verify = mocker.patch(
            'backend.app.external_payment.verify',
            return_value={"passed": False, "reason": "信用评分不足"}
        )

        # 3. 发起请求
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 1},
                           headers=logged_headers)

        # 4. 接口断言
        assert resp.status_code == 400
        assert '支付验证失败' in resp.get_json()['error']
        assert '信用评分不足' in resp.get_json()['error']

        # 5. 行为验证：确认问了支付系统
        mock_verify.assert_called_once_with(1, 100)

        # 6. 严格的数据不变断言
        after_gold = db_check("SELECT gold FROM players WHERE id=?", (1,))['gold']
        assert after_gold == before_gold

        after_orders = db_check("SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,))['cnt']
        assert after_orders == before_orders

        after_backpack = db_check("SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1))
        assert (after_backpack is None) if (before_backpack is None) else (
                    after_backpack['count'] == before_backpack['count'])

    @allure.feature("支付功能")  # 功能模块：支付
    @allure.story("测试模拟支付")  # 故事线：模拟支付场景
    @allure.severity(allure.severity_level.NORMAL)  # 严重程度：普通
    def test_payment_service_timeout(self, client, logged_headers, mocker, db_check):
        """模拟支付服务超时：接口应兜底返回500，且数据绝对不变"""
        # 1. 记录初始状态
        before_gold = 1000
        before_orders = db_check("SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,))['cnt']
        before_backpack = db_check("SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1))

        # 2. Mock 外部服务，让它抛出连接超时异常
        mock_verify = mocker.patch(
            'backend.app.external_payment.verify',
            side_effect=ConnectionError("支付服务连接超时")
        )

        # 3. 发起请求
        resp = client.post('/api/buy',
                           json={'item_id': 1, 'quantity': 1},
                           headers=logged_headers)

        # 4. 接口断言：配合 app.py 里的 try-except，现在能正常兜底返回 500
        assert resp.status_code == 500
        assert '支付服务异常' in resp.get_json()['error']
        assert '支付服务连接超时' in resp.get_json()['error']

        # 5. 行为验证：确认问了支付系统（虽然挂了，但确实去问了）
        mock_verify.assert_called_once_with(1, 100)

        # 6. 严格的数据不变断言（服务挂了绝不能扣钱）
        after_gold = db_check("SELECT gold FROM players WHERE id=?", (1,))['gold']
        assert after_gold == before_gold

        after_orders = db_check("SELECT COUNT(*) as cnt FROM orders WHERE player_id=?", (1,))['cnt']
        assert after_orders == before_orders

        after_backpack = db_check("SELECT count FROM backpack WHERE player_id=? AND item_id=?", (1, 1))
        assert (after_backpack is None) if (before_backpack is None) else (
                    after_backpack['count'] == before_backpack['count'])
