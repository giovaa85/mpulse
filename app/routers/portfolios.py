import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Portfolio, Symbol, Transaction, User
from ..schemas import PortfolioCreate, PortfolioUpdate, TransactionCreate
from ..services.market import get_or_create_symbol
from ..services.portfolio import get_holdings, get_performance

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


def _get_portfolio_or_404(pid: int, user: User, db: Session) -> Portfolio:
    p = db.query(Portfolio).filter(Portfolio.id == pid, Portfolio.user_id == user.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return p


@router.get("")
def list_portfolios(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ps = db.query(Portfolio).filter(Portfolio.user_id == user.id).all()
    return [{"id": p.id, "name": p.name, "base_currency": p.base_currency,
             "created_at": p.created_at.isoformat()} for p in ps]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_portfolio(
    body: PortfolioCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = Portfolio(user_id=user.id, name=body.name, base_currency=body.base_currency)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name, "base_currency": p.base_currency, "created_at": p.created_at.isoformat()}


@router.put("/{pid}")
def update_portfolio(
    pid: int,
    body: PortfolioUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _get_portfolio_or_404(pid, user, db)
    if body.name is not None:
        p.name = body.name
    if body.base_currency is not None:
        p.base_currency = body.base_currency
    db.commit()
    return {"id": p.id, "name": p.name, "base_currency": p.base_currency}


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _get_portfolio_or_404(pid, user, db)
    db.delete(p)
    db.commit()


@router.get("/{pid}/holdings")
def holdings(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_portfolio_or_404(pid, user, db)
    return get_holdings(pid, db)


@router.get("/{pid}/performance")
def performance(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_portfolio_or_404(pid, user, db)
    return get_performance(pid, db)


@router.get("/{pid}/transactions")
def list_transactions(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_portfolio_or_404(pid, user, db)
    txns = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == pid)
        .order_by(Transaction.ts.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "ticker": t.symbol.ticker,
            "name": t.symbol.name,
            "ts": t.ts.isoformat(),
            "side": t.side,
            "qty": t.qty,
            "price": t.price,
            "fees": t.fees,
            "note": t.note,
        }
        for t in txns
    ]


@router.post("/{pid}/transactions", status_code=status.HTTP_201_CREATED)
def add_transaction(
    pid: int,
    body: TransactionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_portfolio_or_404(pid, user, db)

    try:
        ts = datetime.fromisoformat(body.ts)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format for 'ts'")

    sym = get_or_create_symbol(body.ticker.upper(), db)
    tx = Transaction(
        portfolio_id=pid,
        symbol_id=sym.id,
        ts=ts,
        side=body.side,
        qty=body.qty,
        price=body.price,
        fees=body.fees,
        note=body.note,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return {"id": tx.id, "ticker": sym.ticker, "side": tx.side, "qty": tx.qty, "price": tx.price}


@router.delete("/{pid}/transactions/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    pid: int,
    tx_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_portfolio_or_404(pid, user, db)
    tx = db.query(Transaction).filter(Transaction.id == tx_id, Transaction.portfolio_id == pid).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(tx)
    db.commit()


@router.get("/{pid}/transactions/export")
def export_transactions(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _get_portfolio_or_404(pid, user, db)
    txns = db.query(Transaction).filter(Transaction.portfolio_id == pid).order_by(Transaction.ts).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "ticker", "date", "side", "qty", "price", "fees", "note"])
    for t in txns:
        writer.writerow([t.id, t.symbol.ticker, t.ts.isoformat(), t.side, t.qty, t.price, t.fees, t.note or ""])

    buf.seek(0)
    filename = f"portfolio_{p.name.replace(' ', '_')}_transactions.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{pid}/transactions/import")
async def import_transactions(
    pid: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_portfolio_or_404(pid, user, db)
    content = await file.read()
    text = content.decode("utf-8-sig")  # Handle BOM
    reader = csv.DictReader(io.StringIO(text))

    required = {"ticker", "date", "side", "qty", "price"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise HTTPException(status_code=400, detail=f"CSV must have columns: {required}")

    imported = 0
    errors = []
    for i, row in enumerate(reader, start=2):
        try:
            ts = datetime.fromisoformat(row["date"])
            side = row["side"].lower()
            if side not in ("buy", "sell"):
                raise ValueError(f"side must be buy/sell, got: {side}")
            qty = float(row["qty"])
            price = float(row["price"])
            fees = float(row.get("fees") or 0)
            if qty <= 0 or price <= 0:
                raise ValueError("qty and price must be positive")

            sym = get_or_create_symbol(row["ticker"].upper(), db)
            tx = Transaction(
                portfolio_id=pid, symbol_id=sym.id,
                ts=ts, side=side, qty=qty, price=price, fees=fees,
                note=row.get("note") or None,
            )
            db.add(tx)
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "error": str(exc)})

    db.commit()
    return {"imported": imported, "errors": errors}
