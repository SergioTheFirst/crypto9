import asyncio
import logging

from config import get_config
from state.redis_state import RedisState
from collectors.cex_collector import run_cex_collector
from collectors.dex_collector import run_dex_collector
from core.core_engine import run_core_engine
from core.eval_engine import run_eval_engine
from core.stats_engine import run_stats_engine
from llm.summary_worker import SummaryWorker
from notifier.telegram_notifier import run_notifier
from api.api_server import run_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("run_all")


async def main():
    cfg = get_config()
    redis_state = RedisState(cfg.redis.url)

    tasks = []

    tasks.append(asyncio.create_task(run_cex_collector(redis_state)))
    if cfg.collectors.dex_enabled:
        tasks.append(asyncio.create_task(run_dex_collector(redis_state)))
    tasks.append(asyncio.create_task(run_core_engine(redis_state)))
    tasks.append(asyncio.create_task(run_eval_engine(redis_state)))
    tasks.append(asyncio.create_task(run_stats_engine(redis_state)))

    if cfg.llm.enabled:
        worker = SummaryWorker(redis_state)
        tasks.append(asyncio.create_task(worker.run()))

    if cfg.telegram.enabled:
        tasks.append(asyncio.create_task(run_notifier(redis_state)))

    tasks.append(asyncio.create_task(run_api(redis_state)))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
