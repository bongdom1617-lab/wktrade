from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.schemas import (
    AdxValues,
    AtrValues,
    BollingerValues,
    Candle,
    EmaValues,
    MacdValues,
    RsiValues,
    StochasticValues,
    Timeframe,
    VwapValues,
)


def _safe_float(val: Any, digits: int = 3) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, digits)
    except (TypeError, ValueError):
        return None


def candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume", "open_time_iso"])
    df = pd.DataFrame(
        [
            {
                "time": c.time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "open_time_iso": c.open_time_iso,
                "is_open": c.is_open,
            }
            for c in candles
        ]
    )
    return df


def _wilder_rma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def compute_indicator_series(df: pd.DataFrame, timeframe: Timeframe) -> Dict[str, Any]:
    """Compute full time-series arrays for chart overlays & backend snapshot extraction."""
    if df.empty:
        return {}

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    times = df["time"].astype(int).tolist()

    # EMAs: 9, 20, 50, 100, 200
    ema_9 = close.ewm(span=9, adjust=False).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_100 = close.ewm(span=100, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean()

    # RSI 14 (Wilder smoothing — matches TradingView)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder_rma(gain, 14)
    avg_loss = _wilder_rma(loss, 14)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0.0, 100.0).where(~(avg_gain.eq(0.0) & avg_loss.eq(0.0)), 50.0)

    # MACD (12, 26, 9)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # Bollinger Bands (20, 2.0)
    bb_mid = close.rolling(window=20, min_periods=20).mean()
    bb_std = close.rolling(window=20, min_periods=20).std(ddof=0)
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std
    bb_bw = ((bb_upper - bb_lower) / bb_mid.replace(0.0, np.nan)) * 100.0
    bb_pct_b = (close - bb_lower) / (bb_upper - bb_lower).replace(0.0, np.nan)

    # ATR 14 (Wilder)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = _wilder_rma(tr, 14)

    # ADX 14 (+DI, -DI)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm_s = pd.Series(plus_dm, index=df.index)
    minus_dm_s = pd.Series(minus_dm, index=df.index)
    tr_rma = _wilder_rma(tr, 14).replace(0.0, np.nan)
    plus_di = 100.0 * (_wilder_rma(plus_dm_s, 14) / tr_rma)
    minus_di = 100.0 * (_wilder_rma(minus_dm_s, 14) / tr_rma)
    dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan))
    adx = _wilder_rma(dx.fillna(0.0), 14)

    # Stochastic (14, 3, 3)
    lowest_14 = low.rolling(window=14, min_periods=14).min()
    highest_14 = high.rolling(window=14, min_periods=14).max()
    raw_k = 100.0 * (close - lowest_14) / (highest_14 - lowest_14).replace(0.0, np.nan)
    stoch_k = raw_k.rolling(window=3, min_periods=1).mean()
    stoch_d = stoch_k.rolling(window=3, min_periods=1).mean()

    # Session-anchored UTC intraday VWAP (applicable for M1, M5, M15, M30, H1)
    vwap_applicable = timeframe in ("M1", "M5", "M15", "M30", "H1")
    vwap = pd.Series(np.nan, index=df.index, dtype=float)
    if vwap_applicable:
        typical = (high + low + close) / 3.0
        eff_vol = volume.where(volume > 0.0, 0.0)
        if float(eff_vol.sum()) > 0.0:
            day_keys = [
                datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d")
                for t in times
            ]
            day_series = pd.Series(day_keys, index=df.index)
            cum_pv = (typical * eff_vol).groupby(day_series).cumsum()
            cum_v = eff_vol.groupby(day_series).cumsum().replace(0.0, np.nan)
            vwap = cum_pv / cum_v
        else:
            vwap_applicable = False

    return {
        "times": times,
        "ema_9": ema_9,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_100": ema_100,
        "ema_200": ema_200,
        "rsi": rsi,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "bb_upper": bb_upper,
        "bb_mid": bb_mid,
        "bb_lower": bb_lower,
        "bb_bw": bb_bw,
        "bb_pct_b": bb_pct_b,
        "atr": atr,
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "vwap": vwap,
        "vwap_applicable": vwap_applicable,
    }


