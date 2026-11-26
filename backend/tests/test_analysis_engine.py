from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from app.analysis.mtf import synthesize_mtf
from app.analysis.risk_calculator import calculate_smart_risk_plan
from app.analysis.signal_engine import evaluate_trading_signal
from app.database import init_db
from app.market_data.base import ALL_TIMEFRAMES, TIMEFRAME_SECONDS
from app.market_data.manager import MarketDataManager
from app.schemas import Candle, FeedHealthResponse, LiveQuote, Timeframe


def _make_trend_candles(
    timeframe: Timeframe,
    count: int = 240,
    start_price: float = 3500.0,
    slope_per_bar: float = 0.6,
    swing_amp: float = 2.4,
) -> List[Candle]:
    """Deterministic synthetic OHLC fixtures strictly for unit-testing indicator math & signal rules."""
    step_sec = TIMEFRAME_SECONDS[timeframe]
    now_ts = int(datetime(2026, 11, 24, 9, 0, 0, tzinfo=timezone.utc).timestamp())
    start_ts = now_ts - count * step_sec
    bars: List[Candle] = []
    price = start_price
    for i in range(count):
        # Zero-mean oscillation + clean directional slope so RSI stays in healthy momentum band
        wave = swing_amp * (1.0 if (i % 8) < 4 else -1.0)
        o = price
        c = price + slope_per_bar + (wave * 0.35)
        h = max(o, c) + abs(swing_amp * 0.45)
        l = min(o, c) - abs(swing_amp * 0.45)
        t = start_ts + i * step_sec
        bars.append(
            Candle(
                time=t,
                open_time_iso=datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                open=round(o, 3),
                high=round(h, 3),
                low=round(l, 3),
                close=round(c, 3),
                volume=1000.0 + (i % 7) * 150.0,
                is_open=(i == count - 1),
            )
        )
        price = c
    return bars


def _live_quote(mid: float, spread: float = 0.20, status: str = "LIVE") -> LiveQuote:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return LiveQuote(
        symbol="XAUUSD",
        bid=round(mid - spread / 2, 3),
        ask=round(mid + spread / 2, 3),
        mid=round(mid, 3),
        spread=round(spread, 3),
        spread_bps=round((spread / mid) * 10000, 2),
        provider="UnitTest Fixture",
        quote_timestamp=now_iso,
        fetched_at=now_iso,
        quote_age_seconds=1.0,
        market_state="open",
        status=status,  # type: ignore[arg-type]
    )


def _health(status: str = "LIVE") -> FeedHealthResponse:
    return FeedHealthResponse(
        status=status,  # type: ignore[arg-type]
        active_quote_provider="UnitTest Fixture",
        active_candle_provider="UnitTest Fixture",
        quote_age_seconds=1.0,
        market_state="open",
        last_update=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        message="Live feed active" if status == "LIVE" else "Feed degraded",
    )


def test_all_indicators_and_vwap_applicability():
    candles_map = {tf: _make_trend_candles(tf, count=240, slope_per_bar=0.35) for tf in ALL_TIMEFRAMES}
    mtf, series_map = synthesize_mtf(candles_map)
    assert len(mtf.timeframes) == 7

    m15 = mtf.timeframes["M15"]
    assert m15.ema.ema_9 is not None
    assert m15.ema.ema_20 is not None
    assert m15.ema.ema_50 is not None
    assert m15.ema.ema_100 is not None
    assert m15.ema.ema_200 is not None
    assert m15.ema.ema_200_warmed is True
    assert m15.rsi.value is not None and 0 <= m15.rsi.value <= 100
    assert m15.macd.macd is not None and m15.macd.signal is not None
    assert m15.bollinger.upper is not None and m15.bollinger.lower is not None
    assert m15.atr.value is not None and m15.atr.value > 0
    assert m15.adx.adx is not None
    assert m15.stochastic.k is not None
    assert m15.vwap.applicable is True and m15.vwap.value is not None

    # Intraday session VWAP should be N/A on H4 and D1
    assert mtf.timeframes["H4"].vwap.applicable is False
    assert mtf.timeframes["D1"].vwap.applicable is False

    # Series overlays exist for chart rendering
    assert "ema_9" in series_map["M15"]
    assert "rsi" in series_map["M15"]
    assert "macd_hist" in series_map["M15"]


