# run_all.py

import asyncio
import logging
import uvicorn
import sys

# Импорты конфигурации и состояния
from config import CONFIG
from state.redis_state import RedisState

# Импорты коллекторов
from collectors.cex_collector import run_cex_collector
from collectors.dex_collector import run_dex_collector

# Импорты движков
from core.core_engine import run_core_engine
from core.eval_engine import run_eval_engine
from core.stats_engine import run_stats_engine
from core.param_tuner import run_param_tuner

# Импорты внешних сервисов
from api.api_server import create_app
from notifier.telegram_notifier import TelegramNotifier
from llm.summary_worker import LLMSummaryWorker
# ---

async def main():
    # Настройка логгирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    log = logging.getLogger("MASTER")
    
    log.info("Starting Crypto Intel Premium v9.x")

    # -----------------------------------------
    #  Redis connection
    # -----------------------------------------
    redis = RedisState(CONFIG.redis)

    # -----------------------------------------
    #  Init Services
    # -----------------------------------------
    llm_worker = LLMSummaryWorker(redis, CONFIG)
    notifier = TelegramNotifier(redis, CONFIG)

    # -----------------------------------------
    #  API server
    # -----------------------------------------
    # Настраиваем Uvicorn сервер для работы с нашим FastAPI приложением
    app = create_app(CONFIG)
    api_server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=CONFIG.api.host,
            port=CONFIG.api.port,
            log_level="info",
        )
    )

    # -----------------------------------------
    #  Parallel pipeline (All Engines & Workers)
    # -----------------------------------------
    tasks = [
        # COLLECTORS (Сбор данных)
        asyncio.create_task(run_cex_collector(redis, CONFIG), name="CEX_Collector"),
        asyncio.create_task(run_dex_collector(redis, CONFIG), name="DEX_Collector"),
        
        # CORE ENGINES (Обработка, расчет)
        asyncio.create_task(run_core_engine(redis, CONFIG), name="Core_Engine"),
        
        # UTILITY ENGINES (Статистика, ML, Тюнинг)
        asyncio.create_task(run_eval_engine(redis, CONFIG), name="Eval_Engine"),
        asyncio.create_task(run_stats_engine(redis, CONFIG), name="Stats_Engine"),
        asyncio.create_task(run_param_tuner(redis, CONFIG), name="Param_Tuner"),
        
        # LLM & NOTIFICATIONS (Внешние сервисы)
        asyncio.create_task(llm_worker.run(), name="LLM_Worker"),
        asyncio.create_task(notifier.run(), name="Telegram_Notifier"),

        # API (UI, клиенты)
        asyncio.create_task(api_server.serve(), name="API_Server"),
    ]
    
    # -----------------------------------------
    #  Main Loop: Wait for all tasks
    # -----------------------------------------
    log.info("All services launched. Press Ctrl+C to stop.")
    
    try:
        # Ожидаем завершения всех задач
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        log.warning("System shutting down gracefully by user (Ctrl+C)...")
    finally:
        # Отменяем оставшиеся задачи при завершении
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        log.info("All services stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Обработка Ctrl+C, если она не была обработана внутри main()
        pass
    except RuntimeError as e:
        # Игнорируем специфическую ошибку "Event loop is closed" при прерывании
        if "Event loop is closed" not in str(e):
            raise