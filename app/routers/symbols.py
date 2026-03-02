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


@router.get("/resolve")
def resolve_ticker(
    ticker: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Try to fetch a quote for any ticker (even if not in DB yet). Used for autocomplete live lookup."""
    try:
        q = get_quote(ticker.upper(), db)
        if q.get("price") is None and q.get("stale"):
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' non trovato")
        return {
            "ticker": q.get("ticker", ticker.upper()),
            "name": q.get("name") or ticker.upper(),
            "price": q.get("price"),
            "currency": q.get("currency"),
            "type": "stock",
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' non trovato: {e}")


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