def _detect_rsi_divergence(df: pd.DataFrame, rsi: pd.Series) -> Optional[str]:
    if len(df) < 30:
        return None
    window = min(35, len(df) - 1)
    sub_low = df["low"].iloc[-window:].values
    sub_high = df["high"].iloc[-window:].values
    sub_rsi = rsi.iloc[-window:].values

    # Find local pivot lows (window 2 on each side)
    low_pivots: List[int] = []
    high_pivots: List[int] = []
    for i in range(2, len(sub_low) - 2):
        if np.isnan(sub_rsi[i]):
            continue
        if sub_low[i] <= sub_low[i - 1] and sub_low[i] <= sub_low[i - 2] and sub_low[i] <= sub_low[i + 1] and sub_low[i] <= sub_low[i + 2]:
            low_pivots.append(i)
        if sub_high[i] >= sub_high[i - 1] and sub_high[i] >= sub_high[i - 2] and sub_high[i] >= sub_high[i + 1] and sub_high[i] >= sub_high[i + 2]:
            high_pivots.append(i)

    # Regular Bullish Divergence: lower price low + higher RSI low (recent)
    if len(low_pivots) >= 2:
        p1, p2 = low_pivots[-2], low_pivots[-1]
        if p2 >= len(sub_low) - 10 and (sub_low[p2] < sub_low[p1] * 0.9998) and (sub_rsi[p2] > sub_rsi[p1] + 2.5) and sub_rsi[p1] < 45:
            return "BULLISH_DIVERGENCE"

    # Regular Bearish Divergence: higher price high + lower RSI high (recent)
    if len(high_pivots) >= 2:
        p1, p2 = high_pivots[-2], high_pivots[-1]
        if p2 >= len(sub_high) - 10 and (sub_high[p2] > sub_high[p1] * 1.0002) and (sub_rsi[p2] < sub_rsi[p1] - 2.5) and sub_rsi[p1] > 55:
            return "BEARISH_DIVERGENCE"

    return None


