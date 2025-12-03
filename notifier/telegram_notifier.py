"""Telegram notifier for rare, high-value events."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict

import aiohttp

from config import get_config
from state.models import Signal, SignalSeverity
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, redis_state: RedisState) -> None:
        self.cfg = get_config()
        self.redis_state = redis_state
        self._stop = asyncio.Event()
        self._history: Deque[float] = deque()
        self._debounce: Dict[str, float] = defaultdict(float)

    def _should_send(self, signal: Signal) -> bool:
        now = time.time()
        # Global rate limit
        window = 3600.0
        while self._history and now - self._history[0] > window:
            self._history.popleft()
        if len(self._history) >= self.cfg.telegram.rate_limit_per_hour:
            return False
        key = f"{signal.route.symbol}:{signal.route.buy_exchange}:{signal.route.sell_exchange}"
        if now - self._debounce[key] < self.cfg.telegram.debounce_minutes * 60:
            return False
        if signal.expected_profit_bps < self.cfg.telegram.profit_threshold_bps:
            return False
        return True

    async def _send(self, session: aiohttp.ClientSession, text: str) -> None:
        if not (self.cfg.telegram.bot_token and self.cfg.telegram.chat_id):
            logger.info("Telegram credentials not provided; skipping notification")
            return
        url = f"https://api.telegram.org/bot{self.cfg.telegram.bot_token}/sendMessage"
        payload = {"chat_id": self.cfg.telegram.chat_id, "text": text}
        async with session.post(url, json=payload, timeout=5) as resp:
            if resp.status != 200:
                logger.warning("Telegram send failed: %s", await resp.text())

    def _format_signal(self, signal: Signal) -> str:
        return (
            "[CRITICAL SIGNAL]\n"
            f"Pair: {signal.route.symbol}\n"
            f"Route: buy on {signal.route.buy_exchange}, sell on {signal.route.sell_exchange}\n"
            f"Profit: {signal.expected_profit_bps:.2f} bps (~${signal.expected_profit_usd:.2f})\n"
            f"Volume: ${signal.route.volume_usd:.2f}\n"
            f"Severity: {signal.severity.value}\n"
            f"ts: {signal.created_at.isoformat()}"
        )

    async def _consume_signals(self) -> None:
        async for raw in self.redis_state.subscribe_events():
            try:
                event = raw if isinstance(raw, str) else raw.decode()
                parsed = json.loads(event)
                if parsed.get("type") != "signal":
                    continue
                signal = await self.redis_state.get_signal(parsed["id"])
                if not signal:
                    continue
                if not self._should_send(signal):
                    continue
                text = self._format_signal(signal)
                async with aiohttp.ClientSession() as session:
                    await self._send(session, text)
                    self._history.append(time.time())
                    key = f"{signal.route.symbol}:{signal.route.buy_exchange}:{signal.route.sell_exchange}"
                    self._debounce[key] = time.time()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Notifier error", exc_info=exc)

    async def run(self) -> None:
        if not self.cfg.telegram.enabled:
            logger.info("Telegram notifier disabled")
            return
        await self._consume_signals()

    def stop(self) -> None:
        self._stop.set()


__all__ = ["TelegramNotifier"]
