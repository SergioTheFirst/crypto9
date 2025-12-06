# collectors/cex_collector.py

import asyncio
import logging
from typing import List, Tuple

from config import CONFIG, Config
from state.redis_state import RedisState
from state.models import NormalizedBook
from collectors.sources import EXCHANGE_FETCHERS, FetcherFunction

logger = logging.getLogger("collectors.cex_collector")


async def _fetch_books_for_symbol(
    symbol: str, exchanges: List[str]
) -> List[Tuple[str, NormalizedBook]]:
    """
    Запускает асинхронное получение стаканов для одного символа со всех бирж.
    """
    tasks = []
    
    # Создаем список задач для асинхронного выполнения
    for ex in exchanges:
        fn: FetcherFunction | None = EXCHANGE_FETCHERS.get(ex)
        if fn:
            # Создаем задачу на получение данных и сохраняем информацию о бирже
            tasks.append((ex, fn(symbol)))
    
    if not tasks:
        logger.warning(f"No fetchers found for symbol {symbol} and exchanges {exchanges}")
        return []

    # Ждем завершения всех задач
    results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    
    collected_books: List[Tuple[str, NormalizedBook]] = []
    
    for (ex, _), result in zip(tasks, results):
        if isinstance(result, NormalizedBook):
            collected_books.append((ex, result))
        elif isinstance(result, Exception):
            logger.warning(f"Error fetching {symbol} from {ex}: {type(result).__name__}")
        elif result is None:
            logger.debug(f"No data returned for {symbol} from {ex}.")
            
    return collected_books


async def _cycle(redis: RedisState, cfg: Config) -> None:
    """
    Основной цикл CEX-коллектора.
    Получает данные для всех символов со всех бирж и сохраняет их в Redis.
    """
    symbols = cfg.collector.symbols
    exchanges = cfg.collector.cex_exchanges

    if not symbols or not exchanges:
        logger.warning("CEX collector is running but no symbols or exchanges configured.")
        await asyncio.sleep(cfg.collector.cycle_sec)
        return

    # Запускаем задачи для каждого символа параллельно
    symbol_tasks = [
        _fetch_books_for_symbol(symbol, exchanges) for symbol in symbols
    ]
    
    # Ждем завершения всех сборов по символам
    all_results = await asyncio.gather(*symbol_tasks)
    
    # Формируем словарь Symbol -> {Exchange -> Book}
    all_books: List[Tuple[str, List[Tuple[str, NormalizedBook]]]] = list(zip(symbols, all_results))
    
    # Сохраняем данные в Redis
    for symbol, fetched_books in all_books:
        # Преобразуем List[Tuple[str, NormalizedBook]] в Dict[str, NormalizedBook]
        books_dict = {ex: book for ex, book in fetched_books}
        if books_dict:
            await redis.set_books(symbol, books_dict)
            logger.debug(f"Saved {len(books_dict)} books for {symbol}")

    # Записываем текущее время обновления
    await redis.update_collector_timestamp("cex")

    await asyncio.sleep(cfg.collector.cycle_sec)


async def run_cex_collector(redis: RedisState, cfg: Config = CONFIG) -> None:
    """Точка входа для CEX-коллектора."""
    if not cfg.collector.use_cex:
        logger.info("CEX collector disabled (use_cex=False).")
        return

    logger.info(
        "CEX collector started for symbols=%s, exchanges=%s",
        cfg.collector.symbols,
        cfg.collector.cex_exchanges,
    )
    
    while True:
        try:
            await _cycle(redis, cfg)
        except asyncio.CancelledError:
            logger.warning("CEX collector stopped by cancellation.")
            break
        except Exception as exc:
            logger.exception("CEX collector critical error: %s", exc)
            # В случае критической ошибки ждем дольше
            await asyncio.sleep(10)