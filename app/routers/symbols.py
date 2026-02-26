from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services.market import get_history, get_quote, search_symbols

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


@router.get("/search")
def search(
    q: str = Query("", min_length=1),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    results = search_symbols(q, db)
    return {"results": results}


@router.get("/{ticker}/quote")
def quote(
    ticker: str,
    force: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        return get_quote(ticker.upper(), db, force_refresh=force)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{ticker}/history")
def history(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    force: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        return get_history(ticker.upper(), db, period=period, interval=interval, force_refresh=force)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
