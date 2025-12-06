import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from state.redis_state import _encode, RedisState
from state.models import CoreSignal

log = logging.getLogger("analytics.history_store")


class HistoryStore:
    """Lightweight helper to manage bounded historical data in Redis."""

    def __init__(self, redis: RedisState, cfg):
        self.redis = redis
        self.client = redis.client
        self.cfg = cfg.history
        log.debug("HistoryStore initialized with TTL=%s", self.cfg.ttl_sec)


    # ------------------------
    # Signals
    # ------------------------
    async def append_signal(self, signal: CoreSignal):
        """Добавляет сигнал в исторический список `history:signals`."""
        if not self.cfg.enabled:
            return

        # Важно: используем _encode для корректной сериализации datetime
        record = _encode(signal) 
        
        await self.client.lpush("history:signals", json.dumps(record))
        # Обрезаем список до максимальной длины
        await self.client.ltrim("history:signals", 0, self.cfg.signals_max_len - 1)
        
        if self.cfg.ttl_sec:
            # Устанавливаем TTL для очистки старых данных
            await self.client.expire("history:signals", self.cfg.ttl_sec)


    async def recent_signals(self, limit: int) -> List[Dict[str, Any]]:
        """Получает последние N сигналов из истории."""
        raw = await self.client.lrange("history:signals", 0, limit - 1)
        return [json.loads(item) for item in raw]


    # ------------------------
    # Spreads (для расчетов волатильности)
    # ------------------------
    async def append_spread(self, symbol: str, snapshot: Dict[str, Any]):
        """Добавляет моментальный снимок спреда для символа."""
        if not self.cfg.enabled or not self.cfg.store_spreads:
            return

        key = f"history:spreads:{symbol}"
        payload = _encode(snapshot)
        await self.client.lpush(key, json.dumps(payload))
        await self.client.ltrim(key, 0, self.cfg.spreads_max_len - 1)
        if self.cfg.ttl_sec:
            await self.client.expire(key, self.cfg.ttl_sec)

    async def recent_spreads(self, symbol: str, limit: int) -> List[Dict[str, Any]]:
        """Получает последние N снимков спредов для символа."""
        raw = await self.client.lrange(f"history:spreads:{symbol}", 0, limit - 1)
        return [json.loads(item) for item in raw]

    # ------------------------
    # Features (для ML)
    # ------------------------
    async def append_features(self, features: Dict[str, float], label: float | None = None):
        """Добавляет набор признаков для обучения ML-модели."""
        if not self.cfg.enabled:
            return

        record = {
            "features": features,
            "label": label,
            "created_at": datetime.utcnow().isoformat(),
        }
        await self.client.lpush("history:features:signals", json.dumps(record))
        await self.client.ltrim(
            "history:features:signals", 0, self.cfg.features_max_len - 1
        )
        if self.cfg.ttl_sec:
            await self.client.expire("history:features:signals", self.cfg.ttl_sec)

    async def recent_features(self, limit: int) -> List[Dict[str, Any]]:
        """Получает последние N записей признаков."""
        raw = await self.client.lrange("history:features:signals", 0, limit - 1)
        return [json.loads(item) for item in raw]