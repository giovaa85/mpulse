"""
Tests: cache TTL prevents refetch within TTL window.
Uses mocked _stooq_fetch to control data and timing.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import FetchLog, Quote, Symbol


def _mock_bars(price=150.0, prev_close=148.0):
    return [
        {"ts": datetime(2024, 1, 1), "open": prev_close, "high": price + 1,
         "low": price - 1, "close": prev_close, "volume": 900_000},
        {"ts": datetime(2024, 1, 2), "open": prev_close, "high": price + 1,
         "low": price - 1, "close": price, "volume": 1_000_000},
    ]


@patch("app.services.market._stooq_fetch")
def test_first_fetch_hits_stooq(mock_fetch, auth_client, db):
    """First call for a new ticker must go to Stooq (cache miss)."""
    mock_fetch.return_value = _mock_bars()

    r = auth_client.get("/api/symbols/TESTCACHE1/quote")
    assert r.status_code == 200
    data = r.json()
    assert data["price"] == pytest.approx(150.0)
    assert data["stale"] is False

    log = (
        db.query(FetchLog)
        .filter(FetchLog.key == "quote:TESTCACHE1", FetchLog.cache_hit == False)
        .order_by(FetchLog.fetched_at.desc())
        .first()
    )
    assert log is not None
    assert log.ok is True


@patch("app.services.market._stooq_fetch")
def test_second_fetch_within_ttl_is_cache_hit(mock_fetch, auth_client, db):
    """Second call within TTL must not call Stooq again."""
    mock_fetch.return_value = _mock_bars(200.0, 195.0)

    ticker = "TESTCACHE2"

    # First call: populates cache
    r1 = auth_client.get(f"/api/symbols/{ticker}/quote")
    assert r1.status_code == 200

    # Reset mock call count
    mock_fetch.reset_mock()

    # Second call within TTL: should not call Stooq
    r2 = auth_client.get(f"/api/symbols/{ticker}/quote")
    assert r2.status_code == 200

    assert mock_fetch.call_count == 0, "Stooq was called on cache hit!"

    hit = (
        db.query(FetchLog)
        .filter(FetchLog.key == f"quote:{ticker}", FetchLog.cache_hit == True)
        .order_by(FetchLog.fetched_at.desc())
        .first()
    )
    assert hit is not None, "No cache-hit log entry found"


@patch("app.services.market._stooq_fetch")
def test_force_refresh_bypasses_ttl(mock_fetch, auth_client, db):
    """force=true must bypass TTL and re-fetch."""
    mock_fetch.return_value = _mock_bars(300.0, 290.0)

    ticker = "TESTFORCE"

    r1 = auth_client.get(f"/api/symbols/{ticker}/quote")
    assert r1.status_code == 200

    mock_fetch.reset_mock()

    r2 = auth_client.get(f"/api/symbols/{ticker}/quote?force=true")
    assert r2.status_code == 200

    assert mock_fetch.call_count >= 1, "Stooq was not called on force refresh"


@patch("app.services.market._stooq_fetch")
def test_expired_cache_triggers_refetch(mock_fetch, auth_client, db):
    """After TTL expires, a new fetch should be triggered."""
    mock_fetch.return_value = _mock_bars(100.0, 98.0)

    ticker = "TESTEXPIRED"

    r1 = auth_client.get(f"/api/symbols/{ticker}/quote")
    assert r1.status_code == 200

    # Artificially age the quote past TTL
    sym = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if sym:
        quote = db.get(Quote, sym.id)
        if quote:
            quote.ts = datetime.utcnow() - timedelta(seconds=120)
            db.commit()

    mock_fetch.reset_mock()

    r2 = auth_client.get(f"/api/symbols/{ticker}/quote")
    assert r2.status_code == 200

    assert mock_fetch.call_count >= 1, "Stooq was not called after TTL expiry"
