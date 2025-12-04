from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from redis.asyncio import Redis

from state.models import (
    Event,
    ExchangeStats,
    LLMSummary,
    Signal,
    SignalEvalResult,
    SignalsAggregateStats,
    SymbolMarketStats,
    SystemStatus,
)

logger = logging.getLogger(__name__)


class RedisState:
    def __init__(self, url: str):
        self.client: Redis = Redis.from_url(url, decode_responses=True)

    async def close(self):
        await self.client.close()

    # ------------- books -------------

    async def set_books(self, symbol: str, books: Dict[str, dict]) -> None:
        await self.client.set(f"state:books:{symbol}", json.dumps(books))

    async def get_books(self, symbol: str) -> Dict[str, dict]:
        raw = await self.client.get(f"state:books:{symbol}")
        if not raw:
            return {}
        return json.loads(raw)

    async def get_all_books(self) -> Dict[str, Dict[str, dict]]:
        out: Dict[str, Dict[str, dict]] = {}
        async for key in self.client.scan_iter("state:books:*"):
            symbol = key.split(":", 2)[2]
            out[symbol] = await self.get_books(symbol)
        return out

    # ------------- market stats -------------

    async def set_market_stats(self, items: List[SymbolMarketStats]) -> None:
        await self.client.set(
            "state:market_stats",
            json.dumps([i.model_dump(mode="json") for i in items]),
        )

    async def get_market_stats(self) -> List[SymbolMarketStats]:
        raw = await self.client.get("state:market_stats")
        if not raw:
            return []
        data = json.loads(raw)
        return [SymbolMarketStats(**d) for d in data]

    # ------------- exchange stats -------------

    async def set_exchange_stats(self, items: List[ExchangeStats]) -> None:
        await self.client.set(
            "state:exchange_stats",
            json.dumps([i.model_dump(mode="json") for i in items]),
        )

    async def get_exchange_stats(self) -> List[ExchangeStats]:
        raw = await self.client.get("state:exchange_stats")
        if not raw:
            return []
        data = json.loads(raw)
        return [ExchangeStats(**d) for d in data]

    # ------------- system status -------------

    async def set_system_status(self, status: SystemStatus) -> None:
        await self.client.set(
            "state:system_status",
            json.dumps(status.model_dump(mode="json")),
        )

    async def get_system_status(self) -> Optional[SystemStatus]:
        raw = await self.client.get("state:system_status")
        if not raw:
            return None
        return SystemStatus(**json.loads(raw))

    # ------------- signals -------------

    async def set_signals(self, signals: List[Signal]) -> None:
        await self.client.set(
            "state:signals",
            json.dumps([s.model_dump(mode="json") for s in signals]),
        )

    async def get_signals(self) -> List[dict]:
        raw = await self.client.get("state:signals")
        if not raw:
            return []
        return json.loads(raw)

    async def append_signal(self, signal: Signal) -> None:
        signals = await self.get_signals()
        signals.append(signal.model_dump(mode="json"))
        await self.client.set("state:signals", json.dumps(signals))
        await self.client.publish("streamhub:signals", json.dumps(signal.model_dump(mode="json")))

    # ------------- signal stats -------------

    async def set_signal_stats(self, stats: SignalsAggregateStats) -> None:
        await self.client.set(
            "state:signal_stats",
            json.dumps(stats.model_dump(mode="json")),
        )

    async def get_signal_stats(self) -> Optional[SignalsAggregateStats]:
        raw = await self.client.get("state:signal_stats")
        if not raw:
            return None
        return SignalsAggregateStats(**json.loads(raw))

    # ------------- LLM summaries & events -------------

    async def add_llm_summary(self, summary: LLMSummary) -> None:
        raw = await self.client.get("state:llm_summaries")
        items = json.loads(raw) if raw else []
        items.append(summary.model_dump(mode="json"))
        await self.client.set("state:llm_summaries", json.dumps(items))
        await self.client.publish("streamhub:events", json.dumps(summary.model_dump(mode="json")))

    async def get_llm_summaries(self, limit: int = 10) -> List[dict]:
        raw = await self.client.get("state:llm_summaries")
        if not raw:
            return []
        data = json.loads(raw)
        return data[-limit:]

    # eval results reserved for future
