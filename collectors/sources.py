import httpx
import logging
from state.models import NormalizedBook
from datetime import datetime
from typing import Optional

logger = logging.getLogger("collectors.sources")


async def fetch_binance(symbol: str) -> Optional[NormalizedBook]:
    url = f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}"

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(url)
            r.raise_for_status() 
            data = r.json()

        return NormalizedBook(
            symbol=symbol,
            exchange="binance",
            bid=float(data["bidPrice"]),
            ask=float(data["askPrice"]),
            bid_size=float(data["bidQty"]),     
            ask_size=float(data["askQty"]),     
            updated_at=datetime.utcnow(),       
        )

    except Exception as exc:
        logger.warning(f"Failed to fetch Binance book for {symbol}: {exc}")
        return None


async def fetch_mexc(symbol: str) -> Optional[NormalizedBook]:
    url = f"https://api.mexc.com/api/v3/ticker/bookTicker?symbol={symbol}"

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(url)
            r.raise_for_status() 
            data = r.json()

        return NormalizedBook(
            symbol=symbol,
            exchange="mexc",
            bid=float(data["bidPrice"]),
            ask=float(data["askPrice"]),
            bid_size=float(data["bidQty"]),     
            ask_size=float(data["askQty"]),     
            updated_at=datetime.utcnow(),       
        )

    except Exception as exc:
        logger.warning(f"Failed to fetch MEXC book for {symbol}: {exc}")
        return None