from __future__ import annotations

import json
import logging
import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.analysis.indicators import candles_to_df, compute_indicator_series
from app.backtesting.data_loader import load_historical_candles
from app.backtesting.metrics import calculate_performance_summary
from app.database import SessionLocal
from app.market_data.base import utc_now_iso
from app.models import BacktestRun, BacktestTrade
from app.schemas import (
    BacktestReport,
    BacktestRequest,
    BacktestRunSummaryItem,
    Candle,
    PerformanceTradeRecord,
    Timeframe,
)


logger = logging.getLogger("gold_ai.backtest_engine")


def _compute_causal_htf_trend(df: pd.DataFrame, htf_factor: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Strictly causal (zero-lookahead) higher-timeframe EMA/trend proxy derived from base candles.
    Uses completed rolling higher-timeframe closes (span scaled by htf_factor) so bar i ONLY
    sees data <= bar i.
    """
    close = df["close"].astype(float)
    e_fast = close.ewm(span=max(9 * htf_factor, 18), adjust=False).mean()
    e_mid = close.ewm(span=max(20 * htf_factor, 40), adjust=False).mean()
    e_slow = close.ewm(span=max(50 * htf_factor, 100), adjust=False).mean()

    htf_bull = ((close > e_mid) & (e_fast > e_mid) & (e_mid > e_slow)).values
    htf_bear = ((close < e_mid) & (e_fast < e_mid) & (e_mid < e_slow)).values
    return htf_bull, htf_bear


def run_walk_forward_backtest_on_candles(
    candles: List[Candle],
    request: BacktestRequest,
    dataset_label: str,
) -> BacktestReport:
    """
    Zero-lookahead walk-forward historical XAUUSD backtesting engine.
    - Signals evaluate strictly on closed candle i using causal indicators (EMA 9/20/50/100/200,
      RSI 14, MACD, ATR 14, ADX 14, Stochastic, Bollinger, higher-TF alignment, structural swings).
    - Entries fill at NEXT bar i+1 open plus realistic spread/2 and entry slippage.
    - Conservative intrabar collision rule: if SL and TP fall within the same candle range,
      SL is assumed to trigger first.
    - Every trade records spread + slippage trading costs, realized R, and exact timestamps.
    - Zero trade execution — purely analytical verification.
    """
    if len(candles) < 80:
        raise ValueError(f"Insufficient historical candles ({len(candles)}) — require at least 80 bars.")

    df = candles_to_df(candles)
    series = compute_indicator_series(df, request.timeframe)  # type: ignore[arg-type]

    opens = df["open"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    closes = df["close"].values.astype(float)
    times_iso = df["open_time_iso"].tolist()

    ema9 = series["ema_9"].values
    ema20 = series["ema_20"].values
    ema50 = series["ema_50"].values
    ema100 = series["ema_100"].values
    ema200 = series["ema_200"].values
    rsi = series["rsi"].values
    macd_hist = series["macd_hist"].values
    atr = series["atr"].values
    adx = series["adx"].values
    plus_di = series["plus_di"].values
    minus_di = series["minus_di"].values

    # Causal higher-timeframe trend filter (e.g. 4x base TF: H1 -> H4, M15 -> H1, H4 -> D1)
    htf_bull, htf_bear = _compute_causal_htf_trend(df, htf_factor=4)

    # Trailing rolling ATR baseline (50-bar mean) for volatility regime classification
    atr_s = pd.Series(atr)
    atr_baseline = atr_s.rolling(window=50, min_periods=14).mean().values

    # Trailing structural swing high/low (last 12 bars strictly <= i, zero lookahead)
    roll_swing_low = pd.Series(lows).rolling(window=12, min_periods=5).min().values
    roll_swing_high = pd.Series(highs).rolling(window=12, min_periods=5).max().values

    n = len(df)
    warmup = min(max(60, 120 if n > 260 else 55), n - 10)

    half_spread = request.spread_usd / 2.0
    slip = request.slippage_usd
    round_trip_spread = request.spread_usd
    round_trip_slippage = request.slippage_usd * 2.0
    total_cost_oz = round_trip_spread + round_trip_slippage

    equity = float(request.initial_balance)
    completed_trades: List[PerformanceTradeRecord] = []

    i = warmup
    trade_counter = 0
    cooldown_bars = 2

    while i < n - 2:
        # Ensure causal indicators are finite at bar i
        if (
            np.isnan(atr[i])
            or atr[i] <= 0
            or np.isnan(rsi[i])
            or np.isnan(adx[i])
            or np.isnan(ema200[i])
            or np.isnan(macd_hist[i])
            or np.isnan(macd_hist[i - 1])
        ):
            i += 1
            continue

        cur_close = closes[i]
        cur_atr = float(atr[i])
        cur_base = float(atr_baseline[i]) if not np.isnan(atr_baseline[i]) and atr_baseline[i] > 0 else cur_atr
        vol_ratio = cur_atr / cur_base

        # Spread / extreme whipsaw volatility guard (mirrors live Signal Engine)
        if request.spread_usd > cur_atr * 0.35 or vol_ratio >= 2.2:
            i += 1
            continue

        # Trend strength filter (ADX >= 18)
        if adx[i] < 18.0:
            i += 1
            continue

        # Evaluate directional confluence strictly at closed candle i
        ema_bull = cur_close > ema20[i] and ema9[i] > ema20[i] and ema20[i] > ema50[i]
        ema_bear = cur_close < ema20[i] and ema9[i] < ema20[i] and ema20[i] < ema50[i]
        macro_bull = cur_close > ema100[i] or ema50[i] > ema100[i]
        macro_bear = cur_close < ema100[i] or ema50[i] < ema100[i]

        di_bull = plus_di[i] > minus_di[i] + 1.5
        di_bear = minus_di[i] > plus_di[i] + 1.5

        mom_bull = (macd_hist[i] > 0 or macd_hist[i] > macd_hist[i - 1]) and (46.0 <= rsi[i] <= 71.0)
        mom_bear = (macd_hist[i] < 0 or macd_hist[i] < macd_hist[i - 1]) and (29.0 <= rsi[i] <= 54.0)

        # Avoid chasing price overextended > 1.9 ATR away from EMA 20
        dist_ema20 = cur_close - ema20[i]

        action: Optional[str] = None
        confidence = 60

        if htf_bull[i] and ema_bull and macro_bull and di_bull and mom_bull and dist_ema20 <= cur_atr * 1.9:
            action = "BUY"
            confidence = 65 + (8 if cur_close > ema200[i] else 0) + (7 if adx[i] >= 25 else 0) + (6 if macd_hist[i] > macd_hist[i - 1] else 0)
        elif htf_bear[i] and ema_bear and macro_bear and di_bear and mom_bear and (-dist_ema20) <= cur_atr * 1.9:
            action = "SELL"
            confidence = 65 + (8 if cur_close < ema200[i] else 0) + (7 if adx[i] >= 25 else 0) + (6 if macd_hist[i] < macd_hist[i - 1] else 0)

        if action is None:
            i += 1
            continue

        # Entry fills realistically on NEXT bar (i+1) open + spread/2 + entry slippage
        entry_bar = i + 1
        planned_entry = float(opens[entry_bar])
        vol_buf_mult = 0.50 if vol_ratio >= 1.30 else (0.25 if vol_ratio <= 0.72 else 0.35)
        buf = cur_atr * vol_buf_mult
        min_risk = max(cur_atr * 0.90, 3.0)
        max_risk = max(cur_atr * 2.50, min_risk + 2.0)

        if action == "BUY":
            effective_entry = planned_entry + half_spread + slip
            struct_sl = float(roll_swing_low[i]) - buf
            dist_sl = planned_entry - struct_sl
            if min_risk <= dist_sl <= max_risk:
                stop_loss = struct_sl
            else:
                stop_loss = planned_entry - max(min_risk, min(max_risk, cur_atr * (1.35 + vol_buf_mult)))
            risk_oz = max(effective_entry - stop_loss, 0.5)
            tp1 = planned_entry + (planned_entry - stop_loss) * 1.25
            tp2 = planned_entry + (planned_entry - stop_loss) * max(request.min_rr, 2.0)
            tp3 = planned_entry + (planned_entry - stop_loss) * 3.10
        else:
            effective_entry = planned_entry - half_spread - slip
            struct_sl = float(roll_swing_high[i]) + buf
            dist_sl = struct_sl - planned_entry
            if min_risk <= dist_sl <= max_risk:
                stop_loss = struct_sl
            else:
                stop_loss = planned_entry + max(min_risk, min(max_risk, cur_atr * (1.35 + vol_buf_mult)))
            risk_oz = max(stop_loss - effective_entry, 0.5)
            tp1 = planned_entry - (stop_loss - planned_entry) * 1.25
            tp2 = planned_entry - (stop_loss - planned_entry) * max(request.min_rr, 2.0)
            tp3 = planned_entry - (stop_loss - planned_entry) * 3.10

        planned_rr = round(abs(tp2 - planned_entry) / max(abs(planned_entry - stop_loss), 0.5), 2)

        # Position size strictly derived from current equity & configured risk_percent
        risk_dollars = max(equity * (request.risk_percent / 100.0), 1.0)
        position_oz = risk_dollars / risk_oz

        # Walk forward bar-by-bar from entry_bar until trade completes (conservative SL-first rule)
        current_sl = stop_loss
        tp1_hit = False
        tp2_hit = False
        remaining_weight = 1.0
        weighted_gross_oz = 0.0
        weighted_net_oz = 0.0
        weighted_exit_raw = 0.0
        weighted_exit_eff = 0.0
        outcome = ""
        exit_bar = -1
        max_hold_bars = 96

        for k in range(entry_bar, min(n, entry_bar + max_hold_bars)):
            bar_h = float(highs[k])
            bar_l = float(lows[k])

            if action == "BUY":
                sl_triggered = bar_l <= current_sl
                # Conservative rule: if SL triggers on the same bar as a target, SL fills first!
                if sl_triggered:
                    raw_exit = current_sl
                    eff_exit = raw_exit - half_spread - slip
                    gross_leg = raw_exit - planned_entry
                    net_leg = eff_exit - effective_entry
                    weighted_gross_oz += remaining_weight * gross_leg
                    weighted_net_oz += remaining_weight * net_leg
                    weighted_exit_raw += remaining_weight * raw_exit
                    weighted_exit_eff += remaining_weight * eff_exit
                    remaining_weight = 0.0
                    exit_bar = k
                    if tp2_hit:
                        outcome = "TP2_HIT"
                    elif tp1_hit:
                        outcome = "TP1_HIT" if request.exit_mode == "scaled_tp1_tp2_tp3" else "BREAKEVEN"
                    else:
                        outcome = "SL_HIT"
                    break

                if request.exit_mode == "scaled_tp1_tp2_tp3":
                    if (not tp1_hit) and bar_h >= tp1:
                        tp1_hit = True
                        w = 0.40
                        raw_exit = tp1
                        eff_exit = raw_exit - half_spread - slip
                        weighted_gross_oz += w * (raw_exit - planned_entry)
                        weighted_net_oz += w * (eff_exit - effective_entry)
                        weighted_exit_raw += w * raw_exit
                        weighted_exit_eff += w * eff_exit
                        remaining_weight -= w
                        if request.move_sl_to_be_at_tp1:
                            current_sl = max(current_sl, effective_entry + half_spread + slip)

                    if (not tp2_hit) and bar_h >= tp2:
                        tp2_hit = True
                        w = 0.40
                        raw_exit = tp2
                        eff_exit = raw_exit - half_spread - slip
                        weighted_gross_oz += w * (raw_exit - planned_entry)
                        weighted_net_oz += w * (eff_exit - effective_entry)
                        weighted_exit_raw += w * raw_exit
                        weighted_exit_eff += w * eff_exit
                        remaining_weight -= w
                        current_sl = max(current_sl, tp1)

                    if bar_h >= tp3 and remaining_weight > 0:
                        w = remaining_weight
                        raw_exit = tp3
                        eff_exit = raw_exit - half_spread - slip
                        weighted_gross_oz += w * (raw_exit - planned_entry)
                        weighted_net_oz += w * (eff_exit - effective_entry)
                        weighted_exit_raw += w * raw_exit
                        weighted_exit_eff += w * eff_exit
                        remaining_weight = 0.0
                        exit_bar = k
                        outcome = "TP3_HIT"
                        break
                else:
                    # tp2_primary mode
                    if (not tp1_hit) and bar_h >= tp1:
                        tp1_hit = True
                        if request.move_sl_to_be_at_tp1:
                            current_sl = max(current_sl, effective_entry + half_spread + slip)
                    if bar_h >= tp2:
                        raw_exit = tp2
                        eff_exit = raw_exit - half_spread - slip
                        weighted_gross_oz = raw_exit - planned_entry
                        weighted_net_oz = eff_exit - effective_entry
                        weighted_exit_raw = raw_exit
                        weighted_exit_eff = eff_exit
                        remaining_weight = 0.0
                        exit_bar = k
                        outcome = "TP2_HIT"
                        break
            else:  # SELL
                sl_triggered = bar_h >= current_sl
                if sl_triggered:
                    raw_exit = current_sl
                    eff_exit = raw_exit + half_spread + slip
                    gross_leg = planned_entry - raw_exit
                    net_leg = effective_entry - eff_exit
                    weighted_gross_oz += remaining_weight * gross_leg
                    weighted_net_oz += remaining_weight * net_leg
                    weighted_exit_raw += remaining_weight * raw_exit
                    weighted_exit_eff += remaining_weight * eff_exit
                    remaining_weight = 0.0
                    exit_bar = k
                    if tp2_hit:
                        outcome = "TP2_HIT"
                    elif tp1_hit:
                        outcome = "TP1_HIT" if request.exit_mode == "scaled_tp1_tp2_tp3" else "BREAKEVEN"
                    else:
                        outcome = "SL_HIT"
                    break

                if request.exit_mode == "scaled_tp1_tp2_tp3":
                    if (not tp1_hit) and bar_l <= tp1:
                        tp1_hit = True
                        w = 0.40
                        raw_exit = tp1
                        eff_exit = raw_exit + half_spread + slip
                        weighted_gross_oz += w * (planned_entry - raw_exit)
                        weighted_net_oz += w * (effective_entry - eff_exit)
                        weighted_exit_raw += w * raw_exit
                        weighted_exit_eff += w * eff_exit
                        remaining_weight -= w
                        if request.move_sl_to_be_at_tp1:
                            current_sl = min(current_sl, effective_entry - half_spread - slip)

                    if (not tp2_hit) and bar_l <= tp2:
                        tp2_hit = True
                        w = 0.40
                        raw_exit = tp2
                        eff_exit = raw_exit + half_spread + slip
                        weighted_gross_oz += w * (planned_entry - raw_exit)
                        weighted_net_oz += w * (effective_entry - eff_exit)
                        weighted_exit_raw += w * raw_exit
                        weighted_exit_eff += w * eff_exit
                        remaining_weight -= w
                        current_sl = min(current_sl, tp1)

                    if bar_l <= tp3 and remaining_weight > 0:
                        w = remaining_weight
                        raw_exit = tp3
                        eff_exit = raw_exit + half_spread + slip
                        weighted_gross_oz += w * (planned_entry - raw_exit)
                        weighted_net_oz += w * (effective_entry - eff_exit)
                        weighted_exit_raw += w * raw_exit
                        weighted_exit_eff += w * eff_exit
                        remaining_weight = 0.0
                        exit_bar = k
                        outcome = "TP3_HIT"
                        break
                else:
                    if (not tp1_hit) and bar_l <= tp1:
                        tp1_hit = True
                        if request.move_sl_to_be_at_tp1:
                            current_sl = min(current_sl, effective_entry - half_spread - slip)
                    if bar_l <= tp2:
                        raw_exit = tp2
                        eff_exit = raw_exit + half_spread + slip
                        weighted_gross_oz = planned_entry - raw_exit
                        weighted_net_oz = effective_entry - eff_exit
                        weighted_exit_raw = raw_exit
                        weighted_exit_eff = eff_exit
                        remaining_weight = 0.0
                        exit_bar = k
                        outcome = "TP2_HIT"
                        break

        # If max hold elapsed without hitting SL/TP, only include if strictly closed at bar close (time exit)
        # Skip incomplete trade still open at end of historical sample so ONLY completed signals are counted!
        if remaining_weight > 0:
            last_checked = min(n - 1, entry_bar + max_hold_bars - 1)
            if last_checked == n - 1:
                # Reached end of dataset — do not count unfinished trade in completed stats
                break
            raw_exit = float(closes[last_checked])
            eff_exit = (raw_exit - half_spread - slip) if action == "BUY" else (raw_exit + half_spread + slip)
            gross_leg = (raw_exit - planned_entry) if action == "BUY" else (planned_entry - raw_exit)
            net_leg = (eff_exit - effective_entry) if action == "BUY" else (effective_entry - eff_exit)
            weighted_gross_oz += remaining_weight * gross_leg
            weighted_net_oz += remaining_weight * net_leg
            weighted_exit_raw += remaining_weight * raw_exit
            weighted_exit_eff += remaining_weight * eff_exit
            remaining_weight = 0.0
            exit_bar = last_checked
            outcome = "TP2_HIT" if tp2_hit else ("TP1_HIT" if tp1_hit else "TIME_EXIT")

        trade_counter += 1
        realized_r = round(weighted_net_oz / risk_oz, 3)
        account_pnl = round(position_oz * weighted_net_oz, 2)
        equity = round(equity + account_pnl, 2)

        completed_trades.append(
            PerformanceTradeRecord(
                signal_uid=f"BT-{request.timeframe}-{trade_counter:04d}",
                mode="BACKTEST",
                action=action,  # type: ignore[arg-type]
                timeframe=request.timeframe,
                confidence=min(94, confidence),
                status="COMPLETED",
                outcome=outcome,
                opened_at=times_iso[entry_bar],
                closed_at=times_iso[exit_bar],
                bars_held=max(1, exit_bar - entry_bar + 1),
                planned_entry=round(planned_entry, 2),
                effective_entry=round(effective_entry, 2),
                stop_loss=round(stop_loss, 2),
                tp1=round(tp1, 2),
                tp2=round(tp2, 2),
                tp3=round(tp3, 2),
                exit_price=round(weighted_exit_raw, 2),
                effective_exit=round(weighted_exit_eff, 2),
                planned_rr=planned_rr,
                realized_r=realized_r,
                gross_pnl_usd_oz=round(weighted_gross_oz, 2),
                spread_cost_usd_oz=round(round_trip_spread, 2),
                slippage_cost_usd_oz=round(round_trip_slippage, 2),
                total_cost_usd_oz=round(total_cost_oz, 2),
                net_pnl_usd_oz=round(weighted_net_oz, 2),
                account_pnl_usd=account_pnl,
                equity_after=equity,
                rationale=(
                    f"HTF+EMA aligned {action} (RSI {rsi[i]:.1f}, ADX {adx[i]:.1f}, ATR ${cur_atr:.2f}) -> "
                    f"{outcome.replace('_', ' ')} in {exit_bar - entry_bar + 1} bars after ${total_cost_oz:.2f}/oz costs."
                ),
            )
        )

        # Advance strictly past exit_bar + cooldown to prevent overlapping duplicate trades
        i = exit_bar + cooldown_bars

    summary = calculate_performance_summary(
        mode="BACKTEST",
        completed_trades=completed_trades,
        open_trades_count=0,
        initial_balance=request.initial_balance,
        risk_percent=request.risk_percent,
    )

    run_uid = f"RUN-{uuid.uuid4().hex[:10].upper()}"
    return BacktestReport(
        run_uid=run_uid,
        created_at=utc_now_iso(),
        symbol="XAUUSD",
        timeframe=request.timeframe,
        dataset=request.dataset,
        dataset_label=dataset_label,
        bars_analyzed=len(candles),
        period_start=candles[0].open_time_iso,
        period_end=candles[-1].open_time_iso,
        parameters=request.model_dump(),
        summary=summary,
        trades=completed_trades,
    )


def save_backtest_report(report: BacktestReport) -> None:
    db: Session = SessionLocal()
    try:
        s = report.summary
        p = report.parameters
        run = BacktestRun(
            run_uid=report.run_uid,
            symbol=report.symbol,
            timeframe=report.timeframe,
            dataset=report.dataset,
            dataset_label=report.dataset_label,
            bars_analyzed=report.bars_analyzed,
            period_start=report.period_start,
            period_end=report.period_end,
            spread_usd=float(p["spread_usd"]),
            slippage_usd=float(p["slippage_usd"]),
            initial_balance=float(p["initial_balance"]),
            risk_percent=float(p["risk_percent"]),
            min_rr=float(p["min_rr"]),
            exit_mode=str(p["exit_mode"]),
            move_sl_to_be_at_tp1=bool(p["move_sl_to_be_at_tp1"]),
            completed_trades=s.completed_trades,
            win_rate_pct=s.win_rate_pct,
            profit_factor=s.profit_factor,
            max_drawdown_pct=s.max_drawdown_pct,
            net_profit_usd=s.net_profit_usd,
            net_profit_r=s.net_profit_r,
            avg_rr_realized=s.avg_rr_realized,
            summary_json=s.model_dump_json(),
        )
        db.add(run)

        for idx, t in enumerate(report.trades, start=1):
            db.add(
                BacktestTrade(
                    run_uid=report.run_uid,
                    trade_index=idx,
                    signal_uid=t.signal_uid,
                    action=t.action,
                    timeframe=t.timeframe,
                    confidence=t.confidence,
                    opened_at=t.opened_at,
                    closed_at=t.closed_at or t.opened_at,
                    bars_held=t.bars_held or 1,
                    planned_entry=t.planned_entry,
                    effective_entry=t.effective_entry,
                    stop_loss=t.stop_loss,
                    tp1=t.tp1,
                    tp2=t.tp2,
                    tp3=t.tp3,
                    exit_price=t.exit_price or t.planned_entry,
                    effective_exit=t.effective_exit or t.effective_entry,
                    outcome=t.outcome or "COMPLETED",
                    planned_rr=t.planned_rr,
                    realized_r=t.realized_r or 0.0,
                    gross_pnl_usd_oz=t.gross_pnl_usd_oz or 0.0,
                    spread_cost_usd_oz=t.spread_cost_usd_oz,
                    slippage_cost_usd_oz=t.slippage_cost_usd_oz,
                    net_pnl_usd_oz=t.net_pnl_usd_oz or 0.0,
                    account_pnl_usd=t.account_pnl_usd or 0.0,
                    equity_after=t.equity_after or report.summary.initial_balance,
                    rationale=t.rationale,
                )
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed persisting backtest run %s: %s", report.run_uid, exc)
    finally:
        db.close()


def list_backtest_runs(limit: int = 15) -> List[BacktestRunSummaryItem]:
    db: Session = SessionLocal()
    try:
        rows = db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit).all()
        return [
            BacktestRunSummaryItem(
                run_uid=r.run_uid,
                created_at=r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if r.created_at else utc_now_iso(),
                timeframe=r.timeframe,
                dataset=r.dataset,
                dataset_label=r.dataset_label,
                bars_analyzed=r.bars_analyzed,
                period_start=r.period_start,
                period_end=r.period_end,
                completed_trades=r.completed_trades,
                win_rate_pct=r.win_rate_pct,
                profit_factor=r.profit_factor,
                max_drawdown_pct=r.max_drawdown_pct,
                net_profit_usd=r.net_profit_usd,
                net_profit_r=r.net_profit_r,
                avg_rr_realized=r.avg_rr_realized,
                spread_usd=r.spread_usd,
                slippage_usd=r.slippage_usd,
                exit_mode=r.exit_mode,
            )
            for r in rows
        ]
    finally:
        db.close()


def load_backtest_report(run_uid: Optional[str] = None) -> Optional[BacktestReport]:
    db: Session = SessionLocal()
    try:
        q = db.query(BacktestRun)
        row = q.filter(BacktestRun.run_uid == run_uid).first() if run_uid else q.order_by(BacktestRun.created_at.desc()).first()
        if not row:
            return None
        trade_rows = (
            db.query(BacktestTrade)
            .filter(BacktestTrade.run_uid == row.run_uid)
            .order_by(BacktestTrade.trade_index.asc())
            .all()
        )
        trades = [
            PerformanceTradeRecord(
                signal_uid=t.signal_uid,
                mode="BACKTEST",
                action=t.action,  # type: ignore[arg-type]
                timeframe=t.timeframe,
                confidence=t.confidence,
                status="COMPLETED",
                outcome=t.outcome,
                opened_at=t.opened_at,
                closed_at=t.closed_at,
                bars_held=t.bars_held,
                planned_entry=t.planned_entry,
                effective_entry=t.effective_entry,
                stop_loss=t.stop_loss,
                tp1=t.tp1,
                tp2=t.tp2,
                tp3=t.tp3,
                exit_price=t.exit_price,
                effective_exit=t.effective_exit,
                planned_rr=t.planned_rr,
                realized_r=t.realized_r,
                gross_pnl_usd_oz=t.gross_pnl_usd_oz,
                spread_cost_usd_oz=t.spread_cost_usd_oz,
                slippage_cost_usd_oz=t.slippage_cost_usd_oz,
                total_cost_usd_oz=round(t.spread_cost_usd_oz + t.slippage_cost_usd_oz, 2),
                net_pnl_usd_oz=t.net_pnl_usd_oz,
                account_pnl_usd=t.account_pnl_usd,
                equity_after=t.equity_after,
                rationale=t.rationale,
            )
            for t in trade_rows
        ]
        summary = calculate_performance_summary(
            mode="BACKTEST",
            completed_trades=trades,
            open_trades_count=0,
            initial_balance=row.initial_balance,
            risk_percent=row.risk_percent,
        )
        return BacktestReport(
            run_uid=row.run_uid,
            created_at=row.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if row.created_at else utc_now_iso(),
            symbol=row.symbol,
            timeframe=row.timeframe,
            dataset=row.dataset,
            dataset_label=row.dataset_label,
            bars_analyzed=row.bars_analyzed,
            period_start=row.period_start,
            period_end=row.period_end,
            parameters={
                "timeframe": row.timeframe,
                "dataset": row.dataset,
                "spread_usd": row.spread_usd,
                "slippage_usd": row.slippage_usd,
                "initial_balance": row.initial_balance,
                "risk_percent": row.risk_percent,
                "min_rr": row.min_rr,
                "exit_mode": row.exit_mode,
                "move_sl_to_be_at_tp1": row.move_sl_to_be_at_tp1,
            },
            summary=summary,
            trades=trades,
        )
    finally:
        db.close()


async def execute_and_persist_backtest(
    request: BacktestRequest,
    live_cache: Optional[Dict[Timeframe, List[Candle]]] = None,
) -> BacktestReport:
    candles, label = await load_historical_candles(
        timeframe=request.timeframe,
        dataset=request.dataset,
        live_cache=live_cache,
    )
    report = run_walk_forward_backtest_on_candles(candles, request, label)
    save_backtest_report(report)
    return report
