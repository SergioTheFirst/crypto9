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

    # Лучшая цена для покупки (минимум ask)
    best_ask = min(books.values(), key=lambda b: b.ask)
    # Лучшая цена для продажи (максимум bid)
    best_bid = max(books.values(), key=lambda b: b.bid)

    # Проверка, что арбитражная возможность существует
    if best_bid.bid <= best_ask.ask:
        return None

    # Арбитраж внутри одной биржи не допускается
    if best_bid.exchange == best_ask.exchange:
        return None

    return best_ask, best_bid


async def _cycle(
    redis: RedisState,
    cfg,
    history: HistoryStore,
    signal_filter: SignalFilter,
    clusterer: SignalClusterer,
):
    market_stats = await redis.get_market_stats()
    exchange_stats = await redis.get_exchange_stats()
    param_snap = await redis.get_param_snapshot()

    # Берем параметры из тюнера, если он включен, иначе из конфига
    effective_min_spread = param_snap.min_spread_bps if param_snap else cfg.engine.min_spread_bps
    effective_min_net = param_snap.min_net_profit_usd if param_snap else cfg.engine.min_net_profit_usd
    effective_min_vol = param_snap.min_volume_usd if param_snap else cfg.engine.min_volume_usd

    for symbol in cfg.collector.symbols:
        books = await redis.get_books(symbol)
        best_pair = _pick_best_books(books)

        if not best_pair:
            continue

        best_ask, best_bid = best_pair

        # --- РАСЧЕТ ПАРАМЕТРОВ СИГНАЛА ---
        spread = best_bid.bid - best_ask.ask
        base_mid = (best_ask.ask + best_bid.bid) / 2.0
        spread_bps = (spread / base_mid) * 10_000 if base_mid else 0.0

        # НОВОЕ: Расчет чистой прибыли
        volume_calc_usd = cfg.engine.volume_calc_usd
        fee_rate = cfg.engine.default_fee_rate
        slippage_rate = cfg.engine.default_slippage_rate

        # Количество базовой валюты (например, BTC) для объема volume_calc_usd
        quantity_base = volume_calc_usd / base_mid

        # Валовая прибыль в USD
        gross_profit = spread * quantity_base

        # Общие комиссии (покупка + продажа)
        total_fees_usd = 2 * volume_calc_usd * fee_rate

        # Оценка проскальзывания (в USD)
        total_slippage_usd = volume_calc_usd * slippage_rate

        # Чистая прибыль
        net_profit = gross_profit - total_fees_usd - total_slippage_usd
        net_profit_bps = (net_profit / volume_calc_usd) * 10_000 if volume_calc_usd else 0.0
        volume_usd = volume_calc_usd # Используем объем для фильтрации/отчета

        # --- ФИЛЬТРАЦИЯ ---
        if spread_bps < effective_min_spread:
            continue
        if net_profit < effective_min_net:
            continue
        # Используем volume_calc_usd как необходимый объем
        if volume_usd < effective_min_vol:
            continue

        # --- СОЗДАНИЕ СИГНАЛА ---
        sig = CoreSignal(
            symbol=symbol,
            buy_exchange=best_ask.exchange,
            sell_exchange=best_bid.exchange,
            buy_price=best_ask.ask,
            sell_price=best_bid.bid,
            volume_usd=volume_usd,
            spread=spread,
            spread_bps=spread_bps,
            fee_rate=fee_rate, # Используем заданную ставку комиссии
            slippage_rate=slippage_rate, # Используем заданную ставку проскальзывания
            net_profit=net_profit,
            net_profit_bps=net_profit_bps,
            created_at=datetime.utcnow(),
        )

        # ML Score and Clustering (already exists)
        features = build_signal_features(sig, market_stats, exchange_stats)
        ml_score = await signal_filter.score(features)
        sig.ml_score = ml_score

        cluster_id = clusterer.predict(features)
        sig.cluster_id = cluster_id

        if ml_score is not None and ml_score < cfg.ml.min_score:
            continue

        await redis.push_signal(sig)
        await history.append_signal(sig)
        # Сохраняем фичи для обучения: label=1 (прибыльный), label=0 (убыточный)
        await history.append_features(features, label=1 if net_profit > 0 else 0)
        log.debug(
            "New signal %s -> %.2f USD (S:%.2f BPS, ML:%.2f)",
            sig.symbol,
            sig.net_profit,
            sig.spread_bps,
            sig.ml_score or 0.0,
        )