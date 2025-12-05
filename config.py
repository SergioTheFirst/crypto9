from pydantic import BaseModel, Field


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
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    exchanges: list[str] = Field(default_factory=lambda: ["binance", "mexc"])
    cycle_sec: float = 1.0
    use_dex: bool = False


# -----------------------------
# ENGINE CONFIG
# -----------------------------
class EngineConfig(BaseModel):
    cycle_core_sec: float = 1.0
    cycle_eval_sec: float = 3.0
    cycle_stats_sec: float = 2.0
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    trade_volume_usd: float = 100.0
    min_net_profit_usd: float = 0.0
    min_spread_bps: float = 0.0
    min_volume_usd: float = 0.0


# -----------------------------
# ML CONFIG
# -----------------------------
class MLConfig(BaseModel):
    enabled: bool = False
    model_type: str = "logreg"
    min_score: float = 0.0
    retrain_interval_sec: int = 300
    history_window: int = 500


# -----------------------------
# PARAM TUNER CONFIG
# -----------------------------
class TunerConfig(BaseModel):
    enabled: bool = False
    update_interval_sec: int = 120
    history_window: int = 500


# -----------------------------
# HISTORY CONFIG
# -----------------------------
class HistoryConfig(BaseModel):
    enabled: bool = True
    signals_max_len: int = 10000
    spreads_max_len: int = 1000
    features_max_len: int = 5000
    ttl_sec: int | None = 7 * 24 * 3600
    store_spreads: bool = True


# -----------------------------
# CLUSTERING CONFIG
# -----------------------------
class ClusteringConfig(BaseModel):
    enabled: bool = False
    k: int = 3
    update_interval_sec: int = 600
    history_window: int = 300


# -----------------------------
# MAIN CONFIG
# -----------------------------
class Config(BaseModel):
    redis: RedisConfig = RedisConfig()
    api: APIConfig = APIConfig()
    collector: CollectorConfig = CollectorConfig()
    engine: EngineConfig = EngineConfig()
    ml: MLConfig = MLConfig()
    tuner: TunerConfig = TunerConfig()
    history: HistoryConfig = HistoryConfig()
    clustering: ClusteringConfig = ClusteringConfig()


CONFIG = Config()
