"""Convenience launcher for the full stack."""
from __future__ import annotations

import asyncio
import logging

import uvicorn

from api.api_server import create_app
from collectors.cex_collector import run_cex_collector
from collectors.dex_collector import run_dex_collector
from config import get_config
from core.core_engine import run_core_engine
from core.stats_engine import run_stats_engine
from llm.summary_worker import run_summary_worker
from notifier.telegram_notifier import TelegramNotifier
from state.redis_state import RedisState

logging.basicConfig(level=logging.INFO)


async def _run_api(app, host: str, port: int) -> None:
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def _run_notifier(redis_state: RedisState) -> None:
    notifier = TelegramNotifier(redis_state)
    await notifier.run()


async def main() -> None:
    cfg = get_config()
    redis_state = RedisState()
    app = create_app(redis_state)

    tasks = [
        asyncio.create_task(run_cex_collector()),
        asyncio.create_task(run_core_engine()),
        asyncio.create_task(run_stats_engine()),
        asyncio.create_task(_run_api(app, cfg.api.host, cfg.api.port)),
    ]
    if cfg.collectors.enable_dex:
        tasks.append(asyncio.create_task(run_dex_collector()))
    if cfg.llm.enabled:
        tasks.append(asyncio.create_task(run_summary_worker()))
    if cfg.telegram.enabled:
        tasks.append(asyncio.create_task(_run_notifier(redis_state)))

    try:
        await asyncio.gather(*tasks)
    finally:
        await redis_state.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
