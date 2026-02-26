from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..db import get_db
from ..models import User
from ..services.cache import get_cache_stats

router = APIRouter(tags=["ops"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    # Check DB connectivity
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@router.get("/api/debug/cache-stats")
def cache_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return get_cache_stats(db)
