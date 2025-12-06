# collectors/dex_collector.py

import asyncio
import logging
from datetime import datetime

from config import CONFIG, Config
from state.redis_state import RedisState

logger = logging.getLogger("collectors.dex_collector")


async def _cycle(redis: RedisState, cfg: Config) -> None:
    """
    Основной цикл DEX-коллектора. В текущей версии это заглушка, 
    которая просто обновляет статус в Redis и ждет.
    """
    # В реальной реализации здесь была бы логика подключения к узлам DEX (например, WebSockets, TheGraph)
    # и нормализация полученных данных в NormalizedBook, аналогично CEX.

    # Обновляем статус, чтобы система знала, что компонент работает (если он включен)
    await redis.update_collector_timestamp("dex")

    # DEX отключён по умолчанию, но цикл должен работать безопасно
    await asyncio.sleep(cfg.collector.cycle_sec)


async def run_dex_collector(redis: RedisState, cfg: Config = CONFIG) -> None:
    """Точка входа для DEX-коллектора."""
    if not cfg.collector.use_dex:
        logger.info("DEX collector disabled (use_dex=False).")
        return

    logger.info("DEX collector started.")

    while True:
        try:
            await _cycle(redis, cfg)
        except asyncio.CancelledError:
            logger.warning("DEX collector stopped by cancellation.")
            break
        except Exception as exc:
            logger.exception("DEX collector critical error: %s", exc)
            await asyncio.sleep(5)