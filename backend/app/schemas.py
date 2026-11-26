from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


Timeframe = Literal["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
FeedStatus = Literal["LIVE", "DELAYED", "MARKET_CLOSED", "DISCONNECTED"]
SignalAction = Literal["BUY", "SELL", "WAIT"]
TrendDirection = Literal["BULLISH", "BEARISH", "NEUTRAL"]
VolatilityRegime = Literal["LOW", "NORMAL", "HIGH", "EXTREME"]


class LiveQuote(BaseModel):
    symbol: str = "XAUUSD"
    bid: float
    ask: float
    mid: float
    spread: float
    spread_bps: float = 0.0
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    prev_close: Optional[float] = None
    change_usd: Optional[float] = None
    change_percent: Optional[float] = None
    direction: Optional[str] = None
    provider: str
    secondary_provider: Optional[str] = None
    secondary_mid: Optional[float] = None
    provider_discrepancy_usd: Optional[float] = None
    quote_timestamp: str  # ISO8601 UTC
    fetched_at: str  # ISO8601 UTC
    quote_age_seconds: float
    market_state: str = "open"
    status: FeedStatus = "LIVE"
    warning: Optional[str] = None


class Candle(BaseModel):
    time: int  # Unix epoch seconds UTC (exact TradingView Lightweight Charts format)
    open_time_iso: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    is_open: bool = False


class CandleSeriesResponse(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: Timeframe
    provider: str
    status: FeedStatus
    last_updated: str
    bar_count: int
    candles: List[Candle]
    overlays: Optional[Dict[str, Any]] = None


class ProviderHealth(BaseModel):
    name: str
    role: str  # primary | secondary | optional
    reachable: bool
    latency_ms: Optional[float] = None
    last_success: Optional[str] = None
    last_error: Optional[str] = None


class FeedHealthResponse(BaseModel):
    status: FeedStatus
    active_quote_provider: Optional[str] = None
    active_candle_provider: Optional[str] = None
    quote_age_seconds: Optional[float] = None
    market_state: str = "unknown"
    last_update: Optional[str] = None
    message: str
    providers: List[ProviderHealth] = Field(default_factory=list)
    timeframe_bar_counts: Dict[str, int] = Field(default_factory=dict)


class EmaValues(BaseModel):
    ema_9: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    ema_100: Optional[float] = None
    ema_200: Optional[float] = None
    ema_200_warmed: bool = False
    bars_used: int = 0
    alignment: str = "MIXED"  # STRONG_BULLISH | BULLISH | MIXED | BEARISH | STRONG_BEARISH
    price_vs_ema200_usd: Optional[float] = None


class RsiValues(BaseModel):
    value: Optional[float] = None
    previous: Optional[float] = None
    zone: str = "NEUTRAL"  # OVERBOUGHT | BULLISH_MOMENTUM | NEUTRAL | BEARISH_MOMENTUM | OVERSOLD
    slope: str = "FLAT"  # RISING | FALLING | FLAT
    divergence: Optional[str] = None  # BULLISH_DIVERGENCE | BEARISH_DIVERGENCE | None


class MacdValues(BaseModel):
    macd: Optional[float] = None
    signal: Optional[float] = None
    histogram: Optional[float] = None
    previous_histogram: Optional[float] = None
    crossover: Optional[str] = None  # BULLISH_CROSS | BEARISH_CROSS | None
    momentum_state: str = "NEUTRAL"  # EXPANDING_BULLISH | FADING_BULLISH | EXPANDING_BEARISH | FADING_BEARISH | NEUTRAL


class BollingerValues(BaseModel):
    upper: Optional[float] = None
    middle: Optional[float] = None
    lower: Optional[float] = None
    bandwidth_pct: Optional[float] = None
    percent_b: Optional[float] = None
    squeeze: bool = False
    position: str = "MIDDLE"  # ABOVE_UPPER | UPPER_HALF | LOWER_HALF | BELOW_LOWER


class AtrValues(BaseModel):
    value: Optional[float] = None
    percent_of_price: Optional[float] = None
    baseline_avg: Optional[float] = None
    ratio_to_baseline: Optional[float] = None
    regime: VolatilityRegime = "NORMAL"


class AdxValues(BaseModel):
    adx: Optional[float] = None
    plus_di: Optional[float] = None
    minus_di: Optional[float] = None
    trend_strength: str = "WEAK"  # ABSENT | WEAK | MODERATE | STRONG | EXTREME


class StochasticValues(BaseModel):
    k: Optional[float] = None
    d: Optional[float] = None
    zone: str = "NEUTRAL"  # OVERBOUGHT | NEUTRAL | OVERSOLD
    crossover: Optional[str] = None  # BULLISH_CROSS | BEARISH_CROSS | None


class VwapValues(BaseModel):
    value: Optional[float] = None
    applicable: bool = True
    distance_usd: Optional[float] = None
    position: str = "N/A"  # ABOVE | BELOW | AT_VWAP | N/A


class SupportResistanceLevel(BaseModel):
    price: float
    kind: Literal["SUPPORT", "RESISTANCE"]
    strength: int  # 1-5
    touches: int
    distance_usd: float
    distance_pct: float
    source: str  # swing_cluster | daily_pivot | psychological


class CandlestickPattern(BaseModel):
    name: str
    bias: TrendDirection
    strength: Literal["LOW", "MEDIUM", "HIGH"]
    candle_time: str
    description: str


class BreakoutAssessment(BaseModel):
    status: Literal["NONE", "BULLISH_BREAKOUT", "BEARISH_BREAKOUT", "BULLISH_FALSE_BREAKOUT", "BEARISH_FALSE_BREAKOUT"]
    level: Optional[float] = None
    description: str


class MarketStructureInfo(BaseModel):
    structure_trend: TrendDirection
    pattern: str  # HH_HL | LH_LL | CONSOLIDATION | TRANSITION
    last_swing_high: Optional[float] = None
    last_swing_low: Optional[float] = None
    prev_swing_high: Optional[float] = None
    prev_swing_low: Optional[float] = None
    bos: Optional[str] = None  # BULLISH_BOS | BEARISH_BOS | None
    choch: Optional[str] = None  # BULLISH_CHOCH | BEARISH_CHOCH | None
    reversal_warning: Optional[str] = None


class TimeframeAnalysis(BaseModel):
    timeframe: Timeframe
    role: str
    weight: float
    bar_count: int
    last_candle_time: str
    last_close: float
    trend: TrendDirection
    trend_score: float  # -100 to +100
    momentum_state: str
    ema: EmaValues
    rsi: RsiValues
    macd: MacdValues
    bollinger: BollingerValues
    atr: AtrValues
    adx: AdxValues
    stochastic: StochasticValues
    vwap: VwapValues
    structure: MarketStructureInfo
    support_levels: List[SupportResistanceLevel] = Field(default_factory=list)
    resistance_levels: List[SupportResistanceLevel] = Field(default_factory=list)
    patterns: List[CandlestickPattern] = Field(default_factory=list)
    breakout: BreakoutAssessment
    summary: str


class TimeframeConflict(BaseModel):
    severity: Literal["LOW", "MODERATE", "HIGH"]
    code: str
    timeframes: List[str]
    description: str


class MtfSynthesis(BaseModel):
    overall_bias: TrendDirection
    alignment_score: float  # 0 to 100
    weighted_score: float  # -100 to +100
    bullish_count: int
    bearish_count: int
    neutral_count: int
    has_major_conflict: bool
    conflicts: List[TimeframeConflict] = Field(default_factory=list)
    timeframes: Dict[str, TimeframeAnalysis] = Field(default_factory=dict)


class LevelRationale(BaseModel):
    level_name: str
    price: float
    distance_usd: float
    risk_reward: Optional[float] = None
    reason: str


class RiskPlan(BaseModel):
    direction: Literal["BUY", "SELL"]
    entry_price: float
    entry_zone_low: float
    entry_zone_high: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    risk_usd: float
    reward_tp1_usd: float
    reward_tp2_usd: float
    reward_tp3_usd: float
    rr_tp1: float
    rr_tp2: float
    rr_tp3: float
    meets_min_rr: bool
    atr_reference: float
    volatility_regime: VolatilityRegime
    rationales: List[LevelRationale] = Field(default_factory=list)


class AiExplanation(BaseModel):
    what_is_gold_doing: str
    market_direction: str
    decision_headline: str
    why_decision: str
    confirmations: List[str] = Field(default_factory=list)
    missing_or_warnings: List[str] = Field(default_factory=list)
    invalidation_conditions: List[str] = Field(default_factory=list)
    when_to_avoid: List[str] = Field(default_factory=list)
    level_reasoning: List[str] = Field(default_factory=list)
    engine_mode: str = "Structured Quantitative AI Engine"


class TradingSignal(BaseModel):
    signal_uid: str
    symbol: str = "XAUUSD"
    action: SignalAction
    status: str = "ACTIVE"
    confidence: int  # 0-100
    setup_timeframe: Timeframe = "M15"
    generated_at: str
    market_price: float
    data_provider: str
    feed_status: FeedStatus
    risk_plan: Optional[RiskPlan] = None
    watchlist_levels: Optional[Dict[str, Any]] = None
    explanation: AiExplanation
    disclaimer: str = (
        "Analytical decision-support only. Not financial advice and does not guarantee profits. "
        "No broker connection or automatic trade execution."
    )


class SignalHistoryItem(BaseModel):
    id: int
    signal_uid: str
    action: SignalAction
    status: str
    confidence: int
    setup_timeframe: str
    entry_price: Optional[float] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    risk_reward_tp2: Optional[float] = None
    market_price_at_signal: float
    data_provider: str
    summary: str
    created_at: str
    resolved_at: Optional[str] = None
    resolution_price: Optional[float] = None
    resolution_note: Optional[str] = None


class AlertItem(BaseModel):
    id: int
    severity: str
    category: str
    title: str
    message: str
    price: Optional[float] = None
    timeframe: Optional[str] = None
    created_at: str


class DashboardSnapshot(BaseModel):
    timestamp: str
    quote: Optional[LiveQuote] = None
    feed_health: FeedHealthResponse
    mtf: Optional[MtfSynthesis] = None
    signal: Optional[TradingSignal] = None
    active_trade_monitor: Optional[Dict[str, Any]] = None
    recent_signals: List[SignalHistoryItem] = Field(default_factory=list)
    recent_alerts: List[AlertItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AI Signal Performance, Historical Backtesting & Forward-Testing Schemas
# ---------------------------------------------------------------------------

class PerformanceTradeRecord(BaseModel):
    signal_uid: str
    mode: Literal["BACKTEST", "FORWARD_TEST"]
    action: Literal["BUY", "SELL"]
    timeframe: str
    confidence: int
    status: str  # COMPLETED | OPEN | INVALIDATED
    outcome: Optional[str] = None  # TP1_HIT | TP2_HIT | TP3_HIT | SL_HIT | BREAKEVEN | INVALIDATED | TIME_EXIT | OPEN
    opened_at: str
    closed_at: Optional[str] = None
    bars_held: Optional[int] = None
    planned_entry: float
    effective_entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    exit_price: Optional[float] = None
    effective_exit: Optional[float] = None
    planned_rr: float
    realized_r: Optional[float] = None
    gross_pnl_usd_oz: Optional[float] = None
    spread_cost_usd_oz: float
    slippage_cost_usd_oz: float
    total_cost_usd_oz: float
    net_pnl_usd_oz: Optional[float] = None
    account_pnl_usd: Optional[float] = None
    equity_after: Optional[float] = None
    rationale: str = ""


class EquityPoint(BaseModel):
    trade_number: int
    timestamp: str
    equity_usd: float
    cumulative_r: float
    drawdown_pct: float
    drawdown_r: float


class PerformanceHorizonWindow(BaseModel):
    target_signals: int  # 100 | 300 | 500
    available: bool
    completed_available: int
    sample_size: int
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    win_rate_pct: Optional[float] = None
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    profit_factor: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_drawdown_r: Optional[float] = None
    avg_rr_planned: Optional[float] = None
    avg_rr_realized: Optional[float] = None
    expectancy_r: Optional[float] = None
    net_profit_r: Optional[float] = None
    net_profit_usd: Optional[float] = None
    total_trading_costs_usd_oz: Optional[float] = None
    note: str


class PerformanceSummary(BaseModel):
    mode: Literal["BACKTEST", "FORWARD_TEST"]
    execution_disabled: bool = True
    completed_trades: int
    open_trades: int = 0
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    max_drawdown_usd: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_r: float = 0.0
    avg_rr_planned: Optional[float] = None
    avg_rr_realized: Optional[float] = None
    avg_win_r: Optional[float] = None
    avg_loss_r: Optional[float] = None
    expectancy_r: Optional[float] = None
    expectancy_usd: Optional[float] = None
    gross_profit_usd: float = 0.0
    gross_loss_usd: float = 0.0
    net_profit_usd: float = 0.0
    net_profit_pct: float = 0.0
    net_profit_r: float = 0.0
    avg_win_usd: Optional[float] = None
    avg_loss_usd: Optional[float] = None
    largest_win_usd: Optional[float] = None
    largest_loss_usd: Optional[float] = None
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    total_spread_cost_usd_oz: float = 0.0
    total_slippage_cost_usd_oz: float = 0.0
    total_trading_costs_usd_oz: float = 0.0
    total_trading_costs_account_usd: float = 0.0
    initial_balance: float = 10000.0
    ending_balance: float = 10000.0
    risk_percent: float = 1.0
    tp1_hit_count: int = 0
    tp2_hit_count: int = 0
    tp3_hit_count: int = 0
    sl_hit_count: int = 0
    invalidated_count: int = 0
    horizons: List[PerformanceHorizonWindow] = Field(default_factory=list)
    equity_curve: List[EquityPoint] = Field(default_factory=list)
    verification_note: str


class BacktestRequest(BaseModel):
    timeframe: Literal["M5", "M15", "M30", "H1", "H4", "D1"] = "H1"
    dataset: Literal["extended_gold", "spot_cache", "twelvedata"] = "extended_gold"
    spread_usd: float = Field(default=0.25, ge=0.0, le=5.0)
    slippage_usd: float = Field(default=0.15, ge=0.0, le=5.0)
    initial_balance: float = Field(default=10000.0, ge=100.0, le=10000000.0)
    risk_percent: float = Field(default=1.0, ge=0.1, le=5.0)
    min_rr: float = Field(default=2.0, ge=1.5, le=4.0)
    exit_mode: Literal["scaled_tp1_tp2_tp3", "tp2_primary"] = "scaled_tp1_tp2_tp3"
    move_sl_to_be_at_tp1: bool = True


class BacktestReport(BaseModel):
    run_uid: str
    created_at: str
    symbol: str = "XAUUSD"
    timeframe: str
    dataset: str
    dataset_label: str
    bars_analyzed: int
    period_start: str
    period_end: str
    parameters: Dict[str, Any]
    summary: PerformanceSummary
    trades: List[PerformanceTradeRecord] = Field(default_factory=list)


class BacktestRunSummaryItem(BaseModel):
    run_uid: str
    created_at: str
    timeframe: str
    dataset: str
    dataset_label: str
    bars_analyzed: int
    period_start: str
    period_end: str
    completed_trades: int
    win_rate_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    max_drawdown_pct: float
    net_profit_usd: float
    net_profit_r: float
    avg_rr_realized: Optional[float] = None
    spread_usd: float
    slippage_usd: float
    exit_mode: str


class ForwardTestReport(BaseModel):
    generated_at: str
    data_provider: str
    execution_disabled: bool = True
    assumed_slippage_per_side_usd: float
    summary: PerformanceSummary
    open_signals: List[PerformanceTradeRecord] = Field(default_factory=list)
    completed_signals: List[PerformanceTradeRecord] = Field(default_factory=list)


class PerformanceOverviewResponse(BaseModel):
    generated_at: str
    execution_disabled: bool = True
    forward_test: ForwardTestReport
    latest_backtest: Optional[BacktestReport] = None
    backtest_runs: List[BacktestRunSummaryItem] = Field(default_factory=list)
