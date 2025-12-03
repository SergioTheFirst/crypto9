"""Generates system and market statistics for observability."""
from __future__ import annotations

import asyncio
import logging
from typing import List

from config import get_config
from state.models import ExchangeStats, MarketStats, SystemStats
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class StatsEngine:
    def __init__(self, redis_state: RedisState) -> None:
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _compute_market_stats(self) -> List[MarketStats]:
        stats: List[MarketStats] = []
        for symbol in self.cfg.collectors.symbols:
            bids = []
            asks = []
            for exchange in self.cfg.collectors.exchanges + (["dex"] if self.cfg.collectors.enable_dex else []):
                book = await self.redis_state.get_order_book(exchange, symbol)
                if not book or not book.bids or not book.asks:
                    continue
                bids.append(book.bids[0].price)
                asks.append(book.asks[0].price)
            if not bids or not asks:
                continue
            mid = (max(bids) + min(asks)) / 2
            volatility = (max(bids) - min(asks)) / mid if mid else 0.0
            stats.append(MarketStats(symbol=symbol, volatility=volatility, mid_price=mid))
        return stats

    async def _tick(self) -> None:
        redis_ok = await self.redis_state.ping()
        exchange_stats = await self.redis_state.get_exchange_stats()
        market_stats = await self._compute_market_stats()
        system_stats = SystemStats(
            redis_ok=redis_ok,
            active_exchanges=[s.exchange for s in exchange_stats],
            active_symbols=self.cfg.collectors.symbols,
            total_signals=len(await self.redis_state.recent_signals(1_000)),
            exchange_stats=exchange_stats,
            market_stats=market_stats,
        )
        await self.redis_state.set_system_stats(system_stats)
        logger.debug("Updated system stats")

    async def run(self) -> None:
        while not self._stop.is_set():
            await self._tick()
            await asyncio.sleep(self.cfg.engine.stats_interval)

    def stop(self) -> None:
        self._stop.set()


async def run_stats_engine() -> None:
    engine = StatsEngine(RedisState())
    try:
        await engine.run()
    finally:
        await engine.redis_state.close()


__all__ = ["StatsEngine", "run_stats_engine"]
