from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.market_data.base import (
    ALL_TIMEFRAMES,
    TIMEFRAME_SECONDS,
    MarketDataError,
    is_forex_weekend,
    utc_now,
    utc_now_iso,
)
from app.market_data.biquote import BiQuoteProvider
from app.market_data.fallback_providers import GoldApiSpotProvider, YahooGoldCandleFallbackProvider
from app.market_data.swissquote import SwissquoteBboProvider
from app.market_data.twelvedata import TwelveDataProvider
from app.models import CandleCache
from app.schemas import Candle, FeedHealthResponse, FeedStatus, LiveQuote, Timeframe


logger = logging.getLogger("gold_ai.market_data")


class MarketDataManager:
    """
    Coordinates live external XAUUSD market data feeds with strict data-integrity guarantees:
    - Never fabricates or simulates prices.
    - Cross-verifies Bid/Ask quotes between BiQuote Spot XAUUSD and Swissquote BBO.
    - Persists real historical candles in the database so multi-bar indicators (e.g., EMA 200)
      progressively gain deeper history without inventing data.
    - Explicitly classifies LIVE, DELAYED, MARKET_CLOSED, and DISCONNECTED states.
    """

    def __init__(self) -> None:
        self.biquote = BiQuoteProvider()
        self.swissquote = SwissquoteBboProvider()
        self.goldapi = GoldApiSpotProvider()
        self.yahoo_fallback = YahooGoldCandleFallbackProvider()
        self.twelvedata: Optional[TwelveDataProvider] = (
            TwelveDataProvider(settings.twelve_data_api_key)
            if settings.twelve_data_api_key
            else None
        )

        self.latest_quote: Optional[LiveQuote] = None
        self.candles: Dict[Timeframe, List[Candle]] = {tf: [] for tf in ALL_TIMEFRAMES}
        self.candle_providers: Dict[Timeframe, str] = {}
        self.candle_updated_at: Dict[Timeframe, str] = {}
        self.last_closed_bar_time: Dict[Timeframe, int] = {}

        self._active_quote_provider: Optional[str] = None
        self._active_candle_provider: Optional[str] = None
        self._last_error: Optional[str] = None

    async def close(self) -> None:
        await self.biquote.close()
        await self.swissquote.close()
        await self.goldapi.close()
        await self.yahoo_fallback.close()
        if self.twelvedata:
            await self.twelvedata.close()

    def _classify_feed_status(self, quote: Optional[LiveQuote]) -> Tuple[FeedStatus, Optional[str]]:
        if quote is None:
            return "DISCONNECTED", "No live XAUUSD market data provider is currently reachable."

        # Recalculate real age from quote timestamp right now
        try:
            q_dt = datetime.fromisoformat(quote.quote_timestamp.replace("Z", "+00:00"))
            live_age = max(0.0, (utc_now() - q_dt).total_seconds())
        except Exception:
            live_age = quote.quote_age_seconds

        if quote.market_state != "open" or (is_forex_weekend() and live_age > settings.quote_disconnected_threshold_sec):
            return "MARKET_CLOSED", "Spot Gold (XAUUSD) market is currently closed (weekend/holiday rollover)."

        if live_age > settings.quote_disconnected_threshold_sec:
            return (
                "DELAYED",
                f"Market quote is severely delayed ({int(live_age)}s old). Signals suspended until live feed resumes.",
            )

        if live_age > settings.quote_delayed_threshold_sec or quote.status == "DELAYED":
            return (
                "DELAYED",
                f"Live quote delayed by {int(live_age)}s (threshold {settings.quote_delayed_threshold_sec}s).",
            )

        return "LIVE", None

    async def refresh_quote(self) -> Optional[LiveQuote]:
        """Fetch live XAUUSD Bid/Ask/Spread with automatic failover and secondary cross-check."""
        primary_quote: Optional[LiveQuote] = None
        secondary_quote: Optional[LiveQuote] = None

        # Fetch BiQuote and Swissquote concurrently for lowest latency & cross-verification
        tasks = [self.biquote.fetch_quote(), self.swissquote.fetch_quote()]
        if self.twelvedata and settings.preferred_provider == "twelvedata":
            tasks.insert(0, self.twelvedata.fetch_quote())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        if self.twelvedata and settings.preferred_provider == "twelvedata":
            td_res, bq_res, sq_res = results[0], results[1], results[2]
            if isinstance(td_res, LiveQuote):
                primary_quote = td_res
            if isinstance(bq_res, LiveQuote):
                if primary_quote is None:
                    primary_quote = bq_res
                else:
                    secondary_quote = bq_res
            if isinstance(sq_res, LiveQuote) and secondary_quote is None:
                secondary_quote = sq_res
        else:
            bq_res, sq_res = results[0], results[1]
            if isinstance(bq_res, LiveQuote):
                primary_quote = bq_res
            if isinstance(sq_res, LiveQuote):
                if primary_quote is None:
                    primary_quote = sq_res
                else:
                    # If primary is delayed/stale while Swissquote is fresher, promote Swissquote
                    if primary_quote.quote_age_seconds > settings.quote_delayed_threshold_sec and sq_res.quote_age_seconds < primary_quote.quote_age_seconds:
                        secondary_quote = primary_quote
                        primary_quote = sq_res
                    else:
                        secondary_quote = sq_res

        if primary_quote is None:
            # Tertiary failover: Gold-API Spot XAU if both BiQuote and Swissquote failed
            try:
                primary_quote = await self.goldapi.fetch_quote()
            except Exception as ga_exc:
                errs = [str(r) for r in results if isinstance(r, Exception)] + [str(ga_exc)]
                self._last_error = "; ".join(errs) if errs else "All providers failed"
                logger.warning("XAUUSD quote refresh failed across all 3 providers: %s", self._last_error)
                if self.latest_quote is not None:
                    self.latest_quote.status = "DISCONNECTED"
                    self.latest_quote.warning = f"Feed disconnected: {self._last_error}"
                return None

        # Attach secondary cross-check
        if secondary_quote is not None:
            primary_quote.secondary_provider = secondary_quote.provider
            primary_quote.secondary_mid = secondary_quote.mid
            primary_quote.provider_discrepancy_usd = round(abs(primary_quote.mid - secondary_quote.mid), 3)

        # Compute accurate daily change ($ and %) from real D1 previous close candle
        self._enrich_quote_daily_stats(primary_quote)

        status, warning = self._classify_feed_status(primary_quote)
        primary_quote.status = status
        primary_quote.warning = warning
        if (
            primary_quote.provider_discrepancy_usd is not None
            and primary_quote.provider_discrepancy_usd > 4.0
            and warning is None
        ):
            primary_quote.warning = (
                f"Cross-provider quote divergence detected (${primary_quote.provider_discrepancy_usd:.2f} "
                f"between {primary_quote.provider} and {primary_quote.secondary_provider})."
            )

        self.latest_quote = primary_quote
        self._active_quote_provider = primary_quote.provider
        self._last_error = None

        # Update active (open) candle close/high/low with live mid tick for real-time responsiveness
        if status == "LIVE":
            self._apply_live_tick_to_open_candles(primary_quote)

        return primary_quote

    def _enrich_quote_daily_stats(self, quote: LiveQuote) -> None:
        d1_bars = self.candles.get("D1") or []
        if len(d1_bars) >= 2:
            today_bar = d1_bars[-1]
            prev_bar = d1_bars[-2]
            prev_close = prev_bar.close
            quote.prev_close = round(prev_close, 3)
            change_usd = round(quote.mid - prev_close, 3)
            change_pct = round((change_usd / prev_close) * 100.0, 3) if prev_close > 0 else 0.0
            quote.change_usd = change_usd
            quote.change_percent = change_pct
            quote.direction = "UP" if change_usd > 0 else ("DOWN" if change_usd < 0 else "FLAT")
            # Keep day high/low synchronized with today's D1 candle + live mid
            high_candidates = [v for v in [quote.day_high, today_bar.high, quote.mid] if v is not None]
            low_candidates = [v for v in [quote.day_low, today_bar.low, quote.mid] if v is not None]
            if high_candidates:
                quote.day_high = round(max(high_candidates), 3)
            if low_candidates:
                quote.day_low = round(min(low_candidates), 3)

    def _apply_live_tick_to_open_candles(self, quote: LiveQuote) -> None:
        try:
            tick_ts = int(datetime.fromisoformat(quote.quote_timestamp.replace("Z", "+00:00")).timestamp())
        except Exception:
            return
        mid = quote.mid
        for tf, bars in self.candles.items():
            if not bars:
                continue
            tf_sec = TIMEFRAME_SECONDS[tf]
            last_bar = bars[-1]
            if last_bar.time <= tick_ts < last_bar.time + tf_sec:
                last_bar.close = round(mid, 3)
                if mid > last_bar.high:
                    last_bar.high = round(mid, 3)
                if mid < last_bar.low:
                    last_bar.low = round(mid, 3)
                last_bar.is_open = True

    def _persist_and_merge_candles(self, timeframe: Timeframe, fresh: List[Candle], provider_name: str) -> List[Candle]:
        """Store real fetched candles into DB and merge prior real history (strictly real bars only)."""
        db: Session = SessionLocal()
        try:
            # Upsert fresh bars
            existing_rows = (
                db.query(CandleCache)
                .filter(CandleCache.symbol == "XAUUSD", CandleCache.timeframe == timeframe)
                .order_by(CandleCache.open_time.asc())
                .all()
            )
            by_time: Dict[int, CandleCache] = {row.open_time: row for row in existing_rows}

            for c in fresh:
                row = by_time.get(c.time)
                if row is None:
                    new_row = CandleCache(
                        symbol="XAUUSD",
                        timeframe=timeframe,
                        open_time=c.time,
                        open=c.open,
                        high=c.high,
                        low=c.low,
                        close=c.close,
                        volume=c.volume,
                        provider=provider_name,
                    )
                    db.add(new_row)
                    by_time[c.time] = new_row
                else:
                    row.open = c.open
                    row.high = c.high
                    row.low = c.low
                    row.close = c.close
                    row.volume = c.volume
                    row.provider = provider_name
            db.commit()

            # Rebuild sorted candle list capped to last 600 real bars
            fresh_open_map = {c.time: c.is_open for c in fresh}
            sorted_times = sorted(by_time.keys())[-600:]
            merged: List[Candle] = []
            for t in sorted_times:
                r = by_time[t]
                iso = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                merged.append(
                    Candle(
                        time=t,
                        open_time_iso=iso,
                        open=round(float(r.open), 3),
                        high=round(float(r.high), 3),
                        low=round(float(r.low), 3),
                        close=round(float(r.close), 3),
                        volume=round(float(r.volume), 2),
                        is_open=fresh_open_map.get(t, False),
                    )
                )
            return merged
        except Exception as exc:
            db.rollback()
            logger.warning("Candle cache DB merge skipped for %s: %s", timeframe, exc)
            return fresh
        finally:
            db.close()

    async def refresh_candles(self, timeframe: Timeframe, limit: int = 500) -> Tuple[List[Candle], bool]:
        """
        Fetch real OHLC candlesticks for a single timeframe.
        Returns (candles, new_closed_candle_detected).
        """
        providers = []
        if self.twelvedata and settings.preferred_provider == "twelvedata":
            providers = [self.twelvedata, self.biquote, self.yahoo_fallback]
        elif self.twelvedata:
            providers = [self.biquote, self.twelvedata, self.yahoo_fallback]
        else:
            providers = [self.biquote, self.yahoo_fallback]

        last_err: Optional[Exception] = None
        for prov in providers:
            try:
                fresh = await prov.fetch_candles(timeframe, limit=limit)
                merged = self._persist_and_merge_candles(timeframe, fresh, prov.name)
                prev_closed = self.last_closed_bar_time.get(timeframe)
                # Identify most recent closed bar timestamp
                closed_bars = [b for b in merged if not b.is_open]
                newest_closed = closed_bars[-1].time if closed_bars else (merged[-2].time if len(merged) >= 2 else None)
                new_candle_closed = (
                    prev_closed is not None and newest_closed is not None and newest_closed > prev_closed
                )
                if newest_closed is not None:
                    self.last_closed_bar_time[timeframe] = newest_closed

                self.candles[timeframe] = merged
                self.candle_providers[timeframe] = prov.name
                self.candle_updated_at[timeframe] = utc_now_iso()
                self._active_candle_provider = prov.name

                if timeframe == "D1" and self.latest_quote is not None:
                    self._enrich_quote_daily_stats(self.latest_quote)
                return merged, new_candle_closed
            except Exception as exc:
                last_err = exc
                logger.warning("Failed fetching %s candles from %s: %s", timeframe, prov.name, exc)

        raise MarketDataError(f"All candle providers failed for {timeframe}: {last_err}")

    async def refresh_all_timeframes(self) -> Dict[Timeframe, bool]:
        """Fetch all 7 required XAUUSD timeframes concurrently."""
        tasks = [self.refresh_candles(tf) for tf in ALL_TIMEFRAMES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        closed_flags: Dict[Timeframe, bool] = {}
        for tf, res in zip(ALL_TIMEFRAMES, results):
            if isinstance(res, Exception):
                logger.warning("Timeframe %s refresh error: %s", tf, res)
                closed_flags[tf] = False
            else:
                _, new_closed = res
                closed_flags[tf] = new_closed
        return closed_flags

    def get_candles(self, timeframe: Timeframe) -> List[Candle]:
        return list(self.candles.get(timeframe, []))

    def get_health(self) -> FeedHealthResponse:
        status, warning = self._classify_feed_status(self.latest_quote)
        providers = [self.biquote.health(), self.swissquote.health()]
        if self.twelvedata:
            providers.append(self.twelvedata.health())

        bar_counts = {tf: len(self.candles.get(tf, [])) for tf in ALL_TIMEFRAMES}
        if status == "LIVE":
            msg = f"Live XAUUSD spot feed active via {self._active_quote_provider}."
        elif warning:
            msg = warning
        else:
            msg = "Initializing live XAUUSD market data connection."

        return FeedHealthResponse(
            status=status,
            active_quote_provider=self._active_quote_provider,
            active_candle_provider=self._active_candle_provider,
            quote_age_seconds=self.latest_quote.quote_age_seconds if self.latest_quote else None,
            market_state=self.latest_quote.market_state if self.latest_quote else "unknown",
            last_update=self.latest_quote.quote_timestamp if self.latest_quote else None,
            message=msg,
            providers=providers,
            timeframe_bar_counts=bar_counts,
        )
