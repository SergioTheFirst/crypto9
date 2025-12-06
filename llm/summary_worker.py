# llm/summary_worker.py

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from config import CONFIG, Config
from state.redis_state import RedisState
from state.models import CoreSignal, LLMSummary, SystemStatus, MarketStats, ExchangeStats

logger = logging.getLogger("llm.summary_worker")


class LLMSummaryWorker:
    def __init__(self, redis: RedisState, cfg: Config) -> None:
        self._redis = redis
        self._cfg = cfg.llm
        self._engine_cfg = cfg.engine
        
        # Используем фиксированные значения, т.к. они не определены в config.py
        self._max_signals_in_context = 20 
        self._summary_interval_sec = 1800 # 30 минут
        
        # Настройки LLM API
        self._model = "@cf/meta/llama-2-7b-chat-int8"
        self._api_url = f"https://api.cloudflare.com/client/v4/accounts/{self._cfg.account_id}/ai/run/{self._model}"
        

    async def _load_context(self) -> Optional[str]:
        """Собирает данные из Redis и форматирует их в строку контекста для LLM."""
        
        # 1. Сигналы (фильтруем по порогу high-value)
        all_signals: List[CoreSignal] = await self._redis.get_signals()
        
        high_value_signals = sorted(
            [
                s for s in all_signals 
                if s.net_profit_bps is not None and s.net_profit_bps >= self._engine_cfg.notify_min_profit_bps
            ], 
            key=lambda s: s.created_at, 
            reverse=True
        )[:self._max_signals_in_context]
        
        signal_context = "Recent High-Value Signals (Max 20):\n"
        if high_value_signals:
            for s in high_value_signals:
                signal_context += (
                    f"- {s.symbol} | Buy {s.buy_exchange} @ {s.buy_price:.4f} "
                    f"| Sell {s.sell_exchange} @ {s.sell_price:.4f} "
                    f"| Net Profit: {s.net_profit:.2f} USD ({s.net_profit_bps:.2f} bps)\n"
                )
        else:
            signal_context += "- No high-value signals detected in the active pool.\n"
        
        
        # 2. Общий статус и Exchange Health
        sys_status: Optional[SystemStatus] = await self._redis.get_system_status()
        exchange_context = "Exchange Health Status:\n"
        if sys_status and sys_status.exchanges:
            for ex, stats in sys_status.exchanges.items():
                exchange_context += (
                    f"- {ex.upper()}: Status={stats.status}, Delay={stats.delay_ms:.0f}ms, "
                    f"ErrorRate={stats.error_rate:.2f}\n"
                )
        else:
            exchange_context += "- No exchange status available (data feed may be down).\n"

        # 3. Market Stats (Volatility)
        market_stats: List[MarketStats] = await self._redis.get_market_stats()
        market_context = "Market Volatility (1H):\n"
        if market_stats:
            for m in market_stats:
                 market_context += f"- {m.symbol}: Mid={m.last_mid:.4f}, Volatility={m.volatility_1h:.4f}\n"
        
        
        # 4. Формирование финального промпта
        prompt = (
            "You are an advisory AI for a high-frequency crypto arbitrage system (Crypto Intel Premium v9).\n"
            "Your only task is to generate a concise, human-readable summary of the last 30 minutes of market activity. "
            "Focus on key insights, exchange health changes, and the overall market regime (e.g., quiet, high volatility). "
            "DO NOT mention trading decisions or recommend actions. The summary must be under 5 sentences.\n\n"
            "--- CONTEXT ---\n"
            f"Time of summary: {datetime.utcnow().isoformat()} UTC\n\n"
            f"{exchange_context}\n"
            f"{market_context}\n"
            f"{signal_context}\n"
            "--- SUMMARY ---\n"
            "Generate your concise, high-value summary here:"
        )
        
        if not sys_status and not high_value_signals and not market_stats:
            logger.debug("LLM context is empty, skipping cycle.")
            return None

        return prompt

    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Вызывает LLM API (заглушка для Cloudflare Workers AI)."""
        if not self._cfg.enabled or not self._cfg.api_key:
            logger.debug("LLM API disabled or key missing.")
            return None
            
        logger.debug("Calling Cloudflare LLM API...")

        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "prompt": prompt,
            "max_tokens": 256,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._api_url, headers=headers, json=data, timeout=15) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Cloudflare LLM API failed (%d): %s", resp.status, body)
                        return None
                    data = await resp.json()
        except Exception as e:
            logger.error("Cloudflare LLM request failed: %s", e, exc_info=True)
            return None

        result = data.get("result") or {}
        text = str(result.get("response") or result.get("output") or result.get("text") or "").strip()

        return text if text else None


    async def run(self) -> None:
        """Основной цикл LLM worker'а."""
        if not self._cfg.enabled:
            logger.info("LLM summary worker disabled in config.")
            return

        logger.info("LLM summary worker started.")
        
        while True:
            try:
                # Проверка периодичности запуска
                last_summary: Optional[LLMSummary] = await self._redis.get_llm_summary()
                now = datetime.utcnow()
                
                if last_summary and (now - last_summary.created_at).total_seconds() < self._summary_interval_sec:
                    sleep_time = self._summary_interval_sec - (now - last_summary.created_at).total_seconds()
                    await asyncio.sleep(sleep_time)
                    continue
                
                logger.info("Generating new LLM summary...")
                ctx = await self._load_context()
                
                if ctx:
                    text = await self._call_llm(ctx)
                    
                    if text:
                        summary = LLMSummary(
                            text=text,
                            created_at=datetime.utcnow()
                        )
                        await self._redis.set_llm_summary(summary)
                        logger.info("LLM summary successfully generated and stored.")

            except asyncio.CancelledError:
                logger.warning("LLM summary worker stopped by cancellation.")
                break
            except Exception as e:
                logger.error("LLM summary loop error: %s", e, exc_info=True)

            await asyncio.sleep(60)