import asyncio
import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import CONFIG, Config
from state.redis_state import RedisState

logger = logging.getLogger("stream.streamhub")


def _encode_to_json(obj: BaseModel) -> str:
    """Helper to convert Pydantic model to JSON string."""
    # model_dump_json() - более эффективный способ сериализации в Pydantic v2
    return obj.model_dump_json()


async def _system_status_stream(redis: RedisState, cfg: Config):
    """
    Отправляет SystemStatus каждые N секунд как SSE.
    """
    # Используем интервал из нового конфига
    interval = cfg.api.status_stream_interval_sec
    
    while True:
        try:
            status = await redis.get_system_status()
            if status:
                # Отправляем в формате SSE
                data = _encode_to_json(status)
                yield f"data: {data}\n\n"
        except Exception as e:
            logger.error(f"System stream error: {e}")
            # Ждем дольше в случае ошибки, чтобы не спамить
            await asyncio.sleep(interval * 5)
            continue

        await asyncio.sleep(interval)


def get_stream_router(redis: RedisState, cfg: Config = CONFIG) -> APIRouter:
    router = APIRouter()

    @router.get("/stream/system")
    async def system_stream():
        return StreamingResponse(
            _system_status_stream(redis, cfg),
            media_type="text/event-stream"
        )

    return router