import asyncio
import logging
from typing import Optional

from config import CONFIG, Config
from state.redis_state import RedisState

logger = logging.getLogger("notifier.telegram_notifier")


async def _send_message(token: str, chat_id: str, text: str) -> None:
    """
    Минимальная заглушка. Реальный HTTP будет добавлен позже.
    """
    logger.info("[TELEGRAM] %s", text)


async def run_notifier(redis: RedisState, cfg: Config = CONFIG) -> None:
    if not cfg.telegram.enabled:
        logger.info("Telegram notifier disabled.")
        return

    logger.info("Telegram notifier started")

    while True:
        try:
            # Пока просто читаем системный статус раз в N секунд
            status = await redis.get_system_status()
            if status:
                await _send_message(
                    cfg.telegram.token,
                    cfg.telegram.chat_id,
                    f"System OK: {status.get('status', 'unknown')}",
                )

            await asyncio.sleep(cfg.telegram.cycle_sec)

        except Exception as exc:
            logger.exception("Notifier error: %s", exc)
            await asyncio.sleep(5)
