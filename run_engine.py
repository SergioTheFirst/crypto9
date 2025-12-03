"""Run collectors and engines."""
from __future__ import annotations

import asyncio
import logging

from collectors.cex_collector import run_cex_collector
from collectors.dex_collector import run_dex_collector
from core.core_engine import run_core_engine
from core.stats_engine import run_stats_engine

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    tasks = [
        asyncio.create_task(run_cex_collector()),
        asyncio.create_task(run_core_engine()),
        asyncio.create_task(run_stats_engine()),
    ]
    dex_task = asyncio.create_task(run_dex_collector())
    tasks.append(dex_task)
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
