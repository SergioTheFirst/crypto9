import asyncio
import logging
from datetime import datetime
from typing import Optional

from analytics.features import build_signal_features
from analytics.history_store import HistoryStore
from ml.signal_clustering import SignalClusterer
from ml.signal_filter import SignalFilter
from state.models import CoreSignal, NormalizedBook
from state.redis_state import RedisState

log = logging.getLogger("core.core_engine")


async def run_core_engine(redis: RedisState, cfg):
    log.info("Core engine started")

    interval = cfg.engine.cycle_core_sec
    history = HistoryStore(redis, cfg)
    signal_filter = SignalFilter(cfg, redis)
    clusterer = SignalClusterer(cfg, redis)

    # background workers
    asyncio.create_task(signal_filter.training_loop(history))
    asyncio.create_task(clusterer.training_loop(history))

    while True:
        try:
            await _cycle(redis, cfg, history, signal_filter, clusterer)
        except Exception as e:
            log.error(f"Core engine error: {e}")

        await asyncio.sleep(interval)


def _pick_best_books(books: dict[str, NormalizedBook]) -> Optional[tuple[NormalizedBook, NormalizedBook]]:
    if not books:
        return None

    best_ask = min(books.values(), key=lambda b: b.ask)
    best_bid = max(books.values(), key=lambda b: b.bid)

    if best_bid.bid <= best_ask.ask:
        return None

    return best_ask, best_bid


async def _cycle(redis: RedisState, cfg, history: HistoryStore, signal_filter: SignalFilter, clusterer: SignalClusterer) -> None:
    market_stats_list = await redis.get_market_stats()
    exchange_stats_list = await redis.get_exchange_stats()
    market_stats = {m.symbol: m for m in market_stats_list}
    exchange_stats = {e.exchange: e for e in exchange_stats_list}

    tuned = await redis.get_param_snapshot()
    effective_min_net = tuned.min_net_profit_usd if tuned else cfg.engine.min_net_profit_usd
    effective_min_spread_bps = tuned.min_spread_bps if tuned else cfg.engine.min_spread_bps
    effective_min_vol = tuned.min_volume_usd if tuned else cfg.engine.min_volume_usd

    for symbol in cfg.collector.symbols:
        books = await redis.get_books(symbol)
        if len(books) < 2:
            continue

        picked = _pick_best_books(books)
        if not picked:
            continue

        best_ask, best_bid = picked
        spread = best_bid.bid - best_ask.ask

        fee_rate = cfg.engine.fee_rate
        slippage_rate = cfg.engine.slippage_rate
        volume_usd = cfg.engine.trade_volume_usd

        effective_buy = best_ask.ask * (1 + fee_rate + slippage_rate)
        effective_sell = best_bid.bid * (1 - fee_rate - slippage_rate)

        # assume volume denominated in quote asset USD
        qty = volume_usd / effective_buy
        gross = effective_sell * qty
        cost = effective_buy * qty
        net_profit = gross - cost

        base_mid = (best_ask.ask + best_bid.bid) / 2 if best_bid.bid else 0
        spread_bps = (spread / base_mid) * 10_000 if base_mid else 0.0
        net_profit_bps = (net_profit / volume_usd) * 10_000 if volume_usd else 0.0

        if spread_bps < effective_min_spread_bps:
            continue
        if net_profit < effective_min_net:
            continue
        if volume_usd < effective_min_vol:
            continue

        sig = CoreSignal(
            symbol=symbol,
            buy_exchange=best_ask.exchange,
            sell_exchange=best_bid.exchange,
            buy_price=best_ask.ask,
            sell_price=best_bid.bid,
            volume_usd=volume_usd,
            spread=spread,
            spread_bps=spread_bps,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            net_profit=net_profit,
            net_profit_bps=net_profit_bps,
            created_at=datetime.utcnow(),
        )

        features = build_signal_features(sig, market_stats, exchange_stats)
        ml_score = await signal_filter.score(features)
        sig.ml_score = ml_score

        cluster_id = clusterer.predict(features)
        sig.cluster_id = cluster_id

        if ml_score is not None and ml_score < cfg.ml.min_score:
            continue

        await redis.push_signal(sig)
        await history.append_signal(sig)
        await history.append_features(features, label=1 if net_profit > 0 else 0)
        log.debug(
            "New signal %s -> buy %s / sell %s | spread=%.6f net=%.6f ml=%.3f",
            symbol,
            best_ask.exchange,
            best_bid.exchange,
            spread,
            net_profit,
            ml_score if ml_score is not None else -1,
        )
