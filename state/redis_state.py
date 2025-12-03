"""Typed Redis access layer for Crypto Intel Premium v9."""
from __future__ import annotations

import asyncio
import json
from typing import List, Optional

from redis.asyncio import Redis

from config import get_config
from state.models import (
    ExchangeStats,
    LLMSummary,
    OrderBook,
    Signal,
    SystemStats,
)


class RedisState:
    """Provides typed access to Redis-backed state."""

    def __init__(self, redis: Optional[Redis] = None) -> None:
        cfg = get_config().redis
        self._redis = redis or Redis.from_url(
            cfg.url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=cfg.connection_timeout,
            health_check_interval=cfg.health_check_interval,
        )
        self._pubsub_channel = "events"

    @property
    def redis(self) -> Redis:
        return self._redis

    async def close(self) -> None:
        await self._redis.aclose()

    async def set_order_book(self, book: OrderBook) -> None:
        key = f"book:{book.exchange}:{book.symbol}"
        await self._redis.set(key, book.model_dump_json())
        await self._redis.publish(self._pubsub_channel, json.dumps({"type": "book", "key": key}))

    async def get_order_book(self, exchange: str, symbol: str) -> Optional[OrderBook]:
        data = await self._redis.get(f"book:{exchange}:{symbol}")
        if not data:
            return None
        return OrderBook.model_validate_json(data)

    async def set_signal(self, signal: Signal) -> None:
        await self._redis.set(f"signal:{signal.id}", signal.model_dump_json())
        await self._redis.lpush("signals", signal.model_dump_json())
        await self._redis.ltrim("signals", 0, 499)
        await self._redis.publish(self._pubsub_channel, json.dumps({"type": "signal", "id": signal.id}))

    async def get_signal(self, signal_id: str) -> Optional[Signal]:
        data = await self._redis.get(f"signal:{signal_id}")
        if not data:
            return None
        return Signal.model_validate_json(data)

    async def recent_signals(self, limit: int = 50) -> List[Signal]:
        entries = await self._redis.lrange("signals", 0, limit - 1)
        return [Signal.model_validate_json(e) for e in entries]

    async def set_system_stats(self, stats: SystemStats) -> None:
        await self._redis.set("stats:system", stats.model_dump_json())
        await self._redis.publish(self._pubsub_channel, json.dumps({"type": "stats"}))

    async def get_system_stats(self) -> Optional[SystemStats]:
        data = await self._redis.get("stats:system")
        if not data:
            return None
        return SystemStats.model_validate_json(data)

    async def upsert_exchange_stats(self, stats: ExchangeStats) -> None:
        await self._redis.hset("stats:exchange", stats.exchange, stats.model_dump_json())

    async def get_exchange_stats(self) -> List[ExchangeStats]:
        raw = await self._redis.hvals("stats:exchange")
        return [ExchangeStats.model_validate_json(item) for item in raw]

    async def store_llm_summary(self, summary: LLMSummary) -> None:
        await self._redis.lpush("llm:summaries", summary.model_dump_json())
        await self._redis.ltrim("llm:summaries", 0, 19)
        await self._redis.publish(self._pubsub_channel, json.dumps({"type": "llm_summary", "id": summary.id}))

    async def recent_llm_summaries(self, limit: int = 5) -> List[LLMSummary]:
        entries = await self._redis.lrange("llm:summaries", 0, limit - 1)
        return [LLMSummary.model_validate_json(e) for e in entries]

    async def subscribe_events(self):
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._pubsub_channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield message["data"]
        finally:
            await pubsub.unsubscribe(self._pubsub_channel)
            await pubsub.close()

    async def ping(self) -> bool:
        try:
            await asyncio.wait_for(self._redis.ping(), timeout=2)
            return True
        except Exception:
            return False


__all__ = ["RedisState"]
