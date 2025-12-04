from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from itertools import permutations
from typing import Dict, List, Tuple

from config import get_config
from state.models import OrderBook, OrderBookLevel, Route, Signal, SignalSeverity
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


def _clean_levels(levels: List[OrderBookLevel]) -> List[OrderBookLevel]:
    cleaned: List[OrderBookLevel] = []
    for lvl in levels:
        if any(
            math.isnan(val) or val <= 0.0 for val in (float(lvl.price), float(lvl.amount))
        ):
            continue
        cleaned.append(lvl)
    return cleaned


def _normalize_book(book: OrderBook, max_age: int) -> OrderBook | None:
    if not book.bids or not book.asks:
        return None

    bids = _clean_levels(book.bids)
    asks = _clean_levels(book.asks)

    if not bids or not asks:
        return None

    best_bid = bids[0].price
    best_ask = asks[0].price

    if any(math.isnan(val) or val <= 0.0 for val in (float(best_bid), float(best_ask))):
        return None

    if best_bid >= best_ask:
        return None

    age = datetime.utcnow() - book.timestamp
    if age > timedelta(seconds=max_age):
        return None

    return OrderBook(
        symbol=book.symbol,
        exchange=book.exchange,
        bids=bids,
        asks=asks,
        timestamp=book.timestamp,
    )


def _available_notional(buy_book: OrderBook, sell_book: OrderBook) -> float:
    buy_level = buy_book.asks[0]
    sell_level = sell_book.bids[0]
    qty = min(buy_level.amount, sell_level.amount)
    return float(qty * buy_level.price)


def _slippage_bps(volume_usd: float) -> float:
    # deterministic, volume-linked slippage in bps
    return min(50.0, math.sqrt(max(volume_usd, 0.0)) / 25.0)


def compute_route_profit(
    buy_book: OrderBook,
    sell_book: OrderBook,
    notional_usd: float,
    fee_buy: float,
    fee_sell: float,
    withdraw_fee_usd: float,
) -> Tuple[float, float, float]:
    if notional_usd <= 0:
        return 0.0, 0.0, 0.0

    buy_price = float(buy_book.asks[0].price)
    sell_price = float(sell_book.bids[0].price)
    qty = notional_usd / buy_price

    gross_revenue = qty * sell_price
    gross_cost = notional_usd

    buy_fee = gross_cost * fee_buy
    sell_fee = gross_revenue * fee_sell
    slippage_cost = gross_cost * (_slippage_bps(notional_usd) / 10_000.0)

    profit_usd = gross_revenue - gross_cost - buy_fee - sell_fee - withdraw_fee_usd - slippage_cost
    profit_bps = (profit_usd / gross_cost) * 10_000.0 if gross_cost else 0.0
    spread_bps = ((sell_price - buy_price) / buy_price) * 10_000.0 if buy_price else 0.0

    return profit_usd, profit_bps, spread_bps


class CoreEngine:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _compute_signals_for_symbol(self, symbol: str) -> List[Signal]:
        books = await self.redis_state.get_books(symbol)
        if not books:
            return []

        normalized: Dict[str, OrderBook] = {}
        for ex, book in books.items():
            normalized_book = _normalize_book(book, self.cfg.engine.max_book_age_sec)
            if normalized_book:
                normalized[ex] = normalized_book

        exchanges = list(normalized.keys())
        if len(exchanges) < 2:
            return []

        signals: List[Signal] = []
        notional_cap = float(self.cfg.engine.volume_cap_usd)
        min_volume = float(self.cfg.engine.min_volume_usd)

        for buy_ex, sell_ex in permutations(exchanges, 2):
            buy_book = normalized[buy_ex]
            sell_book = normalized[sell_ex]

            available_usd = _available_notional(buy_book, sell_book)
            volume_usd = min(notional_cap, available_usd)
            if volume_usd < min_volume:
                continue

            fee_buy = self.cfg.fees.get(buy_ex, {}).get("taker", 0.001)
            fee_sell = self.cfg.fees.get(sell_ex, {}).get("taker", 0.001)
            withdraw_fee = self.cfg.fees.get(sell_ex, {}).get("withdraw", 0.0)

            profit_usd, profit_bps, spread_bps = compute_route_profit(
                buy_book=buy_book,
                sell_book=sell_book,
                notional_usd=volume_usd,
                fee_buy=fee_buy,
                fee_sell=fee_sell,
                withdraw_fee_usd=withdraw_fee,
            )

            if profit_usd <= 0:
                continue
            if profit_bps < self.cfg.engine.min_profit_bps:
                continue
            if spread_bps < self.cfg.engine.spread_threshold_bps:
                continue

            severity = (
                SignalSeverity.critical
                if profit_bps >= self.cfg.telegram.profit_threshold_bps
                else SignalSeverity.elevated
            )
            tags = ["spread"]
            if volume_usd > (notional_cap * 0.5):
                tags.append("high_volume")

            route = Route(
                symbol=symbol,
                buy_exchange=buy_ex,
                sell_exchange=sell_ex,
                buy_price=buy_book.asks[0].price,
                sell_price=sell_book.bids[0].price,
                volume_usd=volume_usd,
            )
            signal_id = f"{symbol}_{buy_ex}_{sell_ex}_{int(datetime.utcnow().timestamp())}"
            signal = Signal(
                id=signal_id,
                symbol=symbol,
                route=route,
                expected_profit_bps=profit_bps,
                expected_profit_usd=profit_usd,
                spread_bps=spread_bps,
                profit_usd=profit_usd,
                volume_usd=volume_usd,
                confidence=0.9,
                severity=severity,
                tags=tags,
            )
            signals.append(signal)

        return signals

    async def _cycle(self):
        all_signals: List[Signal] = []
        for symbol in self.cfg.collectors.symbols:
            sigs = await self._compute_signals_for_symbol(symbol)
            all_signals.extend(sigs)

        await self.redis_state.set_signals(all_signals)
        for sig in all_signals:
            await self.redis_state.client.publish("streamhub:signals", sig.model_dump_json())

    async def run(self):
        logger.info("Core engine started")
        while not self._stop.is_set():
            try:
                await self._cycle()
            except Exception as e:
                logger.exception("Core engine error: %s", e)
            await asyncio.sleep(1.0)

    def stop(self):
        self._stop.set()


async def run_core_engine(redis_state: RedisState):
    engine = CoreEngine(redis_state)
    await engine.run()
