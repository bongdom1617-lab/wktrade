from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List

import httpx

from app.market_data.base import BaseMarketProvider, MarketDataError, parse_iso_utc, utc_now, utc_now_iso
from app.schemas import Candle, LiveQuote, Timeframe


YAHOO_TF_MAP: Dict[str, tuple] = {
    "M1": ("1m", "1d"),
    "M5": ("5m", "5d"),
    "M15": ("15m", "5d"),
    "M30": ("30m", "1mo"),
    "H1": ("1h", "1mo"),
    "H4": ("1h", "3mo"),
    "D1": ("1d", "2y"),
}


class GoldApiSpotProvider(BaseMarketProvider):
    """Tertiary public XAU Spot quote failover (api.gold-api.com) when BiQuote & Swissquote are unreachable."""

    name = "Gold-API Spot XAU (Failover)"
    role = "fallback"
    supports_candles = False
    ENDPOINT = "https://api.gold-api.com/price/XAU"

    def __init__(self, timeout: float = 8.0) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "GoldAI-Analyzer/1.0", "Accept": "application/json"},
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_quote(self) -> LiveQuote:
        t0 = time.perf_counter()
        try:
            resp = await self._client.get(self.ENDPOINT)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status_code != 200:
                raise MarketDataError(f"Gold-API HTTP {resp.status_code}")
            data = resp.json()
            price = float(data["price"])
            if price <= 500.0:
                raise MarketDataError(f"Implausible Gold-API price {price}")
            ts_raw = data.get("updatedAt") or utc_now_iso()
            q_dt = parse_iso_utc(str(ts_raw))
            age = max(0.0, (utc_now() - q_dt).total_seconds())
            self.mark_success(elapsed_ms)
            return LiveQuote(
                symbol="XAUUSD",
                bid=round(price, 3),
                ask=round(price, 3),
                mid=round(price, 3),
                spread=0.0,
                spread_bps=0.0,
                provider=self.name,
                quote_timestamp=q_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                fetched_at=utc_now_iso(),
                quote_age_seconds=round(age, 1),
                market_state="open",
                status="LIVE",
                warning="Operating on tertiary Gold-API failover quote (Bid/Ask spread unavailable).",
            )
        except Exception as exc:
            self.mark_error(str(exc))
            raise MarketDataError(f"Gold-API failover failed: {exc}") from exc


class YahooGoldCandleFallbackProvider(BaseMarketProvider):
    """Transparent fallback OHLC candlestick source (COMEX Gold GC=F) used ONLY when primary spot OHLC providers fail."""

    name = "Yahoo COMEX Gold GC=F (Fallback)"
    role = "fallback"
    supports_candles = True

    def __init__(self, timeout: float = 12.0) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_quote(self) -> LiveQuote:
        raise MarketDataError("Yahoo fallback is candle-only")

    async def fetch_candles(self, timeframe: Timeframe, limit: int = 300) -> List[Candle]:
        iv, rng = YAHOO_TF_MAP[timeframe]
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval={iv}&range={rng}"
        t0 = time.perf_counter()
        try:
            resp = await self._client.get(url)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status_code != 200:
                raise MarketDataError(f"Yahoo fallback HTTP {resp.status_code}")
            payload = resp.json()
            res = (payload.get("chart", {}).get("result") or [None])[0]
            if not res:
                raise MarketDataError("Yahoo fallback empty chart result")
            ts_list = res.get("timestamp") or []
            q = (res.get("indicators", {}).get("quote") or [{}])[0]
            opens, highs, lows, closes = q.get("open") or [], q.get("high") or [], q.get("low") or [], q.get("close") or []
            vols = q.get("volume") or []

            dedup: Dict[int, Candle] = {}
            for i, ts in enumerate(ts_list):
                if i >= len(closes):
                    break
                if any(v is None for v in (opens[i], highs[i], lows[i], closes[i])):
                    continue
                fo, fh, fl, fc = float(opens[i]), float(highs[i]), float(lows[i]), float(closes[i])
                if min(fo, fh, fl, fc) <= 500.0:
                    continue
                t_int = int(ts)
                dedup[t_int] = Candle(
                    time=t_int,
                    open_time_iso=datetime.fromtimestamp(t_int, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    open=round(fo, 3),
                    high=round(max(fh, fo, fc), 3),
                    low=round(min(fl, fo, fc), 3),
                    close=round(fc, 3),
                    volume=round(float(vols[i]) if (i < len(vols) and vols[i] is not None) else 0.0, 2),
                    is_open=False,
                )

            bars = [dedup[k] for k in sorted(dedup.keys())]
            if timeframe == "H4" and bars:
                # Aggregate 1h bars into 4h buckets
                buckets: Dict[int, List[Candle]] = {}
                for b in bars:
                    b_ts = (b.time // 14400) * 14400
                    buckets.setdefault(b_ts, []).append(b)
                bars = [
                    Candle(
                        time=ts,
                        open_time_iso=datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        open=grp[0].open,
                        high=max(x.high for x in grp),
                        low=min(x.low for x in grp),
                        close=grp[-1].close,
                        volume=round(sum(x.volume for x in grp), 2),
                        is_open=False,
                    )
                    for ts, grp in sorted(buckets.items())
                ]

            if not bars:
                raise MarketDataError(f"Yahoo fallback returned 0 bars for {timeframe}")
            bars[-1].is_open = True
            self.mark_success(elapsed_ms)
            return bars[-limit:]
        except Exception as exc:
            self.mark_error(str(exc))
            raise MarketDataError(f"Yahoo candle fallback failed ({timeframe}): {exc}") from exc
