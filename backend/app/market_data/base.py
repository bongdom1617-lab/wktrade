from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.schemas import Candle, LiveQuote, ProviderHealth, Timeframe


ALL_TIMEFRAMES: List[Timeframe] = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

TIMEFRAME_SECONDS: Dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}


class MarketDataError(RuntimeError):
    """Raised when an external market data provider fails or returns invalid data."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_forex_weekend(now_utc: Optional[datetime] = None) -> bool:
    """Spot Gold (XAUUSD) trades ~23h/day Sun 22:00 UTC through Fri 22:00 UTC."""
    now = now_utc or utc_now()
    wd = now.weekday()  # Mon=0 .. Sun=6
    if wd == 5:  # Saturday
        return True
    if wd == 4 and now.hour >= 22:  # Friday >= 22:00 UTC
        return True
    if wd == 6 and now.hour < 22:  # Sunday < 22:00 UTC
        return True
    return False


class BaseMarketProvider(ABC):
    name: str = "Unknown"
    role: str = "primary"
    supports_candles: bool = False

    def __init__(self) -> None:
        self.reachable: bool = False
        self.latency_ms: Optional[float] = None
        self.last_success: Optional[str] = None
        self.last_error: Optional[str] = None

    def mark_success(self, latency_ms: float) -> None:
        self.reachable = True
        self.latency_ms = round(latency_ms, 1)
        self.last_success = utc_now_iso()
        self.last_error = None

    def mark_error(self, err: str) -> None:
        self.reachable = False
        self.last_error = err

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            role=self.role,
            reachable=self.reachable,
            latency_ms=self.latency_ms,
            last_success=self.last_success,
            last_error=self.last_error,
        )

    @abstractmethod
    async def fetch_quote(self) -> LiveQuote:
        raise NotImplementedError

    async def fetch_candles(self, timeframe: Timeframe, limit: int = 500) -> List[Candle]:
        raise NotImplementedError(f"{self.name} does not provide OHLC candlesticks")

    async def close(self) -> None:
        return None
