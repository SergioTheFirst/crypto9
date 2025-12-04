from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, PositiveFloat, PositiveInt


# =========================================================
# Redis settings
# =========================================================
class RedisSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    decode_responses: bool = True
    prefix: str = "CIP9_STATE_"  # unified global prefix


# =========================================================
# Collector settings
# =========================================================
class CollectorSettings(BaseModel):
    enabled: bool = True
    symbols: List[str] = ["BTCUSDT", "ETHUSDT"]
    exchanges: List[str] = ["binance", "mexc"]
    cycle_sec: PositiveInt = 2


# =========================================================
# Core Engine settings
# =========================================================
class EngineSettings(BaseModel):
    enabled: bool = True
    min_profit_usd: PositiveFloat = 300.0
    min_profit_pct: PositiveFloat = 0.7
    min_volume_usd: PositiveFloat = 15000.0
    cooldown_sec: PositiveInt = 1800  # 30 min
    cycle_sec: PositiveInt = 2


# =========================================================
# Evaluation Engine settings
# =========================================================
class EvalSettings(BaseModel):
    enabled: bool = True
    virtual_hold_sec: PositiveInt = 30
    cycle_sec: PositiveInt = 5


# =========================================================
# Telegram notifier
# =========================================================
class TelegramSettings(BaseModel):
    enabled: bool = False
    token: Optional[str] = None
    chat_id: Optional[str] = None
    cycle_sec: PositiveInt = 5


# =========================================================
# LLM summary worker
# =========================================================
class LLMSettings(BaseModel):
    enabled: bool = False
    endpoint: Optional[HttpUrl] = None
    api_key: Optional[str] = None
    cycle_sec: PositiveInt = 20
    max_signals: PositiveInt = 20


# =========================================================
# API server settings
# =========================================================
class APISettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: List[str] = []


# =========================================================
# Global AppConfig object
# =========================================================
class Config(BaseModel):
    redis: RedisSettings = RedisSettings()
    collectors: CollectorSettings = CollectorSettings()
    engine: EngineSettings = EngineSettings()
    eval: EvalSettings = EvalSettings()
    telegram: TelegramSettings = TelegramSettings()
    llm: LLMSettings = LLMSettings()
    api: APISettings = APISettings()


# =========================================================
# get_config() + global instance
# =========================================================
@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config()


CONFIG = get_config()
