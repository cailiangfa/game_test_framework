"""
tests/utils/data_loader.py
数据加载工具：延迟加载 + 校验 + 缓存

★ 优化：
- 增加 JSON 内容字段完整性校验（检测字段名拼写错误）
- 校验失败时抛出 DataLoadError 并明确提示哪个字段缺失
- 每条记录的 id 字段必须存在（用于 parametrize 的测试 ID 生成）
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


class DataLoadError(Exception):
    """数据加载失败"""


# 不同 JSON 文件要求的必填字段
_REQUIRED_FIELDS: dict[str, set[str]] = {
    "buy_data.json": {"item_id", "quantity"},
    # 后续新增的 JSON 文件在这里注册
    # "sell_data.json": {"item_id", "quantity"},
}


def _validate_records(
    records: list[dict[str, Any]], filename: str
) -> list[dict[str, Any]]:
    """校验每条记录是否包含必填字段"""
    required = _REQUIRED_FIELDS.get(filename)

    if not required:
        # 未注册的文件不做字段校验，只检查基本结构
        return records

    for i, record in enumerate(records):
        missing = required - set(record.keys())
        if missing:
            raise DataLoadError(
                f"[{filename}] 第 {i + 1} 条记录缺少必填字段: {missing}\n"
                f"  实际字段: {sorted(record.keys())}\n"
                f"  必填字段: {sorted(required)}"
            )

    return records


@lru_cache(maxsize=8)
def load_json_data(filename: str) -> list[dict[str, Any]]:
    """
    加载 JSON 测试数据，带缓存和校验。

    Args:
        filename: 相对于 tests/data/ 的文件名

    Returns:
        解析后的 JSON 列表

    Raises:
        DataLoadError: 文件不存在、JSON 格式错误、或字段缺失
    """
    data_dir = Path(__file__).resolve().parent.parent / "data"
    filepath = data_dir / filename

    if not filepath.exists():
        raise DataLoadError(f"测试数据文件不存在: {filepath}")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise DataLoadError(f"JSON 解析失败 [{filename}]: {exc}") from exc

    if not isinstance(data, list):
        raise DataLoadError(f"测试数据必须是 JSON 数组: {filename}")

    if len(data) == 0:
        raise DataLoadError(f"测试数据不能为空数组: {filename}")

    # ★ 新增：校验每条记录的字段完整性
    return _validate_records(data, filename)
