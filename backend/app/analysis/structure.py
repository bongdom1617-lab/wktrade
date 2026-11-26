from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from app.schemas import (
    BreakoutAssessment,
    CandlestickPattern,
    MarketStructureInfo,
    SupportResistanceLevel,
)


def detect_swings(df: pd.DataFrame, left: int = 3, right: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """Identify fractal swing highs and swing lows from real OHLC bars."""
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    swing_highs: List[Tuple[int, float]] = []
    swing_lows: List[Tuple[int, float]] = []
    if n < left + right + 1:
        return swing_highs, swing_lows

    for i in range(left, n - right):
        win_h = highs[i - left : i + right + 1]
        win_l = lows[i - left : i + right + 1]
        if highs[i] == np.max(win_h) and highs[i] > highs[i - 1] and highs[i] >= highs[i + 1]:
            swing_highs.append((i, float(highs[i])))
        if lows[i] == np.min(win_l) and lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            swing_lows.append((i, float(lows[i])))

    return swing_highs, swing_lows


def analyze_market_structure(
    df: pd.DataFrame,
    atr_value: float,
    rsi_divergence: Optional[str] = None,
) -> Tuple[MarketStructureInfo, List[Tuple[int, float]], List[Tuple[int, float]]]:
    swing_highs, swing_lows = detect_swings(df, left=3, right=3)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        swing_highs, swing_lows = detect_swings(df, left=2, right=2)

    last_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else last_close

    last_sh = swing_highs[-1][1] if len(swing_highs) >= 1 else None
    prev_sh = swing_highs[-2][1] if len(swing_highs) >= 2 else None
    last_sl = swing_lows[-1][1] if len(swing_lows) >= 1 else None
    prev_sl = swing_lows[-2][1] if len(swing_lows) >= 2 else None

    tol = max(atr_value * 0.12, 0.25)
    pattern = "CONSOLIDATION"
    structure_trend = "NEUTRAL"

    if all(v is not None for v in (last_sh, prev_sh, last_sl, prev_sl)):
        hh = last_sh > prev_sh + tol
        hl = last_sl > prev_sl + tol
        lh = last_sh < prev_sh - tol
        ll = last_sl < prev_sl - tol
        if hh and hl:
            pattern = "HH_HL"
            structure_trend = "BULLISH"
        elif lh and ll:
            pattern = "LH_LL"
            structure_trend = "BEARISH"
        elif (hh and ll) or (lh and hl):
            pattern = "TRANSITION"
            structure_trend = "NEUTRAL"
        elif hl and not ll:
            pattern = "HH_HL"
            structure_trend = "BULLISH"
        elif lh and not hh:
            pattern = "LH_LL"
            structure_trend = "BEARISH"

    bos: Optional[str] = None
    choch: Optional[str] = None

    # Detect Break of Structure (BOS) or Change of Character (CHoCH) on recent closes
    if last_sh is not None and last_close > last_sh:
        if structure_trend == "BEARISH":
            choch = "BULLISH_CHOCH"
        else:
            bos = "BULLISH_BOS"
            structure_trend = "BULLISH"
    elif last_sl is not None and last_close < last_sl:
        if structure_trend == "BULLISH":
            choch = "BEARISH_CHOCH"
        else:
            bos = "BEARISH_BOS"
            structure_trend = "BEARISH"
    elif prev_sh is not None and last_sh is not None and prev_close <= last_sh < last_close:
        bos = "BULLISH_BOS"

    reversal_warning: Optional[str] = None
    if choch == "BULLISH_CHOCH":
        reversal_warning = f"Potential bullish reversal: price broke above prior lower swing high (${last_sh:.2f})."
    elif choch == "BEARISH_CHOCH":
        reversal_warning = f"Potential bearish reversal: price broke below prior higher swing low (${last_sl:.2f})."
    elif rsi_divergence == "BULLISH_DIVERGENCE":
        reversal_warning = "Bullish RSI divergence detected — downside momentum is weakening."
    elif rsi_divergence == "BEARISH_DIVERGENCE":
        reversal_warning = "Bearish RSI divergence detected — upside momentum is fading."

    info = MarketStructureInfo(
        structure_trend=structure_trend,  # type: ignore[arg-type]
        pattern=pattern,
        last_swing_high=round(last_sh, 3) if last_sh is not None else None,
        last_swing_low=round(last_sl, 3) if last_sl is not None else None,
        prev_swing_high=round(prev_sh, 3) if prev_sh is not None else None,
        prev_swing_low=round(prev_sl, 3) if prev_sl is not None else None,
        bos=bos,
        choch=choch,
        reversal_warning=reversal_warning,
    )
    return info, swing_highs, swing_lows


def compute_support_resistance(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
    atr_value: float,
) -> Tuple[List[SupportResistanceLevel], List[SupportResistanceLevel]]:
    """Cluster swing pivots into verified institutional Support & Resistance zones."""
    current_price = float(df["close"].iloc[-1])
    cluster_tol = max(atr_value * 0.42, current_price * 0.0008, 0.8)

    raw_points: List[Tuple[float, int]] = []
    n = len(df)
    for idx, price in swing_highs:
        recency_bonus = 2 if idx >= n - 45 else 1
        raw_points.append((price, recency_bonus))
    for idx, price in swing_lows:
        recency_bonus = 2 if idx >= n - 45 else 1
        raw_points.append((price, recency_bonus))

    # Also include recent session extremes
    if len(df) >= 20:
        raw_points.append((float(df["high"].tail(48).max()), 1))
        raw_points.append((float(df["low"].tail(48).min()), 1))

    # Agglomerative clustering by price proximity
    clusters: List[dict] = []
    for price, weight in sorted(raw_points, key=lambda x: x[0]):
        merged = False
        for cl in clusters:
            if abs(price - cl["center"]) <= cluster_tol:
                cl["prices"].append(price)
                cl["weight"] += weight
                cl["center"] = float(np.mean(cl["prices"]))
                merged = True
                break
        if not merged:
            clusters.append({"center": price, "prices": [price], "weight": weight, "source": "swing_cluster"})

    # Count actual historical bar touches near each cluster center
    highs = df["high"].values
    lows = df["low"].values
    touch_tol = max(atr_value * 0.25, 0.5)

    supports: List[SupportResistanceLevel] = []
    resistances: List[SupportResistanceLevel] = []

    for cl in clusters:
        lvl = round(cl["center"], 2)
        touches = int(np.sum((lows <= lvl + touch_tol) & (highs >= lvl - touch_tol)))
        touches = max(touches, len(cl["prices"]))
        strength = min(5, max(1, int(round(1 + min(3, len(cl["prices"])) * 0.8 + min(6, touches) * 0.3))))
        dist = round(abs(current_price - lvl), 2)
        dist_pct = round((dist / current_price) * 100.0, 3) if current_price > 0 else 0.0

        # Ignore levels practically sitting on top of exact current tick (<0.15 ATR) as S/R noise
        if dist < max(atr_value * 0.12, 0.30):
            continue

        if lvl < current_price:
            supports.append(
                SupportResistanceLevel(
                    price=lvl,
                    kind="SUPPORT",
                    strength=strength,
                    touches=touches,
                    distance_usd=dist,
                    distance_pct=dist_pct,
                    source="swing_cluster",
                )
            )
        else:
            resistances.append(
                SupportResistanceLevel(
                    price=lvl,
                    kind="RESISTANCE",
                    strength=strength,
                    touches=touches,
                    distance_usd=dist,
                    distance_pct=dist_pct,
                    source="swing_cluster",
                )
            )

    # Sort nearest first, keeping strongest well-spaced levels
    supports.sort(key=lambda x: x.distance_usd)
    resistances.sort(key=lambda x: x.distance_usd)

    def _dedup_spacing(levels: List[SupportResistanceLevel], min_gap: float) -> List[SupportResistanceLevel]:
        out: List[SupportResistanceLevel] = []
        for lv in levels:
            if all(abs(lv.price - kept.price) >= min_gap for kept in out):
                out.append(lv)
            if len(out) >= 4:
                break
        return out

    min_gap = max(atr_value * 0.55, 1.5)
    supports = _dedup_spacing(supports, min_gap)
    resistances = _dedup_spacing(resistances, min_gap)

    # Add nearest psychological $25/$50 round level if fewer than 3 levels exist
    step = 25.0
    if len(supports) < 2:
        round_sup = float(np.floor((current_price - min_gap) / step) * step)
        if round_sup > 0 and all(abs(round_sup - s.price) >= min_gap for s in supports):
            dist = round(current_price - round_sup, 2)
            supports.append(
                SupportResistanceLevel(
                    price=round(round_sup, 2),
                    kind="SUPPORT",
                    strength=2,
                    touches=1,
                    distance_usd=dist,
                    distance_pct=round((dist / current_price) * 100.0, 3),
                    source="psychological",
                )
            )
            supports.sort(key=lambda x: x.distance_usd)
    if len(resistances) < 2:
        round_res = float(np.ceil((current_price + min_gap) / step) * step)
        if all(abs(round_res - r.price) >= min_gap for r in resistances):
            dist = round(round_res - current_price, 2)
            resistances.append(
                SupportResistanceLevel(
                    price=round(round_res, 2),
                    kind="RESISTANCE",
                    strength=2,
                    touches=1,
                    distance_usd=dist,
                    distance_pct=round((dist / current_price) * 100.0, 3),
                    source="psychological",
                )
            )
            resistances.sort(key=lambda x: x.distance_usd)

    return supports[:4], resistances[:4]


def detect_breakouts(
    df: pd.DataFrame,
    supports: List[SupportResistanceLevel],
    resistances: List[SupportResistanceLevel],
    atr_value: float,
) -> BreakoutAssessment:
    """Detect clean breakouts and liquidity-sweep false breakouts from real closed candles."""
    if len(df) < 12:
        return BreakoutAssessment(status="NONE", level=None, description="Insufficient bars for breakout validation.")

    # Use last closed candle (index -2 if last bar is open, else -1)
    idx = -2 if bool(df["is_open"].iloc[-1]) and len(df) >= 15 else -1
    bar = df.iloc[idx]
    prior = df.iloc[max(0, len(df) + idx - 24) : len(df) + idx]
    if prior.empty:
        return BreakoutAssessment(status="NONE", level=None, description="No recent range breakout.")

    prior_high = float(prior["high"].max())
    prior_low = float(prior["low"].min())
    o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    rng = max(h - l, 0.01)
    body = abs(c - o)
    body_ratio = body / rng
    avg_vol = float(prior["volume"].mean()) if float(prior["volume"].mean()) > 0 else 0.0
    vol_confirm = avg_vol > 0 and float(bar["volume"]) >= avg_vol * 1.15

    # Bullish Breakout: closed firmly above prior 24-bar resistance
    if c > prior_high + atr_value * 0.08 and body_ratio >= 0.42:
        vol_txt = " with expanding tick volume" if vol_confirm else ""
        return BreakoutAssessment(
            status="BULLISH_BREAKOUT",
            level=round(prior_high, 2),
            description=f"Confirmed bullish breakout: candle closed at ${c:.2f} above 24-bar resistance ${prior_high:.2f}{vol_txt}.",
        )

    # Bearish Breakout: closed firmly below prior 24-bar support
    if c < prior_low - atr_value * 0.08 and body_ratio >= 0.42:
        vol_txt = " with expanding tick volume" if vol_confirm else ""
        return BreakoutAssessment(
            status="BEARISH_BREAKOUT",
            level=round(prior_low, 2),
            description=f"Confirmed bearish breakdown: candle closed at ${c:.2f} below 24-bar support ${prior_low:.2f}{vol_txt}.",
        )

    # Bullish False Breakout (Bull Trap): wick pierced resistance then rejected back below
    if h > prior_high + atr_value * 0.15 and c < prior_high - atr_value * 0.05:
        return BreakoutAssessment(
            status="BULLISH_FALSE_BREAKOUT",
            level=round(prior_high, 2),
            description=f"False upside breakout (bull trap) above ${prior_high:.2f}: wick spiked to ${h:.2f} before closing back inside at ${c:.2f}.",
        )

    # Bearish False Breakout (Bear Trap / Liquidity Sweep): wick pierced support then reclaimed
    if l < prior_low - atr_value * 0.15 and c > prior_low + atr_value * 0.05:
        return BreakoutAssessment(
            status="BEARISH_FALSE_BREAKOUT",
            level=round(prior_low, 2),
            description=f"False downside breakdown (liquidity sweep) below ${prior_low:.2f}: wick swept ${l:.2f} before reclaiming ${c:.2f}.",
        )

    nearest_res = resistances[0].price if resistances else round(prior_high, 2)
    nearest_sup = supports[0].price if supports else round(prior_low, 2)
    return BreakoutAssessment(
        status="NONE",
        level=None,
        description=f"Trading inside active range (${nearest_sup:.2f} support to ${nearest_res:.2f} resistance).",
    )


def detect_candlestick_patterns(df: pd.DataFrame) -> List[CandlestickPattern]:
    """Identify institutional price-action candlestick patterns on recent closed bars."""
    if len(df) < 5:
        return []

    end = len(df) - 1 if bool(df["is_open"].iloc[-1]) else len(df)
    if end < 3:
        return []

    c1 = df.iloc[end - 3]
    c2 = df.iloc[end - 2]
    c3 = df.iloc[end - 1]

    patterns: List[CandlestickPattern] = []

    def _metrics(row):
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        rng = max(h - l, 1e-6)
        body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        return o, h, l, c, rng, body, upper_wick, lower_wick

    o2, h2, l2, cl2, rng2, b2, uw2, lw2 = _metrics(c2)
    o3, h3, l3, cl3, rng3, b3, uw3, lw3 = _metrics(c3)
    o1, h1, l1, cl1, rng1, b1, uw1, lw1 = _metrics(c1)
    t3 = str(c3["open_time_iso"])

    # 1. Bullish Engulfing
    if cl2 < o2 and cl3 > o3 and o3 <= cl2 and cl3 >= o2 and b3 > b2 * 1.05:
        patterns.append(
            CandlestickPattern(
                name="Bullish Engulfing",
                bias="BULLISH",
                strength="HIGH",
                candle_time=t3,
                description=f"Bullish candle (${o3:.2f} -> ${cl3:.2f}) fully engulfed prior bearish body.",
            )
        )

    # 2. Bearish Engulfing
    if cl2 > o2 and cl3 < o3 and o3 >= cl2 and cl3 <= o2 and b3 > b2 * 1.05:
        patterns.append(
            CandlestickPattern(
                name="Bearish Engulfing",
                bias="BEARISH",
                strength="HIGH",
                candle_time=t3,
                description=f"Bearish candle (${o3:.2f} -> ${cl3:.2f}) fully engulfed prior bullish body.",
            )
        )

    # 3. Hammer / Bullish Pin Bar
    if lw3 >= b3 * 2.0 and uw3 <= rng3 * 0.25 and (b3 / rng3) <= 0.38:
        patterns.append(
            CandlestickPattern(
                name="Bullish Pin Bar / Hammer",
                bias="BULLISH",
                strength="MEDIUM",
                candle_time=t3,
                description=f"Strong lower-wick rejection off ${l3:.2f} closing near high at ${cl3:.2f}.",
            )
        )

    # 4. Shooting Star / Bearish Pin Bar
    if uw3 >= b3 * 2.0 and lw3 <= rng3 * 0.25 and (b3 / rng3) <= 0.38:
        patterns.append(
            CandlestickPattern(
                name="Bearish Pin Bar / Shooting Star",
                bias="BEARISH",
                strength="MEDIUM",
                candle_time=t3,
                description=f"Sharp upper-wick rejection off ${h3:.2f} closing near low at ${cl3:.2f}.",
            )
        )

    # 5. Morning Star (3-bar bullish reversal)
    if (
        cl1 < o1 and (b1 / rng1) >= 0.45
        and (b2 / rng2) <= 0.32
        and cl3 > o3 and cl3 >= (o1 + cl1) / 2.0
    ):
        patterns.append(
            CandlestickPattern(
                name="Morning Star",
                bias="BULLISH",
                strength="HIGH",
                candle_time=t3,
                description="Three-candle bullish reversal reclaiming over half of prior sell candle.",
            )
        )

    # 6. Evening Star (3-bar bearish reversal)
    if (
        cl1 > o1 and (b1 / rng1) >= 0.45
        and (b2 / rng2) <= 0.32
        and cl3 < o3 and cl3 <= (o1 + cl1) / 2.0
    ):
        patterns.append(
            CandlestickPattern(
                name="Evening Star",
                bias="BEARISH",
                strength="HIGH",
                candle_time=t3,
                description="Three-candle bearish reversal rejecting prior advance.",
            )
        )

    # 7. Bullish / Bearish Marubozu (strong momentum close)
    if (b3 / rng3) >= 0.80:
        if cl3 > o3:
            patterns.append(
                CandlestickPattern(
                    name="Bullish Momentum Candle",
                    bias="BULLISH",
                    strength="MEDIUM",
                    candle_time=t3,
                    description=f"Full-bodied bullish expansion candle (${o3:.2f} -> ${cl3:.2f}) with minimal upper wick.",
                )
            )
        else:
            patterns.append(
                CandlestickPattern(
                    name="Bearish Momentum Candle",
                    bias="BEARISH",
                    strength="MEDIUM",
                    candle_time=t3,
                    description=f"Full-bodied bearish expansion candle (${o3:.2f} -> ${cl3:.2f}) with minimal lower wick.",
                )
            )

    # 8. Inside Bar (volatility compression)
    if h3 < h2 and l3 > l2:
        patterns.append(
            CandlestickPattern(
                name="Inside Bar",
                bias="NEUTRAL",
                strength="LOW",
                candle_time=t3,
                description="Range contracted strictly inside prior candle — watch for directional break.",
            )
        )

    # 9. Doji (indecision)
    if (b3 / rng3) <= 0.12 and not patterns:
        patterns.append(
            CandlestickPattern(
                name="Doji (Indecision)",
                bias="NEUTRAL",
                strength="LOW",
                candle_time=t3,
                description=f"Open (${o3:.2f}) and close (${cl3:.2f}) balanced — equilibrium / pause.",
            )
        )

    return patterns[:3]
