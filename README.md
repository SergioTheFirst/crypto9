# Crypto Intel Premium v9

**Crypto Intel Premium v9** is a modular, read-only crypto market intelligence system:

- Collects orderbooks from multiple CEX (and optionally DEX).
- Normalizes and analyzes market data in real time.
- Detects rare, high-quality opportunities.
- Exposes data via an operator Dashboard (HTTP + SSE + WebSocket).
- Sends rare, important alerts via Telegram.
- Uses an **LLM only for human-readable summaries**, never for trading logic.

The system is designed around **safety, determinism, and observability**.  
See `CONSTITUTION.md` for non-negotiable project rules.

---

## Features

- Multi-exchange CEX collector with backoff and health tracking.
- Optional DEX collector that never blocks the system.
- Core engine for normalized spread and profit computation.
- Redis-backed state and pub/sub (single source of truth).
- Premium operator Dashboard (v9) powered by FastAPI.
- StreamHub for SSE/WS live updates.
- Telegram notifier with strict anti-spam rules.
- LLM-based summaries of rare events (optional, advisory only).

---

## Components

- `config.py` – global configuration and feature flags.
- `state/redis_state.py` – typed Redis access layer.
- `collectors/cex_collector.py` – CEX orderbook ingestion.
- `collectors/dex_collector.py` – optional DEX quotes.
- `core/core_engine.py` – signal generation logic.
- `core/stats_engine.py` – market and system stats.
- `stream/streamhub.py` – Redis pub/sub → SSE/WS bridge.
- `api/api_server.py` – FastAPI app serving UI and JSON APIs.
- `notifier/telegram_notifier.py` – rare critical alerts.
- `llm/summary_worker.py` – advisory event summaries.
- `ui/` – Premium Dashboard static assets.

Detailed architecture: `ARCHITECTURE.md`  
API contracts: `API.md`  
Notifications contract: `NOTIFICATIONS.md`  
LLM behavior: `LLM_DESIGN.md`  
Development standards: `DEVELOPMENT.md`

---

## Quickstart

> NOTE: This is a high-level outline. See `DEVELOPMENT.md` for details.

### 1. Requirements

- Python 3.11+
- Redis server running and reachable
- (Optional) Telegram bot token and chat ID
- (Optional) OpenAI/LLM credentials for summaries

### 2. Installation

```bash
git clone <your-repo-url> crypto-intel-v9
cd crypto-intel-v9
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
