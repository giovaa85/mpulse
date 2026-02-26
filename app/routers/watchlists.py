import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Symbol, User, Watchlist, WatchlistItem
from ..schemas import WatchlistCreate, WatchlistItemAdd, WatchlistOut, WatchlistUpdate
from ..services.market import get_or_create_symbol, get_quote

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


def _get_wl_or_404(wl_id: int, user: User, db: Session) -> Watchlist:
    wl = db.query(Watchlist).filter(Watchlist.id == wl_id, Watchlist.user_id == user.id).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return wl


@router.get("")
def list_watchlists(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wls = db.query(Watchlist).filter(Watchlist.user_id == user.id).order_by(Watchlist.created_at).all()
    result = []
    for wl in wls:
        items = []
        for it in wl.items:
            sym: Symbol = it.symbol
            q = get_quote(sym.ticker, db)
            items.append({
                "ticker": sym.ticker,
                "name": sym.name,
                "price": q.get("price"),
                "change_abs": q.get("change_abs"),
                "change_pct": q.get("change_pct"),
                "currency": sym.currency,
                "stale": q.get("stale", False),
            })
        result.append({
            "id": wl.id,
            "name": wl.name,
            "created_at": wl.created_at.isoformat(),
            "items": items,
        })
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def create_watchlist(
    body: WatchlistCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = Watchlist(user_id=user.id, name=body.name)
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return {"id": wl.id, "name": wl.name, "created_at": wl.created_at.isoformat(), "items": []}


@router.put("/{wl_id}")
def update_watchlist(
    wl_id: int,
    body: WatchlistUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = _get_wl_or_404(wl_id, user, db)
    wl.name = body.name
    db.commit()
    return {"id": wl.id, "name": wl.name}


@router.delete("/{wl_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(
    wl_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = _get_wl_or_404(wl_id, user, db)
    db.delete(wl)
    db.commit()


@router.post("/{wl_id}/items", status_code=status.HTTP_201_CREATED)
def add_item(
    wl_id: int,
    body: WatchlistItemAdd,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = _get_wl_or_404(wl_id, user, db)
    ticker = body.ticker.upper()

    try:
        sym = get_or_create_symbol(ticker, db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Validate by fetching a live quote; surface errors to the user
    q = get_quote(ticker, db)
    if q.get("stale") and q.get("price") is None:
        raise HTTPException(status_code=422, detail=q.get("stale_reason") or f"Could not fetch data for {ticker}")

    # Check duplicate
    existing = db.query(WatchlistItem).filter(
        WatchlistItem.watchlist_id == wl.id,
        WatchlistItem.symbol_id == sym.id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{ticker} already in watchlist")

    item = WatchlistItem(watchlist_id=wl.id, symbol_id=sym.id)
    db.add(item)
    db.commit()
    return {"ticker": sym.ticker, "name": sym.name}


@router.delete("/{wl_id}/items/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item(
    wl_id: int,
    ticker: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = _get_wl_or_404(wl_id, user, db)
    ticker = ticker.upper()
    sym = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Symbol not found")
    deleted = db.query(WatchlistItem).filter(
        WatchlistItem.watchlist_id == wl.id,
        WatchlistItem.symbol_id == sym.id,
    ).delete()
    db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not in watchlist")


@router.get("/{wl_id}/export")
def export_watchlist(
    wl_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wl = _get_wl_or_404(wl_id, user, db)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ticker", "name", "type", "currency"])
    for it in wl.items:
        sym = it.symbol
        writer.writerow([sym.ticker, sym.name or "", sym.type or "", sym.currency or ""])
    buf.seek(0)
    filename = f"watchlist_{wl.name.replace(' ', '_')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
