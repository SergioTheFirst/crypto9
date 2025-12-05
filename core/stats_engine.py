import asyncio
import logging
from datetime import datetime
from typing import List

from state.redis_state import RedisState
from state.models import MarketStats, ExchangeStats, SystemStatus

log = logging.getLogger("core.stats_engine")


async def run_stats_engine(redis: RedisState, cfg):
    log.info("Stats engine started")

    interval = cfg.engine.cycle_stats_sec

    while True:
        try:
            await _cycle(redis)
        except Exception as e:
            log.error(f"Stats engine error: {e}")

        await asyncio.sleep(interval)


async def _cycle(redis: RedisState):
    # MARKET
    market = await _calc_market_stats(redis)

    # EXCHANGES
    exch = await _calc_exchange_stats(redis)

    # SAVE market
    await redis.set_market_stats(market)
    await redis.set_exchange_stats(exch)

    # SYSTEM STATUS
    sys = SystemStatus(
        status="ok",
        redis="ok",
        llm="disabled",
        telegram="disabled",
        dex="disabled",
        symbols=len(market),
        exchanges={e.exchange: e for e in exch},
        last_update_ts=datetime.utcnow().isoformat(),
    )

    await redis.set_system_status(sys)


async def _calc_market_stats(redis: RedisState) -> List[MarketStats]:
    result = []

    for symbol in ["BTCUSDT", "ETHUSDT"]:
        books = await redis.get_books(symbol)
        if not books:
            continue

        mids = [(b.bid + b.ask) / 2 for b in books.values()]
        mid = sum(mids) / len(mids)

        result.append(
            MarketStats(
                symbol=symbol,
                last_mid=mid,
                volatility_1h=0.0,
                updated_at=datetime.utcnow(),
            )
        )

    return result


async def _calc_exchange_stats(redis: RedisState) -> List[ExchangeStats]:
    now = datetime.utcnow()

    return [
        ExchangeStats(
            exchange="binance",
            status="excellent",
            delay_ms=12,
            error_rate=0.0,
            updated_at=now,
        ),
        ExchangeStats(
            exchange="mexc",
            status="excellent",
            delay_ms=14,
            error_rate=0.0,
            updated_at=now,
        ),
    ]
