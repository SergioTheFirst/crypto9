"""LLM summary worker producing advisory summaries only."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List

from config import get_config
from state.models import LLMSummary, Signal
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class SummaryWorker:
    def __init__(self, redis_state: RedisState) -> None:
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()

    def _render_summary(self, signals: List[Signal]) -> str:
        if not signals:
            return "Quiet market: no high-confidence signals in the recent window."
        lines = ["Recent opportunities:"]
        for sig in signals:
            lines.append(
                f"- {sig.route.symbol}: buy {sig.route.buy_exchange} @ {sig.route.buy_price:.2f}, "
                f"sell {sig.route.sell_exchange} @ {sig.route.sell_price:.2f} (+{sig.expected_profit_bps:.1f} bps)"
            )
        return "\n".join(lines)

    async def _generate(self) -> None:
        signals = await self.redis_state.recent_signals(self.cfg.llm.max_signals)
        summary = LLMSummary(
            id=f"llm_{int(datetime.utcnow().timestamp())}",
            title="Market summary",
            text=self._render_summary(signals),
        )
        await self.redis_state.store_llm_summary(summary)
        logger.info("Stored LLM summary %s", summary.id)

    async def run(self) -> None:
        if not self.cfg.llm.enabled:
            logger.info("LLM summary worker disabled")
            return
        while not self._stop.is_set():
            await self._generate()
            await asyncio.sleep(self.cfg.llm.summary_interval_minutes * 60)

    def stop(self) -> None:
        self._stop.set()


async def run_summary_worker() -> None:
    worker = SummaryWorker(RedisState())
    try:
        await worker.run()
    finally:
        await worker.redis_state.close()


__all__ = ["SummaryWorker", "run_summary_worker"]
