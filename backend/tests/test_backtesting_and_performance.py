from __future__ import annotations

import pytest

from app.backtesting.data_loader import load_historical_candles
from app.backtesting.engine import run_walk_forward_backtest_on_candles
from app.backtesting.metrics import calculate_performance_summary
from app.database import init_db
from app.schemas import BacktestRequest, PerformanceTradeRecord


def _trade(idx: int, net_r: float, acct_pnl: float, spread: float = 0.25, slip: float = 0.30) -> PerformanceTradeRecord:
    return PerformanceTradeRecord(
        signal_uid=f"TST-{idx:04d}",
        mode="BACKTEST",
        action="BUY",
        timeframe="H1",
        confidence=75,
        status="COMPLETED",
        outcome="TP2_HIT" if net_r > 0 else ("SL_HIT" if net_r < 0 else "BREAKEVEN"),
        opened_at=f"2026-01-{(idx % 28) + 1:02d}T10:00:00Z",
        closed_at=f"2026-01-{(idx % 28) + 1:02d}T14:00:00Z",
        bars_held=4,
        planned_entry=3500.0,
        effective_entry=3500.28,
        stop_loss=3490.0,
        tp1=3512.5,
        tp2=3520.0,
        tp3=3531.0,
        exit_price=3520.0 if net_r > 0 else 3490.0,
        effective_exit=3519.72 if net_r > 0 else 3489.72,
        planned_rr=2.0,
        realized_r=net_r,
        gross_pnl_usd_oz=20.0 if net_r > 0 else -10.0,
        spread_cost_usd_oz=spread,
        slippage_cost_usd_oz=slip,
        total_cost_usd_oz=round(spread + slip, 2),
        net_pnl_usd_oz=19.45 if net_r > 0 else -10.55,
        account_pnl_usd=acct_pnl,
        equity_after=10000.0 + acct_pnl,
        rationale="Unit test verifiable trade",
    )


def test_zero_completed_signals_never_fabricates_metrics():
    summary = calculate_performance_summary("FORWARD_TEST", [], open_trades_count=1)
    assert summary.execution_disabled is True
    assert summary.completed_trades == 0
    assert summary.open_trades == 1
    assert summary.win_rate_pct is None
    assert summary.profit_factor is None
    assert summary.avg_rr_realized is None
    assert len(summary.horizons) == 3
    assert [h.target_signals for h in summary.horizons] == [100, 300, 500]
    assert all(h.available is False for h in summary.horizons)


def test_exact_metrics_and_100_300_500_horizons():
    # 6 wins (+200 / +2.0R) and 4 losses (-100 / -1.0R) -> Win Rate 60%, PF = 1200/400 = 3.0, Avg Realized R:R = 2.0
    sample_10 = [
        _trade(1, 2.0, 200.0),
        _trade(2, -1.0, -100.0),
        _trade(3, -1.0, -100.0),
        _trade(4, 2.0, 200.0),
        _trade(5, 2.0, 200.0),
        _trade(6, -1.0, -100.0),
        _trade(7, 2.0, 200.0),
        _trade(8, 2.0, 200.0),
        _trade(9, -1.0, -100.0),
        _trade(10, 2.0, 200.0),
    ]
    s = calculate_performance_summary("BACKTEST", sample_10, initial_balance=10000.0)
    assert s.completed_trades == 10
    assert s.winning_trades == 6
    assert s.losing_trades == 4
    assert s.win_rate_pct == 60.0
    assert s.profit_factor == 3.0
    assert s.avg_rr_realized == 2.0
    assert s.net_profit_usd == 800.0
    assert s.max_drawdown_usd == 200.0
    assert s.total_spread_cost_usd_oz == 2.5
    assert s.total_slippage_cost_usd_oz == 3.0
    assert s.total_trading_costs_usd_oz == 5.5
    assert all(h.available is False for h in s.horizons)

    # 120 completed trades -> 100 available, 300 & 500 unavailable
    sample_120 = [_trade(i, 2.0 if i % 2 == 0 else -1.0, 200.0 if i % 2 == 0 else -100.0) for i in range(1, 121)]
    s120 = calculate_performance_summary("BACKTEST", sample_120)
    assert s120.horizons[0].available is True and s120.horizons[0].sample_size == 100
    assert s120.horizons[1].available is False
    assert s120.horizons[2].available is False

    # 520 completed trades -> 100, 300, 500 all available
    sample_520 = [_trade(i, 1.8 if i % 2 == 0 else -1.0, 180.0 if i % 2 == 0 else -100.0) for i in range(1, 521)]
    s520 = calculate_performance_summary("BACKTEST", sample_520)
    assert all(h.available is True for h in s520.horizons)
    assert [h.sample_size for h in s520.horizons] == [100, 300, 500]


@pytest.mark.asyncio
async def test_real_historical_gold_backtest_with_trading_costs():
    """Run real historical walk-forward backtest on 2-year H1 Gold candles and verify cost impact & timestamps."""
    init_db()
    bars, label = await load_historical_candles("H1", "extended_gold")
    assert len(bars) >= 500, f"Expected deep real H1 history, got {len(bars)}"

    req_low_cost = BacktestRequest(
        timeframe="H1",
        dataset="extended_gold",
        spread_usd=0.20,
        slippage_usd=0.10,
        initial_balance=10000.0,
        risk_percent=1.0,
        min_rr=2.0,
    )
    req_high_cost = BacktestRequest(
        timeframe="H1",
        dataset="extended_gold",
        spread_usd=0.80,
        slippage_usd=0.40,
        initial_balance=10000.0,
        risk_percent=1.0,
        min_rr=2.0,
    )

    rep_low = run_walk_forward_backtest_on_candles(bars, req_low_cost, label)
    rep_high = run_walk_forward_backtest_on_candles(bars, req_high_cost, label)

    assert rep_low.summary.execution_disabled is True
    assert rep_low.summary.mode == "BACKTEST"
    assert rep_low.summary.completed_trades > 20, f"Expected substantial real H1 signals, got {rep_low.summary.completed_trades}"
    assert rep_low.summary.total_trading_costs_usd_oz > 0
    assert rep_high.summary.total_trading_costs_usd_oz > rep_low.summary.total_trading_costs_usd_oz
    assert rep_high.summary.net_profit_r < rep_low.summary.net_profit_r

    # Verify timestamp ordering and non-overlapping trades
    for idx, t in enumerate(rep_low.trades):
        assert t.opened_at <= (t.closed_at or t.opened_at)
        if idx > 0:
            assert t.opened_at >= (rep_low.trades[idx - 1].closed_at or rep_low.trades[idx - 1].opened_at)

    print(
        f"\n[REAL 2Y H1 BACKTEST VERIFIED] {label} | Completed={rep_low.summary.completed_trades} | "
        f"WinRate={rep_low.summary.win_rate_pct}% | PF={rep_low.summary.profit_factor} | "
        f"MaxDD={rep_low.summary.max_drawdown_pct}% ({rep_low.summary.max_drawdown_r}R) | "
        f"AvgRR={rep_low.summary.avg_rr_realized} | Net={rep_low.summary.net_profit_r:+.2f}R "
        f"(${rep_low.summary.net_profit_usd:+.2f}) | Costs=${rep_low.summary.total_trading_costs_usd_oz:.2f}/oz"
    )
    for h in rep_low.summary.horizons:
        print(f"  Horizon {h.target_signals}: available={h.available} (done={h.completed_available}) WR={h.win_rate_pct}% PF={h.profit_factor} NetR={h.net_profit_r}")
