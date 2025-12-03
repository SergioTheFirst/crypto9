# Crypto Intel Premium v9 — Project Constitution

This document defines **non-negotiable rules** for the Crypto Intel Premium v9 system.

Any implementation that violates these rules is **invalid**, even if tests pass.

---

## 1. Mission

Crypto Intel Premium v9 is a **read-only trading intelligence system**:

- It **observes** centralized and decentralized exchanges.
- It **detects and ranks** rare, high-quality opportunities.
- It **reports** important events to a human operator (Dashboard + Telegram).
- It **never executes trades** and **never controls funds**.

---

## 2. Core Principles

1. **Safety > Profit > Cleverness**

   - No optimization or "smart trick" is allowed if it reduces transparency or safety.
   - The system must fail **loudly and explicitly**, never silently.

2. **LLM is advisory-only**

   - LLM **never** participates in core trading logic or signal generation.
   - LLM produces **summaries and human-readable context only**.
   - If LLM is down, the rest of the system must work unchanged.

3. **Deterministic core**

   - All market calculations (orderbook normalization, spread, fees, PnL) are **pure, deterministic functions**.
   - Same input → same output. No hidden state, no random factors.

4. **Graceful degradation**

   - If DEX is down → system continues with CEX only.
   - If one CEX is down → system continues with remaining exchanges.
   - If Redis is temporarily down → processes keep retrying and log clear errors.
   - If Telegram or LLM are down → core engine keeps running.

5. **Observability**

   - At any time, a human must be able to see:
     - system health,
     - loaded symbols,
     - active exchanges,
     - number of active signals.
   - Logs must be structured and minimal, not spammy.

6. **Minimalism**

   - No unused abstractions.
   - No "future-proofing" that complicates the code.
   - Every module must have a **single clear responsibility**.

7. **Human in the loop**

   - All signals are suggestions, not orders.
   - System is designed for human operators.

---

## 3. Architecture Rules

1. **Single source of truth: Redis**

   - All shared state is stored in Redis:
     - order books,
     - signals,
     - system status,
     - stats.
   - There is no in-memory global shared state across services.

2. **Layered structure**

   - **Collectors** → write normalized books into Redis.
   - **Core engine** → reads from Redis, computes signals, writes signals + stats to Redis.
   - **StreamHub** → consumes Redis pub/sub and exposes it via SSE/WS.
   - **API server** → reads from Redis and StreamHub and serves the Dashboard.
   - **LLM worker** → reads aggregated events, produces summaries.
   - **Telegram notifier** → listens to critical events and sends rare alerts.

3. **No direct circular dependencies**

   - A module must not import each other in a cycle (e.g., `core_engine` importing `api_server` etc.).
   - Dependencies flow "downwards": config → state → collectors/core → stream/api → llm/notifier.

4. **Config-first**

   - All runtime behavior is controlled through `config.py` and environment variables.
   - No hard-coded magic values inside business logic.

---

## 4. Notifications Rules

1. Telegram is **not** a log sink and **not** a debug console.
2. Telegram is **only** for:
   - system startup/shutdown,
   - critical errors and degraded modes,
   - rare, high-confidence trading opportunities,
   - important human-level summaries (LLM digest).
3. Flooding Telegram with low-value events is considered a **constitutional violation**.

---

## 5. LLM Rules

1. LLM cannot:
   - change configs,
   - change thresholds,
   - change signal acceptance criteria,
   - decide whether a signal is "tradable".

2. LLM can only:
   - summarize N most recent signals,
   - explain market context in human language,
   - compress events for Telegram and UI.

If this is violated, the implementation is **invalid**.

---

## 6. UI & API Rules

1. UI is a **Premium operator console**, not a marketing gadget.
2. "Connecting…" states are unacceptable in a healthy system.
3. The Dashboard must:
   - show clear system status,
   - show whether Redis is reachable,
   - show number of active symbols and exchanges,
   - show when the last data update was received.

4. API contracts must be:
   - explicit,
   - stable,
   - documented in `API.md`.

---

## 7. Coding Standards (high-level)

Details in `DEVELOPMENT.md`, but in short:

- Python 3.11+
- Type hints everywhere.
- Pydantic models for all external-facing schemas and Redis payloads.
- No silent `except Exception: pass`.
- All network calls have timeouts and retries.

---

## 8. Non-negotiable Constraints for Codex

1. Do not introduce trading execution.
2. Do not couple LLM with core engine logic.
3. Do not send frequent Telegram events.
4. Do not break the documented API schemas.
5. If something is underspecified, choose the **simplest safe option**, not the most clever one.
