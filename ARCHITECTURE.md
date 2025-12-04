
---

## 3️⃣ `ARCHITECTURE.md`

```markdown
# Architecture — Crypto Intel Premium v9

This document describes the architecture of Crypto Intel Premium v9.

---

## 1. High-Level Overview

The system is composed of multiple cooperating services, all sharing state via Redis:

```text
[CEX APIs]   [DEX APIs (optional)]
    |                 |
    v                 v
collectors/cex_collector.py
collectors/dex_collector.py
             |
             v
        Redis (state:books, stats)
             |
             v
      core/core_engine.py
             |
             v
        Redis (state:signals, stats)
             |
             v
      stream/streamhub.py
             |
     +-------+--------+
     |                |
SSE / HTTP        WS / HTTP
     |                |
 ui/ (Dashboard)   API clients

llm/summary_worker.py → Redis (events) → notifier/telegram_notifier.py
