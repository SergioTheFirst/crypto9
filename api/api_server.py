import logging
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from config import get_config
from state.redis_state import RedisState
from state.models import Signal, LLMSummary, Event

from api.schemas import (
    EventsResponse,
    ExchangeStatsResponse,
    MarketStatsResponse,
    SignalsResponse,
    SignalsStatsResponse,
    StatusResponse,
    SummariesResponse,
)
from stream.streamhub import get_stream_router

logger = logging.getLogger(__name__)


def create_app(redis_state: RedisState) -> FastAPI:
    cfg = get_config()
    app = FastAPI(title="Crypto Intel Premium v9")

    if cfg.api.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(o) for o in cfg.api.cors_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    ui_dir = Path(__file__).resolve().parent.parent / "ui"

    @app.get("/", response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        index_file = ui_dir / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="UI not found")
        return HTMLResponse(index_file.read_text(encoding="utf-8"))

    @app.get("/api/status", response_model=StatusResponse)
    async def api_status() -> StatusResponse:
        status = await redis_state.get_system_status()
        if not status:
            status = StatusResponse()
        return status

    @app.get("/api/signals", response_model=SignalsResponse)
    async def api_signals(
        limit: int = Query(50, ge=1, le=500),
        min_profit_bps: Optional[float] = Query(None),
        symbol: Optional[str] = Query(None),
    ) -> SignalsResponse:
        items: List[Signal] = await redis_state.get_signals()

        if min_profit_bps is not None:
            items = [s for s in items if s.expected_profit_bps >= min_profit_bps]
        if symbol is not None:
            items = [s for s in items if s.symbol == symbol]

        return SignalsResponse(signals=items[:limit])

    @app.get("/api/stats/market", response_model=MarketStatsResponse)
    async def api_market_stats() -> MarketStatsResponse:
        stats = await redis_state.get_market_stats()
        return MarketStatsResponse(symbols=stats)

    @app.get("/api/stats/exchanges", response_model=ExchangeStatsResponse)
    async def api_exchanges() -> ExchangeStatsResponse:
        stats = await redis_state.get_exchange_stats()
        return ExchangeStatsResponse(exchanges=stats)

    @app.get("/api/stats/signals", response_model=SignalsStatsResponse)
    async def api_signals_stats() -> SignalsStatsResponse:
        stats = await redis_state.get_signal_stats()
        if not stats:
            stats = SignalsStatsResponse(
                total_signals=0, active_signals=0, avg_profit_bps=0.0
            )
        return stats

    @app.get("/api/events", response_model=EventsResponse)
    async def api_events() -> EventsResponse:
        summaries = await redis_state.get_llm_summaries(limit=10)
        events = [
            Event(
                id=s.id,
                kind=s.kind,
                title=s.title,
                text=s.text,
                created_at=s.created_at,
            )
            for s in summaries
        ]
        return EventsResponse(events=events)

    @app.get("/api/summaries", response_model=SummariesResponse)
    async def api_summaries() -> SummariesResponse:
        summaries = await redis_state.get_llm_summaries(limit=10)
        return SummariesResponse(events=summaries)

    @app.get("/ui/index.html")
    async def ui_index() -> FileResponse:
        index_file = ui_dir / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="UI not found")
        return FileResponse(index_file)

    app.include_router(get_stream_router(redis_state))
    return app


async def run_api(redis_state: RedisState):
    import uvicorn

    app = create_app(redis_state)
    cfg = get_config()
    config = uvicorn.Config(
        app,
        host=cfg.api.host,
        port=cfg.api.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()
