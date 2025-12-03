"""CEX orderbook collector with retry and health tracking."""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

import aiohttp

from config import get_config
from state.models import ExchangeHealth, ExchangeStats, OrderBook, OrderBookLevel
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class CEXCollector:
    def __init__(self, redis_state: RedisState) -> None:
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _fetch_orderbook(self, session: aiohttp.ClientSession, exchange: str, symbol: str) -> OrderBook:
        # Placeholder URL structure; in real deployment this would be exchange-specific.
        url = f"https://api.{exchange}.com/depth?symbol={symbol}&limit=5"
        async with session.get(url, timeout=self.cfg.collectors.http_timeout) as resp:
            data = await resp.json()
        bids = [OrderBookLevel(price=float(p), amount=float(a)) for p, a in data.get("bids", [])]
        asks = [OrderBookLevel(price=float(p), amount=float(a)) for p, a in data.get("asks", [])]
        return OrderBook(symbol=symbol, exchange=exchange, bids=bids, asks=asks)

    async def _collect_for_exchange(self, exchange: str) -> None:
        backoff = self.cfg.collectors.poll_interval
        async with aiohttp.ClientSession() as session:
            while not self._stop.is_set():
                for symbol in self.cfg.collectors.symbols:
                    try:
                        book = await self._fetch_orderbook(session, exchange, symbol)
                        await self.redis_state.set_order_book(book)
                        stats = ExchangeStats(exchange=exchange, health=ExchangeHealth.healthy, latency_ms=self.cfg.collectors.http_timeout * 1000)
                        await self.redis_state.upsert_exchange_stats(stats)
                        backoff = self.cfg.collectors.poll_interval
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("CEX collector error", exc_info=exc)
                        backoff = min(backoff * 2, self.cfg.collectors.max_backoff)
                        stats = ExchangeStats(exchange=exchange, health=ExchangeHealth.degraded, latency_ms=0.0, error_rate=1.0)
                        await self.redis_state.upsert_exchange_stats(stats)
                await asyncio.sleep(backoff)

    async def run(self) -> None:
        tasks = [asyncio.create_task(self._collect_for_exchange(ex)) for ex in self.cfg.collectors.exchanges]
        try:
            await asyncio.gather(*tasks)
        finally:
            self._stop.set()
            for task in tasks:
                task.cancel()

    def stop(self) -> None:
        self._stop.set()


async def run_cex_collector() -> None:
    collector = CEXCollector(RedisState())
    try:
        await collector.run()
    finally:
        await collector.redis_state.close()


__all__ = ["CEXCollector", "run_cex_collector"]
