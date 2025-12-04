from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from redis.asyncio import Redis

from state.models import (
    Event,
    ExchangeStats,
    LLMSummary,
    OrderBook,
    Signal,
    SignalEvalResult,
    SignalsAggregateStats,
    SymbolMarketStats,
    SystemStatus,
    VirtualEvalResult,
    VirtualTrade,
)

logger = logging.getLogger(__name__)


class RedisState:
    def __init__(self, url: str):
        self.client: Redis = Redis.from_url(url, decode_responses=True)

    async def close(self):
        await self.client.close()

    # ------------- books -------------

    async def set_books(self, symbol: str, books: Dict[str, OrderBook]) -> None:
        payload = {ex: book.model_dump(mode="json") for ex, book in books.items()}
        await self.client.set(f"state:books:{symbol}", json.dumps(payload))

    async def get_books(self, symbol: str) -> Dict[str, OrderBook]:
        raw = await self.client.get(f"state:books:{symbol}")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        out: Dict[str, OrderBook] = {}
        for ex, book in data.items():
            try:
                out[ex] = OrderBook(**book)
            except Exception:
                continue
        return out

    async def get_all_books(self) -> Dict[str, Dict[str, OrderBook]]:
        out: Dict[str, Dict[str, OrderBook]] = {}
        async for key in self.client.scan_iter("state:books:*"):
            symbol = key.split(":", 2)[2]
            out[symbol] = await self.get_books(symbol)
        return out

    # ------------- market stats -------------

    async def set_market_stats(self, items: List[SymbolMarketStats]) -> None:
        await self.client.set(
            "state:market_stats",
            json.dumps([i.model_dump(mode="json") for i in items]),
        )

    async def get_market_stats(self) -> List[SymbolMarketStats]:
        raw = await self.client.get("state:market_stats")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [SymbolMarketStats(**d) for d in data]

    # ------------- exchange stats -------------

    async def set_exchange_stats(self, items: List[ExchangeStats]) -> None:
        await self.client.set(
            "state:exchange_stats",
            json.dumps([i.model_dump(mode="json") for i in items]),
        )

    async def get_exchange_stats(self) -> List[ExchangeStats]:
        raw = await self.client.get("state:exchange_stats")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [ExchangeStats(**d) for d in data]

    # ------------- system status -------------

    async def set_system_status(self, status: SystemStatus) -> None:
        await self.client.set(
            "state:system_status",
            json.dumps(status.model_dump(mode="json")),
        )

    async def get_system_status(self) -> Optional[SystemStatus]:
        raw = await self.client.get("state:system_status")
        if not raw:
            return None
        try:
            return SystemStatus(**json.loads(raw))
        except Exception:
            return None

    # ------------- signals -------------

    async def set_signals(self, signals: List[Signal]) -> None:
        await self.client.set(
            "state:signals",
            json.dumps([s.model_dump(mode="json") for s in signals]),
        )

    async def get_signals(self) -> List[Signal]:
        raw = await self.client.get("state:signals")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        out: List[Signal] = []
        for item in data:
            try:
                out.append(Signal(**item))
            except Exception:
                continue
        return out

    async def append_signal(self, signal: Signal) -> None:
        signals = await self.get_signals()
        signals.append(signal)
        payload = [s.model_dump(mode="json") for s in signals]
        await self.client.set("state:signals", json.dumps(payload))
        await self.client.publish("streamhub:signals", json.dumps(signal.model_dump(mode="json")))

    # ------------- eval buffers -------------

    async def set_eval_pending(self, signal_id: str, payload: VirtualTrade | dict) -> None:
        data = payload.model_dump(mode="json") if isinstance(payload, VirtualTrade) else payload
        await self.client.set(f"eval:pending:{signal_id}", json.dumps(data))

    async def get_all_eval_pending(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        async for key in self.client.scan_iter("eval:pending:*"):
            raw = await self.client.get(key)
            if not raw:
                continue
            try:
                out[key.split(":", 2)[2]] = json.loads(raw)
            except json.JSONDecodeError:
                continue
        return out

    async def delete_eval_pending(self, signal_id: str) -> None:
        await self.client.delete(f"eval:pending:{signal_id}")

    async def append_eval_history(self, signal_id: str, payload: dict) -> None:
        key = f"eval:history:{signal_id}"
        raw = await self.client.get(key)
        history = json.loads(raw) if raw else []
        history.append(payload)
        await self.client.set(key, json.dumps(history))

    async def set_eval_pending_trade(
        self, trade: VirtualTrade, ttl_seconds: Optional[int] = None
    ) -> None:
        payload = trade.model_dump(mode="json")
        if ttl_seconds:
            await self.client.set(
                f"eval:pending:{trade.signal_id}", json.dumps(payload), ex=ttl_seconds
            )
        else:
            await self.client.set(
                f"eval:pending:{trade.signal_id}", json.dumps(payload)
            )

    async def get_eval_pending_trade(
        self, signal_id: str
    ) -> Optional[VirtualTrade]:
        raw = await self.client.get(f"eval:pending:{signal_id}")
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        try:
            return VirtualTrade(**data)
        except Exception:
            return None

    async def get_all_eval_pending_trades(self) -> Dict[str, VirtualTrade]:
        pending_raw = await self.get_all_eval_pending()
        out: Dict[str, VirtualTrade] = {}
        for signal_id, data in pending_raw.items():
            try:
                out[signal_id] = VirtualTrade(**data)
            except Exception:
                continue
        return out

    async def set_eval_result(self, result: VirtualEvalResult) -> None:
        payload = result.model_dump(mode="json")
        await self.client.set(
            f"eval:results:{result.signal_id}", json.dumps(payload)
        )

    async def get_eval_result(self, signal_id: str) -> Optional[VirtualEvalResult]:
        raw = await self.client.get(f"eval:results:{signal_id}")
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return VirtualEvalResult(**data)
        except Exception:
            return None

    async def get_all_eval_results(self) -> List[VirtualEvalResult]:
        out: List[VirtualEvalResult] = []
        async for key in self.client.scan_iter("eval:results:*"):
            raw = await self.client.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw)
                out.append(VirtualEvalResult(**data))
            except Exception:
                continue
        return out

    async def append_eval_history_entry(self, result: VirtualEvalResult) -> None:
        key_global = "eval:history"
        key_symbol = f"eval:history:{result.symbol}"
        payload = result.model_dump(mode="json")
        for key in (key_global, key_symbol):
            raw = await self.client.get(key)
            history = json.loads(raw) if raw else []
            history.append(payload)
            await self.client.set(key, json.dumps(history))

    # ------------- signal stats -------------

    async def set_signal_stats(self, stats: SignalsAggregateStats) -> None:
        await self.client.set(
            "state:signal_stats",
            json.dumps(stats.model_dump(mode="json")),
        )

    async def get_signal_stats(self) -> Optional[SignalsAggregateStats]:
        raw = await self.client.get("state:signal_stats")
        if not raw:
            return None
        try:
            return SignalsAggregateStats(**json.loads(raw))
        except Exception:
            return None

    # ------------- LLM summaries & events -------------

    async def add_llm_summary(self, summary: LLMSummary) -> None:
        raw = await self.client.get("state:llm_summaries")
        items = json.loads(raw) if raw else []
        items.append(summary.model_dump(mode="json"))
        await self.client.set("state:llm_summaries", json.dumps(items))
        await self.client.publish("streamhub:events", json.dumps(summary.model_dump(mode="json")))

    async def get_llm_summaries(self, limit: int = 10) -> List[LLMSummary]:
        raw = await self.client.get("state:llm_summaries")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        summaries: List[LLMSummary] = []
        for entry in data[-limit:]:
            try:
                summaries.append(LLMSummary(**entry))
            except Exception:
                continue
        return summaries

    async def add_event(self, event: Event) -> None:
        raw = await self.client.get("state:events")
        items = json.loads(raw) if raw else []
        items.append(event.model_dump(mode="json"))
        await self.client.set("state:events", json.dumps(items))
        await self.client.publish("streamhub:events", json.dumps(event.model_dump(mode="json")))

    async def get_events(self, limit: int = 50) -> List[Event]:
        raw = await self.client.get("state:events")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        events: List[Event] = []
        for entry in data[-limit:]:
            try:
                events.append(Event(**entry))
            except Exception:
                continue
        return events

    # eval results reserved for future
