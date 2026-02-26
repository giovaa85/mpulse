"""
Tests: stale data fallback when Stooq fails.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import Quote, Symbol


def _make_aged_quote(db, ticker: str, price: float = 120.0) -> Symbol:
    """Insert a symbol + stale quote (aged beyond TTL) into the test DB."""
    sym = Symbol(ticker=ticker, name="Stale Test Corp", type="stock", currency="USD",
                 last_seen_at=datetime.utcnow())
    db.add(sym)
    db.flush()

    quote = Quote(
        symbol_id=sym.id,
        ts=datetime.utcnow() - timedelta(seconds=200),  # Past TTL
        price=price,
        change_abs=1.5,
        change_pct=1.27,
        open=price - 2,
        high=price + 3,
        low=price - 3,
        volume=500_000,
        source="stooq",
        stale=False,
    )
    db.add(quote)
    db.commit()
    return sym


@patch("app.services.market._stooq_fetch")
def test_stale_fallback_on_fetch_failure(mock_fetch, auth_client, db):
    """
    When Stooq raises an exception and there's cached (stale) data,
    the endpoint must return the old data with stale=True.
    """
    ticker = "STALEFALLBACK"
    sym = _make_aged_quote(db, ticker, price=99.5)

    mock_fetch.side_effect = Exception("Simulated network error")

    r = auth_client.get(f"/api/symbols/{ticker}/quote")
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["stale"] is True, f"Expected stale=True, got: {data}"
    assert data["price"] == pytest.approx(99.5), f"Expected stale price 99.5, got: {data['price']}"
    assert data["stale_reason"] is not None


@patch("app.services.market._stooq_fetch")
def test_no_cache_and_fetch_fails_returns_error_dict(mock_fetch, auth_client, db):
    """
    When there's no cached data and Stooq fails,
    the endpoint still returns 200 with stale=True and no price.
    """
    ticker = "NODATA_FAIL"

    mock_fetch.side_effect = Exception("Total outage")

    r = auth_client.get(f"/api/symbols/{ticker}/quote")
    assert r.status_code == 200

    data = r.json()
    assert data["stale"] is True


@patch("app.services.crypto.httpx.get")
def test_crypto_stale_fallback(mock_get, auth_client):
    """
    When CoinGecko fails and there's in-memory cache,
    crypto endpoint returns stale data.
    """
    from app.services import crypto as crypto_svc

    # Pre-populate memory cache
    crypto_svc._crypto_memory_cache["data"] = [
        {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC",
         "price_usd": 50000.0, "change_24h_pct": 1.5, "stale": False}
    ]
    crypto_svc._crypto_memory_cache["fetched_at"] = 0  # Expired

    # Make CoinGecko fail
    mock_get.side_effect = Exception("CoinGecko down")

    r = auth_client.get("/api/crypto/overview")
    assert r.status_code == 200

    data = r.json()["data"]
    assert len(data) > 0
    assert data[0]["stale"] is True


@patch("app.services.market._stooq_fetch")
def test_markets_overview_partial_stale(mock_fetch, auth_client, db):
    """
    Markets overview should return whatever data is available;
    failed tickers appear as stale.
    """
    mock_fetch.return_value = [
        {"ts": datetime(2024, 1, 1), "open": 4450.0, "high": 4520.0,
         "low": 4430.0, "close": 4450.0, "volume": 900_000},
        {"ts": datetime(2024, 1, 2), "open": 4450.0, "high": 4520.0,
         "low": 4430.0, "close": 4500.0, "volume": 1_000_000},
    ]

    r = auth_client.get("/api/markets/overview")
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, list)
    assert len(data) > 0
