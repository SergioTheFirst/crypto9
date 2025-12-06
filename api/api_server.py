import json
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware

from config import CONFIG
from state.redis_state import RedisState
from stream.streamhub import get_stream_router


def create_app(cfg: CONFIG.__class__):
    app = FastAPI(title="Crypto Intel Premium v9.x API")

    # CORS (нужно для UI)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    redis = RedisState(cfg.redis)

    # Добавляем роутер для стримов
    app.include_router(get_stream_router(redis, cfg))

    # ------------------------- STATUS -------------------------\
    @app.get("/api/status")
    async def api_status():
        stat = await redis.get_system_status()
        # Pydantic-модели по умолчанию могут быть возвращены напрямую FastAPI
        return JSONResponse(stat)

    # ------------------------- MARKET -------------------------\
    @app.get("/api/market")
    async def api_market():
        market = await redis.get_market_stats()
        if not market:
            return JSONResponse({"detail": "No market stats"}, status_code=404)
        return JSONResponse(market)

    # ------------------------- SIGNALS ------------------------\
    # ИСПРАВЛЕНИЕ: Добавлен параметр limit для получения ограниченного количества сигналов.
    @app.get("/api/signals")
    async def api_signals(limit: int = Query(default=100, ge=1, le=1000)):
        signals = await redis.get_signals(limit=limit)
        return JSONResponse(signals)

    # ------------------------- SIGNAL STATS --------------------\
    @app.get("/api/stats/signals")
    async def api_signal_stats():
        stats = await redis.get_signal_stats()
        if not stats:
            return JSONResponse({"detail": "No signal stats"}, status_code=404)
        return JSONResponse(stats)

    # ------------------------- HISTORICAL DATA --------------------\
    # Здесь можно добавить эндпоинты для получения истории из HistoryStore

    # ВРЕМЕННО УДАЛЕН. Функционал стрима перенесен в streamhub.py
    # ------------------------- LIVE STREAM --------------------
    # @app.get("/api/stream")
    # async def api_stream(request: Request):
    #    ...

    return app