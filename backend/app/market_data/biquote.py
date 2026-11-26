from __future__ import annotations

import time
from typing import Dict, List, Optional

import httpx

from app.market_data.base import (
    BaseMarketProvider,
    MarketDataError,
    parse_iso_utc,
    utc_now,
    utc_now_iso,
)
from app.schemas import Candle, LiveQuote, Timeframe


BIQUOTE_INTERVAL_MAP: Dict[str, str] = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}


class BiQuoteProvider(BaseMarketProvider):
    """Public real-time Spot XAUUSD REST feed (Bid/Ask/Spread + M1..D1 OHLC candlesticks)."""

    name = "BiQuote Spot XAUUSD"
    role = "primary"
    supports_candles = True
    BASE_URL = "https://biquote.io/api"

    def __init__(self, timeout: float = 10.0) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "GoldAI-Analyzer/1.0",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str, params: Optional[Dict[str, object]] = None) -> dict:
        url = f"{self.BASE_URL}{path}"
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            t0 = time.perf_counter()
            try:
                resp = await self._client.get(url, params=params)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if resp.status_code != 200:
                    raise MarketDataError(f"BiQuote HTTP {resp.status_code} on {path}")
                payload = resp.json()
                self.mark_success(elapsed_ms)
                return payload
            except Exception as exc:
                last_exc = exc
                if attempt == 1:
                    self.mark_error(str(exc))
                    raise MarketDataError(f"BiQuote request failed ({path}): {exc}") from exc
        raise MarketDataError(f"BiQuote request failed ({path}): {last_exc}")

    async def fetch_quote(self) -> LiveQuote:
        data = await self._get_json("/XAUUSD")
        try:
            bid = float(data["bid"])
            ask = float(data["ask"])
        except (KeyError, TypeError, ValueError) as exc:
            self.mark_error(f"Invalid BiQuote quote payload: {exc}")
            raise MarketDataError(f"Invalid BiQuote quote payload: {exc}") from exc

        if bid <= 0 or ask <= 0 or ask < bid - 1.0:
            raise MarketDataError(f"Implausible XAUUSD quote bid={bid} ask={ask}")

        mid = float(data.get("mid") or (bid + ask) / 2.0)
        spread = round(max(0.0, ask - bid), 4)
        spread_bps = round((spread / mid) * 10000.0, 2) if mid > 0 else 0.0

        ts_raw = data.get("lastQuoteAt") or data.get("timestamp")
        if not ts_raw:
            raise MarketDataError("BiQuote quote missing timestamp")
        quote_dt = parse_iso_utc(str(ts_raw))
        now = utc_now()
        age_sec = max(0.0, (now - quote_dt).total_seconds())
        if data.get("quoteAgeSeconds") is not None:
            # Prefer conservative (larger) age between server-reported and local clock diff (clamped >= 0)
            try:
                reported_age = float(data["quoteAgeSeconds"])
                if reported_age >= 0:
                    age_sec = max(age_sec, reported_age) if abs(age_sec - reported_age) < 60 else reported_age
            except (TypeError, ValueError):
                pass

        market_state = str(data.get("marketState") or "open").lower()
        is_stale = bool(data.get("stale", False))

        day_high = float(data["high"]) if data.get("high") else None
        day_low = float(data["low"]) if data.get("low") else None

        return LiveQuote(
            symbol="XAUUSD",
            bid=round(bid, 3),
            ask=round(ask, 3),
            mid=round(mid, 3),
            spread=round(spread, 3),
            spread_bps=spread_bps,
            day_high=round(day_high, 3) if day_high else None,
            day_low=round(day_low, 3) if day_low else None,
            direction=str(data.get("direction") or "").upper() or None,
            provider=self.name,
            quote_timestamp=quote_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            fetched_at=utc_now_iso(),
            quote_age_seconds=round(age_sec, 1),
            market_state=market_state,
            status="DELAYED" if is_stale else "LIVE",
        )

    async def fetch_candles(self, timeframe: Timeframe, limit: int = 500) -> List[Candle]:
        interval = BIQUOTE_INTERVAL_MAP[timeframe]
        data = await self._get_json("/XAUUSD/ohlc", params={"interval": interval, "limit": limit})
        raw_bars = data.get("bars")
        if not isinstance(raw_bars, list) or not raw_bars:
            raise MarketDataError(f"BiQuote returned no OHLC bars for {timeframe}")

        dedup: Dict[int, Candle] = {}
        for item in raw_bars:
            try:
                open_dt = parse_iso_utc(str(item["openTime"]))
                epoch = int(open_dt.timestamp())
                o = float(item["open"])
                h = float(item["high"])
                l = float(item["low"])
                c = float(item["close"])
                if min(o, h, l, c) <= 0:
                    continue
                # Enforce OHLC envelope consistency in case of tick rounding
                h = max(h, o, c)
                l = min(l, o, c)
                vol = float(item.get("tickVolume") or item.get("volume") or 0.0)
                dedup[epoch] = Candle(
                    time=epoch,
                    open_time_iso=open_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    open=round(o, 3),
                    high=round(h, 3),
                    low=round(l, 3),
                    close=round(c, 3),
                    volume=round(vol, 2),
                    is_open=bool(item.get("isOpen", False)),
                )
            except (KeyError, TypeError, ValueError):
                continue

        candles = [dedup[k] for k in sorted(dedup.keys())]
        if not candles:
            raise MarketDataError(f"BiQuote returned zero valid candles for {timeframe}")
        return candles
