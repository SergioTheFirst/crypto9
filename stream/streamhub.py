from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, WebSocket
from sse_starlette.sse import EventSourceResponse

from state.redis_state import RedisState

logger = logging.getLogger(__name__)


async def redis_sse_stream(redis: RedisState, channel: str) -> AsyncGenerator[str, None]:
    pubsub = redis.client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                yield f"data: {msg['data']}\n\n"
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


def get_stream_router(redis: RedisState) -> APIRouter:
    router = APIRouter()

    @router.get("/stream/system")
    async def stream_system():
        return EventSourceResponse(redis_sse_stream(redis, "streamhub:system"))

    @router.get("/stream/market")
    async def stream_market():
        return EventSourceResponse(redis_sse_stream(redis, "streamhub:market"))

    @router.websocket("/ws/signals")
    async def ws_signals(ws: WebSocket):
        await ws.accept()
        pubsub = redis.client.pubsub()
        await pubsub.subscribe("streamhub:signals")
        try:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    await ws.send_text(msg["data"])
        finally:
            await pubsub.unsubscribe("streamhub:signals")
            await pubsub.close()
            await ws.close()

    return router
