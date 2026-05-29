"""
Pydantic Schema - API 契约层
作用：
1. 请求前校验参数类型（item_id 必须 > 0）
2. 响应后校验返回结构（确保后端没偷偷改字段名）
3. 自动生成文档，面试能讲"防御式编程"
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BuyRequest(BaseModel):
    item_id: int = Field(gt=0, description="道具ID必须大于0")
    quantity: int = Field(ge=1, le=99, description="数量1-99")


class BuyResponse(BaseModel):
    gold_remain: int
    msg: str = "购买成功"


class SellRequest(BaseModel):
    item_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=99)


class SellResponse(BaseModel):
    gold_remain: int
    msg: str = "出售成功"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)


class LoginResponse(BaseModel):
    token: str


class GoldResponse(BaseModel):
    gold: int


class ErrorResponse(BaseModel):
    error: str


class BackpackItem(BaseModel):
    item_id: int
    name: str
    count: int


# 数值溢出测试专用：验证后端 int64 边界
class GoldOverflowRequest(BaseModel):
    amount: int = Field(gt=0)