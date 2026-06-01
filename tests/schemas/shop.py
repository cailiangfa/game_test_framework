"""
Pydantic Schema - API 契约层
tests/schemas/shop.py

作用：
1. 请求前校验参数类型（item_id 必须 > 0）
2. 响应后校验返回结构（确保后端没偷偷改字段名）
3. 自动生成文档，面试能讲"防御式编程"

★ 优化：
- quantity 上限与后端 MAX_QUANTITY 对齐（之前 le=99，后端允许 10000）
- BuyResponse / SellResponse 的 msg 去掉默认值（防止后端漏返回字段时校验"假通过"）
- 新增 BackpackResponse、HealthResponse、RegisterResponse
- GoldOverflowRequest 加注释说明用途
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ========== 请求 Schema ==========

class BuyRequest(BaseModel):
    """购买请求契约"""
    item_id: int = Field(gt=0, description="道具ID必须大于0")
    quantity: int = Field(ge=1, le=10000, description="数量1-10000，与后端 MAX_QUANTITY 对齐")


class SellRequest(BaseModel):
    """出售请求契约"""
    item_id: int = Field(gt=0, description="道具ID必须大于0")
    quantity: int = Field(ge=1, le=10000, description="数量1-10000，与后端 MAX_QUANTITY 对齐")


class LoginRequest(BaseModel):
    """登录请求契约"""
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)


class RegisterRequest(BaseModel):
    """注册请求契约"""
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)


class GoldOverflowRequest(BaseModel):
    """
    数值溢出测试专用：验证后端 int64 边界
    用途：构造超大 amount 验证后端是否正确处理整数溢出
    注意：此 Schema 仅用于边界测试，不对应任何生产接口
    """
    amount: int = Field(gt=0)


# ========== 响应 Schema ==========

class BuyResponse(BaseModel):
    """购买响应契约 — msg 无默认值，后端漏返回时校验直接报错"""
    gold_remain: int
    msg: str  # ★ 去掉默认值 "购买成功"：契约校验不应自动补字段


class SellResponse(BaseModel):
    """出售响应契约"""
    gold_remain: int
    msg: str  # ★ 同上


class LoginResponse(BaseModel):
    """登录响应契约"""
    token: str


class RegisterResponse(BaseModel):
    """注册响应契约"""
    msg: str


class GoldResponse(BaseModel):
    """金币查询响应契约"""
    gold: int


class ErrorResponse(BaseModel):
    """错误响应契约"""
    error: str


class BackpackItem(BaseModel):
    """背包单个道具"""
    item_id: int
    name: str
    count: int


class HealthResponse(BaseModel):
    """健康检查响应契约"""
    status: Literal["healthy", "unhealthy"]
    db: str = "connected"
