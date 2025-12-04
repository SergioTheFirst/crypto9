from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta

from config import get_config
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class EvalEngine:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _cycle(self):
        pending = await self.redis_state.get_all_eval_pending()
        if not pending:
            return

        now = datetime.utcnow()
        hold = timedelta(seconds=self.cfg.eval.virtual_hold_sec)

        for signal_id, payload in pending.items():
            try:
                opened_at = datetime.fromisoformat(payload.get("timestamp"))
            except Exception:
                await self.redis_state.delete_eval_pending(signal_id)
                continue

            symbol = payload.get("symbol")
            exchanges = payload.get("exchanges", {})
            buy_ex = exchanges.get("buy")
            sell_ex = exchanges.get("sell")
            volume_usd = float(payload.get("volume_usd", self.cfg.engine.volume_cap_usd))

            books_raw = await self.redis_state.get_books(symbol) if symbol else {}
            buy_book = books_raw.get(buy_ex) if books_raw else None
            sell_book = books_raw.get(sell_ex) if books_raw else None

            grade = "NEUTRAL"
            realized_profit = 0.0

            if buy_book and sell_book:
                try:
                    buy_price = float(buy_book.get("asks", [{}])[0].get("price"))
                    sell_price = float(sell_book.get("bids", [{}])[0].get("price"))
                except Exception:
                    buy_price = 0.0
                    sell_price = 0.0

                if all(
                    [
                        buy_price > 0,
                        sell_price > 0,
                        not math.isnan(buy_price),
                        not math.isnan(sell_price),
                        sell_price > buy_price,
                    ]
                ):
                    qty = volume_usd / buy_price
                    fee_buy = self.cfg.fees.get(buy_ex, {}).get("taker", 0.001)
                    fee_sell = self.cfg.fees.get(sell_ex, {}).get("taker", 0.001)
                    withdraw_fee = self.cfg.fees.get(sell_ex, {}).get("withdraw", 0.0)
                    slippage = 0.5 * math.sqrt(max(volume_usd, 0.0) / 10_000.0)

                    gross = qty * (sell_price - buy_price)
                    buy_fee = volume_usd * fee_buy
                    sell_fee = qty * sell_price * fee_sell
                    realized_profit = gross - buy_fee - sell_fee - withdraw_fee - slippage

                    if realized_profit > 0:
                        grade = "WIN"
                    elif realized_profit < 0:
                        grade = "LOSS"

            record = {
                "signal_id": signal_id,
                "grade": grade,
                "profit_usd": realized_profit,
                "timestamp": now.isoformat(),
            }
            await self.redis_state.append_eval_history(signal_id, record)

            if now - opened_at >= hold:
                await self.redis_state.delete_eval_pending(signal_id)

    async def run(self):
        logger.info("Eval engine started")
        while not self._stop.is_set():
            try:
                await self._cycle()
            except Exception as e:
                logger.exception("Eval engine error: %s", e)
            await asyncio.sleep(self.cfg.eval.poll_interval)

    def stop(self):
        self._stop.set()


async def run_eval_engine(redis_state: RedisState):
    engine = EvalEngine(redis_state)
    await engine.run()
