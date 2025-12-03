"""Deterministic signal generation engine."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict, List, Tuple

from config import get_config
from state.models import OrderBook, RouteQuote, Signal, SignalSeverity
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


def _best_bid_ask(books: List[OrderBook]) -> Tuple[OrderBook | None, OrderBook | None]:
    best_bid: Tuple[float, OrderBook] | None = None
    best_ask: Tuple[float, OrderBook] | None = None
    for book in books:
        if book.bids:
            price = book.bids[0].price
            if best_bid is None or price > best_bid[0]:
                best_bid = (price, book)
        if book.asks:
            price = book.asks[0].price
            if best_ask is None or price < best_ask[0]:
                best_ask = (price, book)
    return (best_bid[1] if best_bid else None, best_ask[1] if best_ask else None)


def _compute_profit_bps(buy: float, sell: float) -> float:
    return (sell - buy) / buy * 10_000


class CoreEngine:
    def __init__(self, redis_state: RedisState) -> None:
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()
        self._confirmations: Dict[str, int] = {}

    async def _load_books(self, symbol: str) -> List[OrderBook]:
        books: List[OrderBook] = []
        for exchange in self.cfg.collectors.exchanges:
            book = await self.redis_state.get_order_book(exchange, symbol)
            if book:
                books.append(book)
        if self.cfg.collectors.enable_dex:
            dex_book = await self.redis_state.get_order_book("dex", symbol)
            if dex_book:
                books.append(dex_book)
        return books

    async def _evaluate_symbol(self, symbol: str) -> None:
        books = await self._load_books(symbol)
        if len(books) < 2:
            return
        best_bid_book, best_ask_book = _best_bid_ask(books)
        if not best_bid_book or not best_ask_book:
            return
        if best_bid_book.exchange == best_ask_book.exchange:
            return
        profit_bps = _compute_profit_bps(best_ask_book.asks[0].price, best_bid_book.bids[0].price)
        if profit_bps < self.cfg.engine.min_profit_bps:
            return
        volume = min(best_bid_book.bids[0].amount, best_ask_book.asks[0].amount) * best_ask_book.asks[0].price
        if volume < self.cfg.engine.min_volume_usd:
            return
        route = RouteQuote(
            symbol=symbol,
            buy_exchange=best_ask_book.exchange,
            sell_exchange=best_bid_book.exchange,
            buy_price=best_ask_book.asks[0].price,
            sell_price=best_bid_book.bids[0].price,
            spread_bps=profit_bps,
            volume_usd=volume,
        )
        key = f"{symbol}:{route.buy_exchange}:{route.sell_exchange}"
        count = self._confirmations.get(key, 0) + 1
        self._confirmations[key] = count
        if count < self.cfg.engine.confirm_window:
            return
        severity = SignalSeverity.critical if profit_bps >= self.cfg.telegram.profit_threshold_bps else SignalSeverity.elevated
        signal = Signal(
            id=str(uuid.uuid4()),
            route=route,
            confidence=min(1.0, count / (self.cfg.engine.confirm_window + 1)),
            expected_profit_bps=profit_bps,
            expected_profit_usd=volume * profit_bps / 10_000,
            status="confirmed",
            severity=severity,
        )
        await self.redis_state.set_signal(signal)
        self._confirmations[key] = 0
        logger.info("Generated signal %s", signal.id)

    async def run(self) -> None:
        while not self._stop.is_set():
            for symbol in self.cfg.collectors.symbols:
                await self._evaluate_symbol(symbol)
            await asyncio.sleep(self.cfg.collectors.poll_interval)

    def stop(self) -> None:
        self._stop.set()


async def run_core_engine() -> None:
    engine = CoreEngine(RedisState())
    try:
        await engine.run()
    finally:
        await engine.redis_state.close()


__all__ = ["CoreEngine", "run_core_engine"]
