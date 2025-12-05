import json
from typing import Dict, List, Optional
from redis.asyncio import Redis

from state.models import (
    NormalizedBook,
    MarketStats,
    ExchangeStats,
    SignalStats,
    SystemStatus,
    CoreSignal,
)


def _encode(obj):
    """Убираем datetime → строка ISO"""
    if hasattr(obj, "model_dump"):
        d = obj.model_dump()
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        return d
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
        return {ex: NormalizedBook(**b) for ex, b in data.items()}

    # --------------------------------------
    # MARKET STATS
    # --------------------------------------
    async def set_market_stats(self, stats: List[MarketStats]):
        await self.client.set(
            "state:market_stats",
            json.dumps([_encode(s) for s in stats])
        )

    async def get_market_stats(self) -> List[MarketStats]:
        raw = await self.client.get("state:market_stats")
        if not raw:
            return []
        return [MarketStats(**item) for item in json.loads(raw)]

    # --------------------------------------
    # EXCHANGE STATS
    # --------------------------------------
    async def set_exchange_stats(self, stats: List[ExchangeStats]):
        await self.client.set(
            "state:exchange_stats",
            json.dumps([_encode(s) for s in stats])
        )

    async def get_exchange_stats(self) -> List[ExchangeStats]:
        raw = await self.client.get("state:exchange_stats")
        if not raw:
            return []
        return [ExchangeStats(**s) for s in json.loads(raw)]

    # --------------------------------------
    # SYSTEM STATUS
    # --------------------------------------
    async def set_system_status(self, status: SystemStatus):
        await self.client.set(
            "state:system_status",
            json.dumps(_encode(status))
        )

    async def get_system_status(self) -> Optional[SystemStatus]:
        raw = await self.client.get("state:system_status")
        if not raw:
            return None
        return SystemStatus(**json.loads(raw))

    # --------------------------------------
    # SIGNALS
    # --------------------------------------
    async def push_signal(self, signal: CoreSignal):
        await self.client.lpush(
            "state:signals",
            json.dumps(_encode(signal))
        )
        await self.client.ltrim("state:signals", 0, 199)

    async def get_signals(self) -> List[CoreSignal]:
        raw_list = await self.client.lrange("state:signals", 0, 200)
        return [CoreSignal(**json.loads(r)) for r in raw_list]

    # --------------------------------------
    # SIGNAL STATS
    # --------------------------------------
    async def set_signal_stats(self, stats: SignalStats):
        await self.client.set(
            "state:signal_stats",
            json.dumps(_encode(stats))
        )

    async def get_signal_stats(self) -> Optional[SignalStats]:
        raw = await self.client.get("state:signal_stats")
        if not raw:
            return None
        return SignalStats(**json.loads(raw))
