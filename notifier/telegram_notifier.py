from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp

from config import get_config
from state.models import LLMSummary, Signal
from state.redis_state import RedisState

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, redis_state: RedisState):
        self.cfg = get_config()
        self.redis = redis_state
        self.last_alert_times: dict[str, datetime] = {}
        self._stop = asyncio.Event()

    async def _send(self, text: str):
        if not self.cfg.telegram.bot_token or not self.cfg.telegram.chat_id:
            logger.warning("Telegram not configured")
            return
        url = f"https://api.telegram.org/bot{self.cfg.telegram.bot_token}/sendMessage"
        payload = {"chat_id": self.cfg.telegram.chat_id, "text": text}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=30) as resp:
                    if resp.status != 200:
                        logger.error("Telegram error: %s", await resp.text())
        except Exception as e:
            logger.exception("Telegram send error: %s", e)

    def _should_send(self, key: str) -> bool:
        now = datetime.utcnow()
        last = self.last_alert_times.get(key)
        if last is None or now - last > timedelta(minutes=self.cfg.telegram.debounce_minutes):
            self.last_alert_times[key] = now
            return True
        return False

    async def _check_signals(self):
        signals = await self.redis.get_signals()
        for raw in signals:
            s = Signal(**raw)
            if s.severity != "critical":
                continue
            key = f"critical:{s.symbol}:{s.route.buy_exchange}:{s.route.sell_exchange}"
            if not self._should_send(key):
                continue
            txt = (
                f"[CRITICAL SIGNAL]\n\n"
                f"{s.symbol}\n"
                f"Buy: {s.route.buy_exchange} @ {s.route.buy_price}\n"
                f"Sell: {s.route.sell_exchange} @ {s.route.sell_price}\n"
                f"Profit: {s.expected_profit_bps:.2f} bps\n"
                f"Volume: {s.route.volume_usd}$\n"
                f"Time: {s.created_at}\n"
            )
            await self._send(txt)

    async def _check_llm(self):
        summaries = await self.redis.get_llm_summaries(limit=3)
        for raw in summaries:
            s = LLMSummary(**raw)
            key = f"llm:{s.id}"
            if not self._should_send(key):
                continue
            await self._send(f"[LLM SUMMARY]\n\n{s.text}")

    async def run(self):
        if not self.cfg.telegram.enabled:
            logger.info("Telegram notifier disabled.")
            return
        logger.info("Telegram notifier started")
        while not self._stop.is_set():
            try:
                await self._check_signals()
                await self._check_llm()
            except Exception as e:
                logger.exception("Notifier error: %s", e)
            await asyncio.sleep(5)

    def stop(self):
        self._stop.set()


async def run_notifier(redis_state: RedisState):
    notifier = TelegramNotifier(redis_state)
    await notifier.run()
