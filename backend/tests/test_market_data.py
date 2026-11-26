from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.database import init_db
from app.market_data.base import ALL_TIMEFRAMES
from app.market_data.manager import MarketDataManager
from app.schemas import LiveQuote


@pytest.mark.asyncio
async def test_live_xauusd_quote_and_all_timeframes():
    """Verify live external XAUUSD spot quote (Bid/Ask/Spread) and all 7 candlestick timeframes."""
    init_db()
    mgr = MarketDataManager()
    try:
        # 1. Fetch all 7 timeframes first so D1 prev_close enriches daily change
        closed_flags = await mgr.refresh_all_timeframes()
        for tf in ALL_TIMEFRAMES:
            bars = mgr.get_candles(tf)
            assert len(bars) >= 50, f"Expected >=50 live bars for {tf}, got {len(bars)}"
            # Verify strict ascending timestamps and valid OHLC
            for i in range(1, len(bars)):
                assert bars[i].time > bars[i - 1].time, f"Non-ascending timestamps on {tf}"
            for b in bars[-10:]:
                assert b.high >= max(b.open, b.close)
                assert b.low <= min(b.open, b.close)
                assert b.close > 500.0  # Plausible spot gold price

        # 2. Fetch live quote with cross-provider verification
        quote = await mgr.refresh_quote()
        assert quote is not None, "Expected live XAUUSD quote from external provider"
        assert quote.symbol == "XAUUSD"
        assert quote.bid > 500.0
        assert quote.ask >= quote.bid
        assert quote.spread >= 0.0
        assert quote.provider in ("BiQuote Spot XAUUSD", "Swissquote BBO XAU/USD", "Twelve Data XAU/USD")
        assert quote.change_usd is not None
        assert quote.change_percent is not None
        assert quote.status in ("LIVE", "DELAYED", "MARKET_CLOSED")

        health = mgr.get_health()
        assert health.active_quote_provider is not None
        assert health.active_candle_provider is not None
        assert all(health.timeframe_bar_counts[tf] >= 50 for tf in ALL_TIMEFRAMES)

        print(
            f"\n[LIVE VERIFIED] {quote.provider} | Bid={quote.bid} Ask={quote.ask} "
            f"Spread={quote.spread} | Change={quote.change_usd:+.2f} ({quote.change_percent:+.2f}%) | "
            f"Secondary={quote.secondary_provider} (diff=${quote.provider_discrepancy_usd}) | "
            f"Age={quote.quote_age_seconds}s | Status={quote.status}"
        )
        print("Timeframe bars:", health.timeframe_bar_counts)
    finally:
        await mgr.close()


def test_delayed_and_disconnected_detection():
    """Verify delayed and disconnected market data detection never fabricates live status."""
    mgr = MarketDataManager()
    # Disconnected when no quote exists
    status, msg = mgr._classify_feed_status(None)
    assert status == "DISCONNECTED"
    assert msg is not None

    # Delayed when quote is 45 seconds old
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale_quote = LiveQuote(
        symbol="XAUUSD",
        bid=3600.0,
        ask=3600.3,
        mid=3600.15,
        spread=0.3,
        provider="BiQuote Spot XAUUSD",
        quote_timestamp=old_ts,
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        quote_age_seconds=45.0,
        market_state="open",
        status="LIVE",
    )
    status2, msg2 = mgr._classify_feed_status(stale_quote)
    assert status2 == "DELAYED"
    assert "delayed" in (msg2 or "").lower()

    # Market closed explicitly detected
    closed_quote = stale_quote.model_copy(update={"market_state": "closed"})
    status3, _ = mgr._classify_feed_status(closed_quote)
    assert status3 == "MARKET_CLOSED"
