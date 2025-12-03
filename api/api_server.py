"""FastAPI server exposing dashboard and data APIs."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from config import get_config
from api.schemas import HealthResponse, SignalsResponse, StatsResponse, SummariesResponse
from state.redis_state import RedisState
from stream.streamhub import get_stream_router

logger = logging.getLogger(__name__)


def get_redis_state() -> RedisState:
    return RedisState()


def create_app(redis_state: Optional[RedisState] = None) -> FastAPI:
    cfg = get_config()
    app = FastAPI(title="Crypto Intel Premium v9", version="0.1.0")

    if cfg.api.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(o) for o in cfg.api.cors_origins],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    rs = redis_state or RedisState()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await rs.close()

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        redis_ok = await rs.ping()
        return HealthResponse(status="ok" if redis_ok else "degraded", redis_ok=redis_ok)

    @app.get("/signals", response_model=SignalsResponse)
    async def list_signals(limit: int = 50) -> SignalsResponse:
        signals = await rs.recent_signals(limit)
        return SignalsResponse(signals=signals)

    @app.get("/stats", response_model=StatsResponse)
    async def stats() -> StatsResponse:
        current = await rs.get_system_stats()
        if not current:
            raise HTTPException(status_code=503, detail="Stats unavailable")
        return StatsResponse(stats=current)

    @app.get("/llm/summaries", response_model=SummariesResponse)
    async def summaries(limit: int = 5) -> SummariesResponse:
        items = await rs.recent_llm_summaries(limit)
        return SummariesResponse(summaries=items)

    ui_dir = Path(__file__).resolve().parent.parent / "ui"

    @app.get("/", response_class=HTMLResponse)
    async def index() -> FileResponse:
        index_file = ui_dir / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return FileResponse(index_file)

    @app.get("/ui/{asset}")
    async def static_asset(asset: str) -> FileResponse:
        target = ui_dir / asset
        if not target.exists():
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(target)

    app.include_router(get_stream_router(rs))
    return app


__all__ = ["create_app"]
