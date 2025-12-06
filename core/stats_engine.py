import asyncio
import logging
from datetime import datetime
from typing import List, Dict

from analytics.history_store import HistoryStore
from state.redis_state import RedisState
from state.models import MarketStats, ExchangeStats, SystemStatus, NormalizedBook

log = logging.getLogger("core.stats_engine")


async def run_stats_engine(redis: RedisState, cfg):
    log.info("Stats engine started")

    interval = cfg.engine.cycle_stats_sec
    history = HistoryStore(redis, cfg)

    while True:
        try:
            await _cycle(redis, cfg, history)
        except Exception as e:
            log.error(f"Stats engine error: {e}")

        await asyncio.sleep(interval)


async def _cycle(redis: RedisState, cfg, history: HistoryStore):
    market = await _calc_market_stats(redis, cfg, history)
    exch = await _calc_exchange_stats(redis, cfg)

    await redis.set_market_stats(market)
    await redis.set_exchange_stats(exch)

    sys = SystemStatus(
        status="ok",
        redis="ok",
        llm="disabled",
        telegram="disabled",
        dex="disabled",
        symbols=len(market),
        exchanges={e.exchange: e for e in exch},
        last_update_ts=datetime.utcnow(),
    )

    await redis.set_system_status(sys)


async def _calc_market_stats(redis: RedisState, cfg, history: HistoryStore) -> List[MarketStats]:
    result = []
    for symbol in cfg.collector.symbols:
        books: Dict[str, NormalizedBook] = await redis.get_books(symbol)
        if not books:
            continue

        mids = [(b.ask + b.bid) / 2 for b in books.values()]
        if not mids:
            continue

        mid = sum(mids) / len(mids)

        try:
            best_ask = min(books.values(), key=lambda b: b.ask)
            best_bid = max(books.values(), key=lambda b: b.bid)
            spread = best_bid.bid - best_ask.ask
            spread_bps = (spread / mid) * 10_000 if mid else 0.0
            
            await history.append_spread(
                symbol,
                {
                    "symbol": symbol,
                    "spread": spread,
                    "spread_bps": spread_bps,
                    "best_bid": best_bid.bid,
                    "best_ask": best_ask.ask,
                    "updated_at": datetime.utcnow(),
                },
            )
        except Exception:
            pass

        result.append(
            MarketStats(
                symbol=symbol,
                last_mid=mid,
                volatility_1h=0.0,
                updated_at=datetime.utcnow(),
            )
        )

    return result


async def _calc_exchange_stats(redis: RedisState, cfg) -> List[ExchangeStats]:
    now = datetime.utcnow()
    reference_books: Dict[str, NormalizedBook] = await redis.get_books(cfg.collector.symbols[0]) if cfg.collector.symbols else {}
    
    all_exchanges = cfg.collector.cex_exchanges 
    
    stats_list = []
    
    for ex in all_exchanges:
        book_available = ex in reference_books
        
        status = "excellent" if book_available else "warming_up"
        delay_ms = 0.0
        error_rate = 0.0
        
        stats_list.append(
            ExchangeStats(
                exchange=ex,
                status=status,
                delay_ms=delay_ms,
                error_rate=error_rate,
                updated_at=now,
            )
        )
        
    return stats_list