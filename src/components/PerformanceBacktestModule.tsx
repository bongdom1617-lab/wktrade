"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Award,
  BarChart2,
  CheckCircle2,
  Clock,
  FlaskConical,
  GitCompare,
  Lock,
  Play,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import EquityCurveChart from "@/components/EquityCurveChart";
import {
  fetchBacktestRunDetail,
  fetchPerformanceOverview,
  runHistoricalBacktest,
} from "@/lib/api";
import { fmtDateTime, fmtPct, fmtPrice, fmtUsd } from "@/lib/format";
import type {
  BacktestReport,
  BacktestRequestPayload,
  PerformanceOverviewResponse,
  PerformanceSummary,
  PerformanceTradeRecord,
} from "@/lib/types";

type ActiveTab = "backtest" | "forward" | "compare";
type TradeFilter = "ALL" | "WIN" | "LOSS" | "BUY" | "SELL";

interface PerformanceBacktestModuleProps {
  syncKey?: string;
}

export default function PerformanceBacktestModule({ syncKey }: PerformanceBacktestModuleProps) {
  const [tab, setTab] = useState<ActiveTab>("backtest");
  const [overview, setOverview] = useState<PerformanceOverviewResponse | null>(null);
  const [activeBacktest, setActiveBacktest] = useState<BacktestReport | null>(null);
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [runningBt, setRunningBt] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Backtest configuration controls
  const [form, setForm] = useState<BacktestRequestPayload>({
    timeframe: "H1",
    dataset: "extended_gold",
    spread_usd: 0.25,
    slippage_usd: 0.15,
    initial_balance: 10000,
    risk_percent: 1.0,
    min_rr: 2.0,
    exit_mode: "scaled_tp1_tp2_tp3",
    move_sl_to_be_at_tp1: true,
  });

  const [tradeFilter, setTradeFilter] = useState<TradeFilter>("ALL");
  const [visibleLimit, setVisibleLimit] = useState<number>(30);

  const loadOverview = useCallback(async () => {
    setLoadingOverview(true);
    try {
      const data = await fetchPerformanceOverview();
      setOverview(data);
      if (data.latest_backtest) {
        setActiveBacktest((prev) => prev || data.latest_backtest);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load performance overview");
    } finally {
      setLoadingOverview(false);
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview, syncKey]);

  // Automatic self-healing retry if backend was temporarily restarting
  useEffect(() => {
    if (!error) return;
    const retry = setTimeout(() => {
      loadOverview();
    }, 5000);
    return () => clearTimeout(retry);
  }, [error, loadOverview]);

  const handleRunBacktest = async () => {
    setRunningBt(true);
    setError(null);
    try {
      const report = await runHistoricalBacktest(form);
      setActiveBacktest(report);
      setVisibleLimit(30);
      setTab("backtest");
      const fresh = await fetchPerformanceOverview();
      setOverview(fresh);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Historical backtest failed");
    } finally {
      setRunningBt(false);
    }
  };

  const handleSelectSavedRun = async (runUid: string) => {
    if (!runUid) return;
    setError(null);
    try {
      const detail = await fetchBacktestRunDetail(runUid);
      setActiveBacktest(detail);
      setVisibleLimit(30);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed loading saved backtest run");
    }
  };

  const forwardReport = overview?.forward_test ?? null;
  const btSummary = activeBacktest?.summary ?? null;
  const fwSummary = forwardReport?.summary ?? null;

  const filteredTrades = useMemo(() => {
    const source: PerformanceTradeRecord[] =
      tab === "forward"
        ? [...(forwardReport?.open_signals ?? []), ...(forwardReport?.completed_signals ?? [])]
        : [...(activeBacktest?.trades ?? [])].reverse();

    return source.filter((t) => {
      if (tradeFilter === "ALL") return true;
      if (tradeFilter === "BUY") return t.action === "BUY";
      if (tradeFilter === "SELL") return t.action === "SELL";
      if (tradeFilter === "WIN") return (t.realized_r ?? 0) > 0.02;
      if (tradeFilter === "LOSS") return (t.realized_r ?? 0) < -0.02;
      return true;
    });
  }, [tab, forwardReport, activeBacktest, tradeFilter]);

  const renderSummaryCards = (s: PerformanceSummary | null) => {
    if (!s) return null;
    const hasCompleted = s.completed_trades > 0;
    return (
      <div className="space-y-4">
        {/* Core KPI Strip */}
        <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-6">
          {/* Win Rate */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Win Rate</div>
            <div className="mt-1 font-mono text-xl font-bold text-white tabular-nums">
              {s.win_rate_pct !== null ? `${s.win_rate_pct.toFixed(1)}%` : "N/A"}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
              <span className="text-emerald-400">{s.winning_trades}W</span> /{" "}
              <span className="text-red-400">{s.losing_trades}L</span>
              {s.breakeven_trades > 0 ? ` / ${s.breakeven_trades}BE` : ""}
            </div>
          </div>

          {/* Profit Factor */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Profit Factor</div>
            <div
              className={`mt-1 font-mono text-xl font-bold tabular-nums ${
                s.profit_factor === null
                  ? "text-slate-400"
                  : s.profit_factor >= 1.25
                    ? "text-emerald-400"
                    : s.profit_factor >= 1.0
                      ? "text-amber-300"
                      : "text-red-400"
              }`}
            >
              {s.profit_factor !== null ? s.profit_factor.toFixed(2) : "N/A"}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
              GP {fmtUsd(s.gross_profit_usd, 0)} / GL {fmtUsd(s.gross_loss_usd, 0)}
            </div>
          </div>

          {/* Max Drawdown */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Max Drawdown</div>
            <div className="mt-1 font-mono text-xl font-bold text-red-400 tabular-nums">
              {hasCompleted ? `-${s.max_drawdown_pct.toFixed(2)}%` : "N/A"}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
              {hasCompleted ? `-${fmtUsd(s.max_drawdown_usd, 2)} (${s.max_drawdown_r.toFixed(2)}R)` : "0 completed"}
            </div>
          </div>

          {/* Average Risk-to-Reward */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Avg Risk:Reward</div>
            <div className="mt-1 font-mono text-xl font-bold text-sky-300 tabular-nums">
              {s.avg_rr_realized !== null ? `1:${s.avg_rr_realized.toFixed(2)}` : "N/A"}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
              Plan {s.avg_rr_planned !== null ? `1:${s.avg_rr_planned.toFixed(2)}` : "—"} • Exp{" "}
              {s.expectancy_r !== null ? `${s.expectancy_r >= 0 ? "+" : ""}${s.expectancy_r.toFixed(2)}R` : "—"}
            </div>
          </div>

          {/* Net Return (Net of Costs) */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Net P&L (After Costs)</div>
            <div
              className={`mt-1 font-mono text-xl font-bold tabular-nums ${
                !hasCompleted
                  ? "text-slate-400"
                  : s.net_profit_usd >= 0
                    ? "text-emerald-400"
                    : "text-red-400"
              }`}
            >
              {hasCompleted ? fmtUsd(s.net_profit_usd, 2, true) : "N/A"}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
              {hasCompleted
                ? `${fmtPct(s.net_profit_pct, 2)} (${s.net_profit_r >= 0 ? "+" : ""}${s.net_profit_r.toFixed(2)}R)`
                : `Bal ${fmtUsd(s.initial_balance, 0)}`}
            </div>
          </div>

          {/* Trading Costs (Spread + Slippage) */}
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.04] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-amber-300">
              Trading Costs Drag
            </div>
            <div className="mt-1 font-mono text-xl font-bold text-amber-200 tabular-nums">
              {hasCompleted ? fmtUsd(s.total_trading_costs_account_usd, 2) : "$0.00"}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
              Spr ${s.total_spread_cost_usd_oz.toFixed(2)} + Slip ${s.total_slippage_cost_usd_oz.toFixed(2)} /oz
            </div>
          </div>
        </div>

        {/* Secondary Win/Loss Breakdown Strip */}
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-800/80 bg-[#070b12] px-3.5 py-2.5 font-mono text-[11px] sm:grid-cols-4 xl:grid-cols-8 tabular-nums">
          <div>
            <div className="text-[10px] text-slate-500">Completed</div>
            <div className="font-semibold text-white">{s.completed_trades}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">Open (Excluded)</div>
            <div className="font-semibold text-sky-300">{s.open_trades}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">Avg Win</div>
            <div className="font-semibold text-emerald-400">
              {s.avg_win_usd !== null ? fmtUsd(s.avg_win_usd, 2, true) : "—"}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">Avg Loss</div>
            <div className="font-semibold text-red-400">
              {s.avg_loss_usd !== null ? `-${fmtUsd(s.avg_loss_usd, 2)}` : "—"}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">Best / Worst</div>
            <div className="font-semibold text-slate-200">
              {s.largest_win_usd !== null ? `+${s.largest_win_usd.toFixed(0)}` : "—"} /{" "}
              {s.largest_loss_usd !== null ? `-${s.largest_loss_usd.toFixed(0)}` : "—"}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">Max W / L Streak</div>
            <div className="font-semibold text-slate-200">
              <span className="text-emerald-400">{s.max_consecutive_wins}</span> /{" "}
              <span className="text-red-400">{s.max_consecutive_losses}</span>
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">TP1 / TP2 / TP3</div>
            <div className="font-semibold text-emerald-300">
              {s.tp1_hit_count} / {s.tp2_hit_count} / {s.tp3_hit_count}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">SL / Invalidated</div>
            <div className="font-semibold text-red-300">
              {s.sl_hit_count} / {s.invalidated_count}
            </div>
          </div>
        </div>

        {/* 100 / 300 / 500 Completed Signal Performance Horizons */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-300">
              <Award className="h-3.5 w-3.5 text-amber-400" />
              Rolling Performance History (100 / 300 / 500 Completed Signals)
            </span>
            <span className="font-mono text-[10px] text-slate-500">
              Calculated strictly when full completed sample is available
            </span>
          </div>
          <div className="grid gap-2.5 md:grid-cols-3">
            {s.horizons.map((h) => (
              <div
                key={h.target_signals}
                className={`rounded-xl border p-3 ${
                  h.available
                    ? "border-emerald-500/30 bg-emerald-500/[0.04]"
                    : "border-slate-800 bg-[#080d16]"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-slate-100">
                    Last {h.target_signals} Completed Signals
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                      h.available
                        ? "bg-emerald-500/20 text-emerald-300"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {h.available
                      ? "VERIFIED"
                      : `${h.completed_available} / ${h.target_signals}`}
                  </span>
                </div>

                {h.available ? (
                  <div className="mt-2.5 space-y-2">
                    <div className="grid grid-cols-3 gap-2 font-mono text-xs tabular-nums">
                      <div>
                        <div className="text-[10px] text-slate-500">Win Rate</div>
                        <div className="font-bold text-white">{h.win_rate_pct?.toFixed(1)}%</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500">Profit Factor</div>
                        <div className="font-bold text-amber-300">{h.profit_factor?.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500">Max DD</div>
                        <div className="font-bold text-red-400">-{h.max_drawdown_pct?.toFixed(1)}%</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500">Avg R:R</div>
                        <div className="font-semibold text-sky-300">
                          {h.avg_rr_realized !== null ? `1:${h.avg_rr_realized.toFixed(2)}` : "—"}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500">Net R</div>
                        <div
                          className={`font-semibold ${
                            (h.net_profit_r ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          {(h.net_profit_r ?? 0) >= 0 ? "+" : ""}
                          {h.net_profit_r?.toFixed(2)}R
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500">Costs/oz</div>
                        <div className="font-semibold text-slate-300">
                          ${h.total_trading_costs_usd_oz?.toFixed(1)}
                        </div>
                      </div>
                    </div>
                    <div className="text-[10px] font-mono text-slate-500">
                      {fmtDateTime(h.period_start)} → {fmtDateTime(h.period_end)}
                    </div>
                  </div>
                ) : (
                  <div className="mt-2.5 space-y-2">
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full bg-amber-400/70"
                        style={{
                          width: `${Math.min(100, (h.completed_available / h.target_signals) * 100)}%`,
                        }}
                      />
                    </div>
                    <p className="text-[11px] leading-relaxed text-slate-400">{h.note}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Equity Curve */}
        <EquityCurveChart
          points={s.equity_curve}
          initialBalance={s.initial_balance}
          label={s.mode === "BACKTEST" ? "Historical Backtest" : "Live Paper Forward-Test"}
        />

        {/* Verification Audit Footer */}
        <div className="flex items-start gap-2 rounded-lg border border-slate-800 bg-[#080d16] px-3 py-2 text-[11px] text-slate-400">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
          <span>{s.verification_note}</span>
        </div>
      </div>
    );
  };

  return (
    <section id="performance" className="terminal-panel gold-glow p-4 md:p-5 space-y-5">
      {/* Module Header */}
      <div className="flex flex-col gap-3 border-b border-slate-800/90 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <FlaskConical className="h-4 w-4 text-amber-400" />
            <h2 className="text-base font-bold tracking-wide text-slate-50">
              AI Signal Performance & Historical Backtesting
            </h2>
            <span className="inline-flex items-center gap-1 rounded border border-red-500/35 bg-red-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-red-300">
              <Lock className="h-3 w-3" />
              EXECUTION DISABLED
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Strictly separated Historical XAUUSD Backtesting and Live Non-Executing Forward Testing — including spread,
            slippage, and timestamped audit trails. Zero invented metrics.
          </p>
        </div>

        {/* Separated Mode Switcher */}
        <div className="flex flex-wrap items-center gap-1.5">
          <div className="inline-flex rounded-lg border border-slate-800 bg-[#070b12] p-1">
            <button
              type="button"
              onClick={() => {
                setTab("backtest");
                setTradeFilter("ALL");
              }}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                tab === "backtest"
                  ? "bg-amber-400 text-slate-950"
                  : "text-slate-400 hover:text-slate-100"
              }`}
            >
              <BarChart2 className="h-3.5 w-3.5" />
              Historical Backtest
            </button>
            <button
              type="button"
              onClick={() => {
                setTab("forward");
                setTradeFilter("ALL");
              }}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                tab === "forward"
                  ? "bg-sky-400 text-slate-950"
                  : "text-slate-400 hover:text-slate-100"
              }`}
            >
              <Activity className="h-3.5 w-3.5" />
              Live Forward Test ({fwSummary?.completed_trades ?? 0})
            </button>
            <button
              type="button"
              onClick={() => setTab("compare")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                tab === "compare"
                  ? "bg-slate-200 text-slate-950"
                  : "text-slate-400 hover:text-slate-100"
              }`}
            >
              <GitCompare className="h-3.5 w-3.5" />
              Compare
            </button>
          </div>

          <button
            type="button"
            onClick={loadOverview}
            disabled={loadingOverview}
            className="rounded-lg border border-slate-800 bg-[#080d16] p-2 text-slate-400 transition hover:border-amber-400/40 hover:text-amber-300"
            title="Refresh performance statistics"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingOverview ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/40 bg-red-950/50 px-3.5 py-2.5 text-xs text-red-200">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* TAB 1: HISTORICAL XAUUSD BACKTESTING */}
      {tab === "backtest" && (
        <div className="space-y-4">
          {/* Interactive Backtest Runner Controls */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3.5 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
                Historical Walk-Forward Backtest Configuration (Zero Lookahead)
              </span>
              {overview && overview.backtest_runs.length > 0 && (
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="text-slate-400">Saved Runs:</span>
                  <select
                    value={activeBacktest?.run_uid || ""}
                    onChange={(e) => handleSelectSavedRun(e.target.value)}
                    className="rounded-md border border-slate-700 bg-[#070b12] px-2 py-1 font-mono text-[11px] text-slate-200 focus:border-amber-400 focus:outline-none"
                  >
                    {overview.backtest_runs.map((r) => (
                      <option key={r.run_uid} value={r.run_uid}>
                        {r.timeframe} • {r.completed_trades} trades • WR{" "}
                        {r.win_rate_pct !== null ? `${r.win_rate_pct.toFixed(1)}%` : "N/A"} •{" "}
                        {r.run_uid}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-8">
              <div>
                <label className="block text-[10px] font-semibold uppercase text-slate-400">Timeframe</label>
                <select
                  value={form.timeframe}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      timeframe: e.target.value as BacktestRequestPayload["timeframe"],
                    }))
                  }
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2 py-1.5 font-mono text-xs text-white focus:border-amber-400/60 focus:outline-none"
                >
                  <option value="M5">M5 (60D)</option>
                  <option value="M15">M15 (60D)</option>
                  <option value="M30">M30 (60D)</option>
                  <option value="H1">H1 (2Y Deep)</option>
                  <option value="H4">H4 (2Y)</option>
                  <option value="D1">D1 (5Y)</option>
                </select>
              </div>

              <div className="col-span-2 sm:col-span-2">
                <label className="block text-[10px] font-semibold uppercase text-slate-400">
                  Real Historical Dataset
                </label>
                <select
                  value={form.dataset}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      dataset: e.target.value as BacktestRequestPayload["dataset"],
                    }))
                  }
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2 py-1.5 text-xs text-white focus:border-amber-400/60 focus:outline-none"
                >
                  <option value="extended_gold">Extended Real Gold (COMEX GC=F 60D–5Y)</option>
                  <option value="spot_cache">BiQuote Spot XAUUSD Native Cache</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-semibold uppercase text-slate-400">Spread ($)</label>
                <input
                  type="number"
                  min="0"
                  max="5"
                  step="0.05"
                  value={form.spread_usd}
                  onChange={(e) => setForm((f) => ({ ...f, spread_usd: parseFloat(e.target.value) || 0 }))}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2 py-1.5 font-mono text-xs text-white focus:border-amber-400/60 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] font-semibold uppercase text-slate-400">Slippage ($/side)</label>
                <input
                  type="number"
                  min="0"
                  max="5"
                  step="0.05"
                  value={form.slippage_usd}
                  onChange={(e) => setForm((f) => ({ ...f, slippage_usd: parseFloat(e.target.value) || 0 }))}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2 py-1.5 font-mono text-xs text-white focus:border-amber-400/60 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] font-semibold uppercase text-slate-400">Risk %</label>
                <input
                  type="number"
                  min="0.25"
                  max="5"
                  step="0.25"
                  value={form.risk_percent}
                  onChange={(e) => setForm((f) => ({ ...f, risk_percent: parseFloat(e.target.value) || 1.0 }))}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2 py-1.5 font-mono text-xs text-white focus:border-amber-400/60 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] font-semibold uppercase text-slate-400">Exit Model</label>
                <select
                  value={form.exit_mode}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      exit_mode: e.target.value as BacktestRequestPayload["exit_mode"],
                    }))
                  }
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2 py-1.5 text-xs text-white focus:border-amber-400/60 focus:outline-none"
                >
                  <option value="scaled_tp1_tp2_tp3">Scaled TP1/2/3</option>
                  <option value="tp2_primary">Full TP2 (1:2R)</option>
                </select>
              </div>

              <div className="flex items-end">
                <button
                  type="button"
                  onClick={handleRunBacktest}
                  disabled={runningBt}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-amber-400 px-3 py-1.5 text-xs font-bold text-slate-950 shadow transition hover:bg-amber-300 disabled:opacity-50"
                >
                  {runningBt ? (
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Play className="h-3.5 w-3.5" />
                  )}
                  <span>{runningBt ? "Running..." : "Run Backtest"}</span>
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
              <label className="inline-flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.move_sl_to_be_at_tp1}
                  onChange={(e) => setForm((f) => ({ ...f, move_sl_to_be_at_tp1: e.target.checked }))}
                  className="rounded border-slate-700 bg-slate-900 text-amber-400 focus:ring-0"
                />
                <span>Move Stop Loss to Breakeven (incl. costs) after TP1 hit</span>
              </label>
              <span className="font-mono text-[10px] text-slate-500">
                Round-trip cost: ${(form.spread_usd + form.slippage_usd * 2).toFixed(2)}/oz • Conservative SL-first
                intrabar rule
              </span>
            </div>
          </div>

          {activeBacktest ? (
            <div className="space-y-4">
              {/* Active Backtest Dataset Banner */}
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-400/25 bg-amber-400/[0.06] px-3.5 py-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-amber-400/20 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-300">
                    BACKTEST • {activeBacktest.run_uid}
                  </span>
                  <strong className="text-slate-100">{activeBacktest.dataset_label}</strong>
                </div>
                <div className="font-mono text-[11px] text-slate-300 tabular-nums">
                  {fmtDateTime(activeBacktest.period_start)} → {fmtDateTime(activeBacktest.period_end)}
                </div>
              </div>

              {renderSummaryCards(btSummary)}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-800 bg-[#070b12] py-10 text-center">
              <p className="text-sm font-semibold text-slate-200">No Historical Backtest Executed Yet</p>
              <p className="mx-auto mt-1 max-w-xl text-xs text-slate-400">
                Click <strong className="text-amber-300">Run Backtest</strong> above to run a zero-lookahead
                walk-forward simulation on real historical Gold candles with spread and slippage included.
              </p>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: LIVE NON-EXECUTING FORWARD TESTING */}
      {tab === "forward" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-sky-500/30 bg-sky-500/[0.07] px-3.5 py-2.5 text-xs">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-sky-400 shrink-0" />
              <span className="text-sky-100">
                <strong>Live Paper Forward-Testing (Zero Broker Execution):</strong> Tracks real-time AI{" "}
                <code>BUY</code> / <code>SELL</code> signals directly against live{" "}
                <strong>{forwardReport?.data_provider || "BiQuote Spot XAUUSD"}</strong> Bid/Ask quotes plus{" "}
                <strong className="font-mono">
                  ${(forwardReport?.assumed_slippage_per_side_usd ?? 0.15).toFixed(2)}/side
                </strong>{" "}
                slippage. Completely isolated from historical backtests.
              </span>
            </div>
            <span className="font-mono text-[10px] text-sky-300">
              Open: {fwSummary?.open_trades ?? 0} • Completed: {fwSummary?.completed_trades ?? 0}
            </span>
          </div>

          {renderSummaryCards(fwSummary)}
        </div>
      )}

      {/* TAB 3: STRICTLY SEPARATED SIDE-BY-SIDE COMPARISON */}
      {tab === "compare" && (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#070b12]">
          <table className="w-full min-w-[640px] border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                <th className="px-4 py-3">Performance Metric</th>
                <th className="px-4 py-3 text-amber-300">
                  Historical Backtest ({activeBacktest ? `${activeBacktest.timeframe} • ${activeBacktest.run_uid}` : "Not Run"})
                </th>
                <th className="px-4 py-3 text-sky-300">
                  Live Forward Test (Non-Executing Paper)
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 font-mono tabular-nums">
              {[
                {
                  metric: "Completed Verifiable Signals",
                  bt: btSummary ? String(btSummary.completed_trades) : "—",
                  fw: fwSummary ? `${fwSummary.completed_trades} (${fwSummary.open_trades} open)` : "0",
                },
                {
                  metric: "Win Rate (%)",
                  bt: btSummary?.win_rate_pct !== null && btSummary?.win_rate_pct !== undefined ? `${btSummary.win_rate_pct.toFixed(2)}%` : "N/A",
                  fw: fwSummary?.win_rate_pct !== null && fwSummary?.win_rate_pct !== undefined ? `${fwSummary.win_rate_pct.toFixed(2)}%` : "N/A (0 completed)",
                },
                {
                  metric: "Winning / Losing / Breakeven",
                  bt: btSummary ? `${btSummary.winning_trades}W / ${btSummary.losing_trades}L / ${btSummary.breakeven_trades}BE` : "—",
                  fw: fwSummary ? `${fwSummary.winning_trades}W / ${fwSummary.losing_trades}L / ${fwSummary.breakeven_trades}BE` : "—",
                },
                {
                  metric: "Profit Factor",
                  bt: btSummary?.profit_factor !== null && btSummary?.profit_factor !== undefined ? btSummary.profit_factor.toFixed(2) : "N/A",
                  fw: fwSummary?.profit_factor !== null && fwSummary?.profit_factor !== undefined ? fwSummary.profit_factor.toFixed(2) : "N/A",
                },
                {
                  metric: "Maximum Drawdown",
                  bt: btSummary && btSummary.completed_trades > 0 ? `-${btSummary.max_drawdown_pct.toFixed(2)}% (${btSummary.max_drawdown_r.toFixed(2)}R)` : "N/A",
                  fw: fwSummary && fwSummary.completed_trades > 0 ? `-${fwSummary.max_drawdown_pct.toFixed(2)}% (${fwSummary.max_drawdown_r.toFixed(2)}R)` : "N/A",
                },
                {
                  metric: "Average Risk-to-Reward (Realized / Planned)",
                  bt: btSummary?.avg_rr_realized !== null && btSummary?.avg_rr_realized !== undefined ? `1:${btSummary.avg_rr_realized.toFixed(2)} (Plan 1:${btSummary.avg_rr_planned?.toFixed(2)})` : "N/A",
                  fw: fwSummary?.avg_rr_realized !== null && fwSummary?.avg_rr_realized !== undefined ? `1:${fwSummary.avg_rr_realized.toFixed(2)} (Plan 1:${fwSummary.avg_rr_planned?.toFixed(2)})` : "N/A",
                },
                {
                  metric: "Net Profit (After Spread & Slippage)",
                  bt: btSummary && btSummary.completed_trades > 0 ? `${fmtUsd(btSummary.net_profit_usd, 2, true)} (${btSummary.net_profit_r >= 0 ? "+" : ""}${btSummary.net_profit_r.toFixed(2)}R)` : "N/A",
                  fw: fwSummary && fwSummary.completed_trades > 0 ? `${fmtUsd(fwSummary.net_profit_usd, 2, true)} (${fwSummary.net_profit_r >= 0 ? "+" : ""}${fwSummary.net_profit_r.toFixed(2)}R)` : "N/A",
                },
                {
                  metric: "Total Trading Costs (Spread + Slippage)",
                  bt: btSummary ? `${fmtUsd(btSummary.total_trading_costs_account_usd, 2)} ($${btSummary.total_trading_costs_usd_oz.toFixed(2)}/oz)` : "—",
                  fw: fwSummary ? `${fmtUsd(fwSummary.total_trading_costs_account_usd, 2)} ($${fwSummary.total_trading_costs_usd_oz.toFixed(2)}/oz)` : "$0.00",
                },
                {
                  metric: "100 / 300 / 500 Horizon Availability",
                  bt: btSummary ? btSummary.horizons.map((h) => `${h.target_signals}:${h.available ? "OK" : `${h.completed_available}`}`).join(" | ") : "—",
                  fw: fwSummary ? fwSummary.horizons.map((h) => `${h.target_signals}:${h.available ? "OK" : `${h.completed_available}`}`).join(" | ") : "—",
                },
              ].map((row) => (
                <tr key={row.metric} className="hover:bg-slate-800/30">
                  <td className="px-4 py-2.5 font-sans font-medium text-slate-300">{row.metric}</td>
                  <td className="px-4 py-2.5 text-slate-100">{row.bt}</td>
                  <td className="px-4 py-2.5 text-slate-100">{row.fw}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* TIMESTAMPED SIGNAL AUDIT LEDGER (shown on Backtest & Forward tabs) */}
      {tab !== "compare" && (
        <div className="space-y-2.5 border-t border-slate-800/80 pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-amber-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                {tab === "backtest"
                  ? "Historical Backtest Timestamped Trade Ledger"
                  : "Live Forward-Test Timestamped Signal Ledger"}
              </h3>
              <span className="font-mono text-[11px] text-slate-500">
                ({filteredTrades.length} records)
              </span>
            </div>

            <div className="flex items-center gap-1 rounded-lg border border-slate-800 bg-[#070b12] p-0.5">
              {(["ALL", "WIN", "LOSS", "BUY", "SELL"] as TradeFilter[]).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setTradeFilter(f)}
                  className={`rounded px-2 py-0.5 font-mono text-[10px] font-semibold transition ${
                    tradeFilter === f
                      ? "bg-amber-400 text-slate-950"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          {filteredTrades.length === 0 ? (
            <div className="rounded-xl border border-slate-800 bg-[#070b12] py-8 text-center text-xs text-slate-500">
              No timestamped {tab === "backtest" ? "backtest" : "forward-test"} records match this filter yet.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#070b12]">
              <table className="w-full min-w-[920px] border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    <th className="px-3 py-2">Signal & Timestamps (UTC/Local)</th>
                    <th className="px-2 py-2">Side</th>
                    <th className="px-2 py-2">Outcome</th>
                    <th className="px-2 py-2">Entry (Eff.)</th>
                    <th className="px-2 py-2">SL / TP2</th>
                    <th className="px-2 py-2">Exit (Eff.)</th>
                    <th className="px-2 py-2">Costs/oz</th>
                    <th className="px-2 py-2">Realized R</th>
                    <th className="px-3 py-2 text-right">Net P&L ($)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono tabular-nums">
                  {filteredTrades.slice(0, visibleLimit).map((t) => {
                    const isWin = (t.realized_r ?? 0) > 0.02;
                    const isLoss = (t.realized_r ?? 0) < -0.02;
                    return (
                      <tr key={`${t.mode}-${t.signal_uid}-${t.opened_at}`} className="hover:bg-slate-800/30">
                        <td className="px-3 py-2 text-[11px]">
                          <div className="font-semibold text-slate-200">
                            {t.signal_uid} <span className="text-[10px] text-slate-500">({t.timeframe} • {t.confidence}%)</span>
                          </div>
                          <div className="text-[10px] text-slate-400">
                            In: {fmtDateTime(t.opened_at)}
                            {t.closed_at ? ` → Out: ${fmtDateTime(t.closed_at)}` : " → Open"}
                          </div>
                        </td>
                        <td className="px-2 py-2">
                          <span
                            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold ${
                              t.action === "BUY"
                                ? "bg-emerald-500/20 text-emerald-300"
                                : "bg-red-500/20 text-red-300"
                            }`}
                          >
                            {t.action === "BUY" ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                            {t.action}
                          </span>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <span
                            className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${
                              t.status === "OPEN"
                                ? "border-sky-500/35 bg-sky-500/15 text-sky-300"
                                : isWin
                                  ? "border-emerald-500/35 bg-emerald-500/15 text-emerald-300"
                                  : isLoss
                                    ? "border-red-500/35 bg-red-500/15 text-red-300"
                                    : "border-slate-700 bg-slate-800 text-slate-300"
                            }`}
                          >
                            {(t.outcome || t.status).replace("_", " ")}
                          </span>
                        </td>
                        <td className="px-2 py-2 text-[11px] text-slate-200">
                          <div>${fmtPrice(t.planned_entry, 2)}</div>
                          <div className="text-[10px] text-slate-500">Eff ${fmtPrice(t.effective_entry, 2)}</div>
                        </td>
                        <td className="px-2 py-2 text-[11px]">
                          <div className="text-red-300">SL ${fmtPrice(t.stop_loss, 2)}</div>
                          <div className="text-emerald-300">TP2 ${fmtPrice(t.tp2, 2)}</div>
                        </td>
                        <td className="px-2 py-2 text-[11px] text-slate-200">
                          {t.exit_price !== null ? (
                            <>
                              <div>${fmtPrice(t.exit_price, 2)}</div>
                              <div className="text-[10px] text-slate-500">Eff ${fmtPrice(t.effective_exit, 2)}</div>
                            </>
                          ) : (
                            <span className="text-slate-500">Open</span>
                          )}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-amber-300/90">
                          <div>-${t.total_cost_usd_oz.toFixed(2)}</div>
                          <div className="text-[10px] text-slate-500">
                            {t.spread_cost_usd_oz.toFixed(2)}+{t.slippage_cost_usd_oz.toFixed(2)}
                          </div>
                        </td>
                        <td
                          className={`px-2 py-2 font-bold ${
                            t.realized_r === null
                              ? "text-slate-500"
                              : isWin
                                ? "text-emerald-400"
                                : isLoss
                                  ? "text-red-400"
                                  : "text-slate-300"
                          }`}
                        >
                          {t.realized_r !== null
                            ? `${t.realized_r >= 0 ? "+" : ""}${t.realized_r.toFixed(2)}R`
                            : "—"}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-bold ${
                            t.account_pnl_usd === null
                              ? "text-slate-500"
                              : t.account_pnl_usd >= 0
                                ? "text-emerald-400"
                                : "text-red-400"
                          }`}
                        >
                          {t.account_pnl_usd !== null ? fmtUsd(t.account_pnl_usd, 2, true) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {filteredTrades.length > visibleLimit && (
                <div className="border-t border-slate-800 p-2.5 text-center">
                  <button
                    type="button"
                    onClick={() => setVisibleLimit((n) => n + 50)}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1 text-xs font-medium text-slate-300 transition hover:border-amber-400/40 hover:text-amber-200"
                  >
                    Show More Records ({filteredTrades.length - visibleLimit} remaining)
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
