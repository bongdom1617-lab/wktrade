export type Timeframe = "M1" | "M5" | "M15" | "M30" | "H1" | "H4" | "D1";
export type FeedStatus = "LIVE" | "DELAYED" | "MARKET_CLOSED" | "DISCONNECTED";
export type SignalAction = "BUY" | "SELL" | "WAIT";
export type TrendDirection = "BULLISH" | "BEARISH" | "NEUTRAL";
export type VolatilityRegime = "LOW" | "NORMAL" | "HIGH" | "EXTREME";

export interface LiveQuote {
  symbol: string;
  bid: number;
  ask: number;
  mid: number;
  spread: number;
  spread_bps: number;
  day_high: number | null;
  day_low: number | null;
  prev_close: number | null;
  change_usd: number | null;
  change_percent: number | null;
  direction: string | null;
  provider: string;
  secondary_provider: string | null;
  secondary_mid: number | null;
  provider_discrepancy_usd: number | null;
  quote_timestamp: string;
  fetched_at: string;
  quote_age_seconds: number;
  market_state: string;
  status: FeedStatus;
  warning: string | null;
}

export interface Candle {
  time: number;
  open_time_iso: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_open: boolean;
}

export interface TimeValuePoint {
  time: number;
  value: number;
}

export interface ChartOverlays {
  ema_9?: TimeValuePoint[];
  ema_20?: TimeValuePoint[];
  ema_50?: TimeValuePoint[];
  ema_100?: TimeValuePoint[];
  ema_200?: TimeValuePoint[];
  bb_upper?: TimeValuePoint[];
  bb_middle?: TimeValuePoint[];
  bb_lower?: TimeValuePoint[];
  vwap?: TimeValuePoint[];
  rsi_14?: TimeValuePoint[];
  macd_line?: TimeValuePoint[];
  macd_signal?: TimeValuePoint[];
  macd_hist?: TimeValuePoint[];
}

export interface CandleSeriesResponse {
  symbol: string;
  timeframe: Timeframe;
  provider: string;
  status: FeedStatus;
  last_updated: string;
  bar_count: number;
  candles: Candle[];
  overlays: ChartOverlays | null;
}

export interface ProviderHealth {
  name: string;
  role: string;
  reachable: boolean;
  latency_ms: number | null;
  last_success: string | null;
  last_error: string | null;
}

export interface FeedHealthResponse {
  status: FeedStatus;
  active_quote_provider: string | null;
  active_candle_provider: string | null;
  quote_age_seconds: number | null;
  market_state: string;
  last_update: string | null;
  message: string;
  providers: ProviderHealth[];
  timeframe_bar_counts: Record<string, number>;
}

export interface EmaValues {
  ema_9: number | null;
  ema_20: number | null;
  ema_50: number | null;
  ema_100: number | null;
  ema_200: number | null;
  ema_200_warmed: boolean;
  bars_used: number;
  alignment: string;
  price_vs_ema200_usd: number | null;
}

export interface RsiValues {
  value: number | null;
  previous: number | null;
  zone: string;
  slope: string;
  divergence: string | null;
}

export interface MacdValues {
  macd: number | null;
  signal: number | null;
  histogram: number | null;
  previous_histogram: number | null;
  crossover: string | null;
  momentum_state: string;
}

export interface BollingerValues {
  upper: number | null;
  middle: number | null;
  lower: number | null;
  bandwidth_pct: number | null;
  percent_b: number | null;
  squeeze: boolean;
  position: string;
}

export interface AtrValues {
  value: number | null;
  percent_of_price: number | null;
  baseline_avg: number | null;
  ratio_to_baseline: number | null;
  regime: VolatilityRegime;
}

export interface AdxValues {
  adx: number | null;
  plus_di: number | null;
  minus_di: number | null;
  trend_strength: string;
}

export interface StochasticValues {
  k: number | null;
  d: number | null;
  zone: string;
  crossover: string | null;
}

export interface VwapValues {
  value: number | null;
  applicable: boolean;
  distance_usd: number | null;
  position: string;
}

export interface SupportResistanceLevel {
  price: number;
  kind: "SUPPORT" | "RESISTANCE";
  strength: number;
  touches: number;
  distance_usd: number;
  distance_pct: number;
  source: string;
}

export interface CandlestickPattern {
  name: string;
  bias: TrendDirection;
  strength: "LOW" | "MEDIUM" | "HIGH";
  candle_time: string;
  description: string;
}

export interface BreakoutAssessment {
  status: string;
  level: number | null;
  description: string;
}

export interface MarketStructureInfo {
  structure_trend: TrendDirection;
  pattern: string;
  last_swing_high: number | null;
  last_swing_low: number | null;
  prev_swing_high: number | null;
  prev_swing_low: number | null;
  bos: string | null;
  choch: string | null;
  reversal_warning: string | null;
}

