
#config.py
"""
配置中心 - 支持多环境切换
基于 Pydantic Settings：自动读取环境变量 / .env 文件
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent


class TestEnv(str, Enum):
    local = "local"
    staging = "staging"
    ci = "ci"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 环境标识 ----
    test_env: TestEnv = TestEnv.local

    # ---- 数据库 ----
    game_db: str = str(PROJECT_ROOT / "tests" / "test.db")

    # ---- 服务地址（UI / 并发测试用）----
    host: str = "127.0.0.1"
    port: int = 5000

    # ---- Playwright ----
    headless: bool = True
    browser_type: str = "chromium"

    # ---- Trace 策略 ----
    trace: bool = True

    # ---- 超时 ----
    default_timeout: int = 10

    # ---- 日志级别（CI 用 INFO，本地可开 DEBUG）----
    @property
    def log_level(self) -> str:
        if self.test_env == TestEnv.ci:
            return "INFO"
        return os.getenv("LOG_LEVEL", "DEBUG")

    # ---- 便捷属性 ----
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


settings = Settings()