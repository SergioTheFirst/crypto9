from fastapi import FastAPI
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
        return s.model_dump()

    @app.get("/api/market")
    async def get_market():
        m = await redis.get_market_stats()
        if not m:
            return {"detail": "Market stats not available"}
        return [x.model_dump() for x in m]

    @app.get("/api/signals")
    async def get_signals():
        sigs = await redis.get_signals()
        return [s.model_dump() for s in sigs]

    return app
