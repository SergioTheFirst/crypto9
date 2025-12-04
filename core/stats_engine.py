from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime
from statistics import mean
from typing import Optional

from config import get_config
from state.redis_state import RedisState
from state.models import (
    ExchangeHealth,
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
            updated_ts: list[datetime] = []
            for ex, book in books.items():
                bids = book.get("bids") or []
                asks = book.get("asks") or []
                if not bids or not asks:
                    continue
                try:
                    best_bid = float(bids[0]["price"])
                    best_ask = float(asks[0]["price"])
                except Exception:
                    continue
                if any(
                    math.isnan(val) or val <= 0 for val in (best_bid, best_ask)
                ):
                    continue
                mids.append((best_bid + best_ask) / 2.0)
                ts_raw = book.get("timestamp") or book.get("ts")
                try:
                    if isinstance(ts_raw, datetime):
                        updated_ts.append(ts_raw)
                    elif ts_raw:
                        updated_ts.append(datetime.fromisoformat(ts_raw))
                except Exception:
                    continue
            if not mids:
                continue
            mid = sum(mids) / len(mids)
            stats.append(
                SymbolMarketStats(
                    symbol=symbol,
                    last_mid=mid,
                    volatility_1h=0.0,
                    updated_at=max(updated_ts) if updated_ts else datetime.utcnow(),
                )
            )
        return stats

    async def _compute_exchange_stats(self) -> list[ExchangeStats]:
        books = await self.redis_state.get_all_books()
        counts: dict[str, int] = {}
        newest_ts: dict[str, datetime] = {}
        for symbol, exs in books.items():
            for ex, book in exs.items():
                counts[ex] = counts.get(ex, 0) + 1
                ts_raw = book.get("timestamp") or book.get("ts")
                ts_val: Optional[datetime] = None
                if isinstance(ts_raw, datetime):
                    ts_val = ts_raw
                elif ts_raw:
                    try:
                        ts_val = datetime.fromisoformat(ts_raw)
                    except Exception:
                        ts_val = None
                if ts_val:
                    prev = newest_ts.get(ex)
                    if not prev or ts_val > prev:
                        newest_ts[ex] = ts_val

        stats: list[ExchangeStats] = []
        for ex in self.cfg.collectors.cex_exchanges:
            seen = counts.get(ex, 0)
            health = ExchangeHealth.excellent if seen > 0 else ExchangeHealth.offline
            stats.append(
                ExchangeStats(
                    name=ex,
                    health=health,
                    latency_ms=100.0 if seen else 0.0,
                    error_rate=0.0,
                    timeout_rate=0.0,
                    books_seen=seen,
                    updated_at=newest_ts.get(ex, datetime.utcnow()),
                )
            )
        return stats

    async def _compute_signal_stats(self) -> SignalsAggregateStats:
        signals = await self.redis_state.get_signals()
        active = len(signals)
        avg_profit = (
            sum(s.get("expected_profit_bps", 0.0) for s in signals) / active
            if active
            else 0.0
        )

        eval_results = await self.redis_state.get_all_eval_results()
        wins = len([r for r in eval_results if r.grade == "WIN"])
        losses = len([r for r in eval_results if r.grade == "LOSS"])
        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
        avg_final_profit = (
            mean([r.final_profit_usd for r in eval_results]) if eval_results else 0.0
        )

        return SignalsAggregateStats(
            total_signals=active,
            active_signals=active,
            avg_profit_bps=avg_profit,
            total_evaluated=len(eval_results),
            win_rate=win_rate,
            avg_final_profit_usd=avg_final_profit,
        )

    async def _update_system_status(
        self, market_stats: list[SymbolMarketStats], ex_stats: list[ExchangeStats]
    ):
        exchanges_dict = {e.name: e.health.value for e in ex_stats}
        overall = "ok"
        if any(e.health == ExchangeHealth.offline for e in ex_stats):
            overall = "degraded"
        if not market_stats:
            overall = "degraded"
        status = SystemStatus(
            status=overall,
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
