"""Run the FastAPI server."""
from __future__ import annotations

import uvicorn

from api.api_server import create_app
from config import get_config


if __name__ == "__main__":
    cfg = get_config().api
    uvicorn.run(create_app(), host=cfg.host, port=cfg.port, reload=False)
