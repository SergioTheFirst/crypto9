from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from config import get_config
from state.models import LLMSummary
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class SummaryWorker:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    async def _generate_summary(self):
        # Very simple stub: just count signals
        signals = await self.redis_state.get_signals()
        text = f"Summary at {datetime.utcnow().isoformat()}: {len(signals)} active signals."
        summary = LLMSummary(
            id=f"llm_{int(datetime.utcnow().timestamp())}",
            title="Market Summary",
            text=text,
        )
        await self.redis_state.add_llm_summary(summary)
        logger.info("Stored LLM summary %s", summary.id)

    async def run(self):
        if not self.cfg.llm.enabled:
            logger.info("LLM worker disabled.")
            return

        logger.info("LLM summary worker started")
        while not self._stop.is_set():
            try:
                await self._generate_summary()
            except Exception as e:
                logger.exception("LLM worker error: %s", e)
            await asyncio.sleep(self.cfg.llm.summary_interval_minutes * 60)

    def stop(self):
        self._stop.set()
