from __future__ import annotations

import asyncio
import logging

from config import get_config
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class DEXCollector:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def run(self):
        logger.info("DEX collector disabled / stub (no real DEX integration yet)")
        while not self._stop.is_set():
            await asyncio.sleep(5)

    def stop(self):
        self._stop.set()


async def run_dex_collector(redis_state: RedisState):
    collector = DEXCollector(redis_state)
    await collector.run()
