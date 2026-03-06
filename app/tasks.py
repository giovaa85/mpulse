"""
Background tasks:
  - WebSocket connection manager
  - Periodic broadcaster (indices + crypto + per-user watchlist)
  - Periodic alert checker
"""
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from .config import settings

logger = logging.getLogger(__name__)


# ── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        # user_id -> set of WebSocket connections
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[user_id].add(ws)
        logger.debug("WS connected user_id=%d  total=%d", user_id, self.count())

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        self._connections[user_id].discard(ws)
        if not self._connections[user_id]:
            del self._connections[user_id]
        logger.debug("WS disconnected user_id=%d  total=%d", user_id, self.count())

    def has_connections(self) -> bool:
        return bool(self._connections)

    def count(self) -> int:
        return sum(len(v) for v in self._connections.values())

    def get_connected_users(self) -> list[int]:
        return list(self._connections.keys())

    async def send_to_user(self, user_id: int, data: dict) -> None:
        dead = set()
        for ws in list(self._connections.get(user_id, set())):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections[user_id].discard(ws)

    async def broadcast(self, data: dict) -> None:
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, data)


manager = ConnectionManager()


# ── WebSocket endpoint helper ─────────────────────────────────────────────────

async def handle_ws_connection(websocket: WebSocket, user_id: int) -> None:
    """Manages a single WS connection lifecycle."""
    await manager.connect(user_id, websocket)
    try:
        while True:
            # Wait for client messages (ping keepalive)
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WS error user_id=%d: %s", user_id, exc)
    finally:
        manager.disconnect(user_id, websocket)


# ── Sync helpers (run in thread pool via asyncio.to_thread) ───────────────────

def _fetch_markets_sync() -> list[dict]:
    from .db import get_db_ctx
    from .services.market import get_markets_overview
    with get_db_ctx() as db:
        return get_markets_overview(db)


def _fetch_crypto_sync() -> list[dict]:
    from .db import get_db_ctx
    from .services.crypto import get_crypto_overview
    with get_db_ctx() as db:
        return get_crypto_overview(db)


def _prefetch_quotes_sync() -> None:
    """Pre-populate quote cache for all configured tickers so dashboard loads instantly."""
    import time as _time
    from .config import settings
    from .db import get_db_ctx
    from .services.market import get_quote

    tickers = list(settings.INDICES) + list(settings.TOP_STOCKS) + list(settings.COMMODITIES)
    with get_db_ctx() as db:
        for ticker in tickers:
            try:
                get_quote(ticker, db)
                _time.sleep(0.3)
            except Exception as exc:
                logger.debug("Quote prefetch failed for %s: %s", ticker, exc)


def _prefetch_history_sync() -> None:
    """Pre-populate 1y history for all configured tickers so dashboard can show 1M/1Y returns."""
    import time as _time
    from .config import settings
    from .db import get_db_ctx
    from .services.market import get_history

    tickers = list(settings.INDICES) + list(settings.TOP_STOCKS) + list(settings.COMMODITIES)
    with get_db_ctx() as db:
        for ticker in tickers:
            try:
                get_history(ticker, db, period="1y", interval="1d")
                _time.sleep(0.3)
            except Exception as exc:
                logger.debug("History prefetch failed for %s: %s", ticker, exc)


def _fetch_user_watchlist_sync(user_id: int) -> list[dict]:
    from .db import get_db_ctx
    from .services.market import get_watchlist_quotes
    with get_db_ctx() as db:
        return get_watchlist_quotes(user_id, db)


def _check_alerts_sync() -> list[dict]:
    from .db import get_db_ctx
    from .services.alerts import check_all_alerts
    with get_db_ctx() as db:
        return check_all_alerts(db)


# ── Background tasks ──────────────────────────────────────────────────────────

async def run_broadcaster() -> None:
    """Periodically push market updates to all connected WS clients."""
    await asyncio.sleep(5)  # Startup delay
    while True:
        try:
            if manager.has_connections():
                # Fetch shared data
                indices = await asyncio.to_thread(_fetch_markets_sync)
                crypto = await asyncio.to_thread(_fetch_crypto_sync)

                # Per-user watchlist
                for user_id in manager.get_connected_users():
                    watchlist = await asyncio.to_thread(_fetch_user_watchlist_sync, user_id)
                    await manager.send_to_user(user_id, {
                        "type": "market_update",
                        "payload": {
                            "indices": indices,
                            "crypto": crypto[:5],
                            "watchlist": watchlist,
                            "ts": datetime.utcnow().isoformat(),
                        },
                    })
        except Exception as exc:
            logger.error("Broadcaster error: %s", exc)

        await asyncio.sleep(settings.BROADCAST_INTERVAL)


async def run_quote_prewarmer() -> None:
    """At startup and every QUOTE_TTL*4, pre-fetch current quotes for all configured tickers."""
    await asyncio.sleep(5)  # Start quickly so dashboard loads fast
    while True:
        try:
            logger.info("Quote prewarmer started for all configured tickers…")
            await asyncio.to_thread(_prefetch_quotes_sync)
            logger.info("Quote prewarmer completed.")
        except Exception as exc:
            logger.error("Quote prewarmer error: %s", exc)
        await asyncio.sleep(settings.QUOTE_TTL * 4)


async def run_history_prefetcher() -> None:
    """At startup and every HISTORY_TTL, pre-fetch 1y history for all configured tickers."""
    await asyncio.sleep(8)  # Let the server fully start first
    while True:
        try:
            logger.info("History prefetch started for all configured tickers…")
            await asyncio.to_thread(_prefetch_history_sync)
            logger.info("History prefetch completed.")
        except Exception as exc:
            logger.error("History prefetcher error: %s", exc)
        await asyncio.sleep(settings.HISTORY_TTL)


async def run_alert_checker() -> None:
    """Check all enabled alerts against current prices every 60 seconds."""
    await asyncio.sleep(10)  # Startup delay
    while True:
        try:
            triggered = await asyncio.to_thread(_check_alerts_sync)
            for event in triggered:
                uid = event.get("user_id")
                if uid and manager.has_connections():
                    await manager.send_to_user(uid, {
                        "type": "alert_triggered",
                        "payload": event,
                    })
        except Exception as exc:
            logger.error("Alert checker error: %s", exc)

        await asyncio.sleep(60)
