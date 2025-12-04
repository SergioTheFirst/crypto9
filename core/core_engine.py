from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from itertools import combinations
from typing import Dict, List, Tuple

from config import get_config
from state.models import OrderBook, OrderBookLevel, Route, Signal, SignalSeverity
from state.redis_state import RedisState

logger = logging.getLogger(__name__)

# Реальные близкие к бою комиссии (taker):
# Binance: ~0.04% (0.0004)
# MEXC:   ~0.1%  (0.0010) — зависит от уровня, берём консервативно
TAKER_FEES: Dict[str, float] = {
    "binance": 0.0004,
    "mexc": 0.0010,
}


def simulate_trade(
    bids: List[OrderBookLevel],
    asks: List[OrderBookLevel],
    notional_usd: float,
    fee_buy: float,
    fee_sell: float,
) -> Tuple[float, float, float]:
    """
    Имитация арбитражной сделки:
      - покупаем по стакану "asks" на notional_usd
      - продаём по стакану "bids" всё купленное
      - учитываем комиссии в обе стороны
      - возвращаем: (кол-во базового актива, profit_usd, profit_bps)
    """
    if not bids or not asks or notional_usd <= 0:
        return 0.0, 0.0, 0.0

    # BUY: идём по ask'ам
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
        else:
            bought_qty += lvl.amount
            spent_usd += max_lvl_notional
            remaining_notional -= max_lvl_notional

    if bought_qty <= 0.0:
        return 0.0, 0.0, 0.0

    # SELL: идём по bid'ам
    remaining_qty = bought_qty
    received_usd = 0.0

    for lvl in bids:
        if lvl.amount >= remaining_qty:
            received_usd += remaining_qty * lvl.price
            remaining_qty = 0.0
            break
        else:
            received_usd += lvl.amount * lvl.price
            remaining_qty -= lvl.amount

    if remaining_qty > 0.0:
        # Недостаточная ликвидность на выходе — игнорируем такой арбитраж
        return 0.0, 0.0, 0.0

    # Комиссии
    net_buy = spent_usd * (1.0 + fee_buy)
    net_sell = received_usd * (1.0 - fee_sell)

    profit_usd = net_sell - net_buy
    profit_bps = (profit_usd / net_buy) * 10_000.0 if net_buy > 0 else 0.0

    return bought_qty, profit_usd, profit_bps


class CoreEngine:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _compute_signals_for_symbol(self, symbol: str) -> List[Signal]:
        books_raw = await self.redis_state.get_books(symbol)
        exchanges = list(books_raw.keys())
        if len(exchanges) < 2:
            return []

        books: Dict[str, OrderBook] = {
            ex: OrderBook(**data) for ex, data in books_raw.items()
        }
        signals: List[Signal] = []

        notional = float(self.cfg.engine.volume_cap_usd)

        for buy_ex, sell_ex in combinations(exchanges, 2):
            buy_book = books[buy_ex]
            sell_book = books[sell_ex]

            fee_buy = TAKER_FEES.get(buy_ex, 0.001)
            fee_sell = TAKER_FEES.get(sell_ex, 0.001)

            # Направление 1: покупаем на buy_ex, продаём на sell_ex
            qty, profit_usd, profit_bps = simulate_trade(
                bids=sell_book.bids,
                asks=buy_book.asks,
                notional_usd=notional,
                fee_buy=fee_buy,
                fee_sell=fee_sell,
            )

            if (
                qty > 0
                and profit_usd > 0
                and profit_bps >= self.cfg.engine.min_profit_bps
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
                signals.append(
                    Signal(
                        id=f"{symbol}_{buy_ex}_{sell_ex}_{int(datetime.utcnow().timestamp())}",
                        symbol=symbol,
                        route=route,
                        expected_profit_bps=profit_bps,
                        expected_profit_usd=profit_usd,
                        confidence=0.9,
                        severity=severity,
                        tags=["spread"],
                    )
                )

            # Направление 2: покупаем на sell_ex, продаём на buy_ex
            fee_buy2 = fee_sell
            fee_sell2 = fee_buy

            qty, profit_usd, profit_bps = simulate_trade(
                bids=buy_book.bids,
                asks=sell_book.asks,
                notional_usd=notional,
                fee_buy=fee_buy2,
                fee_sell=fee_sell2,
            )

            if (
                qty > 0
                and profit_usd > 0
                and profit_bps >= self.cfg.engine.min_profit_bps
                and notional >= self.cfg.engine.min_volume_usd
            ):
                severity = (
                    SignalSeverity.critical
                    if profit_bps >= self.cfg.telegram.profit_threshold_bps
                    else SignalSeverity.elevated
                )
                route = Route(
                    symbol=symbol,
                    buy_exchange=sell_ex,
                    sell_exchange=buy_ex,
                    buy_price=sell_book.asks[0].price,
                    sell_price=buy_book.bids[0].price,
                    volume_usd=notional,
                )
                signals.append(
                    Signal(
                        id=f"{symbol}_{sell_ex}_{buy_ex}_{int(datetime.utcnow().timestamp())}",
                        symbol=symbol,
                        route=route,
                        expected_profit_bps=profit_bps,
                        expected_profit_usd=profit_usd,
                        confidence=0.9,
                        severity=severity,
                        tags=["spread"],
                    )
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
