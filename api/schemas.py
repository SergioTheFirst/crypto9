"""API response schemas."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel

from state.models import LLMSummary, Signal, SystemStats


class HealthResponse(BaseModel):
    status: str
    redis_ok: bool


class SignalsResponse(BaseModel):
    signals: List[Signal]


class StatsResponse(BaseModel):
    stats: SystemStats


class SummariesResponse(BaseModel):
    summaries: List[LLMSummary]


__all__ = [
    "HealthResponse",
    "SignalsResponse",
    "StatsResponse",
    "SummariesResponse",
]
