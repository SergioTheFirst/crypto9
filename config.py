from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, HttpUrl, PositiveFloat, PositiveInt
from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    url: str = "redis://localhost:6379/0"
    connection_timeout: float = 5.0
    health_check_interval: float = 10.0

    class Config:
        env_prefix = "CIP9_REDIS__"


class CollectorSettings(BaseSettings):
    # Пары, которые мониторим
    symbols: List[str] = ["BTCUSDT", "ETHUSDT"]

    # Список CEX, с которыми реально работаем
    # ВАЖНО: здесь теперь две биржи
    cex_exchanges: List[str] = ["binance", "mexc"]

    # DEX пока опционален
    dex_enabled: bool = False

    poll_interval: float = 1.0
    max_backoff: float = 10.0
    http_timeout: float = 3.0

    class Config:
        env_prefix = "CIP9_COLLECTORS__"


class EngineSettings(BaseSettings):
    # Минимальная прибыль в бипсах ПОСЛЕ комиссий
    min_profit_bps: PositiveFloat = 5.0

    # Минимальный объём, который считаем осмысленным
    min_volume_usd: PositiveFloat = 100.0

    # Целевой объём сделки (ты просил ~3000 USDT)
    volume_cap_usd: PositiveFloat = 3000.0

    # Через сколько тиков считать сигнал устойчивым (запас на будущее)
    confirm_window: PositiveInt = 3

    # Как часто пересчитывать агрегированные статы
    stats_interval: PositiveInt = 30

    class Config:
        env_prefix = "CIP9_ENGINE__"


class EvalSettings(BaseSettings):
    fast_seconds: PositiveInt = 10
    slow_seconds: PositiveInt = 60
    poll_interval: PositiveInt = 5

    class Config:
        env_prefix = "CIP9_EVAL__"


class TelegramSettings(BaseSettings):
    enabled: bool = False
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    rate_limit_per_hour: int = 12
    debounce_minutes: int = 10
    profit_threshold_bps: float = 25.0

    class Config:
        env_prefix = "CIP9_TELEGRAM__"


class LLMSettings(BaseSettings):
    enabled: bool = False
    summary_interval_minutes: int = 60
    max_signals: int = 20

    class Config:
        env_prefix = "CIP9_LLM__"


class APISettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: List[HttpUrl] = []

    class Config:
        env_prefix = "CIP9_API__"


class Config(BaseSettings):
    redis: RedisSettings = RedisSettings()
    collectors: CollectorSettings = CollectorSettings()
    engine: EngineSettings = EngineSettings()
    eval: EvalSettings = EvalSettings()
    telegram: TelegramSettings = TelegramSettings()
    llm: LLMSettings = LLMSettings()
    api: APISettings = APISettings()

    class Config:
        env_nested_delimiter = "__"
        env_prefix = "CIP9_"


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()

# ============================================================
# Global CONFIG instance for v9.1 modules
# ============================================================
CONFIG = get_config()
