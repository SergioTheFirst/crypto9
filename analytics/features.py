from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, Optional

from state.models import CoreSignal, ExchangeStats, MarketStats


def _ts_to_datetime(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts)


def _symbol_index(symbol: str) -> int:
    return sum(ord(c) for c in symbol) % 1000


def _status_to_score(status: str) -> float:
    mapping = {"excellent": 1.0, "good": 0.8, "warming_up": 0.5, "degraded": 0.2}
    return mapping.get(status, 0.0)


def build_signal_features(
    signal: CoreSignal,
    market_stats: Optional[Dict[str, MarketStats]] = None,
    exchange_stats: Optional[Dict[str, ExchangeStats]] = None,
) -> Dict[str, float]:
    dt = _ts_to_datetime(signal.created_at)
    base_mid = (signal.buy_price + signal.sell_price) / 2 if signal.sell_price else 0.0
    spread_bps = (signal.spread / base_mid) * 10_000 if base_mid else 0.0
    net_profit_bps = (signal.net_profit / signal.volume_usd) * 10_000 if signal.volume_usd else 0.0

    m_stats = market_stats.get(signal.symbol) if market_stats else None
    vol = m_stats.volatility_1h if m_stats else 0.0
    mid = m_stats.last_mid if m_stats else base_mid

    buy_stats = exchange_stats.get(signal.buy_exchange) if exchange_stats else None
    sell_stats = exchange_stats.get(signal.sell_exchange) if exchange_stats else None

    feature_map: Dict[str, float] = {
        "spread_abs": float(signal.spread),
        "spread_bps": float(spread_bps),
        "net_profit_usd": float(signal.net_profit),
        "net_profit_bps": float(net_profit_bps),
        "volume_usd": float(signal.volume_usd),
        "symbol_idx": float(_symbol_index(signal.symbol)),
        "mid_price": float(mid),
        "volatility_1h": float(vol),
        "buy_exchange_score": _status_to_score(buy_stats.status) if buy_stats else 0.5,
        "sell_exchange_score": _status_to_score(sell_stats.status) if sell_stats else 0.5,
        "exchange_pair": float(hash((signal.buy_exchange, signal.sell_exchange)) % 10_000),
        "hour_of_day": dt.hour / 24.0,
    }

    return feature_map


def label_from_profit(signal: CoreSignal, profit_threshold: float) -> int:
    return 1 if signal.net_profit >= profit_threshold else 0
