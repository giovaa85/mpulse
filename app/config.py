from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = "changeme-marketpulse-secret-key-2024"
    SESSION_COOKIE_NAME: str = "mp_session"
    SESSION_MAX_AGE: int = 86400 * 7  # 7 days

    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/mpulse.db"

    LOG_LEVEL: str = "INFO"

    # Cache TTLs (seconds)
    QUOTE_TTL: int = 300  # 5 minutes (prewarmer keeps cache fresh)
    HISTORY_TTL: int = 900       # 15 minutes
    SYMBOL_METADATA_TTL: int = 604800  # 7 days
    CRYPTO_TTL: int = 60

    # Market data — Stooq tickers
    INDICES: list = [
        "^SPX", "^NDX", "^DJI", "^DAX", "^UKX", "^CAC",
        "^IBEX", "^MIB", "^AEX", "^SMI", "^N225", "^HSI",
    ]
    INDEX_NAMES: dict = {
        "^SPX":  "S&P 500",
        "^NDX":  "NASDAQ-100",
        "^DJI":  "Dow Jones",
        "^DAX":  "DAX",
        "^UKX":  "FTSE 100",
        "^CAC":  "CAC 40",
        "^IBEX": "IBEX 35",
        "^MIB":  "FTSE MIB",
        "^AEX":  "AEX",
        "^SMI":  "SMI",
        "^N225": "Nikkei 225",
        "^HSI":  "Hang Seng",
    }

    # Top stocks to track for best/worst dashboard panel (USA + EU blue chips)
    TOP_STOCKS: list = [
        # USA
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
        "META", "TSLA", "AVGO", "JPM", "V",
        "UNH", "XOM", "LLY", "JNJ", "WMT",
        # Europa
        "ASML.NL", "SAP.DE", "SIE.DE", "MC.FR",
        "NESN.SW", "NOVN.SW", "AIR.FR", "AZN.UK",
        "HSBA.UK", "ENI.IT",
    ]
    TOP_STOCK_NAMES: dict = {
        # USA
        "AAPL":    "Apple",
        "MSFT":    "Microsoft",
        "NVDA":    "NVIDIA",
        "AMZN":    "Amazon",
        "GOOGL":   "Alphabet",
        "META":    "Meta",
        "TSLA":    "Tesla",
        "AVGO":    "Broadcom",
        "JPM":     "JPMorgan",
        "V":       "Visa",
        "UNH":     "UnitedHealth",
        "XOM":     "ExxonMobil",
        "LLY":     "Eli Lilly",
        "JNJ":     "J&J",
        "WMT":     "Walmart",
        # Europa
        "ASML.NL": "ASML",
        "SAP.DE":  "SAP",
        "SIE.DE":  "Siemens",
        "MC.FR":   "LVMH",
        "NESN.SW": "Nestlé",
        "NOVN.SW": "Novartis",
        "AIR.FR":  "Airbus",
        "AZN.UK":  "AstraZeneca",
        "HSBA.UK": "HSBC",
        "ENI.IT":  "ENI",
    }

    # Commodities / Materie prime (Stooq futures tickers)
    COMMODITIES: list = [
        "GC.F",   # Oro
        "SI.F",   # Argento
        "CL.F",   # Petrolio WTI
        "NG.F",   # Gas Naturale
        "HG.F",   # Rame
        "PL.F",   # Platino
        "PA.F",   # Palladio
        "ZW.F",   # Frumento
        "ZC.F",   # Mais
        "ZS.F",   # Soia
    ]
    COMMODITY_NAMES: dict = {
        "GC.F":  "Oro (Gold)",
        "SI.F":  "Argento (Silver)",
        "CL.F":  "Petrolio WTI",
        "NG.F":  "Gas Naturale",
        "HG.F":  "Rame (Copper)",
        "PL.F":  "Platino",
        "PA.F":  "Palladio",
        "ZW.F":  "Frumento (Wheat)",
        "ZC.F":  "Mais (Corn)",
        "ZS.F":  "Soia (Soybeans)",
    }

    # Rate limiting for login (per IP)
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_SECS: int = 300  # 5 minutes

    # WebSocket broadcast interval
    BROADCAST_INTERVAL: int = 30

    # Allowed history params
    ALLOWED_PERIODS: set = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
    ALLOWED_INTERVALS: set = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}


settings = Settings()
