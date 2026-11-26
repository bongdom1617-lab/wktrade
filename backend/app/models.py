from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint, Index

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SignalRecord(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    signal_uid = Column(String(64), unique=True, nullable=False, index=True)
    symbol = Column(String(16), default="XAUUSD", nullable=False)
    action = Column(String(16), nullable=False)  # BUY | SELL | WAIT
    status = Column(String(32), default="ACTIVE", nullable=False)
    # ACTIVE | ENTRY_TRIGGERED | TP1_HIT | TP2_HIT | TP3_HIT | SL_HIT | INVALIDATED | EXPIRED | SUPERSEDED
    confidence = Column(Integer, nullable=False)
    setup_timeframe = Column(String(8), default="M15", nullable=False)

    entry_price = Column(Float, nullable=True)
    entry_zone_low = Column(Float, nullable=True)
    entry_zone_high = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    tp1 = Column(Float, nullable=True)
    tp2 = Column(Float, nullable=True)
    tp3 = Column(Float, nullable=True)
    risk_reward_tp1 = Column(Float, nullable=True)
    risk_reward_tp2 = Column(Float, nullable=True)
    risk_reward_tp3 = Column(Float, nullable=True)

    market_price_at_signal = Column(Float, nullable=False)
    data_provider = Column(String(64), nullable=False)
    summary = Column(Text, nullable=False)
    invalidation_conditions = Column(Text, nullable=False)  # JSON list
    explanation_json = Column(Text, nullable=False)
    mtf_snapshot_json = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_price = Column(Float, nullable=True)
    resolution_note = Column(Text, nullable=True)


class AlertEvent(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    severity = Column(String(16), nullable=False)  # INFO | SIGNAL | WARNING | CRITICAL
    category = Column(String(32), nullable=False)  # SIGNAL | TARGET | INVALIDATION | BREAKOUT | FEED | CANDLE
    title = Column(String(160), nullable=False)
    message = Column(Text, nullable=False)
    price = Column(Float, nullable=True)
    timeframe = Column(String(8), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)


class CandleCache(Base):
    __tablename__ = "candle_cache"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "open_time", name="uq_candle_sym_tf_time"),
        Index("ix_candle_tf_time", "timeframe", "open_time"),
    )

    id = Column(Integer, primary_key=True)
    symbol = Column(String(16), default="XAUUSD", nullable=False)
    timeframe = Column(String(8), nullable=False)
    open_time = Column(Integer, nullable=False)  # UNIX timestamp in seconds (UTC)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, default=0.0, nullable=False)
    provider = Column(String(64), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class ForwardTestTrade(Base):
    """
    Live non-executing paper forward-test ledger linked strictly to real-time AI signals.
    No broker orders are ever placed; tracks exact live fill, spread, slippage, and outcome.
    """

    __tablename__ = "forward_test_trades"

    id = Column(Integer, primary_key=True, index=True)
    signal_uid = Column(String(64), unique=True, nullable=False, index=True)
    symbol = Column(String(16), default="XAUUSD", nullable=False)
    action = Column(String(8), nullable=False)  # BUY | SELL
    timeframe = Column(String(8), default="M15", nullable=False)
    confidence = Column(Integer, nullable=False)
    data_provider = Column(String(64), nullable=False)

    status = Column(String(24), default="OPEN", nullable=False, index=True)
    # OPEN | COMPLETED | INVALIDATED
    outcome = Column(String(24), nullable=True)
    # TP1_HIT | TP2_HIT | TP3_HIT | SL_HIT | BREAKEVEN | INVALIDATED | SUPERSEDED

    signal_time = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)
    entry_filled_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    planned_entry = Column(Float, nullable=False)
    effective_entry = Column(Float, nullable=False)  # executable Bid/Ask + entry slippage
    stop_loss = Column(Float, nullable=False)
    tp1 = Column(Float, nullable=False)
    tp2 = Column(Float, nullable=False)
    tp3 = Column(Float, nullable=False)
    planned_rr = Column(Float, nullable=False)

    entry_spread_usd = Column(Float, default=0.20, nullable=False)
    exit_spread_usd = Column(Float, nullable=True)
    slippage_per_side_usd = Column(Float, default=0.15, nullable=False)
    total_spread_cost_usd = Column(Float, default=0.20, nullable=False)
    total_slippage_cost_usd = Column(Float, default=0.30, nullable=False)

    exit_price = Column(Float, nullable=True)
    effective_exit = Column(Float, nullable=True)
    gross_pnl_usd_oz = Column(Float, nullable=True)
    net_pnl_usd_oz = Column(Float, nullable=True)
    realized_r = Column(Float, nullable=True)
    tp1_hit = Column(Boolean, default=False, nullable=False)
    tp2_hit = Column(Boolean, default=False, nullable=False)
    tp3_hit = Column(Boolean, default=False, nullable=False)

    note = Column(Text, nullable=True)


