"""
Centralised cache utilities.
All data-fetching services call log_fetch() to record hits/misses.
The TTL check logic is embedded in each service for clarity.
"""
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import FetchLog

logger = logging.getLogger(__name__)


def log_fetch(
    db: Session,
    key: str,
    source: str,
    *,
    cache_hit: bool,
    duration_ms: int = 0,
    ok: bool = True,
    error: Optional[str] = None,
) -> None:
    """Insert one row into fetch_log (non-fatal on failure)."""
    try:
        entry = FetchLog(
            key=key,
            source=source,
            fetched_at=datetime.utcnow(),
            cache_hit=cache_hit,
            duration_ms=duration_ms,
            ok=ok,
            error=error,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        logger.warning("fetch_log insert failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def get_cache_stats(db: Session) -> dict:
    """Return aggregate stats from fetch_log."""
    from sqlalchemy import func, text
    from ..models import FetchLog

    total = db.query(func.count(FetchLog.id)).scalar() or 0
    hits = db.query(func.count(FetchLog.id)).filter(FetchLog.cache_hit == True).scalar() or 0
    errors = db.query(func.count(FetchLog.id)).filter(FetchLog.ok == False).scalar() or 0
    avg_ms = db.query(func.avg(FetchLog.duration_ms)).filter(FetchLog.cache_hit == False).scalar()

    # Per-source breakdown
    rows = db.execute(
        text("SELECT source, COUNT(*) as cnt FROM fetch_log GROUP BY source ORDER BY cnt DESC")
    ).fetchall()

    return {
        "total_fetches": total,
        "cache_hits": hits,
        "cache_misses": total - hits,
        "hit_ratio": round(hits / total, 3) if total else 0.0,
        "errors": errors,
        "avg_fetch_ms": round(avg_ms or 0, 1),
        "by_source": [{"source": r[0], "count": r[1]} for r in rows],
    }
