import asyncio
import logging
from datetime import datetime
from typing import Optional

from state.models import CoreSignal, NormalizedBook
from state.redis_state import RedisState

log = logging.getLogger("core.core_engine")


async def run_core_engine(redis: RedisState, cfg):
    log.info("Core engine started")

    interval = cfg.engine.cycle_core_sec

    while True:
        try:
            await _cycle(redis, cfg)
        except Exception as e:
            log.error(f"Core engine error: {e}")

        await asyncio.sleep(interval)


def _pick_best_books(books: dict[str, NormalizedBook]) -> Optional[tuple[NormalizedBook, NormalizedBook]]:
    if not books:
        return None

    best_ask = min(books.values(), key=lambda b: b.ask)
    best_bid = max(books.values(), key=lambda b: b.bid)

    if best_bid.bid <= best_ask.ask:
        return None

    return best_ask, best_bid


async def _cycle(redis: RedisState, cfg) -> None:
    for symbol in cfg.collector.symbols:
        books = await redis.get_books(symbol)
        if len(books) < 2:
            continue

        picked = _pick_best_books(books)
        if not picked:
            continue

        best_ask, best_bid = picked
        spread = best_bid.bid - best_ask.ask

        fee_rate = cfg.engine.fee_rate
        slippage_rate = cfg.engine.slippage_rate
        volume_usd = cfg.engine.trade_volume_usd

        effective_buy = best_ask.ask * (1 + fee_rate + slippage_rate)
        effective_sell = best_bid.bid * (1 - fee_rate - slippage_rate)

        # assume volume denominated in quote asset USD
        qty = volume_usd / effective_buy
        gross = effective_sell * qty
        cost = effective_buy * qty
        net_profit = gross - cost

        sig = CoreSignal(
            symbol=symbol,
            buy_exchange=best_ask.exchange,
            sell_exchange=best_bid.exchange,
            buy_price=best_ask.ask,
            sell_price=best_bid.bid,
            volume_usd=volume_usd,
            spread=spread,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            net_profit=net_profit,
            created_at=datetime.utcnow(),
        )

        await redis.push_signal(sig)
        log.debug(
            "New signal %s -> buy %s / sell %s | spread=%.6f net=%.6f",
            symbol,
            best_ask.exchange,
            best_bid.exchange,
            spread,
            net_profit,
        )