class BacktestRun(Base):
    """Persisted historical XAUUSD backtesting run metadata and summary."""

    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_uid = Column(String(64), unique=True, nullable=False, index=True)
    symbol = Column(String(16), default="XAUUSD", nullable=False)
    timeframe = Column(String(8), nullable=False)
    dataset = Column(String(32), nullable=False)  # extended_gold | spot_cache | twelvedata
    dataset_label = Column(String(128), nullable=False)
    bars_analyzed = Column(Integer, nullable=False)
    period_start = Column(String(32), nullable=False)
    period_end = Column(String(32), nullable=False)

    spread_usd = Column(Float, nullable=False)
    slippage_usd = Column(Float, nullable=False)
    initial_balance = Column(Float, nullable=False)
    risk_percent = Column(Float, nullable=False)
    min_rr = Column(Float, nullable=False)
    exit_mode = Column(String(32), nullable=False)
    move_sl_to_be_at_tp1 = Column(Boolean, default=True, nullable=False)

    completed_trades = Column(Integer, nullable=False)
    win_rate_pct = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=False)
    net_profit_usd = Column(Float, nullable=False)
    net_profit_r = Column(Float, nullable=False)
    avg_rr_realized = Column(Float, nullable=True)

    summary_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)


class BacktestTrade(Base):
    """Individual timestamped verifiable signal executed analytically in a historical backtest."""

    __tablename__ = "backtest_trades"
    __table_args__ = (Index("ix_bt_trade_run_idx", "run_uid", "trade_index"),)

    id = Column(Integer, primary_key=True)
    run_uid = Column(String(64), nullable=False, index=True)
    trade_index = Column(Integer, nullable=False)
    signal_uid = Column(String(64), nullable=False)
    action = Column(String(8), nullable=False)  # BUY | SELL
    timeframe = Column(String(8), nullable=False)
    confidence = Column(Integer, nullable=False)

    opened_at = Column(String(32), nullable=False)
    closed_at = Column(String(32), nullable=False)
    bars_held = Column(Integer, nullable=False)

    planned_entry = Column(Float, nullable=False)
    effective_entry = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    tp1 = Column(Float, nullable=False)
    tp2 = Column(Float, nullable=False)
    tp3 = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    effective_exit = Column(Float, nullable=False)

    outcome = Column(String(24), nullable=False)
    planned_rr = Column(Float, nullable=False)
    realized_r = Column(Float, nullable=False)

    gross_pnl_usd_oz = Column(Float, nullable=False)
    spread_cost_usd_oz = Column(Float, nullable=False)
    slippage_cost_usd_oz = Column(Float, nullable=False)
    net_pnl_usd_oz = Column(Float, nullable=False)
    account_pnl_usd = Column(Float, nullable=False)
    equity_after = Column(Float, nullable=False)
    rationale = Column(Text, nullable=False)
