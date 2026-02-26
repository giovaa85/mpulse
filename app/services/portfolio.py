"""
Portfolio analytics: holdings aggregation and performance metrics.
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Portfolio, Symbol, Transaction
from .market import get_history, get_quote

logger = logging.getLogger(__name__)


def get_holdings(portfolio_id: int, db: Session) -> list[dict]:
    """
    Aggregate transactions into current positions with live market value.
    Uses average-cost accounting.
    """
    txns = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == portfolio_id)
        .order_by(Transaction.ts)
        .all()
    )

    # {symbol_id: {qty, total_cost, symbol}}
    positions: dict[int, dict] = {}

    for tx in txns:
        sid = tx.symbol_id
        if sid not in positions:
            positions[sid] = {"qty": 0.0, "total_cost": 0.0, "symbol": tx.symbol}

        if tx.side == "buy":
            positions[sid]["qty"] += tx.qty
            positions[sid]["total_cost"] += tx.qty * tx.price + tx.fees
        elif tx.side == "sell":
            if positions[sid]["qty"] > 0:
                avg = positions[sid]["total_cost"] / positions[sid]["qty"]
                positions[sid]["qty"] -= tx.qty
                positions[sid]["total_cost"] -= tx.qty * avg

    holdings = []
    for sid, pos in positions.items():
        qty = round(pos["qty"], 8)
        if qty < 1e-8:
            continue

        sym: Symbol = pos["symbol"]
        avg_cost = pos["total_cost"] / qty if qty > 0 else 0
        total_cost = round(pos["total_cost"], 2)

        # Get current price
        current_price = None
        current_value = None
        pnl = None
        pnl_pct = None

        try:
            q = get_quote(sym.ticker, db)
            current_price = q.get("price")
            if current_price:
                current_value = round(current_price * qty, 2)
                pnl = round(current_value - total_cost, 2)
                pnl_pct = round(pnl / total_cost * 100, 2) if total_cost else None
        except Exception as exc:
            logger.debug("Price fetch for holding %s: %s", sym.ticker, exc)

        holdings.append({
            "ticker": sym.ticker,
            "name": sym.name,
            "qty": qty,
            "avg_cost": round(avg_cost, 4),
            "total_cost": total_cost,
            "current_price": current_price,
            "current_value": current_value,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct,
            "currency": sym.currency,
        })

    return holdings


def get_performance(portfolio_id: int, db: Session) -> dict:
    """
    Compute equity curve and performance metrics.
    Uses daily closing prices from cached history.
    """
    txns = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == portfolio_id)
        .order_by(Transaction.ts)
        .all()
    )

    if not txns:
        return {"equity_curve": [], "metrics": {}}

    # Collect unique tickers
    symbol_ids = list({t.symbol_id for t in txns})
    symbols = {s.id: s for s in db.query(Symbol).filter(Symbol.id.in_(symbol_ids)).all()}

    # Fetch daily price histories for all symbols
    price_maps: dict[int, dict] = {}  # symbol_id -> {date: close_price}
    for sid, sym in symbols.items():
        try:
            hist = get_history(sym.ticker, db, period="max", interval="1d")
            price_maps[sid] = {
                datetime.fromisoformat(b["ts"]).date(): b["close"]
                for b in hist.get("data", [])
                if b.get("close")
            }
        except Exception as exc:
            logger.debug("History fetch for %s: %s", sym.ticker, exc)
            price_maps[sid] = {}

    start_date = min(t.ts for t in txns).date()
    end_date = date.today()

    equity_curve = []
    positions: dict[int, float] = defaultdict(float)
    total_invested = 0.0
    tx_idx = 0

    cursor = start_date
    while cursor <= end_date:
        # Process transactions up to today
        while tx_idx < len(txns) and txns[tx_idx].ts.date() <= cursor:
            tx = txns[tx_idx]
            if tx.side == "buy":
                positions[tx.symbol_id] += tx.qty
                total_invested += tx.qty * tx.price + tx.fees
            elif tx.side == "sell":
                positions[tx.symbol_id] -= tx.qty
                total_invested -= tx.qty * tx.price
            tx_idx += 1

        # Calculate portfolio value
        value = 0.0
        any_price = False
        for sid, qty in positions.items():
            if qty > 1e-8:
                pm = price_maps.get(sid, {})
                price = _find_price(pm, cursor)
                if price:
                    value += qty * price
                    any_price = True

        if any_price:
            equity_curve.append({"date": str(cursor), "value": round(value, 2)})

        cursor += timedelta(days=1)

    metrics = _calc_metrics(equity_curve, total_invested)
    return {"equity_curve": equity_curve, "metrics": metrics}


def _find_price(price_map: dict, d: date) -> Optional[float]:
    """Find price on or before date `d` (handle weekends/holidays)."""
    for i in range(7):
        p = price_map.get(d - timedelta(days=i))
        if p:
            return p
    return None


def _calc_metrics(equity_curve: list[dict], total_invested: float) -> dict:
    if len(equity_curve) < 2:
        return {}

    values = [p["value"] for p in equity_curve]
    initial = values[0]
    final = values[-1]

    # Daily returns
    returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values)) if values[i - 1]]

    total_return_pct = (final - initial) / initial * 100 if initial else 0

    # Annualised volatility
    n = len(returns)
    if n > 1:
        mean_r = sum(returns) / n
        variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
        vol = (variance ** 0.5) * (252 ** 0.5) * 100
    else:
        vol = 0.0

    # Max drawdown
    max_dd = 0.0
    peak = values[0]
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd

    return {
        "total_return_pct": round(total_return_pct, 2),
        "volatility_annualized_pct": round(vol, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "current_value": round(final, 2),
        "total_invested": round(total_invested, 2),
        "unrealized_pnl": round(final - total_invested, 2),
        "unrealized_pnl_pct": round((final - total_invested) / total_invested * 100, 2) if total_invested else 0,
    }
