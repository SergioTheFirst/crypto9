
---

## 7️⃣ `DEVELOPMENT.md`

```markdown
# Development Guidelines — Crypto Intel Premium v9

This document defines coding standards and expectations for implementation.

---

## 1. Language and Runtime

- Python 3.11+
- Use `asyncio` where appropriate (e.g., API server, collectors).
- Typed code with `typing` and `pydantic`.

---

## 2. Project Structure

Suggested structure:

```text
config.py
run_all.py
run_engine.py
run_api.py
run_llm.py

state/
  __init__.py
  redis_state.py
  models.py

collectors/
  __init__.py
  cex_collector.py
  dex_collector.py

core/
  __init__.py
  core_engine.py
  stats_engine.py

stream/
  __init__.py
  streamhub.py

api/
  __init__.py
  api_server.py
  schemas.py

notifier/
  __init__.py
  telegram_notifier.py

llm/
  __init__.py
  summary_worker.py

ui/
  index.html
  dashboard.js
  premium.css
