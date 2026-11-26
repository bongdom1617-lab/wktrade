from __future__ import annotations

from typing import Dict, List, Tuple

from app.analysis.indicators import (
    candles_to_df,
    compute_indicator_series,
    extract_indicator_snapshot,
)
from app.analysis.structure import (
    analyze_market_structure,
    compute_support_resistance,
    detect_breakouts,
    detect_candlestick_patterns,
)
from app.schemas import (
    Candle,
    MtfSynthesis,
    Timeframe,
    TimeframeAnalysis,
    TimeframeConflict,
    TrendDirection,
)


TIMEFRAME_META: Dict[Timeframe, Tuple[str, float]] = {
    "D1": ("Macro Context", 0.10),
    "H4": ("Major Market Trend", 0.24),
    "H1": ("Main Market Direction", 0.22),
    "M30": ("Trend Confirmation", 0.16),
    "M15": ("Trading Setup", 0.14),
    "M5": ("Entry Confirmation", 0.09),
    "M1": ("Entry Precision", 0.05),
}


def analyze_single_timeframe(timeframe: Timeframe, candles: List[Candle]) -> Tuple[TimeframeAnalysis, Dict]:
    role, weight = TIMEFRAME_META[timeframe]
    df = candles_to_df(candles)
    # Full series including forming bar is returned for 1:1 live chart rendering
    series = compute_indicator_series(df, timeframe)

    # Evaluate confirmed indicator/structure snapshots on CLOSED candles for M5..D1
    # so a brief 1-2 minute mid-bar spike never triggers a premature signal
    use_closed = timeframe in ("M5", "M15", "M30", "H1", "H4", "D1") and len(df) >= 35 and bool(df["is_open"].iloc[-1])
    eval_df = df.iloc[:-1].reset_index(drop=True) if use_closed else df
    eval_series = compute_indicator_series(eval_df, timeframe) if use_closed else series

    ema, rsi, macd, bb, atr, adx, stoch, vwap = extract_indicator_snapshot(eval_df, eval_series, timeframe)

    atr_ref = atr.value if (atr.value and atr.value > 0) else max(float(eval_df["close"].iloc[-1]) * 0.001, 1.0)
    structure, sh, sl = analyze_market_structure(eval_df, atr_ref, rsi.divergence)
    supports, resistances = compute_support_resistance(eval_df, sh, sl, atr_ref)
    breakout = detect_breakouts(eval_df, supports, resistances, atr_ref)
    patterns = detect_candlestick_patterns(eval_df)

    # Compute transparent quantitative trend_score (-100 to +100) from confirmed closed close
    score = 0.0
    last_close = float(eval_df["close"].iloc[-1])

    # 1. EMA stack & position (up to +/-35)
    if ema.alignment == "STRONG_BULLISH":
        score += 32.0
    elif ema.alignment == "BULLISH":
        score += 20.0
    elif ema.alignment == "STRONG_BEARISH":
        score -= 32.0
    elif ema.alignment == "BEARISH":
        score -= 20.0
    else:
        if ema.ema_20 is not None and ema.ema_50 is not None:
            score += 8.0 if last_close > ema.ema_20 and ema.ema_20 > ema.ema_50 else (-8.0 if last_close < ema.ema_20 and ema.ema_20 < ema.ema_50 else 0.0)
    if ema.ema_200 is not None:
        score += 6.0 if last_close > ema.ema_200 else -6.0

    # 2. Market Structure (up to +/-25)
    if structure.structure_trend == "BULLISH":
        score += 18.0
    elif structure.structure_trend == "BEARISH":
        score -= 18.0
    if structure.bos == "BULLISH_BOS" or structure.choch == "BULLISH_CHOCH":
        score += 8.0
    elif structure.bos == "BEARISH_BOS" or structure.choch == "BEARISH_CHOCH":
        score -= 8.0

    # 3. Momentum: MACD + RSI + ADX directional (+DI/-DI) (up to +/-32)
    if macd.histogram is not None:
        if macd.momentum_state == "EXPANDING_BULLISH":
            score += 12.0
        elif macd.momentum_state == "FADING_BULLISH":
            score += 5.0
        elif macd.momentum_state == "EXPANDING_BEARISH":
            score -= 12.0
        elif macd.momentum_state == "FADING_BEARISH":
            score -= 5.0

    if rsi.value is not None:
        if rsi.value >= 55:
            score += 10.0
        elif rsi.value <= 45:
            score -= 10.0

    if adx.plus_di is not None and adx.minus_di is not None and (adx.adx or 0) >= 16:
        if adx.plus_di > adx.minus_di + 2.0:
            score += 10.0
        elif adx.minus_di > adx.plus_di + 2.0:
            score -= 10.0

    # 4. VWAP & Breakout (up to +/-12)
    if vwap.applicable:
        if vwap.position == "ABOVE":
            score += 5.0
        elif vwap.position == "BELOW":
            score -= 5.0
    if breakout.status == "BULLISH_BREAKOUT":
        score += 8.0
    elif breakout.status == "BEARISH_BREAKOUT":
        score -= 8.0
    elif breakout.status == "BULLISH_FALSE_BREAKOUT":
        score -= 7.0
    elif breakout.status == "BEARISH_FALSE_BREAKOUT":
        score += 7.0

    score = round(max(-100.0, min(100.0, score)), 1)

    if score >= 22.0:
        trend: TrendDirection = "BULLISH"
    elif score <= -22.0:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    # Momentum descriptor
    if macd.momentum_state == "EXPANDING_BULLISH" and (rsi.value or 50) >= 52:
        mom_state = "STRONG_BULLISH"
    elif macd.momentum_state == "EXPANDING_BEARISH" and (rsi.value or 50) <= 48:
        mom_state = "STRONG_BEARISH"
    elif (rsi.value or 50) >= 55:
        mom_state = "BULLISH"
    elif (rsi.value or 50) <= 45:
        mom_state = "BEARISH"
    else:
        mom_state = "NEUTRAL"

    summary = (
        f"{timeframe} ({role}): {trend} (score {score:+.0f}), EMA {ema.alignment.replace('_', ' ')}, "
        f"RSI {rsi.value if rsi.value is not None else 'N/A'}, ADX {adx.adx if adx.adx is not None else 'N/A'} "
        f"({adx.trend_strength}), structure {structure.pattern.replace('_', '/')}."
    )

    tf_analysis = TimeframeAnalysis(
        timeframe=timeframe,
        role=role,
        weight=weight,
        bar_count=len(candles),
        last_candle_time=candles[-1].open_time_iso,
        last_close=round(last_close, 3),
        trend=trend,
        trend_score=score,
        momentum_state=mom_state,
        ema=ema,
        rsi=rsi,
        macd=macd,
        bollinger=bb,
        atr=atr,
        adx=adx,
        stochastic=stoch,
        vwap=vwap,
        structure=structure,
        support_levels=supports,
        resistance_levels=resistances,
        patterns=patterns,
        breakout=breakout,
        summary=summary,
    )
    return tf_analysis, series


