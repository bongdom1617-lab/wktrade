from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from app.market_data.base import BaseMarketProvider, MarketDataError, utc_now, utc_now_iso
from app.schemas import Candle, LiveQuote, Timeframe


TWELVEDATA_INTERVAL_MAP: Dict[str, str] = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}


class TwelveDataProvider(BaseMarketProvider):
    """Optional Twelve Data API provider for XAU/USD when TWELVE_DATA_API_KEY is configured."""

    name = "Twelve Data XAU/USD"
    role = "optional"
    supports_candles = True
    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        super().__init__()
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Dict[str, object]) -> dict:
        full_params = dict(params)
        full_params["apikey"] = self._api_key
        t0 = time.perf_counter()
        try:
            resp = await self._client.get(f"{self.BASE_URL}{path}", params=full_params)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            payload = resp.json()
            if resp.status_code != 200 or payload.get("status") == "error":
                msg = payload.get("message") or f"HTTP {resp.status_code}"
                self.mark_error(msg)
                raise MarketDataError(f"Twelve Data error ({path}): {msg}")
            self.mark_success(elapsed_ms)
            return payload
        except MarketDataError:
            raise
        except Exception as exc:
            self.mark_error(str(exc))
            raise MarketDataError(f"Twelve Data request failed ({path}): {exc}") from exc

    async def fetch_quote(self) -> LiveQuote:
        data = await self._get("/quote", {"symbol": "XAU/USD"})
        close_price = float(data["close"])
        ts = int(data.get("timestamp") or int(time.time()))
        quote_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        age_sec = max(0.0, (utc_now() - quote_dt).total_seconds())
        prev_close = float(data["previous_close"]) if data.get("previous_close") else None
        change_usd = round(close_price - prev_close, 3) if prev_close else None
        change_pct = round((change_usd / prev_close) * 100.0, 3) if (prev_close and change_usd is not None) else None
        return LiveQuote(
            symbol="XAUUSD",
            bid=round(close_price, 3),
            ask=round(close_price, 3),
            mid=round(close_price, 3),
            spread=0.0,
            spread_bps=0.0,
            day_high=float(data["high"]) if data.get("high") else None,
            day_low=float(data["low"]) if data.get("low") else None,
            prev_close=prev_close,
            change_usd=change_usd,
            change_percent=change_pct,
            provider=self.name,
            quote_timestamp=quote_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            fetched_at=utc_now_iso(),
            quote_age_seconds=round(age_sec, 1),
            market_state="open" if data.get("is_market_open", True) else "closed",
            status="LIVE",
        )

    async def fetch_candles(self, timeframe: Timeframe, limit: int = 300) -> List[Candle]:
        interval = TWELVEDATA_INTERVAL_MAP[timeframe]
        data = await self._get(
            "/time_series",
            {
                "symbol": "XAU/USD",
                "interval": interval,
                "outputsize": min(limit, 500),
                "timezone": "UTC",
            },
        )
        values = data.get("values") or []
        dedup: Dict[int, Candle] = {}
        for row in values:
            dt_str = str(row["datetime"])
            if len(dt_str) == 10:
                dt_obj = datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                dt_obj = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            epoch = int(dt_obj.timestamp())
            o = float(row["open"])
            h = float(row["high"])
            l = float(row["low"])
            c = float(row["close"])
            vol = float(row.get("volume") or 0.0)
            dedup[epoch] = Candle(
                time=epoch,
                open_time_iso=dt_obj.strftime("%Y-%m-%dT%H:%M:%SZ"),
                open=round(o, 3),
                high=round(max(h, o, c), 3),
                low=round(min(l, o, c), 3),
                close=round(c, 3),
                volume=round(vol, 2),
                is_open=False,
            )
        candles = [dedup[k] for k in sorted(dedup.keys())]
        if candles:
            candles[-1].is_open = True
        return candles