def test_mtf_conflict_forces_wait():
    """When H4 is strongly bullish and H1/M30 are strongly bearish, engine MUST detect conflict and recommend WAIT."""
    candles_map = {
        "D1": _make_trend_candles("D1", slope_per_bar=0.5),
        "H4": _make_trend_candles("H4", slope_per_bar=0.55),
        "H1": _make_trend_candles("H1", slope_per_bar=-0.55),
        "M30": _make_trend_candles("M30", slope_per_bar=-0.45),
        "M15": _make_trend_candles("M15", slope_per_bar=-0.35),
        "M5": _make_trend_candles("M5", slope_per_bar=-0.25),
        "M1": _make_trend_candles("M1", slope_per_bar=-0.15),
    }
    mtf, _ = synthesize_mtf(candles_map)
    assert mtf.has_major_conflict is True
    assert any(c.code == "MAJOR_TREND_CONFLICT" for c in mtf.conflicts)

    last_px = candles_map["M15"][-1].close
    sig = evaluate_trading_signal(_live_quote(last_px), _health("LIVE"), mtf)
    assert sig.action == "WAIT"
    assert sig.risk_plan is None
    assert "WAIT" in sig.explanation.decision_headline


def test_delayed_or_disconnected_feed_forces_wait():
    candles_map = {tf: _make_trend_candles(tf, slope_per_bar=0.35) for tf in ALL_TIMEFRAMES}
    mtf, _ = synthesize_mtf(candles_map)
    last_px = candles_map["M15"][-1].close

    sig_delayed = evaluate_trading_signal(_live_quote(last_px, status="DELAYED"), _health("DELAYED"), mtf)
    assert sig_delayed.action == "WAIT"
    assert sig_delayed.confidence == 0

    sig_disc = evaluate_trading_signal(None, _health("DISCONNECTED"), mtf)
    assert sig_disc.action == "WAIT"
    assert sig_disc.confidence == 0


def test_smart_sl_tp_calculator_enforces_min_rr_and_levels_order():
    candles_map = {tf: _make_trend_candles(tf, slope_per_bar=0.30, swing_amp=3.0) for tf in ALL_TIMEFRAMES}
    mtf, _ = synthesize_mtf(candles_map)
    last_px = candles_map["M15"][-1].close
    q = _live_quote(last_px)

    buy_plan = calculate_smart_risk_plan("BUY", q, mtf, min_rr=2.0)
    assert buy_plan.stop_loss < buy_plan.entry_price < buy_plan.tp1 < buy_plan.tp2 < buy_plan.tp3
    assert buy_plan.rr_tp2 >= 2.0
    assert len(buy_plan.rationales) == 5

    sell_plan = calculate_smart_risk_plan("SELL", q, mtf, min_rr=2.0)
    assert sell_plan.stop_loss > sell_plan.entry_price > sell_plan.tp1 > sell_plan.tp2 > sell_plan.tp3
    assert sell_plan.rr_tp2 >= 2.0
    assert len(sell_plan.rationales) == 5


