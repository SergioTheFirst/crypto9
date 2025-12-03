"""Redis pub/sub bridge exposing SSE and WebSocket streams."""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import EventSourceResponse

from state.redis_state import RedisState


class StreamHub:
    def __init__(self, redis_state: RedisState) -> None:
        self.redis_state = redis_state

    async def _event_generator(self) -> AsyncGenerator[str, None]:
        async for raw in self.redis_state.subscribe_events():
            yield raw

    async def sse(self) -> EventSourceResponse:
        async def event_stream() -> AsyncGenerator[str, None]:
            async for event in self._event_generator():
                yield event

        return EventSourceResponse(event_stream())

    async def websocket(self, ws: WebSocket) -> None:
        await ws.accept()
        try:
            async for event in self._event_generator():
                await ws.send_text(event)
        except WebSocketDisconnect:
            return


def get_stream_router(redis_state: RedisState) -> APIRouter:
    hub = StreamHub(redis_state)
    router = APIRouter()

    @router.get("/stream/events")
    async def stream_events() -> EventSourceResponse:
        return await hub.sse()

    @router.websocket("/ws/events")
    async def websocket_events(ws: WebSocket) -> None:
        await hub.websocket(ws)

    return router


__all__ = ["StreamHub", "get_stream_router"]
