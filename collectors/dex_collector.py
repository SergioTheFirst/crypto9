"""Optional DEX collector with graceful degradation."""
from __future__ import annotations

import asyncio
import logging
from typing import List

import aiohttp

from config import get_config
from state.models import ExchangeHealth, ExchangeStats, OrderBook, OrderBookLevel
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class DEXCollector:
    def __init__(self, redis_state: RedisState) -> None:
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _fetch_quote(self, session: aiohttp.ClientSession, symbol: str) -> OrderBook:
        # DEX endpoints are optional; this is a stub that simulates a shallow book.
        url = f"https://dex.example.com/quote?symbol={symbol}"
        async with session.get(url, timeout=self.cfg.collectors.http_timeout) as resp:
            data = await resp.json()
        bids = [OrderBookLevel(price=float(data["bid"]), amount=float(data.get("bid_size", 0.0)))]
        asks = [OrderBookLevel(price=float(data["ask"]), amount=float(data.get("ask_size", 0.0)))]
        return OrderBook(symbol=symbol, exchange="dex", bids=bids, asks=asks)

    async def _run_once(self) -> None:
        async with aiohttp.ClientSession() as session:
            for symbol in self.cfg.collectors.symbols:
                try:
                    book = await self._fetch_quote(session, symbol)
                    await self.redis_state.set_order_book(book)
                    stats = ExchangeStats(exchange="dex", health=ExchangeHealth.healthy, latency_ms=self.cfg.collectors.http_timeout * 1000)
                    await self.redis_state.upsert_exchange_stats(stats)
                except Exception as exc:  # noqa: BLE001
                    logger.info("DEX collector unavailable", exc_info=exc)
                    stats = ExchangeStats(exchange="dex", health=ExchangeHealth.degraded, latency_ms=0.0, error_rate=1.0)
                    await self.redis_state.upsert_exchange_stats(stats)
                await asyncio.sleep(self.cfg.collectors.poll_interval)

    async def run(self) -> None:
        if not self.cfg.collectors.enable_dex:
            logger.info("DEX collector disabled via configuration")
            return
        while not self._stop.is_set():
            await self._run_once()

    def stop(self) -> None:
        self._stop.set()


async def run_dex_collector() -> None:
    collector = DEXCollector(RedisState())
    try:
        await collector.run()
    finally:
        await collector.redis_state.close()


__all__ = ["DEXCollector", "run_dex_collector"]