def extract_indicator_snapshot(
    df: pd.DataFrame, series: Dict[str, Any], timeframe: Timeframe
) -> Tuple[EmaValues, RsiValues, MacdValues, BollingerValues, AtrValues, AdxValues, StochasticValues, VwapValues]:
    n = len(df)
    last_close = float(df["close"].iloc[-1])

    # EMA snapshot
    e9 = _safe_float(series["ema_9"].iloc[-1], 3)
    e20 = _safe_float(series["ema_20"].iloc[-1], 3)
    e50 = _safe_float(series["ema_50"].iloc[-1], 3)
    e100 = _safe_float(series["ema_100"].iloc[-1], 3)
    e200 = _safe_float(series["ema_200"].iloc[-1], 3)

    alignment = "MIXED"
    if all(v is not None for v in (e9, e20, e50, e100, e200)):
        if last_close > e9 > e20 > e50 > e100 > e200:
            alignment = "STRONG_BULLISH"
        elif last_close < e9 < e20 < e50 < e100 < e200:
            alignment = "STRONG_BEARISH"
        elif last_close > e20 and e9 > e20 and e20 > e50:
            alignment = "BULLISH"
        elif last_close < e20 and e9 < e20 and e20 < e50:
            alignment = "BEARISH"

    ema_model = EmaValues(
        ema_9=e9,
        ema_20=e20,
        ema_50=e50,
        ema_100=e100,
        ema_200=e200,
        ema_200_warmed=n >= 200,
        bars_used=n,
        alignment=alignment,
        price_vs_ema200_usd=round(last_close - e200, 2) if e200 is not None else None,
    )

    # RSI snapshot
    rsi_val = _safe_float(series["rsi"].iloc[-1], 2)
    rsi_prev = _safe_float(series["rsi"].iloc[-2], 2) if n >= 2 else None
    rsi_zone = "NEUTRAL"
    if rsi_val is not None:
        if rsi_val >= 70:
            rsi_zone = "OVERBOUGHT"
        elif rsi_val >= 55:
            rsi_zone = "BULLISH_MOMENTUM"
        elif rsi_val <= 30:
            rsi_zone = "OVERSOLD"
        elif rsi_val <= 45:
            rsi_zone = "BEARISH_MOMENTUM"

    rsi_slope = "FLAT"
    if rsi_val is not None and rsi_prev is not None:
        if rsi_val - rsi_prev > 0.6:
            rsi_slope = "RISING"
        elif rsi_prev - rsi_val > 0.6:
            rsi_slope = "FALLING"

    rsi_model = RsiValues(
        value=rsi_val,
        previous=rsi_prev,
        zone=rsi_zone,
        slope=rsi_slope,
        divergence=_detect_rsi_divergence(df, series["rsi"]),
    )

    # MACD snapshot
    m_line = _safe_float(series["macd_line"].iloc[-1], 3)
    m_sig = _safe_float(series["macd_signal"].iloc[-1], 3)
    m_hist = _safe_float(series["macd_hist"].iloc[-1], 3)
    m_prev_hist = _safe_float(series["macd_hist"].iloc[-2], 3) if n >= 2 else None
    m_prev_line = _safe_float(series["macd_line"].iloc[-2], 3) if n >= 2 else None
    m_prev_sig = _safe_float(series["macd_signal"].iloc[-2], 3) if n >= 2 else None

    m_cross = None
    if all(v is not None for v in (m_line, m_sig, m_prev_line, m_prev_sig)):
        if m_prev_line <= m_prev_sig and m_line > m_sig:
            m_cross = "BULLISH_CROSS"
        elif m_prev_line >= m_prev_sig and m_line < m_sig:
            m_cross = "BEARISH_CROSS"

    m_state = "NEUTRAL"
    if m_hist is not None and m_prev_hist is not None:
        if m_hist > 0:
            m_state = "EXPANDING_BULLISH" if m_hist >= m_prev_hist else "FADING_BULLISH"
        elif m_hist < 0:
            m_state = "EXPANDING_BEARISH" if m_hist <= m_prev_hist else "FADING_BEARISH"

    macd_model = MacdValues(
        macd=m_line,
        signal=m_sig,
        histogram=m_hist,
        previous_histogram=m_prev_hist,
        crossover=m_cross,
        momentum_state=m_state,
    )

    # Bollinger Bands snapshot
    bb_u = _safe_float(series["bb_upper"].iloc[-1], 3)
    bb_m = _safe_float(series["bb_mid"].iloc[-1], 3)
    bb_l = _safe_float(series["bb_lower"].iloc[-1], 3)
    bb_bw = _safe_float(series["bb_bw"].iloc[-1], 3)
    bb_pb = _safe_float(series["bb_pct_b"].iloc[-1], 3)

    bw_window = series["bb_bw"].dropna().tail(50)
    squeeze = False
    if len(bw_window) >= 15 and bb_bw is not None:
        squeeze = bb_bw <= float(np.percentile(bw_window.values, 20))

    bb_pos = "MIDDLE"
    if all(v is not None for v in (bb_u, bb_m, bb_l)):
        if last_close > bb_u:
            bb_pos = "ABOVE_UPPER"
        elif last_close < bb_l:
            bb_pos = "BELOW_LOWER"
        elif last_close >= bb_m:
            bb_pos = "UPPER_HALF"
        else:
            bb_pos = "LOWER_HALF"

    bb_model = BollingerValues(
        upper=bb_u,
        middle=bb_m,
        lower=bb_l,
        bandwidth_pct=bb_bw,
        percent_b=bb_pb,
        squeeze=squeeze,
        position=bb_pos,
    )

    # ATR snapshot & volatility regime
    atr_val = _safe_float(series["atr"].iloc[-1], 3)
    atr_pct = round((atr_val / last_close) * 100.0, 4) if (atr_val is not None and last_close > 0) else None
    atr_hist = series["atr"].dropna().tail(50)
    baseline = _safe_float(atr_hist.mean(), 3) if len(atr_hist) >= 10 else atr_val
    ratio = round(atr_val / baseline, 2) if (atr_val is not None and baseline and baseline > 0) else 1.0

    if ratio >= 1.85:
        regime = "EXTREME"
    elif ratio >= 1.30:
        regime = "HIGH"
    elif ratio <= 0.72:
        regime = "LOW"
    else:
        regime = "NORMAL"

    atr_model = AtrValues(
        value=atr_val,
        percent_of_price=atr_pct,
        baseline_avg=baseline,
        ratio_to_baseline=ratio,
        regime=regime,
    )

    # ADX snapshot
    adx_val = _safe_float(series["adx"].iloc[-1], 2)
    p_di = _safe_float(series["plus_di"].iloc[-1], 2)
    m_di = _safe_float(series["minus_di"].iloc[-1], 2)
    t_str = "WEAK"
    if adx_val is not None:
        if adx_val < 15:
            t_str = "ABSENT"
        elif adx_val < 20:
            t_str = "WEAK"
        elif adx_val < 30:
            t_str = "MODERATE"
        elif adx_val < 45:
            t_str = "STRONG"
        else:
            t_str = "EXTREME"

    adx_model = AdxValues(
        adx=adx_val,
        plus_di=p_di,
        minus_di=m_di,
        trend_strength=t_str,
    )

    # Stochastic snapshot
    sk = _safe_float(series["stoch_k"].iloc[-1], 2)
    sd = _safe_float(series["stoch_d"].iloc[-1], 2)
    sk_prev = _safe_float(series["stoch_k"].iloc[-2], 2) if n >= 2 else None
    sd_prev = _safe_float(series["stoch_d"].iloc[-2], 2) if n >= 2 else None
    s_zone = "NEUTRAL"
    if sk is not None:
        if sk >= 80:
            s_zone = "OVERBOUGHT"
        elif sk <= 20:
            s_zone = "OVERSOLD"
    s_cross = None
    if all(v is not None for v in (sk, sd, sk_prev, sd_prev)):
        if sk_prev <= sd_prev and sk > sd:
            s_cross = "BULLISH_CROSS"
        elif sk_prev >= sd_prev and sk < sd:
            s_cross = "BEARISH_CROSS"

    stoch_model = StochasticValues(k=sk, d=sd, zone=s_zone, crossover=s_cross)

    # VWAP snapshot
    vwap_applicable = bool(series.get("vwap_applicable", False))
    vwap_val = _safe_float(series["vwap"].iloc[-1], 3) if vwap_applicable else None
    vwap_dist = round(last_close - vwap_val, 3) if vwap_val is not None else None
    vwap_pos = "N/A"
    if vwap_val is not None and atr_val:
        if abs(last_close - vwap_val) <= 0.12 * atr_val:
            vwap_pos = "AT_VWAP"
        elif last_close > vwap_val:
            vwap_pos = "ABOVE"
        else:
            vwap_pos = "BELOW"
    elif vwap_val is not None:
        vwap_pos = "ABOVE" if last_close > vwap_val else "BELOW"

    vwap_model = VwapValues(
        value=vwap_val,
        applicable=vwap_applicable and vwap_val is not None,
        distance_usd=vwap_dist,
        position=vwap_pos,
    )

    return ema_model, rsi_model, macd_model, bb_model, atr_model, adx_model, stoch_model, vwap_model


def format_chart_overlays(series: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize indicator time-series into TradingView Lightweight Charts {time, value} arrays."""
    if not series:
        return {}
    times: List[int] = series["times"]

    def _pack(s: pd.Series, digits: int = 3) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        vals = s.values
        for t, v in zip(times, vals):
            if v is not None and not np.isnan(v) and not np.isinf(v):
                out.append({"time": int(t), "value": round(float(v), digits)})
        return out

    return {
        "ema_9": _pack(series["ema_9"], 3),
        "ema_20": _pack(series["ema_20"], 3),
        "ema_50": _pack(series["ema_50"], 3),
        "ema_100": _pack(series["ema_100"], 3),
        "ema_200": _pack(series["ema_200"], 3),
        "bb_upper": _pack(series["bb_upper"], 3),
        "bb_middle": _pack(series["bb_mid"], 3),
        "bb_lower": _pack(series["bb_lower"], 3),
        "vwap": _pack(series["vwap"], 3) if series.get("vwap_applicable") else [],
        "rsi_14": _pack(series["rsi"], 2),
        "macd_line": _pack(series["macd_line"], 3),
        "macd_signal": _pack(series["macd_signal"], 3),
        "macd_hist": _pack(series["macd_hist"], 3),
    }