def synthesize_mtf(candles_by_tf: Dict[Timeframe, List[Candle]]) -> Tuple[MtfSynthesis, Dict[Timeframe, Dict]]:
    """Run simultaneous multi-timeframe analysis across D1, H4, H1, M30, M15, M5, M1 and detect conflicts."""
    ordered: List[Timeframe] = ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]
    analyses: Dict[str, TimeframeAnalysis] = {}
    series_map: Dict[Timeframe, Dict] = {}

    weighted_sum = 0.0
    total_weight = 0.0
    bull_n = 0
    bear_n = 0
    neut_n = 0

    for tf in ordered:
        bars = candles_by_tf.get(tf) or []
        if len(bars) < 25:
            continue
        tf_res, s = analyze_single_timeframe(tf, bars)
        analyses[tf] = tf_res
        series_map[tf] = s
        weighted_sum += tf_res.trend_score * tf_res.weight
        total_weight += tf_res.weight
        if tf_res.trend == "BULLISH":
            bull_n += 1
        elif tf_res.trend == "BEARISH":
            bear_n += 1
        else:
            neut_n += 1

    weighted_score = round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0
    if weighted_score >= 18.0:
        overall_bias: TrendDirection = "BULLISH"
    elif weighted_score <= -18.0:
        overall_bias = "BEARISH"
    else:
        overall_bias = "NEUTRAL"

    # Compute alignment score (0-100): how cohesively the 6 trading timeframes agree with overall bias
    core_tfs = [tf for tf in ("H4", "H1", "M30", "M15", "M5", "M1") if tf in analyses]
    aligned_w = 0.0
    core_w = 0.0
    for tf in core_tfs:
        a = analyses[tf]
        core_w += a.weight
        if overall_bias != "NEUTRAL" and a.trend == overall_bias:
            aligned_w += a.weight
        elif a.trend == "NEUTRAL":
            aligned_w += a.weight * 0.35
    alignment_score = round((aligned_w / core_w) * 100.0, 1) if core_w > 0 else 0.0

    # Explicit multi-timeframe conflict detection
    conflicts: List[TimeframeConflict] = []
    h4 = analyses.get("H4")
    h1 = analyses.get("H1")
    m30 = analyses.get("M30")
    m15 = analyses.get("M15")
    m5 = analyses.get("M5")
    m1 = analyses.get("M1")
    d1 = analyses.get("D1")

    if h4 and h1 and h4.trend != "NEUTRAL" and h1.trend != "NEUTRAL" and h4.trend != h1.trend:
        conflicts.append(
            TimeframeConflict(
                severity="HIGH",
                code="MAJOR_TREND_CONFLICT",
                timeframes=["H4", "H1"],
                description=(
                    f"H4 major trend is {h4.trend} ({h4.trend_score:+.0f}) while H1 main direction is "
                    f"{h1.trend} ({h1.trend_score:+.0f}). High-timeframe disagreement reduces reliability."
                ),
            )
        )

    if h1 and m30 and h1.trend != "NEUTRAL" and m30.trend != "NEUTRAL" and h1.trend != m30.trend:
        conflicts.append(
            TimeframeConflict(
                severity="HIGH",
                code="CONFIRMATION_CONFLICT",
                timeframes=["H1", "M30"],
                description=(
                    f"M30 trend confirmation ({m30.trend}) opposes H1 main direction ({h1.trend})."
                ),
            )
        )

    dominant_htf = h1.trend if (h1 and h1.trend != "NEUTRAL") else (h4.trend if h4 else "NEUTRAL")
    if m15 and dominant_htf != "NEUTRAL" and m15.trend != "NEUTRAL" and m15.trend != dominant_htf:
        conflicts.append(
            TimeframeConflict(
                severity="HIGH",
                code="SETUP_AGAINST_HTF",
                timeframes=["H4", "H1", "M15"],
                description=(
                    f"M15 setup ({m15.trend}) counters higher-timeframe direction ({dominant_htf}). "
                    "Avoid fighting institutional order flow."
                ),
            )
        )

    if m15 and m5 and m15.trend != "NEUTRAL" and m5.trend != "NEUTRAL" and m15.trend != m5.trend:
        conflicts.append(
            TimeframeConflict(
                severity="MODERATE",
                code="ENTRY_CONFIRMATION_CONFLICT",
                timeframes=["M15", "M5"],
                description=(
                    f"M5 entry confirmation ({m5.trend}) has not aligned with M15 setup ({m15.trend}) yet."
                ),
            )
        )

    if m5 and m1 and m5.trend != "NEUTRAL" and m1.trend != "NEUTRAL" and m5.trend != m1.trend:
        conflicts.append(
            TimeframeConflict(
                severity="LOW",
                code="MICRO_ENTRY_DIVERGENCE",
                timeframes=["M5", "M1"],
                description=(
                    f"M1 micro momentum ({m1.trend}) is pulling back against M5 ({m5.trend}) — monitor for precision trigger."
                ),
            )
        )

    if h1 and m15 and (h1.adx.adx or 0) < 18 and (m15.adx.adx or 0) < 18:
        conflicts.append(
            TimeframeConflict(
                severity="MODERATE",
                code="WEAK_TREND_CHOP",
                timeframes=["H1", "M15"],
                description=(
                    f"Low trend strength on both H1 (ADX {h1.adx.adx}) and M15 (ADX {m15.adx.adx}). "
                    "Market is ranging/choppy — breakout signals carry elevated whipsaw risk."
                ),
            )
        )

    if d1 and dominant_htf != "NEUTRAL" and d1.trend != "NEUTRAL" and d1.trend != dominant_htf:
        conflicts.append(
            TimeframeConflict(
                severity="LOW",
                code="D1_MACRO_HEADWIND",
                timeframes=["D1", "H4"],
                description=(
                    f"Intraday bias ({dominant_htf}) runs counter to D1 macro context ({d1.trend}); tighten risk management."
                ),
            )
        )

    has_major_conflict = any(c.severity == "HIGH" for c in conflicts)

    mtf = MtfSynthesis(
        overall_bias=overall_bias,
        alignment_score=alignment_score,
        weighted_score=weighted_score,
        bullish_count=bull_n,
        bearish_count=bear_n,
        neutral_count=neut_n,
        has_major_conflict=has_major_conflict,
        conflicts=conflicts,
        timeframes=analyses,
    )
    return mtf, series_map