def test_aligned_bullish_and_bearish_setups_produce_valid_signals():
    # Construct aligned healthy bullish continuation (bar ends on active bullish impulse, RSI healthy, MACD bullish)
    bull_map = {
        tf: _make_trend_candles(tf, count=236, start_price=3500.0, slope_per_bar=0.42, swing_amp=3.2)
        for tf in ALL_TIMEFRAMES
    }
    mtf_b, _ = synthesize_mtf(bull_map)
    px_b = bull_map["M15"][-1].close
    sig_b = evaluate_trading_signal(_live_quote(px_b, spread=0.20), _health("LIVE"), mtf_b)
    assert sig_b.action == "BUY", f"Expected BUY on aligned bullish data, got {sig_b.action}: {sig_b.explanation.missing_or_warnings}"
    assert sig_b.risk_plan is not None
    assert sig_b.risk_plan.rr_tp2 >= 2.0
    assert 62 <= sig_b.confidence <= 85

    # Verify opposing momentum veto: buying during a down-wave inside an uptrend (MACD expanding bearishly) MUST WAIT
    pullback_map = {
        tf: _make_trend_candles(tf, count=240, start_price=3500.0, slope_per_bar=0.45, swing_amp=3.2)
        for tf in ALL_TIMEFRAMES
    }
    mtf_pb, _ = synthesize_mtf(pullback_map)
    sig_pb = evaluate_trading_signal(_live_quote(pullback_map["M15"][-1].close, spread=0.20), _health("LIVE"), mtf_pb)
    assert sig_pb.action == "WAIT"
    assert any("opposing momentum" in w.lower() for w in sig_pb.explanation.missing_or_warnings)

    # Construct aligned healthy bearish continuation (exact mirror of bull_map: closed bar i=238 is down-wave #3)
    bear_map = {
        tf: _make_trend_candles(tf, count=240, start_price=3700.0, slope_per_bar=-0.35, swing_amp=3.2)
        for tf in ALL_TIMEFRAMES
    }
    mtf_s, _ = synthesize_mtf(bear_map)
    px_s = bear_map["M15"][-1].close
    sig_s = evaluate_trading_signal(_live_quote(px_s, spread=0.20), _health("LIVE"), mtf_s)
    assert sig_s.action == "SELL", f"Expected SELL on aligned bearish data, got {sig_s.action}: {sig_s.explanation.missing_or_warnings}"
    assert sig_s.risk_plan is not None
    assert sig_s.risk_plan.rr_tp2 >= 2.0
    assert 62 <= sig_s.confidence <= 85

    # Verify exhaustion guard: chasing oversold RSI <= 25 MUST return WAIT
    oversold_map = {
        tf: _make_trend_candles(tf, count=240, start_price=3700.0, slope_per_bar=-0.75, swing_amp=2.6)
        for tf in ALL_TIMEFRAMES
    }
    mtf_os, _ = synthesize_mtf(oversold_map)
    sig_os = evaluate_trading_signal(_live_quote(oversold_map["M15"][-1].close, spread=0.20), _health("LIVE"), mtf_os)
    assert sig_os.action == "WAIT"
    assert any("oversold" in w.lower() for w in sig_os.explanation.missing_or_warnings)


def test_selling_into_support_or_neutral_m5_forces_wait():
    """Regression test for Nov 24 premature SELL at $3,620: neutral M5, rising M15 MACD, or near support MUST WAIT."""
    bear_map = {
        tf: _make_trend_candles(tf, count=239, start_price=3700.0, slope_per_bar=-0.26, swing_amp=3.2)
        for tf in ALL_TIMEFRAMES
    }
    mtf, _ = synthesize_mtf(bear_map)
    px = bear_map["M15"][-1].close

    # Simulate exact Nov 24 conditions: M5 NEUTRAL + M15 MACD expanding bullishly + support floor right below price
    mtf.timeframes["M5"].trend = "NEUTRAL"
    mtf.timeframes["M5"].trend_score = -14.0
    mtf.timeframes["M15"].macd.momentum_state = "EXPANDING_BULLISH"
    if mtf.timeframes["M15"].support_levels:
        mtf.timeframes["M15"].support_levels[0].price = round(px - 1.5, 2)
    mtf.timeframes["M15"].breakout.status = "NONE"

    sig = evaluate_trading_signal(_live_quote(px, spread=0.15), _health("LIVE"), mtf)
    assert sig.action == "WAIT"
    warnings_text = " ".join(sig.explanation.missing_or_warnings).lower()
    assert "m5 entry confirmation" in warnings_text
    assert "opposing momentum" in warnings_text
    assert "support floor" in warnings_text
