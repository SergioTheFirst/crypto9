import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from state.redis_state import RedisState

logger = logging.getLogger(__name__)


async def redis_sse_stream(redis: RedisState, channel: str) -> AsyncGenerator[str, None]:
    pubsub = redis.client.pubsub()
    await pubsub.subscribe(channel)
    try:
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    yield f"data: {message['data']}\n\n"
                else:
                    yield "data: {}\n\n"
                await asyncio.sleep(0.1)
            except Exception as exc:
                logger.warning("sse_stream_error", extra={"channel": channel, "error": str(exc)})
                await asyncio.sleep(0.5)
    finally:
        try:
            await pubsub.unsubscribe(channel)
        finally:
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
            while True:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message.get("type") == "message":
                        await ws.send_text(message["data"])
                    await asyncio.sleep(0.05)
                except WebSocketDisconnect:
                    break
                except Exception as exc:
                    logger.warning("ws_stream_error", extra={"error": str(exc)})
                    await asyncio.sleep(0.2)
        finally:
            try:
                await pubsub.unsubscribe("streamhub:signals")
            finally:
                await pubsub.close()
            try:
                await ws.close()
            except Exception:
                pass

    return router
