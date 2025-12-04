from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from config import get_config
from state.redis_state import RedisState
from state.models import (
    ExchangeStats,
    SignalsAggregateStats,
    SymbolMarketStats,
    SystemStatus,
)

logger = logging.getLogger(__name__)


class StatsEngine:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _compute_market_stats(self) -> list[SymbolMarketStats]:
        stats: list[SymbolMarketStats] = []
        for symbol in self.cfg.collectors.symbols:
            books = await self.redis_state.get_books(symbol)
            if not books:
                continue
            mids = []
            for ex, book in books.items():
                bids = book.get("bids") or []
                asks = book.get("asks") or []
                if not bids or not asks:
                    continue
                best_bid = bids[0]["price"]
                best_ask = asks[0]["price"]
                mids.append((best_bid + best_ask) / 2.0)
            if not mids:
                continue
            mid = sum(mids) / len(mids)
            stats.append(
                SymbolMarketStats(symbol=symbol, last_mid=mid, volatility_1h=0.0)
            )
        return stats

    async def _compute_exchange_stats(self) -> list[ExchangeStats]:
        books = await self.redis_state.get_all_books()
        counts: dict[str, int] = {}
        for symbol, exs in books.items():
            for ex in exs.keys():
                counts[ex] = counts.get(ex, 0) + 1

        stats: list[ExchangeStats] = []
        for ex in self.cfg.collectors.cex_exchanges:
            seen = counts.get(ex, 0)
            health = "excellent" if seen > 0 else "unstable"
            stats.append(
                ExchangeStats(
                    name=ex,
                    health=health,
                    latency_ms=100.0,
                    error_rate=0.0,
                    timeout_rate=0.0,
                    books_seen=seen,
                )
            )
        return stats

    async def _compute_signal_stats(self) -> SignalsAggregateStats:
        signals = await self.redis_state.get_signals()
        active = len(signals)
        avg_profit = 0.0
        if active:
            avg_profit = sum(s.get("expected_profit_bps", 0.0) for s in signals) / active
        return SignalsAggregateStats(
            total_signals=active,
            active_signals=active,
            avg_profit_bps=avg_profit,
        )

    async def _update_system_status(
        self, market_stats: list[SymbolMarketStats], ex_stats: list[ExchangeStats]
    ):
        exchanges_dict = {e.name: e.health.value for e in ex_stats}
        status = SystemStatus(
            status="ok",
            redis="ok",
            llm="enabled" if self.cfg.llm.enabled else "disabled",
            telegram="enabled" if self.cfg.telegram.enabled else "disabled",
            dex="enabled" if self.cfg.collectors.dex_enabled else "disabled",
            symbols=len(market_stats),
            exchanges=exchanges_dict,
            last_update_ts=datetime.utcnow(),
        )
        await self.redis_state.set_system_status(status)
        # also publish to streamhub:system
        await self.redis_state.client.publish(
            "streamhub:system", status.model_dump_json()
        )

    async def _tick(self):
        market_stats = await self._compute_market_stats()
        ex_stats = await self._compute_exchange_stats()
        sig_stats = await self._compute_signal_stats()

        await self.redis_state.set_market_stats(market_stats)
        await self.redis_state.set_exchange_stats(ex_stats)
        await self.redis_state.set_signal_stats(sig_stats)
        await self._update_system_status(market_stats, ex_stats)

    async def run(self):
        logger.info("Stats engine started")
        interval = self.cfg.engine.stats_interval
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:
                logger.exception("Stats engine error: %s", e)
            await asyncio.sleep(interval)

    def stop(self):
        self._stop.set()


async def run_stats_engine(redis_state: RedisState):
    engine = StatsEngine(redis_state)
    await engine.run()
