"""
配置中心 - 支持多环境切换
用法：
    from config import settings
    print(settings.base_url)

命令行覆盖：
    TEST_ENV=staging pytest tests/
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 环境标识：local / staging / ci
    test_env: str = "local"

    # 数据库
    game_db: str = str(PROJECT_ROOT / "tests" / "test.db")

    # 服务地址（UI/并发测试用）
    host: str = "127.0.0.1"
    port: int = 5000

    # Playwright
    headless: bool = True
    browser_type: str = "chromium"

    # 超时
    default_timeout: int = 10

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


settings = Settings()