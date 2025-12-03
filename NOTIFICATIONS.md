
---

## 5️⃣ `NOTIFICATIONS.md`

```markdown
# Notifications — Crypto Intel Premium v9

This document defines **exactly** what can and cannot be sent via Telegram.

Any implementation that spams or misuses Telegram is invalid.

---

## 1. Notification Channels

- **Telegram** — for rare, high-value events only.
- **Dashboard/UI** — for regular monitoring.

Telegram is **never** a replacement for logs.

---

## 2. Allowed Telegram Events

1. **System startup/shutdown**

   - On successful startup of the full system.
   - On clean shutdown or crash (if detected).

2. **Degradation or failure states**

   - Redis unreachable for a sustained period (e.g., > 30 seconds).
   - All CEX collectors failing (no orderbooks).
   - Critical CPU/memory overload or repeated crashes.

3. **Rare trading opportunities**

   - Signals with:
     - expected profit above a high threshold (configurable),
     - sufficient volume,
     - stable conditions (not a one-tick glitch).
   - Must be debounced (e.g., no more than 1 alert per route per X minutes).

4. **LLM summaries (optional)**

   - Periodic digest (e.g., every 30–60 minutes) of:
     - key signals,
     - market changes,
     - exchange problems.

---

## 3. Forbidden Telegram Usage

- No per-cycle or per-signal spam.
- No debug logs (errors, exceptions) unless truly critical.
- No "I'm alive" pings every few seconds.

---

## 4. Debouncing and Rate Limits

- Implement **per-event-key debouncing**:
  - Same type of event (e.g., same symbol+route) is not sent more often than once every N minutes.
- Implement global rate limiting:
  - Hard cap per hour (configurable).
- All limits configurable via `config.py`.

---

## 5. Message Format

Messages should be:

- short,
- structured,
- easily scannable.

Example critical signal:

```text
[CRITICAL SIGNAL]

Pair: BTCUSDT
Route: buy on Binance, sell on OKX
Profit: +0.45% (~$120 on $5k)
Volume: $5,000
Reason: sustained spread > threshold over 3 checks

ts: 2025-12-03T10:21:00Z
