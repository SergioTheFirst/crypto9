import asyncio
import logging
from datetime import datetime

from state.redis_state import RedisState
from state.models import CoreSignal

log = logging.getLogger("core.core_engine")


async def run_core_engine(redis: RedisState, cfg):
    log.info("Core engine started")

    interval = cfg.engine.cycle_core_sec

    while True:
        try:
            await _cycle(redis)
        except Exception as e:
            log.error(f"Core engine error: {e}")

        await asyncio.sleep(interval)


async def _cycle(redis: RedisState):
    # Заглушка — нормальная логика будет позже
    # Сейчас: если есть книги по BTCUSDT — создаём тестовый сигнал
    books = await redis.get_books("BTCUSDT")
    if not books:
        return

    b = list(books.values())[0]

    sig = CoreSignal(
        symbol="BTCUSDT",
        buy_exchange=b.exchange,
        sell_exchange=b.exchange,
        buy_price=b.ask,
        sell_price=b.bid,
        volume_usd=100,
        est_net_profit=(b.bid - b.ask),
        created_at=datetime.utcnow(),
    )

    await redis.push_signal(sig)
