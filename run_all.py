import asyncio
import logging

import uvicorn

from api.api_server import create_app
from collectors.cex_collector import run_cex_collector
from collectors.dex_collector import run_dex_collector
from config import CONFIG
from core.core_engine import run_core_engine
from core.eval_engine import run_eval_engine
from core.stats_engine import run_stats_engine
from state.redis_state import RedisState


async def main():
    logging.basicConfig(level=logging.INFO)

    redis = RedisState(CONFIG.redis)

    app = create_app(CONFIG)
    api = uvicorn.Server(
        uvicorn.Config(app, host=CONFIG.api.host, port=CONFIG.api.port, log_level="info")
    )

    tasks = [
        asyncio.create_task(run_cex_collector(redis, CONFIG)),
        asyncio.create_task(run_dex_collector(redis, CONFIG)),
        asyncio.create_task(run_core_engine(redis, CONFIG)),
        asyncio.create_task(run_eval_engine(redis, CONFIG)),
        asyncio.create_task(run_stats_engine(redis, CONFIG)),
        asyncio.create_task(api.serve()),
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
