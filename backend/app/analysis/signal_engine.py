from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.analysis.ai_explainer import build_ai_explanation
from app.analysis.risk_calculator import calculate_smart_risk_plan
from app.config import settings
from app.market_data.base import utc_now_iso
from app.schemas import (
    FeedHealthResponse,
    LiveQuote,
    MtfSynthesis,
    RiskPlan,
    SignalAction,
    TradingSignal,
)


def evaluate_trading_signal(
    quote: Optional[LiveQuote],
    health: FeedHealthResponse,
    mtf: Optional[MtfSynthesis],
) -> TradingSignal:
    """
    Disciplined, evidence-based XAUUSD AI Signal Engine.
    - Returns exactly ONE primary action: BUY, SELL, or WAIT.
    - Never forces a trade when data is stale/disconnected, timeframes conflict,
      trend is choppy, price is overextended, or R:R < 1:2.0.
    """
    now_iso = utc_now_iso()
    uid = f"SIG-{uuid.uuid4().hex[:10].upper()}"

    # Gate 0: Require live verified market data and full multi-timeframe context
    if quote is None or mtf is None or health.status != "LIVE" or quote.status != "LIVE":
        reason_list = [
            f"Market data feed status is {health.status}: {health.message}",
            "Trading signals are strictly suspended unless verified real-time XAUUSD quotes are active.",
        ]
        explanation = build_ai_explanation(
            action="WAIT",
            quote=quote,
            health=health,
            mtf=mtf,
            risk_plan=None,
            confirmations=[],
            blockers=reason_list,
            confidence=0,
        )
        return TradingSignal(
            signal_uid=uid,
            action="WAIT",
            status="WAIT",
            confidence=0,
            setup_timeframe="M15",
            generated_at=now_iso,
            market_price=quote.mid if quote else 0.0,
            data_provider=quote.provider if quote else (health.active_quote_provider or "Unavailable"),
            feed_status=health.status,
            risk_plan=None,
            watchlist_levels=None,
            explanation=explanation,
        )

    h4 = mtf.timeframes.get("H4")
    h1 = mtf.timeframes.get("H1")
    m30 = mtf.timeframes.get("M30")
    m15 = mtf.timeframes.get("M15")
    m5 = mtf.timeframes.get("M5")
    m1 = mtf.timeframes.get("M1")
    d1 = mtf.timeframes.get("D1")

    if not all([h4, h1, m30, m15, m5]):
        blockers = ["Incomplete multi-timeframe candle history (awaiting H4/H1/M30/M15/M5 synchronization)."]
        explanation = build_ai_explanation(
            action="WAIT", quote=quote, health=health, mtf=mtf, risk_plan=None, confirmations=[], blockers=blockers, confidence=20
        )
        return TradingSignal(
            signal_uid=uid,
            action="WAIT",
            status="WAIT",
            confidence=20,
            setup_timeframe="M15",
            generated_at=now_iso,
            market_price=quote.mid,
            data_provider=quote.provider,
            feed_status=health.status,
            risk_plan=None,
            watchlist_levels=_build_watchlist(quote, mtf),
            explanation=explanation,
        )

    assert h4 and h1 and m30 and m15 and m5

    confirmations: List[str] = []
    blockers: List[str] = []

    # Candidate direction derived from H4 + H1 + M30 core trend
    htf_weighted = h4.trend_score * 0.42 + h1.trend_score * 0.36 + m30.trend_score * 0.22
    candidate_dir: Optional[str] = None
    if htf_weighted >= 16.0:
        candidate_dir = "BUY"
    elif htf_weighted <= -16.0:
        candidate_dir = "SELL"

    # Gate 1: Spread & provider integrity
    atr_m15 = m15.atr.value or 4.0
    if quote.spread > settings.max_normal_spread_usd or quote.spread > atr_m15 * 0.35:
        blockers.append(
            f"Spread is elevated (${quote.spread:.2f}, {quote.spread_bps:.1f} bps vs M15 ATR ${atr_m15:.2f}); "
            "execution slippage risk too high."
        )
    else:
        confirmations.append(f"Live spot spread is tight (${quote.spread:.2f} / {quote.spread_bps:.1f} bps via {quote.provider}).")

    if quote.provider_discrepancy_usd is not None and quote.provider_discrepancy_usd > 4.0:
        blockers.append(
            f"Cross-provider price discrepancy (${quote.provider_discrepancy_usd:.2f} between {quote.provider} "
            f"and {quote.secondary_provider}) exceeds safety threshold."
        )

    # Gate 2: Major HTF directional clarity & conflict check
    if candidate_dir is None:
        blockers.append(
            f"No decisive higher-timeframe directional bias (H4={h4.trend} {h4.trend_score:+.0f}, "
            f"H1={h1.trend} {h1.trend_score:+.0f}, M30={m30.trend} {m30.trend_score:+.0f})."
        )

    for conf in mtf.conflicts:
        if conf.severity == "HIGH":
            blockers.append(f"Timeframe conflict [{conf.code}]: {conf.description}")

    # Gate 3: Trend strength (ADX) & chop filter
    h1_adx = h1.adx.adx or 0.0
    m15_adx = m15.adx.adx or 0.0
    has_breakout = m15.breakout.status in ("BULLISH_BREAKOUT", "BEARISH_BREAKOUT")
    if h1_adx < 16.0 and m15_adx < 16.0 and not has_breakout:
        blockers.append(
            f"Trend strength is absent/choppy (H1 ADX {h1_adx:.1f}, M15 ADX {m15_adx:.1f}; minimum 16+ or confirmed breakout needed)."
        )
    elif max(h1_adx, m15_adx) >= 22.0:
        confirmations.append(f"Healthy trend strength confirmed (H1 ADX {h1_adx:.1f}, M15 ADX {m15_adx:.1f}).")

    # Gate 4: Direction-specific technical confluence scoring (calibrated base=18, realistic cap=85)
    confidence = 18.0
    risk_plan: Optional[RiskPlan] = None

    if candidate_dir in ("BUY", "SELL"):
        is_buy = candidate_dir == "BUY"
        expected_trend = "BULLISH" if is_buy else "BEARISH"
        opp_trend = "BEARISH" if is_buy else "BULLISH"

        # 4a. Higher timeframe alignment (H4, H1, M30)
        htf_matches = sum(1 for tf in (h4, h1, m30) if tf.trend == expected_trend)
        if htf_matches == 3:
            confidence += 22.0
            confirmations.append(
                f"Full higher-timeframe alignment: H4 ({h4.trend_score:+.0f}), H1 ({h1.trend_score:+.0f}), "
                f"and M30 ({m30.trend_score:+.0f}) are all {expected_trend}."
            )
        elif htf_matches == 2 and all(tf.trend != opp_trend for tf in (h4, h1, m30)):
            confidence += 14.0
            confirmations.append(
                f"Higher-timeframe bias favors {expected_trend} (2 of 3 core HTFs aligned with zero opposing trend)."
            )
        else:
            blockers.append(
                f"Insufficient higher-timeframe alignment for {candidate_dir} (H4={h4.trend}, H1={h1.trend}, M30={m30.trend})."
            )

        # 4b. M15 Setup Validation (closed candle)
        if m15.trend == expected_trend:
            confidence += 14.0
            confirmations.append(
                f"M15 closed-candle setup confirms {expected_trend} (EMA {m15.ema.alignment.replace('_', ' ')}, "
                f"structure {m15.structure.pattern.replace('_', '/')})."
            )
        elif m15.trend == "NEUTRAL":
            confidence += 2.0
            blockers.append(f"M15 trading setup is still NEUTRAL (score {m15.trend_score:+.0f}); awaiting directional confirmation.")
        else:
            blockers.append(f"M15 trading setup is {m15.trend} against {candidate_dir} bias.")

        # 4c. Strict M5 Entry Confirmation & M1 Precision (no weak NEUTRAL M5 loophole)
        if m5.trend == expected_trend:
            confidence += 10.0
            confirmations.append(f"M5 entry confirmation aligned {expected_trend} (RSI {m5.rsi.value}, MACD {m5.macd.momentum_state.replace('_', ' ')}).")
        else:
            blockers.append(
                f"M5 entry confirmation is {m5.trend} (score {m5.trend_score:+.0f}, RSI {m5.rsi.value}) — "
                f"strictly requires confirmed {expected_trend} M5 trend before {candidate_dir} entry."
            )

        if m1 is not None:
            if m1.trend == expected_trend:
                confidence += 6.0
                confirmations.append(f"M1 entry precision aligns {expected_trend} (RSI {m1.rsi.value}).")
            elif m1.trend == opp_trend:
                blockers.append(
                    f"M1 micro momentum ({m1.trend}, score {m1.trend_score:+.0f}) is currently pushing against {candidate_dir}; "
                    "wait for short-term bounce/pullback to exhaust."
                )

        # 4c-2. Opposing Momentum Veto (never sell into expanding bullish MACD or buy into expanding bearish MACD)
        if is_buy:
            if m15.macd.momentum_state == "EXPANDING_BEARISH" or m5.macd.momentum_state == "EXPANDING_BEARISH":
                blockers.append(
                    f"Opposing momentum veto: MACD is expanding bearishly (M15={m15.macd.momentum_state.replace('_', ' ')}, "
                    f"M5={m5.macd.momentum_state.replace('_', ' ')}) — wait for downside momentum to stall."
                )
            elif m15.macd.momentum_state == "FADING_BULLISH" and m15.rsi.slope == "FALLING":
                blockers.append("M15 bullish momentum is fading with falling RSI — avoid entering into a weakening push.")
        else:
            if m15.macd.momentum_state == "EXPANDING_BULLISH" or m5.macd.momentum_state == "EXPANDING_BULLISH":
                blockers.append(
                    f"Opposing momentum veto: MACD is expanding bullishly (M15={m15.macd.momentum_state.replace('_', ' ')}, "
                    f"M5={m5.macd.momentum_state.replace('_', ' ')}) — do not sell into an active upward bounce."
                )
            elif m15.macd.momentum_state == "FADING_BEARISH" and m15.rsi.slope == "RISING":
                blockers.append("M15 bearish momentum is fading with rising RSI — avoid selling into a short-term rebound.")

        # 4c-3. Opposing Reversal Candlestick Pattern Veto
        opposing_patterns = [
            p for p in (m15.patterns + m5.patterns)
            if p.bias == opp_trend and p.strength in ("HIGH", "MEDIUM")
        ]
        if opposing_patterns:
            p0 = opposing_patterns[0]
            blockers.append(
                f"Opposing reversal price action ({p0.name}): {p0.description} Stand aside until reversal pressure clears."
            )

        # 4c-4. Room-to-Run & Range-Position Guard (never sell directly into support or buy directly into resistance)
        confirmed_dir_breakout = (
            (is_buy and m15.breakout.status == "BULLISH_BREAKOUT")
            or ((not is_buy) and m15.breakout.status == "BEARISH_BREAKOUT")
        )
        if not confirmed_dir_breakout:
            nearest_sup = m15.support_levels[0].price if m15.support_levels else m15.structure.last_swing_low
            nearest_res = m15.resistance_levels[0].price if m15.resistance_levels else m15.structure.last_swing_high

            if is_buy and nearest_res is not None and nearest_res > quote.mid:
                dist_res = nearest_res - quote.mid
                if dist_res <= atr_m15 * 0.70:
                    blockers.append(
                        f"Buying too close to resistance (${nearest_res:,.2f}, only ${dist_res:.2f} / {dist_res/atr_m15:.2f}x ATR overhead) — "
                        "wait for a pullback to support/EMA or a confirmed candle close above resistance."
                    )
            if (not is_buy) and nearest_sup is not None and nearest_sup < quote.mid:
                dist_sup = quote.mid - nearest_sup
                if dist_sup <= atr_m15 * 0.70:
                    blockers.append(
                        f"Selling too close to support floor (${nearest_sup:,.2f}, only ${dist_sup:.2f} / {dist_sup/atr_m15:.2f}x ATR below) — "
                        "avoid selling at the bottom of a range; wait for a pullback to resistance/EMA or confirmed breakdown below support."
                    )

            # Active range location guard (avoid selling bottom 35% or buying top 35% of active S/R range)
            if (
                nearest_sup is not None
                and nearest_res is not None
                and nearest_sup < quote.mid < nearest_res
                and (nearest_res - nearest_sup) >= atr_m15 * 0.85
            ):
                range_pos = (quote.mid - nearest_sup) / (nearest_res - nearest_sup)
                if (not is_buy) and range_pos < 0.35:
                    blockers.append(
                        f"Poor SELL location: price sits in the bottom {range_pos*100:.0f}% of the active M15 range "
                        f"(${nearest_sup:,.2f}–${nearest_res:,.2f}). Wait for a pullback rally or clean support breakdown."
                    )
                elif is_buy and range_pos > 0.65:
                    blockers.append(
                        f"Poor BUY location: price sits in the top {(1-range_pos)*100:.0f}% of the active M15 range "
                        f"(${nearest_sup:,.2f}–${nearest_res:,.2f}). Wait for a dip toward support or clean resistance breakout."
                    )

        # 4d. RSI Exhaustion & Divergence Guard (never chase climax extremes)
        m15_rsi = m15.rsi.value or 50.0
        if is_buy and m15_rsi >= 75.0:
            blockers.append(f"M15 RSI is overbought ({m15_rsi:.1f} >= 75) — chasing extended upside risks sharp pullback.")
        elif (not is_buy) and m15_rsi <= 25.0:
            blockers.append(f"M15 RSI is oversold ({m15_rsi:.1f} <= 25) — chasing extended downside risks snapback bounce.")
        elif (is_buy and 48.0 <= m15_rsi <= 68.0) or ((not is_buy) and 32.0 <= m15_rsi <= 52.0):
            confidence += 5.0
            confirmations.append(f"M15 RSI ({m15_rsi:.1f}) sits in healthy momentum zone without exhaustion.")

        if is_buy and m15.rsi.divergence == "BEARISH_DIVERGENCE":
            blockers.append("Bearish RSI divergence detected on M15 — upside momentum weakening.")
        elif (not is_buy) and m15.rsi.divergence == "BULLISH_DIVERGENCE":
            blockers.append("Bullish RSI divergence detected on M15 — downside momentum weakening.")

        # 4e. Overextension from EMA 20 guard
        if m15.ema.ema_20 is not None:
            dist_ema20 = quote.mid - m15.ema.ema_20
            if (is_buy and dist_ema20 > atr_m15 * 2.1) or ((not is_buy) and -dist_ema20 > atr_m15 * 2.1):
                blockers.append(
                    f"Price (${quote.mid:.2f}) is overextended ${abs(dist_ema20):.2f} ({abs(dist_ema20)/atr_m15:.1f}x ATR) "
                    f"away from M15 EMA20 (${m15.ema.ema_20:.2f}); wait for pullback."
                )

        # 4f. False breakout / opposing structural trap guard
        if is_buy and m15.breakout.status == "BULLISH_FALSE_BREAKOUT":
            blockers.append(f"Trap warning: {m15.breakout.description}")
        elif (not is_buy) and m15.breakout.status == "BEARISH_FALSE_BREAKOUT":
            blockers.append(f"Trap warning: {m15.breakout.description}")
        elif is_buy and m15.breakout.status in ("BULLISH_BREAKOUT", "BEARISH_FALSE_BREAKOUT"):
            confidence += 5.0
            confirmations.append(m15.breakout.description)
        elif (not is_buy) and m15.breakout.status in ("BEARISH_BREAKOUT", "BULLISH_FALSE_BREAKOUT"):
            confidence += 5.0
            confirmations.append(m15.breakout.description)

        # 4g. VWAP & Candlestick confirmation bonus
        if m15.vwap.applicable:
            if (is_buy and m15.vwap.position == "ABOVE") or ((not is_buy) and m15.vwap.position == "BELOW"):
                confidence += 4.0
                confirmations.append(f"Price is {m15.vwap.position} intraday session VWAP (${m15.vwap.value:.2f}).")

        aligned_patterns = [p for p in (m15.patterns + m5.patterns) if p.bias == expected_trend]
        if aligned_patterns:
            confidence += 4.0
            confirmations.append(f"Price action confirms: {aligned_patterns[0].name} ({aligned_patterns[0].description})")

        # 4h. Volatility extreme guard
        if m15.atr.regime == "EXTREME":
            confidence -= 10.0
            blockers.append(
                f"Extreme volatility regime on M15 (ATR ${atr_m15:.2f}, {m15.atr.ratio_to_baseline:.2f}x normal baseline) — "
                "elevated stop-sweep risk."
            )

        # 4i. D1 macro alignment adjustment
        if d1 is not None:
            if d1.trend == expected_trend:
                confidence += 5.0
                confirmations.append(f"D1 macro trend supports {expected_trend} bias (score {d1.trend_score:+.0f}).")
            elif d1.trend == opp_trend:
                confidence -= 6.0

        # 4j. Smart SL & TP Risk Plan calculation + 1:2 R:R Gate
        risk_plan = calculate_smart_risk_plan(
            direction=candidate_dir,  # type: ignore[arg-type]
            quote=quote,
            mtf=mtf,
            min_rr=settings.min_risk_reward,
        )
        if not risk_plan.meets_min_rr:
            blockers.append(
                f"Risk-to-Reward gate failed (TP2 R:R {risk_plan.rr_tp2:.2f} vs minimum 1:{settings.min_risk_reward:.1f} "
                "or major opposing S/R directly blocks the trade path)."
            )
        else:
            confirmations.append(
                f"Risk-to-Reward validated: 1:{risk_plan.rr_tp1:.2f} (TP1), 1:{risk_plan.rr_tp2:.2f} (TP2), "
                f"1:{risk_plan.rr_tp3:.2f} (TP3) with ${risk_plan.risk_usd:.2f} defined stop risk."
            )

    confidence_int = int(round(max(5.0, min(85.0, confidence))))

    # Final Disciplined Decision
    if candidate_dir in ("BUY", "SELL") and not blockers and confidence_int >= settings.signal_min_confidence and risk_plan is not None:
        action: SignalAction = candidate_dir  # type: ignore[assignment]
        final_plan: Optional[RiskPlan] = risk_plan
        status_str = "ACTIVE"
    else:
        action = "WAIT"
        final_plan = None
        status_str = "WAIT"
        # Cap WAIT confidence display so user clearly sees setup readiness score
        if blockers:
            confidence_int = min(confidence_int, max(15, 58 - len(blockers) * 7))

    explanation = build_ai_explanation(
        action=action,
        quote=quote,
        health=health,
        mtf=mtf,
        risk_plan=final_plan,
        confirmations=confirmations,
        blockers=blockers,
        confidence=confidence_int,
    )

    return TradingSignal(
        signal_uid=uid,
        action=action,
        status=status_str,
        confidence=confidence_int,
        setup_timeframe="M15",
        generated_at=now_iso,
        market_price=quote.mid,
        data_provider=quote.provider,
        feed_status=health.status,
        risk_plan=final_plan,
        watchlist_levels=_build_watchlist(quote, mtf),
        explanation=explanation,
    )


def _build_watchlist(quote: LiveQuote, mtf: MtfSynthesis) -> Dict[str, Any]:
    """Provide objective reference levels when action is WAIT (explicitly NOT an active trade signal)."""
    m15 = mtf.timeframes.get("M15") or mtf.timeframes.get("H1")
    h1 = mtf.timeframes.get("H1") or m15
    if not m15 or not h1:
        return {}
    res = (m15.resistance_levels or h1.resistance_levels)
    sup = (m15.support_levels or h1.support_levels)
    return {
        "note": "Reference market levels to watch — NOT an active trade recommendation.",
        "bullish_breakout_trigger": res[0].price if res else None,
        "bearish_breakdown_trigger": sup[0].price if sup else None,
        "m15_ema20": m15.ema.ema_20,
        "h1_ema50": h1.ema.ema_50,
        "m15_atr": m15.atr.value,
    }
