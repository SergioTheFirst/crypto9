from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta
from itertools import permutations
from typing import Dict, List, Optional, Tuple

from config import get_config
from state.models import OrderBook, OrderBookLevel, Route, Signal, SignalSeverity
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


def _clean_levels(levels: List[OrderBookLevel]) -> List[OrderBookLevel]:
    cleaned: List[OrderBookLevel] = []
    for lvl in levels:
        if any(
            math.isnan(val) or val <= 0.0
            for val in (float(lvl.price), float(lvl.amount))
        ):
            continue
        cleaned.append(lvl)
    return cleaned


def _normalize_book(book: OrderBook, max_age: int) -> Optional[OrderBook]:
    if not book.bids or not book.asks:
        return None

    book.bids = _clean_levels(book.bids)
    book.asks = _clean_levels(book.asks)

    if not book.bids or not book.asks:
        return None

    best_bid = book.bids[0].price
    best_ask = book.asks[0].price

    if any(
        math.isnan(val) or val <= 0.0
        for val in (float(best_bid), float(best_ask))
    ):
        return None

    if best_bid >= best_ask:
        return None

    age = datetime.utcnow() - book.timestamp
    if age > timedelta(seconds=max_age):
        return None

    return book


def _compute_slippage(volume_usd: float) -> float:
    return 0.5 * math.sqrt(max(volume_usd, 0.0) / 10_000.0)


def simulate_trade(
    buy_book: OrderBook,
    sell_book: OrderBook,
    notional_usd: float,
    fee_buy: float,
    fee_sell: float,
    withdraw_fee: float,
) -> Tuple[float, float, float, float]:
    if notional_usd <= 0:
        return 0.0, 0.0, 0.0, 0.0

    bids = sell_book.bids
    asks = buy_book.asks
    if not bids or not asks:
        return 0.0, 0.0, 0.0, 0.0

    remaining_notional = notional_usd
    bought_qty = 0.0
    spent_usd = 0.0

    for lvl in asks:
        max_lvl_notional = lvl.price * lvl.amount
        if max_lvl_notional >= remaining_notional:
            qty = remaining_notional / lvl.price
            bought_qty += qty
            spent_usd += remaining_notional
            remaining_notional = 0.0
            break
        bought_qty += lvl.amount
        spent_usd += max_lvl_notional
        remaining_notional -= max_lvl_notional

    if bought_qty <= 0.0:
        return 0.0, 0.0, 0.0, 0.0

    remaining_qty = bought_qty
    received_usd = 0.0

    for lvl in bids:
        tradable_qty = min(remaining_qty, lvl.amount)
        received_usd += tradable_qty * lvl.price
        remaining_qty -= tradable_qty
        if remaining_qty <= 0:
            break

    if remaining_qty > 0.0:
        return 0.0, 0.0, 0.0, 0.0

    avg_buy_price = spent_usd / bought_qty
    avg_sell_price = received_usd / bought_qty if bought_qty else 0.0

    buy_fee = spent_usd * fee_buy
    sell_fee = received_usd * fee_sell
    slippage = _compute_slippage(notional_usd)

    gross = bought_qty * (avg_sell_price - avg_buy_price)
    profit_usd = gross - buy_fee - sell_fee - withdraw_fee - slippage
    profit_bps = (profit_usd / spent_usd) * 10_000.0 if spent_usd > 0 else 0.0

    spread_bps = ((avg_sell_price - avg_buy_price) / avg_buy_price) * 10_000.0

    return bought_qty, profit_usd, profit_bps, spread_bps


class CoreEngine:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _compute_signals_for_symbol(self, symbol: str) -> List[Signal]:
        books_raw = await self.redis_state.get_books(symbol)
        if not books_raw:
            return []

        normalized: Dict[str, OrderBook] = {}
        for ex, data in books_raw.items():
            try:
                ob = OrderBook(**data)
            except Exception:
                continue
            normalized_book = _normalize_book(ob, self.cfg.engine.max_book_age_sec)
            if normalized_book:
                normalized[ex] = normalized_book

        exchanges = list(normalized.keys())
        if len(exchanges) < 2:
            return []

        signals: List[Signal] = []
        notional = float(self.cfg.engine.volume_cap_usd)

        for buy_ex, sell_ex in permutations(exchanges, 2):
            if buy_ex == sell_ex:
                continue

            buy_book = normalized[buy_ex]
            sell_book = normalized[sell_ex]

            fee_buy = self.cfg.fees.get(buy_ex, {}).get("taker", 0.001)
            fee_sell = self.cfg.fees.get(sell_ex, {}).get("taker", 0.001)
            withdraw_fee = self.cfg.fees.get(sell_ex, {}).get("withdraw", 0.0)

            qty, profit_usd, profit_bps, spread_bps = simulate_trade(
                buy_book=buy_book,
                sell_book=sell_book,
                notional_usd=notional,
                fee_buy=fee_buy,
                fee_sell=fee_sell,
                withdraw_fee=withdraw_fee,
            )

            if (
                qty > 0
                and profit_usd > 0
                and profit_bps >= self.cfg.engine.min_profit_bps
                and spread_bps >= self.cfg.engine.spread_threshold_bps
                and notional >= self.cfg.engine.min_volume_usd
            ):
                severity = (
                    SignalSeverity.critical
                    if profit_bps >= self.cfg.telegram.profit_threshold_bps
                    else SignalSeverity.elevated
                )
                route = Route(
                    symbol=symbol,
                    buy_exchange=buy_ex,
                    sell_exchange=sell_ex,
                    buy_price=buy_book.asks[0].price,
                    sell_price=sell_book.bids[0].price,
                    volume_usd=notional,
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
                    volume_usd=notional,
                    confidence=0.9,
                    severity=severity,
                    tags=["spread", "deterministic", "slippage"],
                )
                signals.append(signal)

                await self.redis_state.set_eval_pending(
                    signal_id,
                    {
                        "symbol": symbol,
                        "open_price": {
                            "buy": route.buy_price,
                            "sell": route.sell_price,
                        },
                        "predicted_profit": profit_usd,
                        "exchanges": {
                            "buy": buy_ex,
                            "sell": sell_ex,
                        },
                        "volume_usd": notional,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

        return signals

    async def _cycle(self):
        all_signals: List[Signal] = []
        for symbol in self.cfg.collectors.symbols:
            sigs = await self._compute_signals_for_symbol(symbol)
            all_signals.extend(sigs)

        await self.redis_state.set_signals(all_signals)

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
