import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import aiohttp
from aiohttp import ClientError, ClientTimeout

from config import get_config
from state.redis_state import RedisState
from state.models import ExchangeHealth, ExchangeStats, NormalizedBook, OrderBook, OrderBookLevel

logger = logging.getLogger("collectors.cex_collector")
logger.setLevel(logging.INFO)


class CEXCollector:
    """
    Premium v9.1 Bulk CEX Collector
    - Binance bulk /api/v3/ticker/bookTicker
    - MEXC bulk /api/v3/ticker/bookTicker
    - Normalization rules: v8-grade
    - Health scoring
    - Adaptive cycle timing
    - Circuit breaker per exchange
    """

    def __init__(self, redis_state: RedisState):
        self.redis = redis_state
        self.cfg = get_config()
        self.symbols = self.cfg.collectors.symbols
        self.exchanges = self.cfg.collectors.cex_exchanges

        # exchange health data
        self.health = {
            ex: {
                "ok": True,
                "fails": 0,
                "latency": None,
                "class": "excellent",
            }
            for ex in self.exchanges
        }

        # circuit breaker per exchange
        self.cb_open = {ex: False for ex in self.exchanges}
        self.cb_open_ts = {ex: 0 for ex in self.exchanges}
        self.cb_timeout = 10  # seconds (bounded by [5, 30])

        self._timeout = ClientTimeout(total=4)
        self._max_retries = 3
        self._backoff_base = 0.5

    # ---------------------------------------------------------
    # Bulk fetchers
    # ---------------------------------------------------------
    async def _fetch_binance_bulk(self, session) -> Optional[Dict[str, OrderBook]]:
        return await self._fetch_with_retry(
            session,
            "binance",
            "https://api.binance.com/api/v3/ticker/bookTicker",
            bid_key="bidPrice",
            ask_key="askPrice",
            bid_size_key="bidQty",
            ask_size_key="askQty",
        )

    async def _fetch_mexc_bulk(self, session) -> Optional[Dict[str, OrderBook]]:
        return await self._fetch_with_retry(
            session,
            "mexc",
            "https://api.mexc.com/api/v3/ticker/bookTicker",
            bid_key="bidPrice",
            ask_key="askPrice",
            bid_size_key="bidQty",
            ask_size_key="askQty",
        )

    async def _fetch_with_retry(
        self,
        session: aiohttp.ClientSession,
        exchange: str,
        url: str,
        *,
        bid_key: str,
        ask_key: str,
        bid_size_key: str,
        ask_size_key: str,
    ) -> Optional[Dict[str, OrderBook]]:
        if self._is_circuit_open(exchange):
            return None

        backoff = self._backoff_base
        for attempt in range(1, self._max_retries + 1):
            t0 = time.time()
            try:
                async with session.get(url, timeout=self._timeout) as r:
                    r.raise_for_status()
                    data = await r.json()
                self._mark_success(exchange, latency=(time.time() - t0) * 1000)
                return self._parse_bulk_response(
                    exchange,
                    data,
                    bid_key=bid_key,
                    ask_key=ask_key,
                    bid_size_key=bid_size_key,
                    ask_size_key=ask_size_key,
                )
            except (asyncio.TimeoutError, ClientError, ValueError, KeyError, TypeError) as exc:
                self._mark_fail(exchange)
                if attempt >= self._max_retries:
                    logger.warning(
                        "exchange_request_failed",
                        extra={"exchange": exchange, "error": str(exc)},
                    )
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 4.0)
            except Exception as exc:
                self._mark_fail(exchange)
                logger.error(
                    "exchange_request_unexpected_error",
                    extra={"exchange": exchange, "error": str(exc)},
                )
                break
        return None

    def _parse_bulk_response(
        self,
        exchange: str,
        data: List[dict],
        *,
        bid_key: str,
        ask_key: str,
        bid_size_key: str,
        ask_size_key: str,
    ) -> Dict[str, OrderBook]:
        out: Dict[str, OrderBook] = {}
        for item in data:
            sym = item.get("symbol")
            if not sym or sym not in self.symbols:
                continue
            normalized = self._normalize_book(
                exchange,
                {
                    "bid": item.get(bid_key),
                    "ask": item.get(ask_key),
                    "bid_size": item.get(bid_size_key),
                    "ask_size": item.get(ask_size_key),
                },
            )
            if normalized:
                out[sym] = self._normalized_to_orderbook(sym, normalized)
        return out

    def _normalized_to_orderbook(self, symbol: str, book: NormalizedBook) -> OrderBook:
        return OrderBook(
            symbol=symbol,
            exchange=book.exchange,
            bids=[OrderBookLevel(price=book.bid, amount=book.bid_size)],
            asks=[OrderBookLevel(price=book.ask, amount=book.ask_size)],
            timestamp=book.ts,
        )

    # ---------------------------------------------------------
    # Normalization (v8-level)
    # ---------------------------------------------------------
    def _normalize_book(self, exchange: str, raw: dict) -> Optional[NormalizedBook]:
        try:
            bid = float(raw["bid"])
            ask = float(raw["ask"])
            bid_size = float(raw["bid_size"])
            ask_size = float(raw["ask_size"])
        except Exception:
            return None

        # invalid prices
        if bid <= 0 or ask <= 0:
            return None

        # minimal sizes
        if bid_size <= 0:
            bid_size = 0.0001
        if ask_size <= 0:
            ask_size = 0.0001

        return NormalizedBook(
            exchange=exchange,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            ts=datetime.utcnow(),
        )

    # ---------------------------------------------------------
    # Exchange health
    # ---------------------------------------------------------
    def _mark_success(self, ex: str, latency: float):
        self.health[ex]["ok"] = True
        self.health[ex]["latency"] = latency
        self.health[ex]["fails"] = 0
        self.health[ex]["class"] = "excellent"
        self.cb_open[ex] = False

    def _mark_fail(self, ex: str):
        self.health[ex]["fails"] += 1
        if self.health[ex]["fails"] >= 3:
            self.cb_open[ex] = True
            self.cb_open_ts[ex] = time.time()
        self.health[ex]["class"] = "fail"

    async def _update_exchange_stats(self):
        stats: List[ExchangeStats] = []
        for ex, info in self.health.items():
            f = info["fails"]
            if f == 0:
                health = ExchangeHealth.excellent
            elif f <= 2:
                health = ExchangeHealth.unstable
            else:
                health = ExchangeHealth.offline

            stats.append(
                ExchangeStats(
                    name=ex,
                    health=health,
                    latency_ms=float(info["latency"] or 0.0),
                    error_rate=float(f),
                    timeout_rate=0.0,
                    books_seen=0,
                    updated_at=datetime.utcnow(),
                )
            )

        await self.redis.set_exchange_stats(stats)

    # ---------------------------------------------------------
    # Main cycle
    # ---------------------------------------------------------
    async def _cycle(self):
        async with aiohttp.ClientSession() as session:
            tasks: List[Tuple[str, asyncio.Future]] = []
            fetchers = {
                "binance": self._fetch_binance_bulk,
                "mexc": self._fetch_mexc_bulk,
            }

            for ex in self.exchanges:
                fetcher = fetchers.get(ex)
                if not fetcher:
                    continue
                if self._is_circuit_open(ex):
                    continue
                tasks.append((ex, asyncio.create_task(fetcher(session))))

            results = await asyncio.gather(
                *(t[1] for t in tasks), return_exceptions=True
            )

            merged_books: Dict[str, Dict[str, OrderBook]] = {}

            for (ex, _), res in zip(tasks, results):
                if isinstance(res, Exception):
                    logger.error(
                        "collector_task_failed", extra={"exchange": ex, "error": str(res)}
                    )
                    self._mark_fail(ex)
                    continue
                if isinstance(res, dict):
                    for sym, book in res.items():
                        merged_books.setdefault(sym, {})[ex] = book

            # store normalized books per symbol preserving exchange order
            for sym in self.symbols:
                sym_books = merged_books.get(sym, {})
                ex_books: Dict[str, OrderBook] = {}
                for ex in self.exchanges:
                    book = sym_books.get(ex)
                    if book:
                        ex_books[ex] = book

                if ex_books:
                    await self.redis.set_books(sym, ex_books)

        await self._update_exchange_stats()

    # ---------------------------------------------------------
    # Circuit breaker
    # ---------------------------------------------------------
    def _check_circuit_breaker(self):
        t = time.time()
        for ex in self.exchanges:
            if self.cb_open[ex] and (t - self.cb_open_ts[ex] >= self.cb_timeout):
                self.cb_open[ex] = False
                self.health[ex]["fails"] = 0

    def _is_circuit_open(self, ex: str) -> bool:
        if not self.cb_open[ex]:
            return False
        t = time.time()
        if t - self.cb_open_ts[ex] >= max(5, min(self.cb_timeout, 30)):
            self.cb_open[ex] = False
            self.health[ex]["fails"] = 0
            return False
        return True

    # ---------------------------------------------------------
    # Adaptive cycle timing
    # ---------------------------------------------------------
    def _cycle_delay(self) -> float:
        total_fails = sum(v["fails"] for v in self.health.values())
        if total_fails == 0:
            return 1.5
        if total_fails <= 5:
            return 4
        return 12

    # ---------------------------------------------------------
    # Public runner
    # ---------------------------------------------------------
    async def run(self):
        logger.info(f"CEX collector started for symbols={self.symbols}, exchanges={self.exchanges}")

        while True:
            try:
                self._check_circuit_breaker()
                await self._cycle()
            except Exception as e:
                logger.error(f"CEX collector error: {e}", exc_info=True)

            await asyncio.sleep(self._cycle_delay())


async def run_cex_collector(redis_state: RedisState):
    collector = CEXCollector(redis_state)
    await collector.run()
