import asyncio
import logging
from datetime import datetime

from state.redis_state import RedisState

log = logging.getLogger("core.eval_engine")


async def run_eval_engine(redis: RedisState, cfg):
    log.info("Eval engine started")

    interval = cfg.engine.cycle_eval_sec

    while True:
        try:
            await _cycle(redis)
        except Exception as e:
            log.error(f"Eval engine error: {e}")

        await asyncio.sleep(interval)


async def _cycle(redis: RedisState):
    # Заглушка — позже добавим реальную проверку виртуальных сделок
    return
