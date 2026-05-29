"""
数据加载工具：延迟加载 + 校验 + 缓存
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


class DataLoadError(Exception):
    """数据加载失败"""


@lru_cache(maxsize=8)
def load_json_data(filename: str) -> list[dict]:
    """
    加载 JSON 测试数据，带缓存和校验。

    Args:
        filename: 相对于 tests/data/ 的文件名

    Returns:
        解析后的 JSON 列表

    Raises:
        DataLoadError: 文件不存在或 JSON 格式错误
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

    return data
