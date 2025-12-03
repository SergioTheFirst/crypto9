
---

## 6️⃣ `LLM_DESIGN.md`

```markdown
# LLM Design — Crypto Intel Premium v9

The LLM in Premium v9 is strictly advisory. It never affects signal generation or thresholds.

---

## 1. Purpose

- Provide **human-readable summaries** of:
  - recent high-value signals,
  - exchange health issues,
  - market regimes (calm, volatile, etc.).
- Help a human operator understand what happened over a time window (e.g., last 15–60 minutes).

---

## 2. Inputs

The LLM worker reads from Redis:

- Recent signals:
  - symbol, route, profit, volume, timestamps.
- Exchange stats:
  - health class, error rates, latency.
- Market stats:
  - volatility per symbol, trend markers (optional).
- System events:
  - degradation or recovery events.

It may process, for example, the last N minutes of data or last N signals.

---

## 3. Outputs

The LLM worker generates **summaries**:

- `LLMSummary` object:

```json
{
  "id": "evt_20251203_001",
  "kind": "llm_summary",
  "title": "Market summary (last 30 minutes)",
  "text": "BTC maintained stable spread opportunities on Binance–OKX...",
  "created_at": "2025-12-03T10:20:30Z"
}
