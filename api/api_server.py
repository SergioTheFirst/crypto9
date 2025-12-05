from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware

from state.redis_state import RedisState


def create_app(cfg):
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    redis = RedisState(cfg.redis)

    @app.get("/api/status")
    async def get_status():
        s = await redis.get_system_status()
        if not s:
            return {"status": "init"}
        return jsonable_encoder(s)

    @app.get("/api/market")
    async def get_market():
        m = await redis.get_market_stats()
        if not m:
            return {"detail": "Market stats not available"}
        return jsonable_encoder(m)

    @app.get("/api/signals")
    async def get_signals():
        sigs = await redis.get_signals()
        return jsonable_encoder(sigs)

    return app
