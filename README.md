# MarketPulse Terminal

A local-first market intelligence web app. No API keys, no cloud services, no Node.js.

## Quick Start

```bash
# 1 – Install dependencies (Python 3.11+ required)
pip install -r requirements.txt

# 2 – Run the server
uvicorn app.main:app --reload
```

Open **http://localhost:8000** in your browser.

## Default Credentials

| Username | Password | Role  |
|----------|----------|-------|
| `admin`  | `admin`  | Admin |
| `demo`   | `demo`   | User  |

## Features

| Feature | Description |
|---------|-------------|
| **Dashboard** | Live indices (S&P 500, NASDAQ, DAX, FTSE 100, FTSE MIB) + Top-10 crypto + watchlist widget |
| **Watchlists** | Multiple named watchlists; add/remove symbols with autocomplete; CSV export |
| **Symbol Detail** | Price quote + interactive history chart (1m → max) with period selector |
| **Portfolio** | Manual buy/sell transactions; holdings with P&L; equity curve + metrics |
| **Alerts** | Price / % change / drawdown triggers; enable/disable; event log |
| **Settings** | Dark/light theme; refresh interval; change password |
| **WebSocket** | Live push updates every 30 s without page reload |
| **Caching** | SQLite-backed TTL cache (quotes: 60 s, history: 15 min); stale fallback |
| **Admin Debug** | `/api/debug/cache-stats` — hit ratio, error count, per-source breakdown |

## Data Sources

- **Stocks / ETFs / Indices**: [yfinance](https://github.com/ranaroussi/yfinance) (no API key)
- **Cryptocurrency**: [CoinGecko public API](https://www.coingecko.com/en/api) (no API key)

## Optional: Run Tests

```bash
pytest tests/ -v
```

Tests cover:
- Login / logout / auth flows
- Cache TTL (no re-fetch within TTL)
- Stale data fallback when sources fail

## Project Structure

```
mpulse/
├── app/
│   ├── main.py           # FastAPI app, startup, middleware
│   ├── config.py         # Settings (TTLs, secret key, etc.)
│   ├── db.py             # SQLAlchemy engine + session + migrations
│   ├── models.py         # ORM models (15 tables)
│   ├── schemas.py        # Pydantic request/response schemas
│   ├── auth.py           # bcrypt + itsdangerous sessions + rate limiting
│   ├── tasks.py          # WebSocket manager + background broadcasters
│   ├── services/
│   │   ├── cache.py      # fetch_log helpers + cache stats
│   │   ├── market.py     # yfinance wrapper (quotes + history)
│   │   ├── crypto.py     # CoinGecko wrapper
│   │   ├── portfolio.py  # Holdings aggregation + performance metrics
│   │   └── alerts.py     # Alert evaluation engine
│   └── routers/
│       ├── auth.py       # POST /api/auth/login|logout|me|change-password
│       ├── markets.py    # GET /api/markets/overview, /api/crypto/overview
│       ├── symbols.py    # GET /api/symbols/search, /{ticker}/quote|history
│       ├── watchlists.py # CRUD /api/watchlists + items + CSV export
│       ├── portfolios.py # CRUD /api/portfolios + transactions + performance
│       ├── alerts.py     # CRUD /api/alerts + /events
│       ├── settings.py   # GET|PUT /api/settings
│       ├── ops.py        # GET /healthz, /api/debug/cache-stats
│       └── ws.py         # WS /ws/stream
├── frontend/
│   ├── index.html        # Single HTML shell (loads Chart.js from CDN)
│   └── assets/
│       ├── style.css     # CSS variables dark/light theme
│       └── app.js        # Vanilla JS SPA (hash router, all pages)
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_cache.py
│   └── test_stale.py
├── requirements.txt
└── README.md
```

## Environment Variables (optional)

Create a `.env` file to override defaults:

```env
SECRET_KEY=your-very-secret-key
LOG_LEVEL=DEBUG
QUOTE_TTL=60
HISTORY_TTL=900
BROADCAST_INTERVAL=30
```

## API Reference

Interactive docs available at **http://localhost:8000/api/docs** (Swagger UI).

Key endpoints:

```
POST /api/auth/login              Body: {username, password}
GET  /api/markets/overview        Major indices quotes
GET  /api/crypto/overview         Top-10 crypto by market cap
GET  /api/symbols/{ticker}/quote  Live quote + stale flag
GET  /api/symbols/{ticker}/history?period=1y&interval=1d
GET  /api/watchlists              All user watchlists with quotes
POST /api/portfolios/{id}/transactions  Add buy/sell transaction
GET  /api/portfolios/{id}/performance  Equity curve + metrics
GET  /api/alerts/events           Recent alert triggers
GET  /api/debug/cache-stats       Admin only
WS  /ws/stream                    Live push (indices + crypto + watchlist)
```
