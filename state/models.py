"""Pydantic models representing shared state stored in Redis."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt


class ExchangeHealth(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    offline = "offline"


class OrderBookLevel(BaseModel):
    price: PositiveFloat
    amount: PositiveFloat


class OrderBook(BaseModel):
    symbol: str
    exchange: str
    bids: List[OrderBookLevel] = Field(default_factory=list)
    asks: List[OrderBookLevel] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RouteQuote(BaseModel):
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: PositiveFloat
    sell_price: PositiveFloat
    spread_bps: float
    volume_usd: PositiveFloat
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SignalSeverity(str, Enum):
    info = "info"
    elevated = "elevated"
    critical = "critical"


class Signal(BaseModel):
    id: str
    route: RouteQuote
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_profit_bps: float
    expected_profit_usd: float
    status: str = Field("new", description="new|confirmed|expired")
    severity: SignalSeverity = SignalSeverity.info
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExchangeStats(BaseModel):
    exchange: str
    health: ExchangeHealth = ExchangeHealth.healthy
    latency_ms: float
    error_rate: float = Field(0.0, ge=0.0, le=1.0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class MarketStats(BaseModel):
    symbol: str
    volatility: float
    mid_price: float
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class SystemStats(BaseModel):
    redis_ok: bool
    active_exchanges: List[str] = Field(default_factory=list)
    active_symbols: List[str] = Field(default_factory=list)
    total_signals: int = 0
    exchange_stats: List[ExchangeStats] = Field(default_factory=list)
    market_stats: List[MarketStats] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class LLMEvent(BaseModel):
    kind: str
    payload: Dict[str, object]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LLMSummary(BaseModel):
    id: str
    kind: str = Field("llm_summary", const=True)
    title: str
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


__all__ = [
    "ExchangeHealth",
    "OrderBookLevel",
    "OrderBook",
    "RouteQuote",
    "SignalSeverity",
    "Signal",
    "ExchangeStats",
    "MarketStats",
    "SystemStats",
    "LLMEvent",
    "LLMSummary",
]
