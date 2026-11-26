from __future__ import annotations

from typing import List, Literal, Optional

from app.schemas import (
    EquityPoint,
    PerformanceHorizonWindow,
    PerformanceSummary,
    PerformanceTradeRecord,
)


HORIZON_TARGETS = (100, 300, 500)


def _compute_core_slice_metrics(
    trades: List[PerformanceTradeRecord],
    initial_balance: float = 10000.0,
) -> dict:
    """Compute strictly factual statistics on an ordered list of COMPLETED trades."""
    n = len(trades)
    if n == 0:
        return {
            "completed_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "breakeven_trades": 0,
            "win_rate_pct": None,
            "profit_factor": None,
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_r": 0.0,
            "avg_rr_planned": None,
            "avg_rr_realized": None,
            "avg_win_r": None,
            "avg_loss_r": None,
            "expectancy_r": None,
            "expectancy_usd": None,
            "gross_profit_usd": 0.0,
            "gross_loss_usd": 0.0,
            "net_profit_usd": 0.0,
            "net_profit_pct": 0.0,
            "net_profit_r": 0.0,
            "avg_win_usd": None,
            "avg_loss_usd": None,
            "largest_win_usd": None,
            "largest_loss_usd": None,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "total_spread_cost_usd_oz": 0.0,
            "total_slippage_cost_usd_oz": 0.0,
            "total_trading_costs_usd_oz": 0.0,
            "total_trading_costs_account_usd": 0.0,
            "ending_balance": round(initial_balance, 2),
            "tp1_hit_count": 0,
            "tp2_hit_count": 0,
            "tp3_hit_count": 0,
            "sl_hit_count": 0,
            "invalidated_count": 0,
            "equity_curve": [],
        }

    wins: List[float] = []
    losses: List[float] = []
    win_rs: List[float] = []
    loss_rs: List[float] = []
    all_rs: List[float] = []
    planned_rrs: List[float] = []
    breakevens = 0

    gross_profit = 0.0
    gross_loss = 0.0
    total_spread_oz = 0.0
    total_slip_oz = 0.0
    total_cost_account = 0.0

    tp1_n = 0
    tp2_n = 0
    tp3_n = 0
    sl_n = 0
    inv_n = 0

    cur_win_streak = 0
    cur_loss_streak = 0
    max_win_streak = 0
    max_loss_streak = 0

    equity = initial_balance
    peak_equity = initial_balance
    max_dd_usd = 0.0
    max_dd_pct = 0.0

    cum_r = 0.0
    peak_r = 0.0
    max_dd_r = 0.0

    equity_curve: List[EquityPoint] = []

    for idx, t in enumerate(trades, start=1):
        r_val = float(t.realized_r if t.realized_r is not None else 0.0)
        acct_pnl = float(t.account_pnl_usd if t.account_pnl_usd is not None else 0.0)
        planned_rrs.append(float(t.planned_rr))
        all_rs.append(r_val)

        total_spread_oz += float(t.spread_cost_usd_oz)
        total_slip_oz += float(t.slippage_cost_usd_oz)
        # Approximate account-level cost proportional to position size (account_pnl vs net_pnl_oz)
        if t.net_pnl_usd_oz and abs(t.net_pnl_usd_oz) > 1e-6 and acct_pnl != 0:
            oz_implied = abs(acct_pnl / t.net_pnl_usd_oz)
            total_cost_account += oz_implied * float(t.total_cost_usd_oz)
        else:
            risk_oz = max(abs(t.effective_entry - t.stop_loss), 0.5)
            oz_implied = (equity * 0.01) / risk_oz
            total_cost_account += oz_implied * float(t.total_cost_usd_oz)

        outcome = (t.outcome or "").upper()
        if outcome == "TP1_HIT":
            tp1_n += 1
        elif outcome == "TP2_HIT":
            tp2_n += 1
        elif outcome == "TP3_HIT":
            tp3_n += 1
        elif outcome == "SL_HIT":
            sl_n += 1
        elif outcome == "INVALIDATED":
            inv_n += 1

        if acct_pnl > 1e-6 or (acct_pnl == 0 and r_val > 0.02):
            wins.append(acct_pnl)
            win_rs.append(r_val)
            gross_profit += acct_pnl
            cur_win_streak += 1
            cur_loss_streak = 0
            max_win_streak = max(max_win_streak, cur_win_streak)
        elif acct_pnl < -1e-6 or (acct_pnl == 0 and r_val < -0.02):
            losses.append(abs(acct_pnl))
            loss_rs.append(abs(r_val))
            gross_loss += abs(acct_pnl)
            cur_loss_streak += 1
            cur_win_streak = 0
            max_loss_streak = max(max_loss_streak, cur_loss_streak)
        else:
            breakevens += 1
            cur_win_streak = 0
            cur_loss_streak = 0

        equity += acct_pnl
        cum_r += r_val

        if equity > peak_equity:
            peak_equity = equity
        dd_usd = max(0.0, peak_equity - equity)
        dd_pct = (dd_usd / peak_equity) * 100.0 if peak_equity > 0 else 0.0
        max_dd_usd = max(max_dd_usd, dd_usd)
        max_dd_pct = max(max_dd_pct, dd_pct)

        if cum_r > peak_r:
            peak_r = cum_r
        dd_r = max(0.0, peak_r - cum_r)
        max_dd_r = max(max_dd_r, dd_r)

        equity_curve.append(
            EquityPoint(
                trade_number=idx,
                timestamp=t.closed_at or t.opened_at,
                equity_usd=round(equity, 2),
                cumulative_r=round(cum_r, 3),
                drawdown_pct=round(dd_pct, 2),
                drawdown_r=round(dd_r, 2),
            )
        )

    decisive = len(wins) + len(losses)
    win_rate = round((len(wins) / decisive) * 100.0, 2) if decisive > 0 else None

    if gross_loss > 0:
        profit_factor: Optional[float] = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = 99.99  # Zero realized losses across winning sample
    else:
        profit_factor = None

    avg_win_usd = round(sum(wins) / len(wins), 2) if wins else None
    avg_loss_usd = round(sum(losses) / len(losses), 2) if losses else None
    avg_win_r = round(sum(win_rs) / len(win_rs), 2) if win_rs else None
    avg_loss_r = round(sum(loss_rs) / len(loss_rs), 2) if loss_rs else None

    # Realized reward-to-risk ratio = Avg Win R / Avg Loss R (or Avg Win $ / Avg Loss $)
    if avg_win_r is not None and avg_loss_r is not None and avg_loss_r > 0:
        avg_rr_realized: Optional[float] = round(avg_win_r / avg_loss_r, 2)
    elif avg_win_r is not None:
        avg_rr_realized = round(avg_win_r, 2)
    else:
        avg_rr_realized = None

    net_profit = round(equity - initial_balance, 2)
    net_profit_pct = round((net_profit / initial_balance) * 100.0, 2) if initial_balance > 0 else 0.0

    return {
        "completed_trades": n,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "breakeven_trades": breakevens,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_usd": round(max_dd_usd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_r": round(max_dd_r, 2),
        "avg_rr_planned": round(sum(planned_rrs) / len(planned_rrs), 2),
        "avg_rr_realized": avg_rr_realized,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "expectancy_r": round(sum(all_rs) / n, 3),
        "expectancy_usd": round(net_profit / n, 2),
        "gross_profit_usd": round(gross_profit, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "net_profit_usd": net_profit,
        "net_profit_pct": net_profit_pct,
        "net_profit_r": round(cum_r, 2),
        "avg_win_usd": avg_win_usd,
        "avg_loss_usd": avg_loss_usd,
        "largest_win_usd": round(max(wins), 2) if wins else None,
        "largest_loss_usd": round(max(losses), 2) if losses else None,
        "max_consecutive_wins": max_win_streak,
        "max_consecutive_losses": max_loss_streak,
        "total_spread_cost_usd_oz": round(total_spread_oz, 2),
        "total_slippage_cost_usd_oz": round(total_slip_oz, 2),
        "total_trading_costs_usd_oz": round(total_spread_oz + total_slip_oz, 2),
        "total_trading_costs_account_usd": round(total_cost_account, 2),
        "ending_balance": round(equity, 2),
        "tp1_hit_count": tp1_n,
        "tp2_hit_count": tp2_n,
        "tp3_hit_count": tp3_n,
        "sl_hit_count": sl_n,
        "invalidated_count": inv_n,
        "equity_curve": equity_curve,
    }


def calculate_performance_summary(
    mode: Literal["BACKTEST", "FORWARD_TEST"],
    completed_trades: List[PerformanceTradeRecord],
    open_trades_count: int = 0,
    initial_balance: float = 10000.0,
    risk_percent: float = 1.0,
) -> PerformanceSummary:
    """
    Build a complete verifiable PerformanceSummary including 100 / 300 / 500 completed signal
    rolling horizons. Never invents or extrapolates missing statistics.
    """
    ordered = sorted(completed_trades, key=lambda t: t.closed_at or t.opened_at)
    core = _compute_core_slice_metrics(ordered, initial_balance=initial_balance)

    horizons: List[PerformanceHorizonWindow] = []
    total_done = len(ordered)

    for target in HORIZON_TARGETS:
        if total_done >= target:
            window_trades = ordered[-target:]
            w = _compute_core_slice_metrics(window_trades, initial_balance=initial_balance)
            horizons.append(
                PerformanceHorizonWindow(
                    target_signals=target,
                    available=True,
                    completed_available=total_done,
                    sample_size=target,
                    period_start=window_trades[0].opened_at,
                    period_end=window_trades[-1].closed_at or window_trades[-1].opened_at,
                    win_rate_pct=w["win_rate_pct"],
                    winning_trades=w["winning_trades"],
                    losing_trades=w["losing_trades"],
                    breakeven_trades=w["breakeven_trades"],
                    profit_factor=w["profit_factor"],
                    max_drawdown_pct=w["max_drawdown_pct"],
                    max_drawdown_r=w["max_drawdown_r"],
                    avg_rr_planned=w["avg_rr_planned"],
                    avg_rr_realized=w["avg_rr_realized"],
                    expectancy_r=w["expectancy_r"],
                    net_profit_r=w["net_profit_r"],
                    net_profit_usd=w["net_profit_usd"],
                    total_trading_costs_usd_oz=w["total_trading_costs_usd_oz"],
                    note=f"Calculated strictly from the most recent {target} completed verifiable signals.",
                )
            )
        else:
            horizons.append(
                PerformanceHorizonWindow(
                    target_signals=target,
                    available=False,
                    completed_available=total_done,
                    sample_size=0,
                    note=(
                        f"{total_done} of {target} completed verifiable signals available. "
                        "Statistics are withheld until full sample is reached — never fabricated."
                    ),
                )
            )

    if total_done == 0:
        verif_note = (
            "0 completed verifiable signals recorded yet. All metrics remain N/A until real signals close — "
            "no statistics are ever invented. Trading execution is permanently disabled."
        )
    else:
        verif_note = (
            f"All metrics computed strictly from {total_done} completed, timestamped, verifiable "
            f"{'historical backtest' if mode == 'BACKTEST' else 'live non-executing forward-test'} signals "
            "net of spread and slippage costs. Trading execution is permanently disabled."
        )

    return PerformanceSummary(
        mode=mode,
        execution_disabled=True,
        open_trades=open_trades_count,
        initial_balance=round(initial_balance, 2),
        risk_percent=risk_percent,
        horizons=horizons,
        verification_note=verif_note,
        **core,
    )
