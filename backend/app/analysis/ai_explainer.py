from __future__ import annotations

from typing import List, Optional

from app.schemas import (
    AiExplanation,
    FeedHealthResponse,
    LiveQuote,
    MtfSynthesis,
    RiskPlan,
    SignalAction,
)


def build_ai_explanation(
    action: SignalAction,
    quote: Optional[LiveQuote],
    health: FeedHealthResponse,
    mtf: Optional[MtfSynthesis],
    risk_plan: Optional[RiskPlan],
    confirmations: List[str],
    blockers: List[str],
    confidence: int,
) -> AiExplanation:
    """
    Zero-hallucination structured market analysis explainer.
    Every price, indicator, timeframe bias, and invalidation level is strictly derived
    from verified backend calculations — never fabricated.
    """
    if quote is None or mtf is None or health.status != "LIVE":
        return AiExplanation(
            what_is_gold_doing=(
                f"Live XAUUSD telemetry is currently {health.status}. {health.message}"
            ),
            market_direction="Unavailable / Suspended pending live verified market feed.",
            decision_headline="WAIT — Live Market Data Required",
            why_decision=(
                "GOLD AI refuses to issue BUY or SELL recommendations on delayed, disconnected, "
                "or closed-market data and never substitutes simulated prices."
            ),
            confirmations=[],
            missing_or_warnings=blockers or [health.message],
            invalidation_conditions=["Resume analysis automatically once live verified quotes return."],
            when_to_avoid=[
                "Never trade when real-time pricing is delayed, disconnected, or during weekend rollover.",
            ],
            level_reasoning=[],
            engine_mode="Structured Quantitative AI Engine (Safety Lock Active)",
        )

    h4 = mtf.timeframes.get("H4")
    h1 = mtf.timeframes.get("H1")
    m30 = mtf.timeframes.get("M30")
    m15 = mtf.timeframes.get("M15")
    m5 = mtf.timeframes.get("M5")
    d1 = mtf.timeframes.get("D1")

    # 1. What is Gold doing right now?
    chg_txt = ""
    if quote.change_usd is not None and quote.change_percent is not None:
        chg_txt = f" ({quote.change_usd:+.2f} / {quote.change_percent:+.2f}% vs prior D1 close)"
    vol_txt = f"{m15.atr.regime.lower()} volatility (M15 ATR ${m15.atr.value:.2f})" if (m15 and m15.atr.value) else "active volatility"
    struct_txt = m15.structure.pattern.replace("_", "/") if m15 else "developing"
    brk_txt = m15.breakout.description if m15 else ""

    what_doing = (
        f"Spot Gold (XAUUSD) is trading at ${quote.mid:,.2f} (Bid ${quote.bid:,.2f} / Ask ${quote.ask:,.2f}, "
        f"spread ${quote.spread:.2f}){chg_txt} with {vol_txt}. "
        f"M15 structure shows {struct_txt}; {brk_txt}"
    )

    # 2. Current market direction
    dir_parts = []
    if d1:
        dir_parts.append(f"D1 Macro: {d1.trend}")
    if h4:
        dir_parts.append(f"H4 Major: {h4.trend}")
    if h1:
        dir_parts.append(f"H1 Main: {h1.trend}")
    if m30:
        dir_parts.append(f"M30 Confirm: {m30.trend}")
    if m15:
        dir_parts.append(f"M15 Setup: {m15.trend}")
    market_direction = (
        f"Overall Multi-Timeframe Bias: {mtf.overall_bias} "
        f"(Alignment {mtf.alignment_score:.0f}%, Weighted Score {mtf.weighted_score:+.1f}). "
        + " | ".join(dir_parts)
    )

    # 3. Why BUY / Why SELL / Why WAIT?
    if action == "BUY" and risk_plan is not None:
        decision_headline = f"BUY XAUUSD — High-Confluence Bullish Setup ({confidence}% Confidence)"
        why_decision = (
            f"BUY is recommended because multi-timeframe structure aligns bullishly across higher and intraday charts "
            f"(weighted score {mtf.weighted_score:+.1f}, {mtf.alignment_score:.0f}% alignment), momentum is constructive "
            f"without overbought exhaustion (M15 RSI {m15.rsi.value if m15 else 'N/A'}), and structural Stop Loss at "
            f"${risk_plan.stop_loss:,.2f} unlocks a clean 1:{risk_plan.rr_tp2:.2f} primary Risk-to-Reward to TP2 (${risk_plan.tp2:,.2f})."
        )
    elif action == "SELL" and risk_plan is not None:
        decision_headline = f"SELL XAUUSD — High-Confluence Bearish Setup ({confidence}% Confidence)"
        why_decision = (
            f"SELL is recommended because higher-timeframe and intraday trend structure align bearishly "
            f"(weighted score {mtf.weighted_score:+.1f}, {mtf.alignment_score:.0f}% alignment), downward momentum is active "
            f"without oversold exhaustion (M15 RSI {m15.rsi.value if m15 else 'N/A'}), and structural Stop Loss at "
            f"${risk_plan.stop_loss:,.2f} provides a validated 1:{risk_plan.rr_tp2:.2f} primary Risk-to-Reward to TP2 (${risk_plan.tp2:,.2f})."
        )
    else:
        decision_headline = f"WAIT — Capital Preservation Mode ({confidence}% Setup Readiness)"
        primary_blocker = blockers[0] if blockers else "Multi-timeframe confluence has not met the institutional threshold."
        why_decision = (
            f"WAIT is recommended to protect capital and avoid low-probability entries. "
            f"Primary reason: {primary_blocker} GOLD AI only triggers BUY or SELL when H4/H1/M30/M15/M5 confluence, "
            f"momentum, spread quality, and >= 1:2.0 Risk-to-Reward all validate simultaneously."
        )

    # 4. Invalidation Conditions
    invalidation_conditions: List[str] = []
    if action == "BUY" and risk_plan is not None:
        invalidation_conditions.append(
            f"Hard price invalidation: Any break below Stop Loss ${risk_plan.stop_loss:,.2f} invalidates the bullish swing structure."
        )
        if m15 and m15.ema.ema_50:
            invalidation_conditions.append(
                f"Momentum invalidation: M15 candle close below EMA 50 (${m15.ema.ema_50:,.2f}) with RSI dropping under 45."
            )
        invalidation_conditions.append(
            "HTF invalidation: H1 or M30 flipping to BEARISH before entry fills cancels the setup."
        )
    elif action == "SELL" and risk_plan is not None:
        invalidation_conditions.append(
            f"Hard price invalidation: Any break above Stop Loss ${risk_plan.stop_loss:,.2f} invalidates the bearish swing structure."
        )
        if m15 and m15.ema.ema_50:
            invalidation_conditions.append(
                f"Momentum invalidation: M15 candle close above EMA 50 (${m15.ema.ema_50:,.2f}) with RSI rising over 55."
            )
        invalidation_conditions.append(
            "HTF invalidation: H1 or M30 flipping to BULLISH before entry fills cancels the setup."
        )
    else:
        if m15 and m15.resistance_levels:
            invalidation_conditions.append(
                f"Watch for a clean M15 close above ${m15.resistance_levels[0].price:,.2f} with H1/M30 bullish alignment to unlock BUY setups."
            )
        if m15 and m15.support_levels:
            invalidation_conditions.append(
                f"Watch for a clean M15 close below ${m15.support_levels[0].price:,.2f} with H1/M30 bearish alignment to unlock SELL setups."
            )
        invalidation_conditions.append(
            "Stand aside until conflicting timeframes resolve into unified directional order flow."
        )

    # 5. When should you avoid entering?
    when_to_avoid: List[str] = []
    if blockers:
        when_to_avoid.extend(blockers[:3])
    if m15 and m15.atr.regime in ("HIGH", "EXTREME"):
        when_to_avoid.append(
            f"Elevated volatility ({m15.atr.regime}, M15 ATR ${m15.atr.value:.2f}): avoid market-chasing big expansion candles; wait for retests."
        )
    if m5 and m5.rsi.value is not None and (m5.rsi.value >= 72 or m5.rsi.value <= 28):
        when_to_avoid.append(
            f"Short-term M5 RSI is stretched ({m5.rsi.value:.1f}): avoid entering right into micro-exhaustion."
        )
    when_to_avoid.append(
        "Avoid entering immediately ahead of high-impact USD macro releases (CPI, NFP, FOMC) or if live spread spikes above $1.50."
    )
    if risk_plan is not None:
        when_to_avoid.append(
            f"Do not chase price outside the valid entry zone (${risk_plan.entry_zone_low:,.2f}–${risk_plan.entry_zone_high:,.2f}), which degrades Risk-to-Reward below 1:2.0."
        )

    # 6. Per-level SL / TP reasoning
    level_reasoning = [f"{r.level_name} (${r.price:,.2f}): {r.reason}" for r in risk_plan.rationales] if risk_plan else []

    return AiExplanation(
        what_is_gold_doing=what_doing,
        market_direction=market_direction,
        decision_headline=decision_headline,
        why_decision=why_decision,
        confirmations=confirmations,
        missing_or_warnings=blockers,
        invalidation_conditions=invalidation_conditions,
        when_to_avoid=when_to_avoid,
        level_reasoning=level_reasoning,
        engine_mode="Structured Quantitative AI Engine",
    )
