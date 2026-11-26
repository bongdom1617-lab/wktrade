from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Literal, Tuple

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.market_data.base import MarketDataError
from app.market_data.twelvedata import TwelveDataProvider
from app.models import CandleCache
from app.schemas import Candle, Timeframe


logger = logging.getLogger("gold_ai.backtest_data")

# In-memory cache (15 min TTL) for Yahoo Finance historical OHLC so repeated backtest runs are instant & polite
_HIST_CACHE: Dict[str, Tuple[float, List[Candle], str]] = {}
_CACHE_TTL_SEC = 900.0


def _resample_candles(base: List[Candle], factor_seconds: int) -> List[Candle]:
    """Strictly causal OHLC aggregation into higher-timeframe buckets."""
    if not base:
        return []
    buckets: Dict[int, List[Candle]] = {}
    for c in base:
        bucket_ts = (c.time // factor_seconds) * factor_seconds
        buckets.setdefault(bucket_ts, []).append(c)
    out: List[Candle] = []
    for ts in sorted(buckets.keys()):
        grp = buckets[ts]
        out.append(
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
        )
    return out


async def _fetch_yahoo_gold_history(interval: str, rng: str) -> List[Candle]:
    """
    Fetch real historical COMEX Gold (GC=F) OHLC bars from Yahoo Finance public chart API
    for multi-year / 60-day historical backtesting. Never fabricates candles.
    """
    cache_key = f"yahoo:GC=F:{interval}:{rng}"
    now = time.monotonic()
    if cache_key in _HIST_CACHE:
        cached_at, cached_bars, _ = _HIST_CACHE[cache_key]
        if (now - cached_at) < _CACHE_TTL_SEC and cached_bars:
            return list(cached_bars)

    urls = [
        f"https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval={interval}&range={rng}",
        f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval={interval}&range={rng}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    last_err: Exception = MarketDataError("Historical Gold feed unreachable")
    async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    last_err = MarketDataError(f"Yahoo Finance HTTP {resp.status_code}")
                    continue
                payload = resp.json()
                results = payload.get("chart", {}).get("result")
                if not results:
                    last_err = MarketDataError("Yahoo Finance returned empty chart result")
                    continue
                res = results[0]
                timestamps = res.get("timestamp") or []
                quote = (res.get("indicators", {}).get("quote") or [{}])[0]
                opens = quote.get("open") or []
                highs = quote.get("high") or []
                lows = quote.get("low") or []
                closes = quote.get("close") or []
                vols = quote.get("volume") or []

                dedup: Dict[int, Candle] = {}
                for i, ts in enumerate(timestamps):
                    if i >= len(closes):
                        break
                    o, h, l, c = opens[i], highs[i], lows[i], closes[i]
                    if any(v is None for v in (o, h, l, c)):
                        continue
                    fo, fh, fl, fc = float(o), float(h), float(l), float(c)
                    if min(fo, fh, fl, fc) <= 500.0:
                        continue
                    fh = max(fh, fo, fc)
                    fl = min(fl, fo, fc)
                    fv = float(vols[i]) if (i < len(vols) and vols[i] is not None) else 0.0
                    t_int = int(ts)
                    dedup[t_int] = Candle(
                        time=t_int,
                        open_time_iso=datetime.fromtimestamp(t_int, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        open=round(fo, 3),
                        high=round(fh, 3),
                        low=round(fl, 3),
                        close=round(fc, 3),
                        volume=round(fv, 2),
                        is_open=False,
                    )

                bars = [dedup[k] for k in sorted(dedup.keys())]
                if len(bars) >= 50:
                    _HIST_CACHE[cache_key] = (now, bars, "Yahoo COMEX Gold (GC=F)")
                    return list(bars)
            except Exception as exc:
                last_err = exc
                logger.warning("Historical Yahoo fetch error (%s): %s", url, exc)

    raise MarketDataError(f"Could not fetch real extended Gold history: {last_err}")


def _load_spot_cache_from_db(timeframe: Timeframe) -> List[Candle]:
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(CandleCache)
            .filter(CandleCache.symbol == "XAUUSD", CandleCache.timeframe == timeframe)
            .order_by(CandleCache.open_time.asc())
            .all()
        )
        return [
            Candle(
                time=int(r.open_time),
                open_time_iso=datetime.fromtimestamp(int(r.open_time), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                open=round(float(r.open), 3),
                high=round(float(r.high), 3),
                low=round(float(r.low), 3),
                close=round(float(r.close), 3),
                volume=round(float(r.volume), 2),
                is_open=False,
            )
            for r in rows
        ]
    finally:
        db.close()


async def load_historical_candles(
    timeframe: Literal["M5", "M15", "M30", "H1", "H4", "D1"],
    dataset: Literal["extended_gold", "spot_cache", "twelvedata"] = "extended_gold",
    live_cache: Dict[Timeframe, List[Candle]] = None,  # type: ignore[assignment]
) -> Tuple[List[Candle], str]:
    """
    Load strictly real, verifiable historical Gold candlesticks for backtesting.
    Returns (candles, human_readable_dataset_label).
    """
    if dataset == "twelvedata":
        if not settings.twelve_data_api_key:
            raise MarketDataError("Twelve Data dataset requires TWELVE_DATA_API_KEY in backend/.env.")
        td = TwelveDataProvider(settings.twelve_data_api_key)
        try:
            bars = await td.fetch_candles(timeframe, limit=5000)
            return bars, f"Twelve Data Spot XAU/USD ({len(bars):,} real {timeframe} bars)"
        finally:
            await td.close()

    if dataset == "spot_cache":
        bars = _load_spot_cache_from_db(timeframe)
        if not bars and live_cache:
            bars = list(live_cache.get(timeframe, []))
        if len(bars) < 60:
            raise MarketDataError(
                f"Insufficient persisted BiQuote Spot XAUUSD bars for {timeframe} ({len(bars)} bars; need >= 60)."
            )
        return bars, f"BiQuote Spot XAUUSD Native History ({len(bars):,} real {timeframe} bars)"

    # Default: extended_gold — real multi-year / 60-day Gold OHLC via Yahoo Finance GC=F
    if timeframe == "M5":
        bars = await _fetch_yahoo_gold_history("5m", "60d")
        return bars, f"Extended Real Gold History — COMEX GC=F 60D ({len(bars):,} M5 bars)"
    if timeframe == "M15":
        bars = await _fetch_yahoo_gold_history("15m", "60d")
        return bars, f"Extended Real Gold History — COMEX GC=F 60D ({len(bars):,} M15 bars)"
    if timeframe == "M30":
        bars_15m = await _fetch_yahoo_gold_history("15m", "60d")
        bars = _resample_candles(bars_15m, 1800)
        return bars, f"Extended Real Gold History — COMEX GC=F 60D ({len(bars):,} M30 bars)"
    if timeframe == "H1":
        bars = await _fetch_yahoo_gold_history("1h", "2y")
        return bars, f"Extended Real Gold History — COMEX GC=F 2Y ({len(bars):,} H1 bars)"
    if timeframe == "H4":
        bars_1h = await _fetch_yahoo_gold_history("1h", "2y")
        bars = _resample_candles(bars_1h, 14400)
        return bars, f"Extended Real Gold History — COMEX GC=F 2Y ({len(bars):,} H4 bars)"
    if timeframe == "D1":
        bars = await _fetch_yahoo_gold_history("1d", "5y")
        return bars, f"Extended Real Gold History — COMEX GC=F 5Y ({len(bars):,} D1 bars)"

    raise MarketDataError(f"Unsupported backtest timeframe: {timeframe}")
