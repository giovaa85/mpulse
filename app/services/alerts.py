"""
Alert evaluation engine.
Called from the background task every 60 seconds.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Alert, AlertEvent, Quote, Symbol
from .market import get_quote

logger = logging.getLogger(__name__)

# Minimum seconds between repeat triggers of the same alert
COOLDOWN_SECS = 300  # 5 minutes


def check_all_alerts(db: Session) -> list[dict]:
    """
    Evaluate all enabled alerts against current quotes.
    Returns list of alert event dicts for triggered alerts (for WS broadcast).
    """
    alerts = db.query(Alert).filter(Alert.is_enabled == True).all()
    triggered = []

    for alert in alerts:
        try:
            event = _check_alert(alert, db)
            if event:
                triggered.append(event)
        except Exception as exc:
            logger.debug("Alert %d check failed: %s", alert.id, exc)

    return triggered


def _check_alert(alert: Alert, db: Session) -> Optional[dict]:
    sym: Symbol = alert.symbol

    # Get current quote (use cache, don't force refresh)
    existing_quote: Optional[Quote] = db.get(Quote, sym.id)
    if not existing_quote or existing_quote.price is None:
        return None

    price = existing_quote.price
    change_pct = existing_quote.change_pct or 0.0

    # Check cooldown
    if alert.last_triggered_at:
        elapsed = (datetime.utcnow() - alert.last_triggered_at).total_seconds()
        if elapsed < COOLDOWN_SECS:
            return None

    # Evaluate condition
    triggered = False
    value = None

    if alert.kind == "price":
        value = price
        triggered = _eval(value, alert.threshold, alert.direction)
    elif alert.kind == "change_pct":
        value = change_pct
        triggered = _eval(value, alert.threshold, alert.direction)
    elif alert.kind == "drawdown":
        # Drawdown: compare current price to 52-week high (from history)
        high_52w = _get_52w_high(sym.id, db)
        if high_52w and high_52w > 0:
            drawdown = (high_52w - price) / high_52w * 100
            value = drawdown
            triggered = _eval(value, alert.threshold, alert.direction)

    if not triggered:
        return None

    # Record trigger
    now = datetime.utcnow()
    alert.last_triggered_at = now

    msg = (
        f"{sym.ticker} {alert.kind} {alert.direction} {alert.threshold} "
        f"(current: {round(value, 4) if value is not None else 'N/A'})"
    )
    payload = {
        "ticker": sym.ticker,
        "kind": alert.kind,
        "threshold": alert.threshold,
        "direction": alert.direction,
        "current_value": value,
        "price": price,
    }

    event = AlertEvent(
        alert_id=alert.id,
        ts=now,
        message=msg,
        payload_json=json.dumps(payload),
    )
    db.add(event)
    db.commit()

    logger.info("Alert triggered: %s", msg)

    return {
        "user_id": alert.user_id,
        "alert_id": alert.id,
        "message": msg,
        "payload": payload,
    }


def _eval(value: float, threshold: float, direction: str) -> bool:
    if direction == "above":
        return value > threshold
    elif direction == "below":
        return value < threshold
    return False


def _get_52w_high(symbol_id: int, db: Session) -> Optional[float]:
    from ..models import History
    cutoff = datetime.utcnow() - timedelta(days=365)
    row = (
        db.query(History)
        .filter(
            History.symbol_id == symbol_id,
            History.ts >= cutoff,
            History.interval == "1d",
        )
        .order_by(History.high.desc())
        .first()
    )
    return row.high if row else None
