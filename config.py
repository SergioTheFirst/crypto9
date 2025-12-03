"""Global configuration and feature flags for Crypto Intel Premium v9."""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import BaseSettings, Field, HttpUrl, PositiveFloat, PositiveInt


class RedisSettings(BaseSettings):
    url: str = Field("redis://localhost:6379/0", description="Redis connection URL")
    connection_timeout: float = Field(5.0, description="Timeout for connecting to Redis")
    health_check_interval: float = Field(10.0, description="Interval for Redis health checks in seconds")


class CollectorSettings(BaseSettings):
    symbols: List[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"], description="Symbols to collect")
    exchanges: List[str] = Field(default_factory=lambda: ["binance", "okx"], description="CEX exchanges to poll")
    poll_interval: float = Field(1.0, description="Base polling interval in seconds")
    max_backoff: float = Field(10.0, description="Maximum backoff when encountering errors")
    http_timeout: float = Field(3.0, description="HTTP timeout for collector requests")
    enable_dex: bool = Field(True, description="Whether to enable optional DEX collection")


class EngineSettings(BaseSettings):
    min_profit_bps: PositiveFloat = Field(5.0, description="Minimum profit threshold in basis points")
    min_volume_usd: PositiveFloat = Field(100.0, description="Minimum notional volume in USD")
    confirm_window: PositiveInt = Field(3, description="Number of consecutive observations required to confirm signal")
    stats_interval: PositiveInt = Field(30, description="Seconds between stats snapshots")


class TelegramSettings(BaseSettings):
    enabled: bool = Field(False, description="Toggle Telegram notifications")
    bot_token: Optional[str] = Field(None, description="Telegram bot token")
    chat_id: Optional[str] = Field(None, description="Telegram chat identifier")
    rate_limit_per_hour: PositiveInt = Field(12, description="Maximum number of messages per hour")
    debounce_minutes: PositiveInt = Field(10, description="Minimum minutes between similar alerts")
    profit_threshold_bps: PositiveFloat = Field(25.0, description="Profit threshold for critical alerts in bps")


class LLMSettings(BaseSettings):
    enabled: bool = Field(False, description="Toggle LLM summary worker")
    provider: Optional[str] = Field(None, description="LLM provider identifier")
    api_key: Optional[str] = Field(None, description="LLM API key")
    summary_interval_minutes: PositiveInt = Field(60, description="Interval for generating summaries")
    max_signals: PositiveInt = Field(20, description="Number of recent signals to summarize")


class APISettings(BaseSettings):
    host: str = Field("127.0.0.1", description="API host")
    port: int = Field(8000, description="API port")
    cors_origins: List[HttpUrl] = Field(default_factory=list, description="Allowed CORS origins")


class Config(BaseSettings):
    redis: RedisSettings = Field(default_factory=RedisSettings)
    collectors: CollectorSettings = Field(default_factory=CollectorSettings)
    engine: EngineSettings = Field(default_factory=EngineSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    api: APISettings = Field(default_factory=APISettings)

    class Config:
        env_nested_delimiter = "__"
        env_prefix = "CIP9_"


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load and cache the application configuration from environment variables."""
    return Config()  # type: ignore[call-arg]


__all__ = [
    "RedisSettings",
    "CollectorSettings",
    "EngineSettings",
    "TelegramSettings",
    "LLMSettings",
    "APISettings",
    "Config",
    "get_config",
]