export interface TimeframeAnalysis {
  timeframe: Timeframe;
  role: string;
  weight: number;
  bar_count: number;
  last_candle_time: string;
  last_close: number;
  trend: TrendDirection;
  trend_score: number;
  momentum_state: string;
  ema: EmaValues;
  rsi: RsiValues;
  macd: MacdValues;
  bollinger: BollingerValues;
  atr: AtrValues;
  adx: AdxValues;
  stochastic: StochasticValues;
  vwap: VwapValues;
  structure: MarketStructureInfo;
  support_levels: SupportResistanceLevel[];
  resistance_levels: SupportResistanceLevel[];
  patterns: CandlestickPattern[];
  breakout: BreakoutAssessment;
  summary: string;
}

export interface TimeframeConflict {
  severity: "LOW" | "MODERATE" | "HIGH";
  code: string;
  timeframes: string[];
  description: string;
}

export interface MtfSynthesis {
  overall_bias: TrendDirection;
  alignment_score: number;
  weighted_score: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  has_major_conflict: boolean;
  conflicts: TimeframeConflict[];
  timeframes: Record<string, TimeframeAnalysis>;
}

export interface LevelRationale {
  level_name: string;
  price: number;
  distance_usd: number;
  risk_reward: number | null;
  reason: string;
}

export interface RiskPlan {
  direction: "BUY" | "SELL";
  entry_price: number;
  entry_zone_low: number;
  entry_zone_high: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  risk_usd: number;
  reward_tp1_usd: number;
  reward_tp2_usd: number;
  reward_tp3_usd: number;
  rr_tp1: number;
  rr_tp2: number;
  rr_tp3: number;
  meets_min_rr: boolean;
  atr_reference: number;
  volatility_regime: VolatilityRegime;
  rationales: LevelRationale[];
}

export interface AiExplanation {
  what_is_gold_doing: string;
  market_direction: string;
  decision_headline: string;
  why_decision: string;
  confirmations: string[];
  missing_or_warnings: string[];
  invalidation_conditions: string[];
  when_to_avoid: string[];
  level_reasoning: string[];
  engine_mode: string;
}

export interface TradingSignal {
  signal_uid: string;
  symbol: string;
  action: SignalAction;
  status: string;
  confidence: number;
  setup_timeframe: Timeframe;
  generated_at: string;
  market_price: number;
  data_provider: string;
  feed_status: FeedStatus;
  risk_plan: RiskPlan | null;
  watchlist_levels: {
    note?: string;
    bullish_breakout_trigger?: number | null;
    bearish_breakdown_trigger?: number | null;
    m15_ema20?: number | null;
    h1_ema50?: number | null;
    m15_atr?: number | null;
  } | null;
  explanation: AiExplanation;
  disclaimer: string;
}

export interface ActiveTradeMonitor {
  signal_uid: string;
  action: "BUY" | "SELL";
  status: string;
  confidence: number;
  entry_price: number;
  entry_zone_low: number;
  entry_zone_high: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  rr_tp1: number;
  rr_tp2: number;
  rr_tp3: number;
  created_at: string;
  tp1_reached: boolean;
  tp2_reached: boolean;
  tp3_reached: boolean;
  entry_filled: boolean;
  current_exit_price?: number;
  floating_pnl_usd?: number;
  floating_r?: number;
}

export interface SignalHistoryItem {
  id: number;
  signal_uid: string;
  action: SignalAction;
  status: string;
  confidence: number;
  setup_timeframe: string;
  entry_price: number | null;
  entry_zone_low: number | null;
  entry_zone_high: number | null;
  stop_loss: number | null;
  tp1: number | null;
  tp2: number | null;
  tp3: number | null;
  risk_reward_tp2: number | null;
  market_price_at_signal: number;
  data_provider: string;
  summary: string;
  created_at: string;
  resolved_at: string | null;
  resolution_price: number | null;
  resolution_note: string | null;
}

export interface AlertItem {
  id: number;
  severity: string;
  category: string;
  title: string;
  message: string;
  price: number | null;
  timeframe: string | null;
  created_at: string;
}

export interface DashboardSnapshot {
  timestamp: string;
  quote: LiveQuote | null;
  feed_health: FeedHealthResponse;
  mtf: MtfSynthesis | null;
  signal: TradingSignal | null;
  active_trade_monitor: ActiveTradeMonitor | null;
  recent_signals: SignalHistoryItem[];
  recent_alerts: AlertItem[];
}

export interface RiskPreviewResponse {
  matches_ai_signal: boolean;
  current_ai_action: SignalAction;
  account_balance: number;
  risk_percent: number;
  risk_amount_usd: number;
  suggested_ounces: number;
  suggested_lots: number;
  potential_profit_tp1_usd: number;
  potential_profit_tp2_usd: number;
  potential_profit_tp3_usd: number;
  risk_plan: RiskPlan;
}

// ---------------------------------------------------------------------------
// AI Signal Performance, Historical Backtesting & Forward-Testing Types
// ---------------------------------------------------------------------------

