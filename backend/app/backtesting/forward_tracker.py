from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.backtesting.metrics import calculate_performance_summary
from app.database import SessionLocal
from app.market_data.base import utc_now, utc_now_iso
from app.models import ForwardTestTrade, SignalRecord
from app.schemas import (
    ForwardTestReport,
    LiveQuote,
    PerformanceTradeRecord,
    TradingSignal,
)


logger = logging.getLogger("gold_ai.forward_test")

DEFAULT_FORWARD_SLIPPAGE_PER_SIDE_USD = 0.15
DEFAULT_FORWARD_BALANCE = 10000.0
DEFAULT_FORWARD_RISK_PCT = 1.0


def sync_existing_live_signals_to_forward_ledger() -> None:
    """
    Backfill any real persisted live BUY/SELL signals from `signals` that were created
    before the ForwardTestTrade table existed — strictly real live signals only.
    """
    db: Session = SessionLocal()
    try:
        existing_uids = {row[0] for row in db.query(ForwardTestTrade.signal_uid).all()}
        live_records = (
            db.query(SignalRecord)
            .filter(SignalRecord.action.in_(["BUY", "SELL"]))
            .order_by(SignalRecord.created_at.asc())
            .all()
        )
        for rec in live_records:
            if rec.signal_uid in existing_uids:
                continue
            if rec.entry_price is None or rec.stop_loss is None or rec.tp2 is None:
                continue
            spread_est = 0.20
            slip = DEFAULT_FORWARD_SLIPPAGE_PER_SIDE_USD
            eff_entry = (
                rec.entry_price + spread_est / 2.0 + slip
                if rec.action == "BUY"
                else rec.entry_price - spread_est / 2.0 - slip
            )
            is_closed = rec.status in ("SL_HIT", "TP3_HIT", "INVALIDATED", "SUPERSEDED", "EXPIRED")
            ft = ForwardTestTrade(
                signal_uid=rec.signal_uid,
                symbol=rec.symbol,
                action=rec.action,
                timeframe=rec.setup_timeframe,
                confidence=rec.confidence,
                data_provider=rec.data_provider,
                status="COMPLETED" if is_closed else "OPEN",
                outcome=rec.status if is_closed else None,
                signal_time=rec.created_at or utc_now(),
                entry_filled_at=rec.created_at if rec.status != "ACTIVE" else None,
                closed_at=rec.resolved_at if is_closed else None,
                planned_entry=rec.entry_price,
                effective_entry=round(eff_entry, 3),
                stop_loss=rec.stop_loss,
                tp1=rec.tp1 or rec.tp2,
                tp2=rec.tp2,
                tp3=rec.tp3 or rec.tp2,
                planned_rr=rec.risk_reward_tp2 or 2.0,
                entry_spread_usd=spread_est,
                slippage_per_side_usd=slip,
                total_spread_cost_usd=spread_est,
                total_slippage_cost_usd=round(slip * 2.0, 3),
                tp1_hit=rec.status in ("TP1_HIT", "TP2_HIT", "TP3_HIT"),
                tp2_hit=rec.status in ("TP2_HIT", "TP3_HIT"),
                tp3_hit=rec.status == "TP3_HIT",
                note=rec.resolution_note or rec.summary,
            )
            if is_closed and rec.resolution_price is not None:
                _apply_close_accounting(ft, rec.resolution_price, spread_est, rec.status, rec.resolution_note or "")
            db.add(ft)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Forward ledger sync skipped: %s", exc)
    finally:
        db.close()


def _apply_close_accounting(
    ft: ForwardTestTrade,
    raw_exit_price: float,
    exit_spread_usd: float,
    outcome: str,
    note: str,
) -> None:
    slip = ft.slippage_per_side_usd
    eff_exit = (raw_exit_price - slip) if ft.action == "BUY" else (raw_exit_price + slip)
    gross_oz = (
        (raw_exit_price - ft.planned_entry)
        if ft.action == "BUY"
        else (ft.planned_entry - raw_exit_price)
    )
    net_oz = (
        (eff_exit - ft.effective_entry)
        if ft.action == "BUY"
        else (ft.effective_entry - eff_exit)
    )
    risk_oz = max(abs(ft.effective_entry - ft.stop_loss), 0.5)
    realized_r = round(net_oz / risk_oz, 3)

    ft.status = "COMPLETED"
    ft.outcome = outcome
    ft.closed_at = utc_now()
    ft.exit_price = round(raw_exit_price, 3)
    ft.effective_exit = round(eff_exit, 3)
    ft.exit_spread_usd = round(exit_spread_usd, 3)
    ft.total_spread_cost_usd = round((ft.entry_spread_usd + exit_spread_usd) / 2.0, 3)
    ft.total_slippage_cost_usd = round(slip * 2.0, 3)
    ft.gross_pnl_usd_oz = round(gross_oz, 3)
    ft.net_pnl_usd_oz = round(net_oz, 3)
    ft.realized_r = realized_r
    ft.note = note


