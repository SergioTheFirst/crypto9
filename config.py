from pydantic import BaseModel, Field
from typing import List


# ----------------------------------------------------
# REDIS
# ----------------------------------------------------
class RedisConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0


# ----------------------------------------------------
# API
# ----------------------------------------------------
class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    # НОВОЕ: Интервал обновления статуса для SSE-стрима
    status_stream_interval_sec: float = Field(default=1.0, description="Interval for system status SSE stream.")


# ----------------------------------------------------
# COLLECTOR
# ----------------------------------------------------
class CollectorConfig(BaseModel):
    use_cex: bool = True
    use_dex: bool = False
    cycle_sec: float = 1.0

    symbols: List[str] = ["BTCUSDT", "ETHUSDT"]
    cex_exchanges: List[str] = ["binance", "mexc"]


# ----------------------------------------------------
# ENGINE
# ----------------------------------------------------
class EngineConfig(BaseModel):
    cycle_core_sec: float = 1.5
    cycle_eval_sec: float = 5.0
    cycle_stats_sec: float = 3.0

    min_spread_usd: float = 0.50
    min_volume_usd: float = 100.0
    
    # НОВОЕ: Объемы и ставки для расчета профита
    volume_calc_usd: float = Field(default=500.0, description="Volume used for profit calculation.")
    default_fee_rate: float = Field(default=0.00075, description="Default maker/taker fee rate (e.g., 0.075%).")
    default_slippage_rate: float = Field(default=0.0001, description="Default slippage percentage for a trade.")


# ----------------------------------------------------
# EVAL
# ----------------------------------------------------
class EvalConfig(BaseModel):
    cycle_sec: float = 5.0
    # НОВОЕ: Максимальное количество сигналов для расчета статистики
    signals_eval_limit: int = Field(default=500, description="Max number of recent signals to use for evaluation stats.")


# ----------------------------------------------------
# STATS
# ----------------------------------------------------
class StatsConfig(BaseModel):
    max_market_stats: int = 50


# ----------------------------------------------------
# ML
# ----------------------------------------------------
class MLConfig(BaseModel):
    enabled: bool = True
    train_interval_sec: float = 300.0
    history_window: int = 2000
    min_score: float = 0.6


# ----------------------------------------------------
# CLUSTERING
# ----------------------------------------------------
class ClusteringConfig(BaseModel):
    enabled: bool = False
    min_samples: int = 5
    eps: float = 0.4


# ----------------------------------------------------
# HISTORY STORE
# ----------------------------------------------------
class HistoryConfig(BaseModel):
    enable: bool = True
    signals_max_len: int = 5000
    spreads_max_len: int = 100
    features_max_len: int = 10000
    ttl_sec: int | None = None # TTL for history records


# ----------------------------------------------------\
# TELEGRAM
# ----------------------------------------------------\
class TelegramConfig(BaseModel):
    token: str = ""
    chat_id: int = 0
    admin_chat_id: int = 0
    enabled: bool = False


# ----------------------------------------------------\
# LLM
# ----------------------------------------------------\
class LLMConfig(BaseModel):
    enabled: bool = False
    provider: str = "cloudflare"
    account_id: str = ""
    api_key: str = ""
    max_signals: int = 50
    update_interval_sec: float = 900.0 # 15 minutes


# ----------------------------------------------------
# PARAM TUNER
# ----------------------------------------------------\
class TunerConfig(BaseModel):
    enabled: bool = False
    update_interval_sec: float = 300.0
    history_window: int = 5000 # Use 5000 signals for snapshot calculation


# ----------------------------------------------------\
# FINAL CONFIG
# ----------------------------------------------------\
class Config(BaseModel):
    redis: RedisConfig = RedisConfig()
    api: APIConfig = APIConfig()
    collector: CollectorConfig = CollectorConfig()
    engine: EngineConfig = EngineConfig()
    eval: EvalConfig = EvalConfig()
    stats: StatsConfig = StatsConfig()
    ml: MLConfig = MLConfig()
    clustering: ClusteringConfig = ClusteringConfig()
    history: HistoryConfig = HistoryConfig()
    telegram: TelegramConfig = TelegramConfig()
    llm: LLMConfig = LLMConfig()
    tuner: TunerConfig = TunerConfig()


CONFIG = Config()