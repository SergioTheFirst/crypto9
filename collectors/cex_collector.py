import asyncio
import aiohttp
import time
from typing import Dict, List, Optional
from config import CONFIG
from state.redis_state import RedisState
from state.models import NormalizedBook
import logging

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
        self.symbols = CONFIG.symbols
        self.exchanges = CONFIG.exchanges

        # exchange health data
        self.health = {
            ex: {
                "ok": True,
                "fails": 0,
                "latency": None,
                "class": "excellent"
            }
            for ex in self.exchanges
        }

        # circuit breaker per exchange
        self.cb_open = {ex: False for ex in self.exchanges}
        self.cb_open_ts = {ex: 0 for ex in self.exchanges}
        self.cb_timeout = 10  # seconds

    # ---------------------------------------------------------
    # Bulk fetchers
    # ---------------------------------------------------------
    async def _fetch_binance_bulk(self, session) -> Dict[str, dict]:
        url = "https://api.binance.com/api/v3/ticker/bookTicker"
        t0 = time.time()
        try:
            async with session.get(url, timeout=3) as r:
                data = await r.json()
        except Exception:
            self._mark_fail("binance")
            return {}

        self._mark_success("binance", latency=(time.time() - t0) * 1000)

        out = {}
        for item in data:
            sym = item["symbol"]
            if sym in self.symbols:
                out[sym] = {
                    "bid": float(item["bidPrice"]),
                    "bid_size": float(item["bidQty"]),
                    "ask": float(item["askPrice"]),
                    "ask_size": float(item["askQty"])
                }
        return out

    async def _fetch_mexc_bulk(self, session) -> Dict[str, dict]:
        url = "https://api.mexc.com/api/v3/ticker/bookTicker"
        t0 = time.time()

        try:
            async with session.get(url, timeout=3) as r:
                data = await r.json()
        except Exception:
            self._mark_fail("mexc")
            return {}

        self._mark_success("mexc", latency=(time.time() - t0) * 1000)

        out = {}
        for item in data:
            sym = item["symbol"]
            if sym in self.symbols:
                out[sym] = {
                    "bid": float(item["bidPrice"]),
                    "bid_size": float(item["bidQty"]),
                    "ask": float(item["askPrice"]),
                    "ask_size": float(item["askQty"])
                }
        return out

    # ---------------------------------------------------------
    # Normalization (v8-level)
    # ---------------------------------------------------------
    def _normalize_book(self, raw: dict) -> Optional[NormalizedBook]:
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

        mid = (bid + ask) / 2
        liquidity = (bid_size + ask_size) * mid

        return NormalizedBook(
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            mid=mid,
            liquidity_score=liquidity
        )

    # ---------------------------------------------------------
    # Exchange health
    # ---------------------------------------------------------
    def _mark_success(self, ex: str, latency: float):
        self.health[ex]["ok"] = True
        self.health[ex]["latency"] = latency
        self.health[ex]["fails"] = 0
        self.health[ex]["class"] = "excellent"

    def _mark_fail(self, ex: str):
        self.health[ex]["fails"] += 1
        if self.health[ex]["fails"] >= 3:
            self.cb_open[ex] = True
            self.cb_open_ts[ex] = time.time()
        self.health[ex]["class"] = "fail"

    async def _update_exchange_stats(self):
        stats = []
        for ex, info in self.health.items():
            cls = "excellent"
            f = info["fails"]
            if f == 0:
                cls = "excellent"
            elif f <= 2:
                cls = "warn"
            else:
                cls = "fail"

            stats.append({
                "name": ex,
                "class": cls,
                "latency_ms": info["latency"] or 0.0,
                "error_rate": f,
                "updated_at": time.time(),
            })

        await self.redis.set_exchange_stats(stats)

    # ---------------------------------------------------------
    # Main cycle
    # ---------------------------------------------------------
    async def _cycle(self):
        async with aiohttp.ClientSession() as session:

            # fetch all exchanges
            tasks = []
            if "binance" in self.exchanges and not self.cb_open["binance"]:
                tasks.append(self._fetch_binance_bulk(session))

            if "mexc" in self.exchanges and not self.cb_open["mexc"]:
                tasks.append(self._fetch_mexc_bulk(session))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            merged_books = {}

            for res in results:
                if isinstance(res, dict):
                    for sym, book in res.items():
                        if sym not in merged_books:
                            merged_books[sym] = {}
                        merged_books[sym].update({res: book})

            # normalize + store
            for sym in self.symbols:
                ex_books = {}
                for ex in self.exchanges:
                    if sym in merged_books and ex in merged_books[sym]:
                        nb = self._normalize_book(merged_books[sym][ex])
                        if nb:
                            ex_books[ex] = nb.model_dump()

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