export interface PerformanceTradeRecord {
  signal_uid: string;
  mode: "BACKTEST" | "FORWARD_TEST";
  action: "BUY" | "SELL";
  timeframe: string;
  confidence: number;
  status: string;
  outcome: string | null;
  opened_at: string;
  closed_at: string | null;
  bars_held: number | null;
  planned_entry: number;
  effective_entry: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  exit_price: number | null;
  effective_exit: number | null;
  planned_rr: number;
  realized_r: number | null;
  gross_pnl_usd_oz: number | null;
  spread_cost_usd_oz: number;
  slippage_cost_usd_oz: number;
  total_cost_usd_oz: number;
  net_pnl_usd_oz: number | null;
  account_pnl_usd: number | null;
  equity_after: number | null;
  rationale: string;
}

export interface EquityPoint {
  trade_number: number;
  timestamp: string;
  equity_usd: number;
  cumulative_r: number;
  drawdown_pct: number;
  drawdown_r: number;
}

export interface PerformanceHorizonWindow {
  target_signals: number;
  available: boolean;
  completed_available: number;
  sample_size: number;
  period_start: string | null;
  period_end: string | null;
  win_rate_pct: number | null;
  winning_trades: number;
  losing_trades: number;
  breakeven_trades: number;
  profit_factor: number | null;
  max_drawdown_pct: number | null;
  max_drawdown_r: number | null;
  avg_rr_planned: number | null;
  avg_rr_realized: number | null;
  expectancy_r: number | null;
  net_profit_r: number | null;
  net_profit_usd: number | null;
  total_trading_costs_usd_oz: number | null;
  note: string;
}

export interface PerformanceSummary {
  mode: "BACKTEST" | "FORWARD_TEST";
  execution_disabled: boolean;
  completed_trades: number;
  open_trades: number;
  winning_trades: number;
  losing_trades: number;
  breakeven_trades: number;
  win_rate_pct: number | null;
  profit_factor: number | null;
  max_drawdown_usd: number;
  max_drawdown_pct: number;
  max_drawdown_r: number;
  avg_rr_planned: number | null;
  avg_rr_realized: number | null;
  avg_win_r: number | null;
  avg_loss_r: number | null;
  expectancy_r: number | null;
  expectancy_usd: number | null;
  gross_profit_usd: number;
  gross_loss_usd: number;
  net_profit_usd: number;
  net_profit_pct: number;
  net_profit_r: number;
  avg_win_usd: number | null;
  avg_loss_usd: number | null;
  largest_win_usd: number | null;
  largest_loss_usd: number | null;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  total_spread_cost_usd_oz: number;
  total_slippage_cost_usd_oz: number;
  total_trading_costs_usd_oz: number;
  total_trading_costs_account_usd: number;
  initial_balance: number;
  ending_balance: number;
  risk_percent: number;
  tp1_hit_count: number;
  tp2_hit_count: number;
  tp3_hit_count: number;
  sl_hit_count: number;
  invalidated_count: number;
  horizons: PerformanceHorizonWindow[];
  equity_curve: EquityPoint[];
  verification_note: string;
}

export interface BacktestRequestPayload {
  timeframe: "M5" | "M15" | "M30" | "H1" | "H4" | "D1";
  dataset: "extended_gold" | "spot_cache" | "twelvedata";
  spread_usd: number;
  slippage_usd: number;
  initial_balance: number;
  risk_percent: number;
  min_rr: number;
  exit_mode: "scaled_tp1_tp2_tp3" | "tp2_primary";
  move_sl_to_be_at_tp1: boolean;
}

export interface BacktestReport {
  run_uid: string;
  created_at: string;
  symbol: string;
  timeframe: string;
  dataset: string;
  dataset_label: string;
  bars_analyzed: number;
  period_start: string;
  period_end: string;
  parameters: BacktestRequestPayload;
  summary: PerformanceSummary;
  trades: PerformanceTradeRecord[];
}

export interface BacktestRunSummaryItem {
  run_uid: string;
  created_at: string;
  timeframe: string;
  dataset: string;
  dataset_label: string;
  bars_analyzed: number;
  period_start: string;
  period_end: string;
  completed_trades: number;
  win_rate_pct: number | null;
  profit_factor: number | null;
  max_drawdown_pct: number;
  net_profit_usd: number;
  net_profit_r: number;
  avg_rr_realized: number | null;
  spread_usd: number;
  slippage_usd: number;
  exit_mode: string;
}

export interface ForwardTestReport {
  generated_at: string;
  data_provider: string;
  execution_disabled: boolean;
  assumed_slippage_per_side_usd: number;
  summary: PerformanceSummary;
  open_signals: PerformanceTradeRecord[];
  completed_signals: PerformanceTradeRecord[];
}

export interface PerformanceOverviewResponse {
  generated_at: string;
  execution_disabled: boolean;
  forward_test: ForwardTestReport;
  latest_backtest: BacktestReport | null;
  backtest_runs: BacktestRunSummaryItem[];
}
