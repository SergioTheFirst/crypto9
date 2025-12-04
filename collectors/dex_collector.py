from __future__ import annotations

import asyncio
import logging

import aiohttp

from config import get_config
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class DEXCollector:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _probe(self) -> bool:
        """Lightweight reachability check for the configured DEX endpoint."""
        if not self.cfg.collectors.dex_enabled:
            return False

        # No concrete DEX integration yet; treat missing endpoint as unreachable
        endpoint = getattr(self.cfg.collectors, "dex_health_url", None)
        if not endpoint:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=3):
                    return True
        except Exception:
            return False

    async def run(self):
        reachable = await self._probe()
        if not reachable:
            logger.warning("dex_collector_unreachable", extra={"enabled": self.cfg.collectors.dex_enabled})
            return

        logger.info("DEX collector reachable but integration stubbed; idle mode engaged")
        while not self._stop.is_set():
            await asyncio.sleep(5)

    def stop(self):
        self._stop.set()


async def run_dex_collector(redis_state: RedisState):
    collector = DEXCollector(redis_state)
    await collector.run()
