from __future__ import annotations

from typing import List

from pydantic import BaseModel

from state.models import (
    Event,
    ExchangeStats,
    LLMSummary,
    Signal,
    SignalsAggregateStats,
    SymbolMarketStats,
    SystemStatus,
)


class StatusResponse(SystemStatus):
    pass


class SignalsResponse(BaseModel):
    signals: List[Signal]


class MarketStatsResponse(BaseModel):
    symbols: List[SymbolMarketStats]


class ExchangeStatsResponse(BaseModel):
    exchanges: List[ExchangeStats]


class SignalsStatsResponse(SignalsAggregateStats):
    pass


class EventsResponse(BaseModel):
    events: List[Event]


class SummariesResponse(BaseModel):
    events: List[LLMSummary]
