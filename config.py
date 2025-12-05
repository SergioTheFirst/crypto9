from pydantic import BaseModel


# -----------------------------
# REDIS CONFIG
# -----------------------------
class RedisConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0


# -----------------------------
# API CONFIG
# -----------------------------
class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


# -----------------------------
# COLLECTORS CONFIG
# -----------------------------
class CollectorConfig(BaseModel):
    symbols: list[str] = ["BTCUSDT", "ETHUSDT"]
    exchanges: list[str] = ["binance", "mexc"]
    cycle_sec: float = 1.0
    use_dex: bool = False


# -----------------------------
# ENGINE CONFIG
# -----------------------------
class EngineConfig(BaseModel):
    cycle_core_sec: float = 1.0
    cycle_eval_sec: float = 3.0
    cycle_stats_sec: float = 2.0


# -----------------------------
# MAIN CONFIG
# -----------------------------
class Config(BaseModel):
    redis: RedisConfig = RedisConfig()
    api: APIConfig = APIConfig()
    collector: CollectorConfig = CollectorConfig()
    engine: EngineConfig = EngineConfig()


CONFIG = Config()