def record_forward_signal_open(sig: TradingSignal, quote: Optional[LiveQuote]) -> None:
    """Open a non-executing paper forward-test entry when GOLD AI emits a new live BUY/SELL signal."""
    if sig.action not in ("BUY", "SELL") or sig.risk_plan is None:
        return
    rp = sig.risk_plan
    spread = quote.spread if quote is not None else 0.20
    slip = DEFAULT_FORWARD_SLIPPAGE_PER_SIDE_USD

    # Executable paper fill price (Ask + slippage for BUY, Bid - slippage for SELL)
    if quote is not None:
        raw_exec = quote.ask if sig.action == "BUY" else quote.bid
    else:
        raw_exec = rp.entry_price + spread / 2.0 if sig.action == "BUY" else rp.entry_price - spread / 2.0
    eff_entry = (raw_exec + slip) if sig.action == "BUY" else (raw_exec - slip)

    db: Session = SessionLocal()
    try:
        exists = db.query(ForwardTestTrade).filter(ForwardTestTrade.signal_uid == sig.signal_uid).first()
        if exists:
            return
        ft = ForwardTestTrade(
            signal_uid=sig.signal_uid,
            symbol=sig.symbol,
            action=sig.action,
            timeframe=sig.setup_timeframe,
            confidence=sig.confidence,
            data_provider=sig.data_provider,
            status="OPEN",
            signal_time=utc_now(),
            planned_entry=rp.entry_price,
            effective_entry=round(eff_entry, 3),
            stop_loss=rp.stop_loss,
            tp1=rp.tp1,
            tp2=rp.tp2,
            tp3=rp.tp3,
            planned_rr=rp.rr_tp2,
            entry_spread_usd=round(spread, 3),
            slippage_per_side_usd=slip,
            total_spread_cost_usd=round(spread, 3),
            total_slippage_cost_usd=round(slip * 2.0, 3),
            note=sig.explanation.decision_headline,
        )
        db.add(ft)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed recording forward-test open %s: %s", sig.signal_uid, exc)
    finally:
        db.close()


def update_forward_signal_milestone(signal_uid: str, milestone: str, quote: Optional[LiveQuote] = None) -> None:
    db: Session = SessionLocal()
    try:
        ft = db.query(ForwardTestTrade).filter(ForwardTestTrade.signal_uid == signal_uid).first()
        if not ft or ft.status == "COMPLETED":
            return
        if milestone == "ENTRY_TRIGGERED" and ft.entry_filled_at is None:
            ft.entry_filled_at = utc_now()
            if quote is not None:
                raw_exec = quote.ask if ft.action == "BUY" else quote.bid
                ft.effective_entry = round(
                    raw_exec + ft.slippage_per_side_usd if ft.action == "BUY" else raw_exec - ft.slippage_per_side_usd,
                    3,
                )
                ft.entry_spread_usd = round(quote.spread, 3)
        elif milestone == "TP1_HIT":
            ft.tp1_hit = True
        elif milestone == "TP2_HIT":
            ft.tp1_hit = True
            ft.tp2_hit = True
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed updating forward milestone %s: %s", signal_uid, exc)
    finally:
        db.close()


def close_forward_signal(
    signal_uid: str,
    outcome: str,
    exit_price: float,
    exit_spread_usd: float,
    note: str,
) -> None:
    """Close an open forward-test paper signal with exact exit timestamp, spread & slippage costs."""
    db: Session = SessionLocal()
    try:
        ft = db.query(ForwardTestTrade).filter(ForwardTestTrade.signal_uid == signal_uid).first()
        if not ft or ft.status == "COMPLETED":
            return
        if outcome == "TP3_HIT":
            ft.tp1_hit = True
            ft.tp2_hit = True
            ft.tp3_hit = True
        _apply_close_accounting(ft, exit_price, exit_spread_usd, outcome, note)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed closing forward signal %s: %s", signal_uid, exc)
    finally:
        db.close()


