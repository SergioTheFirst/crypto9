"""Run the LLM summary worker."""
from __future__ import annotations

import asyncio

from llm.summary_worker import run_summary_worker


if __name__ == "__main__":
    try:
        asyncio.run(run_summary_worker())
    except KeyboardInterrupt:
        pass
