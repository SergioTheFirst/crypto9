from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from config import get_config
from state.redis_state import RedisState
from state.models import VirtualEvalResult, VirtualTrade

logger = logging.getLogger(__name__)


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
            signal_id = sig.get("id")
            if not signal_id:
                continue

            existing = await self.redis_state.get_eval_pending_trade(signal_id)
            if existing:
                continue

            existing_result = await self.redis_state.get_eval_result(signal_id)
            if existing_result:
                continue

            route = sig.get("route", {}) or {}
            symbol = sig.get("symbol") or route.get("symbol")
            buy_exchange = route.get("buy_exchange") or route.get("buy")
            sell_exchange = route.get("sell_exchange") or route.get("sell")
            open_price_buy = float(route.get("buy_price", 0.0) or 0.0)
            open_price_sell = float(route.get("sell_price", 0.0) or 0.0)
            volume_usd = float(
                sig.get("volume_usd")
                or route.get("volume_usd")
                or self.cfg.engine.volume_cap_usd
            )
            predicted_profit = float(sig.get("expected_profit_usd") or 0.0)

            ts_raw: Optional[str] = None
            for key in ("ts", "created_at"):
                if sig.get(key):
                    ts_raw = sig.get(key)
                    break
            try:
                open_ts = (
                    ts_raw if isinstance(ts_raw, datetime) else datetime.fromisoformat(ts_raw)
                )
            except Exception:
                open_ts = datetime.utcnow()
            if isinstance(open_ts, str):
                open_ts = datetime.fromisoformat(open_ts)

            if not (symbol and buy_exchange and sell_exchange and open_price_buy > 0):
                continue

            trade = VirtualTrade(
                signal_id=signal_id,
                symbol=symbol,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                open_price_buy=open_price_buy,
                open_price_sell=open_price_sell,
                open_ts=open_ts,
                volume_usd=volume_usd,
                predicted_profit_usd=predicted_profit,
            )
            await self.redis_state.set_eval_pending_trade(trade, ttl_seconds=ttl)

    @staticmethod
    def _best_bid(book: dict) -> Optional[float]:
        bids = book.get("bids") if isinstance(book, dict) else None
        if not bids:
            return None
        level = bids[0]
        if isinstance(level, dict):
            return float(level.get("price", 0.0) or 0.0)
        if isinstance(level, (list, tuple)) and level:
            return float(level[0])
        return None

    @staticmethod
    def _best_ask(book: dict) -> Optional[float]:
        asks = book.get("asks") if isinstance(book, dict) else None
        if not asks:
            return None
        level = asks[0]
        if isinstance(level, dict):
            return float(level.get("price", 0.0) or 0.0)
        if isinstance(level, (list, tuple)) and level:
            return float(level[0])
        return None

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

            close_sell_price = self._best_bid(buy_book)
            close_buy_price = self._best_ask(sell_book)
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
