"""
CoinGecko public API wrapper with SQLite caching.
No API key required.
"""
import json
import logging
import time
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import FetchLog
from .cache import log_fetch

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
CACHE_KEY = "crypto:overview"

# We store the last result as JSON in the FetchLog's error column (repurposed).
# More efficient: use a dedicated cache table, but for this app we use a simple
# approach: serialize crypto data to a text column in a dedicated FetchLog row.
# Actually: we store it in a real approach using the fetch_log key lookup and
# a separate JSON file cached in memory. But to keep everything in SQLite we'll
# add a small helper that stores blob data alongside fetch_log.

# Simpler: use a module-level dict as in-process cache, and persist to DB via
# a dedicated approach using fetch_log + a companion "cache_blobs" or just
# serialize into the Symbol/Quote tables for crypto coins.
#
# Cleanest solution for this requirement: store crypto data as a JSON blob
# in the FetchLog "error" column (repurposed as "payload" for cache hits).
# This avoids adding a new table.

_crypto_memory_cache: dict = {}  # {"data": [...], "fetched_at": float}


def get_crypto_overview(db: Session, force_refresh: bool = False) -> list[dict]:
    """
    Return top-10 cryptos by market cap from CoinGecko.
    Cached for settings.CRYPTO_TTL seconds in memory + DB log.
    Falls back to stale data on failure.
    """
    now = time.time()
    cached_data = _crypto_memory_cache.get("data")
    cached_at = _crypto_memory_cache.get("fetched_at", 0.0)

    # Memory cache hit
    if not force_refresh and cached_data and (now - cached_at) < settings.CRYPTO_TTL:
        log_fetch(db, CACHE_KEY, "cache", cache_hit=True)
        return cached_data

    # Try DB-persisted cache
    last_ok = (
        db.query(FetchLog)
        .filter(FetchLog.key == CACHE_KEY, FetchLog.ok == True, FetchLog.cache_hit == False)
        .order_by(FetchLog.fetched_at.desc())
        .first()
    )

    if not force_refresh and last_ok:
        age = (datetime.utcnow() - last_ok.fetched_at).total_seconds()
        if age < settings.CRYPTO_TTL and last_ok.error:  # error column holds JSON payload
            try:
                data = json.loads(last_ok.error)
                _crypto_memory_cache["data"] = data
                _crypto_memory_cache["fetched_at"] = now
                log_fetch(db, CACHE_KEY, "cache", cache_hit=True)
                return data
            except Exception:
                pass

    # Fetch from CoinGecko
    t0 = time.perf_counter()
    try:
        resp = httpx.get(
            COINGECKO_URL,
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 10,
                "page": 1,
                "sparkline": "false",
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        raw = resp.json()

        data = [
            {
                "id": c["id"],
                "name": c["name"],
                "symbol": c["symbol"].upper(),
                "price_usd": c.get("current_price") or 0.0,
                "change_24h_pct": round(c.get("price_change_percentage_24h") or 0.0, 2),
                "market_cap": c.get("market_cap"),
                "volume_24h": c.get("total_volume"),
                "image": c.get("image"),
                "stale": False,
            }
            for c in raw
        ]

        _crypto_memory_cache["data"] = data
        _crypto_memory_cache["fetched_at"] = now

        ms = int((time.perf_counter() - t0) * 1000)
        # Store JSON payload in error column for persistence
        _persist_crypto_log(db, CACHE_KEY, ms, data)
        return data

    except Exception as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        log_fetch(db, CACHE_KEY, "coingecko", cache_hit=False, duration_ms=ms, ok=False, error=str(exc))
        logger.warning("CoinGecko fetch failed: %s", exc)

        # Return stale in-memory data
        if cached_data:
            stale = [dict(c, stale=True) for c in cached_data]
            return stale
        # Try DB persisted data
        if last_ok and last_ok.error:
            try:
                old = json.loads(last_ok.error)
                return [dict(c, stale=True) for c in old]
            except Exception:
                pass
        return []


def _persist_crypto_log(db: Session, key: str, duration_ms: int, data: list) -> None:
    """Store crypto data JSON in fetch_log for persistence across restarts."""
    try:
        entry = FetchLog(
            key=key,
            source="coingecko",
            fetched_at=datetime.utcnow(),
            cache_hit=False,
            duration_ms=duration_ms,
            ok=True,
            error=json.dumps(data),  # repurposed as payload
        )
        db.add(entry)
        db.commit()
        # Trim old entries (keep last 20 per key)
        old_ids = (
            db.query(FetchLog.id)
            .filter(FetchLog.key == key)
            .order_by(FetchLog.fetched_at.desc())
            .offset(20)
            .all()
        )
        if old_ids:
            db.query(FetchLog).filter(FetchLog.id.in_([r[0] for r in old_ids])).delete()
            db.commit()
    except Exception as exc:
        logger.warning("Failed to persist crypto log: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
