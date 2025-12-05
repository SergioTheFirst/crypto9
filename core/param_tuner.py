import asyncio
import logging
import statistics
from datetime import datetime
from typing import List

from analytics.history_store import HistoryStore
from state.models import CoreSignal, ParamSnapshot

log = logging.getLogger("core.param_tuner")


def _extract_signals(raw: List[dict]) -> List[CoreSignal]:
    result = []
    for item in raw:
        try:
            result.append(CoreSignal(**item))
        except Exception as exc:
            log.debug("Skipping invalid historical signal: %s", exc)
    return result


def _compute_snapshot(signals: List[CoreSignal], defaults) -> ParamSnapshot:
    if not signals:
        return ParamSnapshot(
            min_net_profit_usd=defaults.engine.min_net_profit_usd,
            min_spread_bps=defaults.engine.min_spread_bps,
            min_volume_usd=defaults.engine.min_volume_usd,
            updated_at=datetime.utcnow(),
        )

    net_profits = [s.net_profit for s in signals]
    spreads = [s.spread_bps or 0 for s in signals]
    volumes = [s.volume_usd for s in signals]

    median_profit = statistics.median(net_profits)
    p75_profit = statistics.quantiles(net_profits, n=4)[2] if len(net_profits) >= 4 else median_profit
    median_spread = statistics.median(spreads) if spreads else defaults.engine.min_spread_bps
    median_volume = statistics.median(volumes) if volumes else defaults.engine.min_volume_usd

    return ParamSnapshot(
        min_net_profit_usd=max(defaults.engine.min_net_profit_usd, p75_profit),
        min_spread_bps=max(defaults.engine.min_spread_bps, median_spread),
        min_volume_usd=max(defaults.engine.min_volume_usd, median_volume),
        updated_at=datetime.utcnow(),
    )


async def run_param_tuner(redis, cfg):
    if not cfg.tuner.enabled:
        log.info("Param tuner disabled")
        return

    history = HistoryStore(redis, cfg)
    interval = cfg.tuner.update_interval_sec

    log.info("Param tuner started")
    while True:
        try:
            raw_signals = await history.recent_signals(cfg.tuner.history_window)
            signals = _extract_signals(raw_signals)
            snap = _compute_snapshot(signals, cfg)
            await redis.set_param_snapshot(snap)
            log.debug(
                "Tuner snapshot updated: profit>=%.4f spread>=%.4f vol>=%.2f",
                snap.min_net_profit_usd,
                snap.min_spread_bps,
                snap.min_volume_usd,
            )
        except Exception as exc:
            log.error("Param tuner error: %s", exc)

        await asyncio.sleep(interval)
