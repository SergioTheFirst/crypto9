import asyncio
import logging

from config import CONFIG, Config
from state.redis_state import RedisState

logger = logging.getLogger("collectors.dex_collector")


async def _cycle(redis: RedisState, cfg: Config) -> None:
    # DEX отключён, но цикл должен работать безопасно
    await asyncio.sleep(cfg.collector.cycle_sec)


async def run_dex_collector(redis: RedisState, cfg: Config = CONFIG) -> None:
    if not cfg.collector.use_dex:
        logger.info("DEX collector disabled (use_dex=False).")
        return

    logger.info("DEX collector started.")

    while True:
        try:
            await _cycle(redis, cfg)
        except Exception as exc:
            logger.exception("DEX collector error: %s", exc)
            await asyncio.sleep(5)
