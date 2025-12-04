from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Literal

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt


class ExchangeHealth(str, Enum):
    excellent = "excellent"
    good = "good"
    unstable = "unstable"
    degraded = "degraded"
    offline = "offline"
class NormalizedBook(BaseModel):
    """
    Normalized orderbook snapshot (used by collectors and core engine).
    Compatible with Pydantic v2.
    """

    exchange: str = Field(..., description="Exchange name")
    bid: float = Field(..., description="Best bid price")
    ask: float = Field(..., description="Best ask price")
    bid_size: float = Field(..., description="Available size at bid")
    ask_size: float = Field(..., description="Available size at ask")
    ts: datetime = Field(default_factory=datetime.utcnow, description="Collection timestamp")


class OrderBookLevel(BaseModel):
    price: PositiveFloat
    amount: PositiveFloat


class OrderBook(BaseModel):
    symbol: str
    exchange: str
    bids: List[OrderBookLevel] = Field(default_factory=list)
    asks: List[OrderBookLevel] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Route(BaseModel):
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: PositiveFloat
    sell_price: PositiveFloat
    volume_usd: PositiveFloat
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SignalSeverity(str, Enum):
    info = "info"
    elevated = "elevated"
    critical = "critical"


class Signal(BaseModel):
    id: str
    symbol: str
    route: Route
    expected_profit_bps: float
    expected_profit_usd: float
    spread_bps: float = 0.0
    profit_usd: float = 0.0
    volume_usd: float = 0.0
    ts: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: str = "new"
    severity: SignalSeverity = SignalSeverity.info
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SymbolMarketStats(BaseModel):
    symbol: str
    last_mid: float
    volatility_1h: float
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ExchangeStats(BaseModel):
    name: str
    health: ExchangeHealth
    latency_ms: float
    error_rate: float
    timeout_rate: float = 0.0
    books_seen: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SignalsAggregateStats(BaseModel):
    total_signals: int
    active_signals: int
    avg_profit_bps: float
    total_evaluated: int = 0
    win_rate: float = 0.0
    avg_final_profit_usd: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SystemStatus(BaseModel):
    status: str = "ok"
    redis: str = "ok"
    llm: str = "disabled"
    telegram: str = "disabled"
    dex: str = "unavailable"
    symbols: int = 0
    exchanges: Dict[str, str] = Field(default_factory=dict)
    last_update_ts: datetime = Field(default_factory=datetime.utcnow)


class LLMSummary(BaseModel):
    id: str
    kind: Literal["llm_summary"] = "llm_summary"
    title: str
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Event(BaseModel):
    id: str
    kind: str
    title: str
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SignalEvalResult(BaseModel):
    signal_id: str
    fast_done: bool = False
    slow_done: bool = False
    real_profit_fast_bps: Optional[float] = None
    real_profit_slow_bps: Optional[float] = None
    execution_quality: Optional[str] = None
    stability_quality: Optional[str] = None


class VirtualTrade(BaseModel):
    signal_id: str
    symbol: str
    buy_exchange: str
    sell_exchange: str
    open_price_buy: float
    open_price_sell: float
    open_ts: datetime
    volume_usd: float
    predicted_profit_usd: float


class VirtualEvalResult(BaseModel):
    signal_id: str
    symbol: str
    buy_exchange: str
    sell_exchange: str
    open_ts: datetime
    eval_ts: datetime
    final_profit_usd: float
    grade: Literal["WIN", "NEUTRAL", "LOSS"]