def build_forward_test_report(
    active_provider: str,
    initial_balance: float = DEFAULT_FORWARD_BALANCE,
    risk_percent: float = DEFAULT_FORWARD_RISK_PCT,
) -> ForwardTestReport:
    """
    Generate the strictly live, non-executing Forward-Testing report from verifiable DB records.
    Never invents or fabricates performance metrics.
    """
    db: Session = SessionLocal()
    try:
        rows = db.query(ForwardTestTrade).order_by(ForwardTestTrade.signal_time.asc()).all()
    finally:
        db.close()

    completed_records: List[PerformanceTradeRecord] = []
    open_records: List[PerformanceTradeRecord] = []

    equity = initial_balance

    for r in rows:
        total_cost_oz = round(float(r.total_spread_cost_usd) + float(r.total_slippage_cost_usd), 3)
        opened_iso = (r.entry_filled_at or r.signal_time).strftime("%Y-%m-%dT%H:%M:%SZ") if (r.entry_filled_at or r.signal_time) else utc_now_iso()
        closed_iso = r.closed_at.strftime("%Y-%m-%dT%H:%M:%SZ") if r.closed_at else None

        if r.status == "COMPLETED" and r.net_pnl_usd_oz is not None:
            risk_oz = max(abs(r.effective_entry - r.stop_loss), 0.5)
            risk_dollars = max(equity * (risk_percent / 100.0), 1.0)
            oz_size = risk_dollars / risk_oz
            acct_pnl = round(oz_size * float(r.net_pnl_usd_oz), 2)
            equity = round(equity + acct_pnl, 2)

            completed_records.append(
                PerformanceTradeRecord(
                    signal_uid=r.signal_uid,
                    mode="FORWARD_TEST",
                    action=r.action,  # type: ignore[arg-type]
                    timeframe=r.timeframe,
                    confidence=r.confidence,
                    status="COMPLETED",
                    outcome=r.outcome,
                    opened_at=opened_iso,
                    closed_at=closed_iso,
                    planned_entry=round(r.planned_entry, 2),
                    effective_entry=round(r.effective_entry, 2),
                    stop_loss=round(r.stop_loss, 2),
                    tp1=round(r.tp1, 2),
                    tp2=round(r.tp2, 2),
                    tp3=round(r.tp3, 2),
                    exit_price=round(r.exit_price, 2) if r.exit_price is not None else None,
                    effective_exit=round(r.effective_exit, 2) if r.effective_exit is not None else None,
                    planned_rr=round(r.planned_rr, 2),
                    realized_r=round(r.realized_r, 3) if r.realized_r is not None else 0.0,
                    gross_pnl_usd_oz=round(r.gross_pnl_usd_oz, 2) if r.gross_pnl_usd_oz is not None else 0.0,
                    spread_cost_usd_oz=round(r.total_spread_cost_usd, 2),
                    slippage_cost_usd_oz=round(r.total_slippage_cost_usd, 2),
                    total_cost_usd_oz=round(total_cost_oz, 2),
                    net_pnl_usd_oz=round(r.net_pnl_usd_oz, 2),
                    account_pnl_usd=acct_pnl,
                    equity_after=equity,
                    rationale=r.note or "Live non-executing paper forward-test signal.",
                )
            )
        else:
            open_records.append(
                PerformanceTradeRecord(
                    signal_uid=r.signal_uid,
                    mode="FORWARD_TEST",
                    action=r.action,  # type: ignore[arg-type]
                    timeframe=r.timeframe,
                    confidence=r.confidence,
                    status="OPEN",
                    outcome="OPEN",
                    opened_at=opened_iso,
                    closed_at=None,
                    planned_entry=round(r.planned_entry, 2),
                    effective_entry=round(r.effective_entry, 2),
                    stop_loss=round(r.stop_loss, 2),
                    tp1=round(r.tp1, 2),
                    tp2=round(r.tp2, 2),
                    tp3=round(r.tp3, 2),
                    planned_rr=round(r.planned_rr, 2),
                    spread_cost_usd_oz=round(r.total_spread_cost_usd, 2),
                    slippage_cost_usd_oz=round(r.total_slippage_cost_usd, 2),
                    total_cost_usd_oz=round(total_cost_oz, 2),
                    rationale=r.note or "Active live paper forward-test signal (execution disabled).",
                )
            )

    summary = calculate_performance_summary(
        mode="FORWARD_TEST",
        completed_trades=completed_records,
        open_trades_count=len(open_records),
        initial_balance=initial_balance,
        risk_percent=risk_percent,
    )

    return ForwardTestReport(
        generated_at=utc_now_iso(),
        data_provider=active_provider,
        execution_disabled=True,
        assumed_slippage_per_side_usd=DEFAULT_FORWARD_SLIPPAGE_PER_SIDE_USD,
        summary=summary,
        open_signals=list(reversed(open_records)),
        completed_signals=list(reversed(completed_records)),
    )
