from fastapi import FastAPI, Query
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
    async def get_signals(min_ml_score: float | None = Query(None)):
        sigs = await redis.get_signals()
        if min_ml_score is not None:
            sigs = [s for s in sigs if s.ml_score is None or s.ml_score >= min_ml_score]
        return jsonable_encoder(sigs)

    @app.get("/api/params")
    async def get_params():
        snap = await redis.get_param_snapshot()
        return jsonable_encoder(snap) if snap else {"detail": "tuner_disabled"}

    @app.get("/api/clusters")
    async def get_clusters():
        clusters = await redis.get_cluster_state()
        return jsonable_encoder(clusters) if clusters else {"clusters": []}

    return app
