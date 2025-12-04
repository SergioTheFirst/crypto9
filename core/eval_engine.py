import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from config import get_config
from state.redis_state import RedisState
from state.models import VirtualEvalResult, VirtualTrade

logger = logging.getLogger(__name__)


def _best_bid(book: Optional[object]) -> Optional[float]:
    if not book or not getattr(book, "bids", None):
        return None
    level = book.bids[0]
    try:
        return float(level.price)
    except Exception:
        return None


def _best_ask(book: Optional[object]) -> Optional[float]:
    if not book or not getattr(book, "asks", None):
        return None
    level = book.asks[0]
    try:
        return float(level.price)
    except Exception:
        return None


class EvalEngine:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _create_virtual_trades(self) -> None:
        signals = await self.redis_state.get_signals()
        hold_seconds = self.cfg.eval.virtual_hold_sec
        ttl = int(hold_seconds * 2.5)

        for sig in signals:
            signal_id = sig.id
            existing = await self.redis_state.get_eval_pending_trade(signal_id)
            if existing:
                continue

            existing_result = await self.redis_state.get_eval_result(signal_id)
            if existing_result:
                continue

            route = sig.route
            trade = VirtualTrade(
                signal_id=signal_id,
                symbol=sig.symbol,
                buy_exchange=route.buy_exchange,
                sell_exchange=route.sell_exchange,
                open_price_buy=route.buy_price,
                open_price_sell=route.sell_price,
                open_ts=sig.created_at,
                volume_usd=sig.volume_usd or route.volume_usd,
                predicted_profit_usd=sig.expected_profit_usd,
            )
            await self.redis_state.set_eval_pending_trade(trade, ttl_seconds=ttl)

    async def _evaluate_pending(self) -> None:
        pending = await self.redis_state.get_all_eval_pending_trades()
        if not pending:
            return

        now = datetime.utcnow()
        hold = timedelta(seconds=self.cfg.eval.virtual_hold_sec)

        for signal_id, trade in pending.items():
            if now - trade.open_ts < hold:
                continue

            books_raw = await self.redis_state.get_books(trade.symbol)
            buy_book = books_raw.get(trade.buy_exchange) if books_raw else None
            sell_book = books_raw.get(trade.sell_exchange) if books_raw else None
            if not (buy_book and sell_book):
                continue

            close_sell_price = _best_bid(sell_book)
            close_buy_price = _best_ask(buy_book)
            if not close_sell_price or not close_buy_price:
                continue

            spread_open = trade.open_price_sell - trade.open_price_buy
            spread_close = close_sell_price - close_buy_price
            qty = trade.volume_usd / trade.open_price_buy if trade.open_price_buy > 0 else 0.0
            final_profit = (spread_close - spread_open) * qty

            epsilon = 1e-6
            if final_profit > epsilon:
                grade = "WIN"
            elif final_profit < -epsilon:
                grade = "LOSS"
            else:
                grade = "NEUTRAL"

            result = VirtualEvalResult(
                signal_id=trade.signal_id,
                symbol=trade.symbol,
                buy_exchange=trade.buy_exchange,
                sell_exchange=trade.sell_exchange,
                open_ts=trade.open_ts,
                eval_ts=now,
                final_profit_usd=final_profit,
                grade=grade,
            )

            await self.redis_state.set_eval_result(result)
            await self.redis_state.append_eval_history_entry(result)
            await self.redis_state.delete_eval_pending(signal_id)

    async def _cycle(self):
        await self._create_virtual_trades()
        await self._evaluate_pending()

    async def run(self):
        logger.info("Eval engine started")
        while not self._stop.is_set():
            try:
                await self._cycle()
            except Exception as e:
                logger.exception("Eval engine error: %s", e)
            await asyncio.sleep(self.cfg.eval.cycle_sec)

    def stop(self):
        self._stop.set()


async def run_eval_engine(redis_state: RedisState):
    engine = EvalEngine(redis_state)
    await engine.run()
