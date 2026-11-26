from __future__ import annotations

from typing import List, Literal, Optional

from app.config import settings
from app.schemas import (
    LevelRationale,
    LiveQuote,
    MtfSynthesis,
    RiskPlan,
    SupportResistanceLevel,
)


def calculate_smart_risk_plan(
    direction: Literal["BUY", "SELL"],
    quote: LiveQuote,
    mtf: MtfSynthesis,
    min_rr: Optional[float] = None,
) -> RiskPlan:
    """
    Smart SL & TP1/TP2/TP3 calculator grounded in:
    - ATR (M15 primary + H1 structural guard)
    - Market structure (recent swing highs/lows)
    - Support & Resistance clusters
    - Volatility regime adjustment
    - Default minimum Risk-to-Reward >= 1:2.0 (evaluated at TP2)
    """
    min_rr_target = min_rr if min_rr is not None else settings.min_risk_reward

    m15 = mtf.timeframes.get("M15") or mtf.timeframes.get("H1")
    h1 = mtf.timeframes.get("H1") or m15
    m5 = mtf.timeframes.get("M5") or m15
    assert m15 is not None and h1 is not None and m5 is not None

    atr_m15 = m15.atr.value or max(quote.mid * 0.0012, 3.0)
    atr_h1 = h1.atr.value or atr_m15 * 1.8
    regime = m15.atr.regime

    # Volatility multiplier for stop buffer & entry zone width
    vol_buffer_mult = {"LOW": 0.25, "NORMAL": 0.35, "HIGH": 0.50, "EXTREME": 0.65}.get(regime, 0.35)
    zone_half = max(round(atr_m15 * 0.20, 2), round(quote.spread * 1.5, 2), 0.40)

    # Executable reference price (Ask for BUY, Bid for SELL)
    exec_price = quote.ask if direction == "BUY" else quote.bid

    # Entry Zone: anchor on live executable price, gently biased toward EMA9/20 pullback if very close
    entry_anchor = exec_price
    ema20_m5 = m5.ema.ema_20
    entry_reason_extra = "aligned with live spot liquidity"
    if ema20_m5 is not None and abs(exec_price - ema20_m5) <= atr_m15 * 0.55:
        if direction == "BUY" and ema20_m5 < exec_price:
            entry_anchor = round((exec_price * 0.7) + (ema20_m5 * 0.3), 2)
            entry_reason_extra = f"anchored between live Ask (${exec_price:.2f}) and M5 EMA20 pullback (${ema20_m5:.2f})"
        elif direction == "SELL" and ema20_m5 > exec_price:
            entry_anchor = round((exec_price * 0.7) + (ema20_m5 * 0.3), 2)
            entry_reason_extra = f"anchored between live Bid (${exec_price:.2f}) and M5 EMA20 pullback (${ema20_m5:.2f})"
    else:
        entry_anchor = round(exec_price, 2)

    entry_low = round(entry_anchor - zone_half, 2)
    entry_high = round(entry_anchor + zone_half, 2)

    # Gather structural S/R from M15 + H1
    all_supports: List[SupportResistanceLevel] = list(m15.support_levels) + list(h1.support_levels)
    all_resistances: List[SupportResistanceLevel] = list(m15.resistance_levels) + list(h1.resistance_levels)

    min_risk = max(round(atr_m15 * 0.90, 2), 3.0)
    max_risk = max(round(min(atr_m15 * 2.6, atr_h1 * 1.55), 2), min_risk + 2.0)
    buffer = round(atr_m15 * vol_buffer_mult, 2)

    if direction == "BUY":
        # Candidate structural stop anchors below entry: M15 swing low, M5 swing low, nearest support
        candidates: List[tuple] = []
        if m15.structure.last_swing_low is not None and m15.structure.last_swing_low < entry_anchor:
            candidates.append((m15.structure.last_swing_low - buffer, f"M15 swing low (${m15.structure.last_swing_low:.2f}) minus {vol_buffer_mult:.2f}x ATR (${buffer:.2f}) buffer"))
        if m5.structure.last_swing_low is not None and m5.structure.last_swing_low < entry_anchor:
            candidates.append((m5.structure.last_swing_low - buffer, f"M5 swing low (${m5.structure.last_swing_low:.2f}) minus ATR buffer (${buffer:.2f})"))
        near_sups = sorted([s for s in all_supports if s.price < entry_anchor], key=lambda s: entry_anchor - s.price)
        if near_sups:
            s0 = near_sups[0]
            candidates.append((s0.price - buffer, f"nearest support (${s0.price:.2f}, {s0.touches} touches) minus ATR buffer (${buffer:.2f})"))

        # Pick first structural candidate whose risk falls within [min_risk, max_risk]
        chosen_sl: Optional[float] = None
        sl_reason = ""
        for sl_price, reason in candidates:
            dist = entry_anchor - sl_price
            if min_risk <= dist <= max_risk:
                chosen_sl = round(sl_price, 2)
                sl_reason = f"Placed below {reason} to invalidate bullish structure on breakdown."
                break
        if chosen_sl is None:
            # Clamp to volatility-safe ATR stop
            atr_sl_dist = round(max(min_risk, min(max_risk, atr_m15 * (1.35 + vol_buffer_mult))), 2)
            chosen_sl = round(entry_anchor - atr_sl_dist, 2)
            sl_reason = (
                f"Volatility-calibrated ATR stop ({atr_sl_dist:.2f} USD = {atr_sl_dist/atr_m15:.2f}x M15 ATR "
                f"in {regime} volatility) since nearby swing pivots were outside safe stop bounds."
            )

        risk_usd = round(max(0.5, entry_anchor - chosen_sl), 2)

        # Opposing resistance levels above entry
        opp_levels = sorted([r for r in all_resistances if r.price > entry_anchor + risk_usd * 0.8], key=lambda r: r.price)
        tp_pad = round(atr_m15 * 0.12, 2)

        # TP1: ~1.2R - 1.5R (or just ahead of first resistance inside that window)
        tp1_default = round(entry_anchor + risk_usd * 1.25, 2)
        tp1 = tp1_default
        tp1_reason = f"Conservative partial-profit target at 1.25R (+${risk_usd*1.25:.2f}) to lock gains and move SL to breakeven."
        for r in opp_levels:
            cand = round(r.price - tp_pad, 2)
            rr_c = (cand - entry_anchor) / risk_usd
            if 1.10 <= rr_c <= 1.65:
                tp1 = cand
                tp1_reason = f"Positioned ${tp_pad:.2f} ahead of resistance at ${r.price:.2f} ({r.touches} touches) for clean {rr_c:.2f}R partial fill."
                break

        # TP2: >= min_rr_target (default 2.0R), aligned to opposing resistance when within [2.0R, 2.75R]
        tp2_default = round(entry_anchor + risk_usd * max(min_rr_target, 2.1), 2)
        tp2 = tp2_default
        tp2_reason = f"Primary target enforcing >= 1:{min_rr_target:.1f} R:R (+${tp2 - entry_anchor:.2f}) aligned with M15/H1 trend extension."
        for r in opp_levels:
            cand = round(r.price - tp_pad, 2)
            rr_c = (cand - entry_anchor) / risk_usd
            if min_rr_target <= rr_c <= 2.80 and cand > tp1 + atr_m15 * 0.25:
                tp2 = cand
                tp2_reason = f"Aligned ahead of major resistance at ${r.price:.2f} (strength {r.strength}/5) delivering {rr_c:.2f}R."
                break

        # TP3: >= 3.0R structural runner
        tp3_default = round(entry_anchor + risk_usd * 3.2, 2)
        tp3 = tp3_default
        tp3_reason = f"Extended trend-continuation target at 3.20R (+${tp3 - entry_anchor:.2f}) for runner allocation."
        for r in opp_levels:
            cand = round(r.price - tp_pad, 2)
            rr_c = (cand - entry_anchor) / risk_usd
            if 2.90 <= rr_c <= 4.20 and cand > tp2 + atr_m15 * 0.40:
                tp3 = cand
                tp3_reason = f"Extended swing target just below upper H1 resistance at ${r.price:.2f} delivering {rr_c:.2f}R."
                break

        # Only block when a major multi-touch H1 resistance wall sits right in front of entry (< 0.70R)
        major_blocker = any(
            r.strength >= 5 and r.touches >= 4 and (r.price - entry_anchor) < risk_usd * 0.70
            for r in h1.resistance_levels
            if r.price > entry_anchor
        )
        rr1 = round((tp1 - entry_anchor) / risk_usd, 2)
        rr2 = round((tp2 - entry_anchor) / risk_usd, 2)
        rr3 = round((tp3 - entry_anchor) / risk_usd, 2)
        meets_min_rr = (rr2 >= min_rr_target) and (not major_blocker)

    else:  # SELL
        candidates = []
        if m15.structure.last_swing_high is not None and m15.structure.last_swing_high > entry_anchor:
            candidates.append((m15.structure.last_swing_high + buffer, f"M15 swing high (${m15.structure.last_swing_high:.2f}) plus {vol_buffer_mult:.2f}x ATR (${buffer:.2f}) buffer"))
        if m5.structure.last_swing_high is not None and m5.structure.last_swing_high > entry_anchor:
            candidates.append((m5.structure.last_swing_high + buffer, f"M5 swing high (${m5.structure.last_swing_high:.2f}) plus ATR buffer (${buffer:.2f})"))
        near_res = sorted([r for r in all_resistances if r.price > entry_anchor], key=lambda r: r.price - entry_anchor)
        if near_res:
            r0 = near_res[0]
            candidates.append((r0.price + buffer, f"nearest resistance (${r0.price:.2f}, {r0.touches} touches) plus ATR buffer (${buffer:.2f})"))

        chosen_sl = None
        sl_reason = ""
        for sl_price, reason in candidates:
            dist = sl_price - entry_anchor
            if min_risk <= dist <= max_risk:
                chosen_sl = round(sl_price, 2)
                sl_reason = f"Placed above {reason} to invalidate bearish structure on upside reclaim."
                break
        if chosen_sl is None:
            atr_sl_dist = round(max(min_risk, min(max_risk, atr_m15 * (1.35 + vol_buffer_mult))), 2)
            chosen_sl = round(entry_anchor + atr_sl_dist, 2)
            sl_reason = (
                f"Volatility-calibrated ATR stop (+${atr_sl_dist:.2f} = {atr_sl_dist/atr_m15:.2f}x M15 ATR "
                f"in {regime} volatility) since nearby swing highs were outside safe stop bounds."
            )

        risk_usd = round(max(0.5, chosen_sl - entry_anchor), 2)

        opp_levels = sorted([s for s in all_supports if s.price < entry_anchor - risk_usd * 0.8], key=lambda s: s.price, reverse=True)
        tp_pad = round(atr_m15 * 0.12, 2)

        tp1_default = round(entry_anchor - risk_usd * 1.25, 2)
        tp1 = tp1_default
        tp1_reason = f"Conservative partial-profit target at 1.25R (-${risk_usd*1.25:.2f}) to secure gains and move SL to breakeven."
        for s in opp_levels:
            cand = round(s.price + tp_pad, 2)
            rr_c = (entry_anchor - cand) / risk_usd
            if 1.10 <= rr_c <= 1.65:
                tp1 = cand
                tp1_reason = f"Positioned ${tp_pad:.2f} above support at ${s.price:.2f} ({s.touches} touches) for clean {rr_c:.2f}R partial fill."
                break

        tp2_default = round(entry_anchor - risk_usd * max(min_rr_target, 2.1), 2)
        tp2 = tp2_default
        tp2_reason = f"Primary target enforcing >= 1:{min_rr_target:.1f} R:R (-${entry_anchor - tp2:.2f}) aligned with downward M15/H1 impulse."
        for s in opp_levels:
            cand = round(s.price + tp_pad, 2)
            rr_c = (entry_anchor - cand) / risk_usd
            if min_rr_target <= rr_c <= 2.80 and cand < tp1 - atr_m15 * 0.25:
                tp2 = cand
                tp2_reason = f"Aligned above major support at ${s.price:.2f} (strength {s.strength}/5) delivering {rr_c:.2f}R."
                break

        tp3_default = round(entry_anchor - risk_usd * 3.2, 2)
        tp3 = tp3_default
        tp3_reason = f"Extended trend-continuation target at 3.20R (-${entry_anchor - tp3:.2f}) for runner allocation."
        for s in opp_levels:
            cand = round(s.price + tp_pad, 2)
            rr_c = (entry_anchor - cand) / risk_usd
            if 2.90 <= rr_c <= 4.20 and cand < tp2 - atr_m15 * 0.40:
                tp3 = cand
                tp3_reason = f"Extended swing target just above deeper H1 support at ${s.price:.2f} delivering {rr_c:.2f}R."
                break

        major_blocker = any(
            s.strength >= 5 and s.touches >= 4 and (entry_anchor - s.price) < risk_usd * 0.70
            for s in h1.support_levels
            if s.price < entry_anchor
        )
        rr1 = round((entry_anchor - tp1) / risk_usd, 2)
        rr2 = round((entry_anchor - tp2) / risk_usd, 2)
        rr3 = round((entry_anchor - tp3) / risk_usd, 2)
        meets_min_rr = (rr2 >= min_rr_target) and (not major_blocker)

    rationales = [
        LevelRationale(
            level_name="Entry Zone",
            price=entry_anchor,
            distance_usd=round(abs(entry_anchor - exec_price), 2),
            risk_reward=None,
            reason=f"Zone ${entry_low:.2f}–${entry_high:.2f} (±${zone_half:.2f} based on 0.20x M15 ATR), {entry_reason_extra}.",
        ),
        LevelRationale(
            level_name="Stop Loss",
            price=chosen_sl,
            distance_usd=risk_usd,
            risk_reward=1.0,
            reason=sl_reason,
        ),
        LevelRationale(
            level_name="Take Profit 1",
            price=tp1,
            distance_usd=round(abs(tp1 - entry_anchor), 2),
            risk_reward=rr1,
            reason=tp1_reason,
        ),
        LevelRationale(
            level_name="Take Profit 2 (Primary)",
            price=tp2,
            distance_usd=round(abs(tp2 - entry_anchor), 2),
            risk_reward=rr2,
            reason=tp2_reason,
        ),
        LevelRationale(
            level_name="Take Profit 3 (Runner)",
            price=tp3,
            distance_usd=round(abs(tp3 - entry_anchor), 2),
            risk_reward=rr3,
            reason=tp3_reason,
        ),
    ]

    return RiskPlan(
        direction=direction,
        entry_price=entry_anchor,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss=chosen_sl,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        risk_usd=risk_usd,
        reward_tp1_usd=round(abs(tp1 - entry_anchor), 2),
        reward_tp2_usd=round(abs(tp2 - entry_anchor), 2),
        reward_tp3_usd=round(abs(tp3 - entry_anchor), 2),
        rr_tp1=rr1,
        rr_tp2=rr2,
        rr_tp3=rr3,
        meets_min_rr=meets_min_rr,
        atr_reference=round(atr_m15, 2),
        volatility_regime=regime,
        rationales=rationales,
    )
