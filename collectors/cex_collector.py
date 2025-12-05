import asyncio
import logging
from typing import Optional

from config import CONFIG, Config
from state.redis_state import RedisState

logger = logging.getLogger("collectors.cex_collector")


async def _cycle(redis: RedisState, cfg: Config) -> None:
    """
    Один цикл работы CEX-коллектора.

    В версии v9.1.1 это минимальный стабильный скелет:
    - НЕ ходит на реальные биржи (это мы добавим следующим шагом),
    - НЕ пишет ничего в Redis (значит, core_engine просто не увидит книг),
    - зато не падает и не ломает весь backend.

    TODO (следующий этап):
    - Реализовать реальные HTTP-запросы к Binance/MEXC/OKX/Gate/KuCoin.
    - Нормализовать книги в OrderBook-модели.
    - Писать книги в Redis через RedisState.set_books().
    """
    # Здесь можно добавить лёгкий heartbeat-лог раз в N секунд, если нужно.
    await asyncio.sleep(cfg.collector.cycle_sec)


async def run_cex_collector(
    redis: RedisState,
    cfg: Config = CONFIG,
) -> None:
    """
    Точка входа CEX-коллектора для run_all.py.

    ВАЖНО:
    - Никаких get_config().
    - Конфиг приходит извне (CONFIG уже инициализирован в config.py).
    - Ошибки не валят весь процесс — ловим и логируем.
    """
    logger.info(
        "CEX collector started for symbols=%s, exchanges=%s",
        cfg.collector.symbols,
        cfg.collector.exchanges,
    )

    while True:
        try:
            await _cycle(redis, cfg)
        except Exception as exc:
            logger.exception("CEX collector error: %s", exc)
            # Пауза перед повтором, чтобы не устроить лог-флуд
            await asyncio.sleep(5.0)
