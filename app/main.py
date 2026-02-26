"""
MarketPulse Terminal — main FastAPI application.
Entry: uvicorn app.main:app --reload
"""
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers import alerts, auth, markets, ops, portfolios, settings as settings_router, symbols, watchlists, ws
from .tasks import run_alert_checker, run_broadcaster

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mpulse")

BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
ASSETS_DIR = FRONTEND_DIR / "assets"


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting MarketPulse Terminal …")
    init_db()
    # Start background tasks
    broadcaster_task = asyncio.create_task(run_broadcaster())
    alert_task = asyncio.create_task(run_alert_checker())
    logger.info("Background tasks started. Open http://localhost:8000")
    yield
    broadcaster_task.cancel()
    alert_task.cancel()
    try:
        await broadcaster_task
        await alert_task
    except asyncio.CancelledError:
        pass
    logger.info("MarketPulse Terminal shut down.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MarketPulse Terminal",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)


# ── Middleware ────────────────────────────────────────────────────────────────

@app.middleware("http")
async def add_request_id_and_headers(request: Request, call_next) -> Response:
    request_id = str(uuid.uuid4())[:8]
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    # Security headers
    csp = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://coin-images.coingecko.com https://assets.coingecko.com; "
        "connect-src 'self' ws://localhost:* wss://localhost:* ws://127.0.0.1:* wss://127.0.0.1:*;"
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# ── Static files ──────────────────────────────────────────────────────────────

app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


# ── API routers ───────────────────────────────────────────────────────────────

for r in [auth.router, markets.router, symbols.router, watchlists.router,
          portfolios.router, alerts.router, settings_router.router, ops.router, ws.router]:
    app.include_router(r)


# ── SPA catch-all ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def serve_root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/{full_path:path}", include_in_schema=False)
def serve_spa(full_path: str):
    # Let API and WebSocket routes handle themselves (they're registered first)
    return FileResponse(str(FRONTEND_DIR / "index.html"))
