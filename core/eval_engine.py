from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from config import get_config
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class EvalEngine:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _cycle(self):
        # Placeholder: in future, read signals and books and compute eval.
        # Currently, just sleeps and logs occasionally.
        logger.debug("Eval cycle tick at %s", datetime.utcnow().isoformat())

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
