import asyncio
import logging
from datetime import datetime

from state.redis_state import RedisState
from state.models import SignalStats

log = logging.getLogger("core.eval_engine")


async def run_eval_engine(redis, cfg):
    interval = cfg.eval.cycle_sec
    log.info("Eval engine started")

    while True:
        try:
            await _cycle(redis)

        except Exception as e:
            log.error(f"Eval engine error: {e}")

        await asyncio.sleep(interval)


async def _cycle(redis: RedisState):
    signals = await redis.get_signals()
    if not signals:
        return

    total = len(signals)
    profitable = sum(1 for s in signals if s.net_profit > 0)
    avg_profit = sum(s.net_profit for s in signals) / total if total else 0.0

    stats = SignalStats(
        signals_total=total,
        profitable_signals=profitable,
        avg_profit=avg_profit,
        updated_at=datetime.utcnow(),
    )

    await redis.set_signal_stats(stats)