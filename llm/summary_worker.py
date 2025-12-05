import asyncio
import logging
from datetime import datetime

from config import CONFIG, Config
from state.redis_state import RedisState

logger = logging.getLogger("llm.summary_worker")


async def _generate_summary() -> str:
    """
    Заглушка LLM. Настоящий вызов будет потом.
    """
    now = datetime.utcnow().isoformat()
    return f"[LLM SUMMARY]\nSystem heartbeat at {now}"


async def run_llm_worker(redis: RedisState, cfg: Config = CONFIG) -> None:
    if not cfg.llm.enabled:
        logger.info("LLM worker disabled.")
        return

    logger.info("LLM worker started.")

    while True:
        try:
            text = await _generate_summary()

            await redis.set_system_status({"status": "ok", "summary": text})

            await asyncio.sleep(cfg.llm.cycle_sec)

        except Exception as exc:
            logger.exception("LLM worker error: %s", exc)
            await asyncio.sleep(5)
