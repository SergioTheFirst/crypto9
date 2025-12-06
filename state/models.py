from __future__ import annotations
from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, Field


# ============================
#  BOOK STRUCTURES
# ============================

class NormalizedBook(BaseModel):
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    exchange: str
    updated_at: datetime


# ============================
#  MARKET STATS
# ============================

class MarketStats(BaseModel):
    symbol: str
    last_mid: float
    volatility_1h: float
    updated_at: datetime


# ============================
#  EXCHANGE STATS
# ============================

class ExchangeStats(BaseModel):
    exchange: str
    status: str
    delay_ms: float
    error_rate: float
    updated_at: datetime


# ============================
#  SYSTEM STATUS
# ============================

class SystemStatus(BaseModel):
    status: str
    redis: str
    llm: str
    telegram: str
    dex: str
    symbols: int
    exchanges: Dict[str, ExchangeStats]
    last_update_ts: datetime


# ============================
#  SIGNAL STRUCTURES
# ============================

class CoreSignal(BaseModel):
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    volume_usd: float
    spread: float
    spread_bps: float | None = None
    fee_rate: float
    slippage_rate: float
    net_profit: float
    net_profit_bps: float | None = None
    ml_score: float | None = None
    cluster_id: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SignalStats(BaseModel):
    signals_total: int
    profitable_signals: int
    avg_profit: float
    updated_at: datetime


# ============================
#  LLM SUMMARY
# ============================

class LLMSummary(BaseModel):
    kind: str = Field(default="llm_summary")
    text: str
    created_at: datetime

# ============================
#  PARAM TUNER
# ============================

class ParamSnapshot(BaseModel):
    min_net_profit_usd: float
    min_spread_bps: float
    min_volume_usd: float
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# ============================
#  CLUSTERING
# ============================

class SignalCluster(BaseModel):
    cluster_id: int
    size: int
    centroid: Dict[str, float]

class ClusterState(BaseModel):
    clusters: List["SignalCluster"]
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# ============================
#  EVENT
# ============================

class Event(BaseModel):
    kind: str
    title: str
    text: str
    created_at: datetime