# notifier/telegram_notifier.py

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import aiohttp

from config import Config
from state.redis_state import RedisState
from state.models import CoreSignal, SystemStatus, LLMSummary 
# NOTE: Для работы требуются методы get_system_status, get_signals, get_llm_summary в RedisState

log = logging.getLogger("notifier.telegram")


class TelegramNotifier:
    """
    Отправляет редкие, высокоценные и критические системные события в Telegram.
    Реализует дебаунсинг и фильтрацию согласно NOTIFICATIONS.md.
    """

    def __init__(self, redis: RedisState, cfg: Config):
        self._redis = redis
        self._cfg = cfg.telegram
        self._engine_cfg = cfg.engine
        self._ml_cfg = cfg.ml
        
        # Кэш для дебаунса: {event_key: last_sent_datetime}
        self._debounce_cache: Dict[str, datetime] = {}
        
        # Состояния для обнаружения изменений
        self._last_system_status: Optional[SystemStatus] = None
        self._last_llm_summary_ts: datetime = datetime.min
        self._last_signal_ts: datetime = datetime.min
        
        if self._cfg.token:
            self.BASE_URL = f"https://api.telegram.org/bot{self._cfg.token}/"
        else:
            self.BASE_URL = ""


    async def _send_message(self, chat_id: int, message: str) -> bool:
        """Отправляет сообщение, используя aiohttp."""
        if not self._cfg.enabled or not self._cfg.token or chat_id == 0:
            log.debug("Telegram disabled or config missing.")
            return False

        url = self.BASE_URL + "sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "MarkdownV2", # Используем MarkdownV2 для форматирования
            "disable_web_page_preview": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=5) as response:
                    if response.status == 200:
                        return True
                    else:
                        text = await response.text()
                        log.error("Telegram API error %d: %s", response.status, text)
                        return False
        except Exception as e:
            log.error("Telegram connection error: %s", e)
            return False

    def _should_debounce(self, key: str, debounce_minutes: int) -> bool:
        """Проверяет и обновляет кэш дебаунса."""
        now = datetime.utcnow()
        last_sent = self._debounce_cache.get(key)
        
        if last_sent is None or (now - last_sent) > timedelta(minutes=debounce_minutes):
            self._debounce_cache[key] = now
            return False
        return True


    async def _check_critical_status(self, current_status: SystemStatus):
        """Проверяет критические состояния (Redis/CEX) и отправляет в Admin Chat."""
        
        if self._last_system_status is None:
            # Первый запуск
            await self._send_message(
                self._cfg.admin_chat_id, 
                f"✅ **[CIP v9] System Startup**\nInitial status: `{current_status.status}`\\."
            )
            self._last_system_status = current_status
            return

        prev_status = self._last_system_status
        messages = []

        # 1. Redis failure/recovery
        if prev_status.redis != current_status.redis:
            if current_status.redis == "fail":
                messages.append("🚨 **CRITICAL: Redis Connection Lost\\!** System is blind\\.")
            elif prev_status.redis == "fail" and current_status.redis == "ok":
                messages.append("🟢 **RECOVERY: Redis is back online\\.**")
        
        # 2. Exchange degradation/recovery
        degraded_exchanges = {ex for ex, stats in current_status.exchanges.items() if stats.status == "degraded"}
        was_degraded = {ex for ex, stats in prev_status.exchanges.items() if stats.status == "degraded"}
        
        for ex in degraded_exchanges - was_degraded:
            messages.append(f"⚠️ **Exchange Degradation:** `{ex.upper()}` has high latency\\.")

        for ex in was_degraded - degraded_exchanges:
             if not self._should_debounce(f"RECOVERY:{ex}", 60):
                messages.append(f"✅ **Exchange Recovery:** `{ex.upper()}` status is back to normal\\.")

        # Отправляем все критические сообщения
        for msg in messages:
            await self._send_message(self._cfg.admin_chat_id, msg)

        self._last_system_status = current_status


    async def _check_llm_summary(self):
        """Проверяет наличие новой LLM сводки и отправляет ее (Rule 4)."""
        summary: Optional[LLMSummary] = await self._redis.get_llm_summary()
        
        if summary and summary.created_at > self._last_llm_summary_ts:
            
            # Экранируем специальные символы для MarkdownV2
            text = summary.text.replace('.', '\\.').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
            
            message = (
                f"🧠 **LLM Market Summary** ({summary.created_at.strftime('%H:%M UTC')})\n\n"
                f"{text}"
            )
            await self._send_message(self._cfg.chat_id, message)
            self._last_llm_summary_ts = summary.created_at


    async def _check_high_value_signals(self):
        """Проверяет новые высокодоходные сигналы и отправляет их (Rule 3)."""
        signals: list[CoreSignal] = await self._redis.get_signals()
        
        new_high_value_signals: list[CoreSignal] = []
        max_ts = self._last_signal_ts

        for signal in signals:
            if signal.created_at.timestamp() > self._last_signal_ts.timestamp():
                
                # Обновляем максимальный timestamp для следующего цикла
                max_ts = max(max_ts, signal.created_at)

                # Проверка порога для уведомления (Rule 3: min_profit_bps)
                is_high_value = (
                    signal.net_profit_bps is not None
                    and signal.net_profit_bps >= self._engine_cfg.notify_min_profit_bps
                )
                
                # Фильтрация по ML-скору, если ML включен
                if self._ml_cfg.enabled and signal.ml_score is not None:
                    is_high_value = is_high_value and (signal.ml_score >= self._ml_cfg.min_score)

                if is_high_value:
                    new_high_value_signals.append(signal)
            
        self._last_signal_ts = max_ts

        for signal in new_high_value_signals:
            # Уникальный ключ дебаунса: символ + маршрут (не чаще 5 мин)
            key = f"SIGNAL:{signal.symbol}:{signal.buy_exchange}-{signal.sell_exchange}"
            
            if not self._should_debounce(key, 5): 
                # Экранирование для MarkdownV2
                symbol = signal.symbol.replace('_', '\\_')
                spread_bps = f"{signal.net_profit_bps:.2f}".replace('.', '\\.')
                
                message = (
                    f"⚡ **HIGH VALUE SIGNAL: {symbol}**\n\n"
                    f"**Net Profit:** `{signal.net_profit:.2f} USD` ({spread_bps} bps)\n"
                    f"**Route:** Buy `{signal.buy_exchange}` @ `{signal.buy_price:.4f}` < Sell `{signal.sell_exchange}` @ `{signal.sell_price:.4f}`\n"
                    f"**Volume:** `{signal.volume_usd:.0f} USD`"
                )
                await self._send_message(self._cfg.chat_id, message)


    async def run(self) -> None:
        """Основной цикл мониторинга и отправки уведомлений."""
        if not self._cfg.enabled:
            log.info("Telegram notifier disabled in config.")
            return

        log.info("Telegram notifier started.")
        
        # Периоды проверки (используем меньшее значение для частого опроса)
        check_interval = min(self._engine_cfg.cycle_core_sec, 5.0) # 1.5s или 5s
        
        while True:
            try:
                # 1. Проверка системного статуса и критических событий
                current_status: Optional[SystemStatus] = await self._redis.get_system_status()
                if current_status:
                    await self._check_critical_status(current_status)
                
                # 2. Проверка новых высокодоходных сигналов
                await self._check_high_value_signals()
                
                # 3. Проверка LLM-сводок (не чаще, чем worker их генерирует)
                await self._check_llm_summary() # Вызов внутри проверит time delta

            except asyncio.CancelledError:
                log.warning("Telegram notifier stopped by cancellation.")
                break
            except Exception as e:
                log.error("Telegram notifier loop error: %s", e, exc_info=True)

            await asyncio.sleep(check_interval)