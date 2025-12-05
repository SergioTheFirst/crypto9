import asyncio
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from config import CONFIG, Config
from state.redis_state import RedisState

logger = logging.getLogger("stream.streamhub")


async def _event_stream(redis: RedisState, cfg: Config):
    """
    Простая SSE-заглушка: отправляет ping каждые N секунд.
    """
    while True:
        yield f"data: ping\n\n"
        await asyncio.sleep(2)


def get_stream_router(redis: RedisState, cfg: Config = CONFIG) -> APIRouter:
    router = APIRouter()

    @router.get("/stream/system")
    async def system_stream():
        return StreamingResponse(
            _event_stream(redis, cfg),
            media_type="text/event-stream"
        )

    return router
