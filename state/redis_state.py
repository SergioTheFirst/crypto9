import json
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel
from redis.asyncio import Redis

from state.models import (
    NormalizedBook,
    MarketStats,
    ExchangeStats,
    SignalStats,
    SystemStatus,
    CoreSignal,
    ParamSnapshot,
    ClusterState,
)


def _encode(obj):
    """Recursively transform datetimes and Pydantic models into JSON-safe structures."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    # Note: model_dump is used for Pydantic v2
    if isinstance(obj, BaseModel):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_encode(v) for v in obj]
    return obj


class RedisState:
    def __init__(self, cfg):
        url = f"redis://{cfg.host}:{cfg.port}/{cfg.db}"
        self.client: Redis = Redis.from_url(url, decode_responses=True)

    # --------------------------------------
    # BOOKS
    # --------------------------------------
    async def set_books(self, symbol: str, books: Dict[str, NormalizedBook]):
        dumped = {ex: _encode(b) for ex, b in books.items()}
        await self.client.set(f"state:books:{symbol}", json.dumps(dumped))

    async def get_books(self, symbol: str) -> Dict[str, NormalizedBook]:
        raw = await self.client.get(f"state:books:{symbol}")
        if not raw:
            return {}
        data = json.loads(raw)
        return {k: NormalizedBook(**v) for k, v in data.items()}

    async def set_book(self, symbol: str, exchange: str, book: NormalizedBook):
        key = f"state:books:{symbol}"
        # Fetch, update, and set back to maintain atomic update of the whole book set
        raw = await self.client.get(key)
        data = json.loads(raw) if raw else {}
        data[exchange] = _encode(book)
        await self.client.set(key, json.dumps(data))

    # --------------------------------------
    # MARKET STATS
    # --------------------------------------
    async def set_market_stats(self, stats: List[MarketStats]):
        dumped = {_s.symbol: _encode(_s) for _s in stats}
        await self.client.set("state:market_stats", json.dumps(dumped))

    async def get_market_stats(self) -> Optional[Dict[str, MarketStats]]:
        raw = await self.client.get("state:market_stats")
        if not raw:
            return None
        data = json.loads(raw)
        return {k: MarketStats(**v) for k, v in data.items()}

    # --------------------------------------
    # EXCHANGE STATS
    # --------------------------------------
    async def set_exchange_stats(self, stats: List[ExchangeStats]):
        dumped = {_s.exchange: _encode(_s) for _s in stats}
        await self.client.set("state:exchange_stats", json.dumps(dumped))

    async def get_exchange_stats(self) -> Optional[Dict[str, ExchangeStats]]:
        raw = await self.client.get("state:exchange_stats")
        if not raw:
            return None
        data = json.loads(raw)
        return {k: ExchangeStats(**v) for k, v in data.items()}

    # --------------------------------------
    # SYSTEM STATUS
    # --------------------------------------
    async def set_system_status(self, status: SystemStatus):
        await self.client.set(
            "state:system_status",
            json.dumps(_encode(status)),
        )

    async def get_system_status(self) -> Optional[SystemStatus]:
        raw = await self.client.get("state:system_status")
        if not raw:
            return None
        return SystemStatus(**json.loads(raw))

    # --------------------------------------
    # SIGNALS (НОВЫЕ/ИСПРАВЛЕННЫЕ МЕТОДЫ)
    # --------------------------------------
    async def push_signal(self, signal: CoreSignal):
        # Сохраняем CoreSignal для движков оценки и API
        await self.client.lpush("state:signals", json.dumps(_encode(signal)))
        # Ограничиваем список, чтобы он не рос бесконечно
        await self.client.ltrim("state:signals", 0, 1000)

    async def get_signals(self, limit: int = 1000) -> List[CoreSignal]:
        raw = await self.client.lrange("state:signals", 0, limit - 1)
        signals = []
        for item in raw:
            try:
                # CoreSignal — внутренняя модель, используется eval_engine
                signals.append(CoreSignal(**json.loads(item)))
            except Exception:
                # Игнорируем некорректные записи
                continue
        return signals

    # --------------------------------------
    # SIGNAL STATS
    # --------------------------------------
    async def set_signal_stats(self, stats: SignalStats):
        await self.client.set(
            "state:signal_stats",
            json.dumps(_encode(stats)),
        )

    async def get_signal_stats(self) -> Optional[SignalStats]:
        raw = await self.client.get("state:signal_stats")
        if not raw:
            return None
        return SignalStats(**json.loads(raw))

    # --------------------------------------
    # PARAM TUNER SNAPSHOT
    # --------------------------------------
    async def set_param_snapshot(self, snap: ParamSnapshot):
        await self.client.set(
            "state:param_tuner",
            json.dumps(_encode(snap)),
        )

    async def get_param_snapshot(self) -> Optional[ParamSnapshot]:
        raw = await self.client.get("state:param_tuner")
        if not raw:
            return None
        return ParamSnapshot(**json.loads(raw))

    # --------------------------------------
    # CLUSTERS
    # --------------------------------------
    async def set_cluster_state(self, clusters: ClusterState):
        await self.client.set("state:clusters:signals", json.dumps(_encode(clusters)))

    async def get_cluster_state(self) -> Optional[ClusterState]:
        raw = await self.client.get("state:clusters:signals")
        if not raw:
            return None
        return ClusterState(**json.loads(raw))