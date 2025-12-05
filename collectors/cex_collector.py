import asyncio
import logging
from datetime import datetime
from typing import Dict, Iterable

import aiohttp

from config import CONFIG, Config
from state.models import NormalizedBook
from state.redis_state import RedisState

logger = logging.getLogger("collectors.cex_collector")


async def _fetch_binance(session: aiohttp.ClientSession, symbol: str) -> NormalizedBook | None:
    url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit=5"
    async with session.get(url, timeout=5) as resp:
        resp.raise_for_status()
        data = await resp.json()
        bid = float(data["bids"][0][0])
        ask = float(data["asks"][0][0])
        bid_size = float(data["bids"][0][1])
        ask_size = float(data["asks"][0][1])
        return NormalizedBook(
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            exchange="binance",
            updated_at=datetime.utcnow(),
        )


async def _fetch_mexc(session: aiohttp.ClientSession, symbol: str) -> NormalizedBook | None:
    url = f"https://api.mexc.com/api/v3/depth?symbol={symbol}&limit=5"
    async with session.get(url, timeout=5) as resp:
        resp.raise_for_status()
        data = await resp.json()
        bid = float(data["bids"][0][0])
        ask = float(data["asks"][0][0])
        bid_size = float(data["bids"][0][1])
        ask_size = float(data["asks"][0][1])
        return NormalizedBook(
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            exchange="mexc",
            updated_at=datetime.utcnow(),
        )


EXCHANGE_FETCHERS = {
    "binance": _fetch_binance,
    "mexc": _fetch_mexc,
}


async def _collect_symbol(
    session: aiohttp.ClientSession,
    symbol: str,
    exchanges: Iterable[str],
) -> Dict[str, NormalizedBook]:
    books: Dict[str, NormalizedBook] = {}
    tasks = []
    for ex in exchanges:
        fetcher = EXCHANGE_FETCHERS.get(ex)
        if not fetcher:
            logger.warning("No fetcher for exchange %s", ex)
            continue
        tasks.append((ex, asyncio.create_task(fetcher(session, symbol))))

    for ex, task in tasks:
        try:
            book = await task
            if book:
                books[ex] = book
        except Exception as exc:
            logger.warning("Failed to fetch %s book for %s: %s", ex, symbol, exc)

    return books


async def _cycle(redis: RedisState, cfg: Config, session: aiohttp.ClientSession) -> None:
    for symbol in cfg.collector.symbols:
        books = await _collect_symbol(session, symbol, cfg.collector.exchanges)
        if books:
            await redis.set_books(symbol, books)
            logger.debug("Updated books for %s: %s", symbol, list(books.keys()))


async def run_cex_collector(
    redis: RedisState,
    cfg: Config = CONFIG,
) -> None:
    """
    CEX collector entrypoint.

    - Periodically polls supported exchanges for order books.
    - Normalizes books into a unified structure.
    - Persists results to Redis so engines can read them.
    """
    logger.info(
        "CEX collector started for symbols=%s, exchanges=%s",
        cfg.collector.symbols,
        cfg.collector.exchanges,
    )

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await _cycle(redis, cfg, session)
            except Exception as exc:
                logger.exception("CEX collector error: %s", exc)
                await asyncio.sleep(5.0)
            await asyncio.sleep(cfg.collector.cycle_sec)
