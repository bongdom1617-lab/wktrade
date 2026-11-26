"use client";

import React from "react";
import { Activity, BarChart3, Flame, Gauge, GitBranch } from "lucide-react";
import type { Timeframe, TimeframeAnalysis } from "@/lib/types";
import { fmtPrice } from "@/lib/format";

interface TechnicalMetricsGridProps {
  timeframe: Timeframe;
  analysis: TimeframeAnalysis | null;
}

export default function TechnicalMetricsGrid({ timeframe, analysis }: TechnicalMetricsGridProps) {
  if (!analysis) {
    return (
      <div className="terminal-panel p-5 text-center text-xs text-slate-400">
        Loading {timeframe} technical indicator breakdown...
      </div>
    );
  }

  const price = analysis.last_close;

  const emaRows = [
    { label: "EMA 9", val: analysis.ema.ema_9, color: "text-sky-400" },
    { label: "EMA 20", val: analysis.ema.ema_20, color: "text-amber-400" },
    { label: "EMA 50", val: analysis.ema.ema_50, color: "text-purple-400" },
    { label: "EMA 100", val: analysis.ema.ema_100, color: "text-rose-400" },
    {
      label: analysis.ema.ema_200_warmed ? "EMA 200" : `EMA 200 (${analysis.ema.bars_used}b)`,
      val: analysis.ema.ema_200,
      color: "text-slate-100",
    },
  ];

  return (
    <div className="terminal-panel flex flex-col p-4 md:p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-amber-400" />
          <h2 className="text-sm font-bold tracking-wide text-slate-100">
            Quantitative Indicators & Market Structure ({timeframe})
          </h2>
        </div>
        <span className="font-mono text-[11px] text-slate-400">
          {analysis.role} • {analysis.bar_count} real bars
        </span>
      </div>

      {/* EMA Ribbon + Key Oscillators */}
      <div className="grid gap-3 lg:grid-cols-12">
        {/* EMA Stack Card */}
        <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3.5 lg:col-span-5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Exponential Moving Averages
            </span>
            <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-300">
              {analysis.ema.alignment.replace("_", " ")}
            </span>
          </div>
          <div className="mt-2.5 space-y-1.5 font-mono text-xs tabular-nums">
            {emaRows.map((row) => {
              const diff = row.val !== null ? price - row.val : null;
              const above = diff !== null && diff >= 0;
              return (
                <div
                  key={row.label}
                  className="flex items-center justify-between rounded-md bg-slate-900/50 px-2.5 py-1.5"
                >
                  <span className={`font-semibold ${row.color}`}>{row.label}</span>
                  <span className="text-slate-100">${fmtPrice(row.val, 2)}</span>
                  <span
                    className={`w-20 text-right text-[11px] ${
                      diff === null ? "text-slate-500" : above ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {diff !== null ? `${diff >= 0 ? "+" : ""}${diff.toFixed(2)}` : "—"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Oscillators & Volatility Grid */}
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:col-span-7">
          {/* RSI 14 */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">RSI (14)</div>
            <div className="mt-1 font-mono text-lg font-bold text-white tabular-nums">
              {analysis.rsi.value !== null ? analysis.rsi.value.toFixed(1) : "—"}
            </div>
            <div className="mt-0.5 text-[10px] text-slate-400">
              {analysis.rsi.zone.replace("_", " ")} • {analysis.rsi.slope}
            </div>
            {analysis.rsi.divergence && (
              <div className="mt-1 text-[10px] font-semibold text-amber-300">
                {analysis.rsi.divergence.replace("_", " ")}
              </div>
            )}
          </div>

          {/* MACD */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">MACD (12,26,9)</div>
            <div
              className={`mt-1 font-mono text-lg font-bold tabular-nums ${
                (analysis.macd.histogram ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"
              }`}
            >
              {analysis.macd.histogram !== null
                ? `${analysis.macd.histogram >= 0 ? "+" : ""}${analysis.macd.histogram.toFixed(2)}`
                : "—"}
            </div>
            <div className="mt-0.5 text-[10px] text-slate-400">
              {analysis.macd.momentum_state.replace("_", " ")}
            </div>
          </div>

          {/* ADX 14 */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">ADX (14)</div>
            <div className="mt-1 font-mono text-lg font-bold text-white tabular-nums">
              {analysis.adx.adx !== null ? analysis.adx.adx.toFixed(1) : "—"}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
              +DI {analysis.adx.plus_di?.toFixed(0) ?? "—"} / -DI {analysis.adx.minus_di?.toFixed(0) ?? "—"}
            </div>
            <div className="text-[10px] font-semibold text-sky-300">{analysis.adx.trend_strength}</div>
          </div>

          {/* ATR Volatility */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              <Gauge className="h-3 w-3 text-amber-400" />
              ATR (14) Vol
            </div>
            <div className="mt-1 font-mono text-lg font-bold text-amber-300 tabular-nums">
              {analysis.atr.value !== null ? `$${analysis.atr.value.toFixed(2)}` : "—"}
            </div>
            <div className="mt-0.5 text-[10px] text-slate-400">
              Regime: <strong className="text-slate-200">{analysis.atr.regime}</strong>
              {analysis.atr.ratio_to_baseline !== null && ` (${analysis.atr.ratio_to_baseline.toFixed(2)}x)`}
            </div>
          </div>

          {/* Stochastic */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Stochastic</div>
            <div className="mt-1 font-mono text-lg font-bold text-white tabular-nums">
              {analysis.stochastic.k !== null ? analysis.stochastic.k.toFixed(1) : "—"}
              <span className="ml-1 text-xs font-normal text-slate-400">
                / {analysis.stochastic.d !== null ? analysis.stochastic.d.toFixed(1) : "—"}
              </span>
            </div>
            <div className="mt-0.5 text-[10px] text-slate-400">
              {analysis.stochastic.zone}
              {analysis.stochastic.crossover ? ` • ${analysis.stochastic.crossover.replace("_", " ")}` : ""}
            </div>
          </div>

          {/* Bollinger & VWAP */}
          <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">BB & VWAP</div>
            <div className="mt-1 font-mono text-sm font-bold text-cyan-300 tabular-nums">
              {analysis.vwap.applicable && analysis.vwap.value
                ? `VWAP $${fmtPrice(analysis.vwap.value, 2)}`
                : "VWAP N/A (HTF)"}
            </div>
            <div className="mt-1 font-mono text-[10px] text-slate-400 tabular-nums">
              BB %B: {analysis.bollinger.percent_b !== null ? `${(analysis.bollinger.percent_b * 100).toFixed(0)}%` : "—"}
              {analysis.bollinger.squeeze && (
                <span className="ml-1 rounded bg-amber-500/20 px-1 text-amber-300">SQUEEZE</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Support & Resistance + Market Structure & Price Action */}
      <div className="grid gap-3 lg:grid-cols-2">
        {/* Support & Resistance Zones */}
        <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-300">
            <Activity className="h-3.5 w-3.5 text-amber-400" />
            Key Support & Resistance Zones ({timeframe})
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-3 font-mono text-xs tabular-nums">
            <div className="space-y-1.5">
              <div className="text-[10px] font-semibold uppercase text-red-400">Resistance Above</div>
              {analysis.resistance_levels.length > 0 ? (
                analysis.resistance_levels.slice(0, 3).map((lv, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded border border-red-500/20 bg-red-500/[0.06] px-2 py-1"
                  >
                    <span className="font-semibold text-red-200">${fmtPrice(lv.price, 2)}</span>
                    <span className="text-[10px] text-slate-400">
                      +${lv.distance_usd.toFixed(1)} • {lv.touches}t
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-[11px] text-slate-500">No nearby resistance</div>
              )}
            </div>

            <div className="space-y-1.5">
              <div className="text-[10px] font-semibold uppercase text-emerald-400">Support Below</div>
              {analysis.support_levels.length > 0 ? (
                analysis.support_levels.slice(0, 3).map((lv, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded border border-emerald-500/20 bg-emerald-500/[0.06] px-2 py-1"
                  >
                    <span className="font-semibold text-emerald-200">${fmtPrice(lv.price, 2)}</span>
                    <span className="text-[10px] text-slate-400">
                      -${lv.distance_usd.toFixed(1)} • {lv.touches}t
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-[11px] text-slate-500">No nearby support</div>
              )}
            </div>
          </div>
        </div>

        {/* Market Structure, Breakouts & Candlestick Patterns */}
        <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3.5 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-300">
              <GitBranch className="h-3.5 w-3.5 text-sky-400" />
              Structure, Breakouts & Patterns
            </div>
            <span className="font-mono text-[10px] text-slate-400">
              {analysis.structure.pattern.replace("_", "/")} ({analysis.structure.structure_trend})
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 font-mono text-[11px] tabular-nums">
            <div className="rounded bg-slate-900/60 px-2.5 py-1.5">
              <span className="text-slate-500">Swing High:</span>{" "}
              <strong className="text-slate-200">${fmtPrice(analysis.structure.last_swing_high, 2)}</strong>
            </div>
            <div className="rounded bg-slate-900/60 px-2.5 py-1.5">
              <span className="text-slate-500">Swing Low:</span>{" "}
              <strong className="text-slate-200">${fmtPrice(analysis.structure.last_swing_low, 2)}</strong>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800/80 bg-slate-900/40 px-2.5 py-2 text-[11px] text-slate-300">
            <span className="font-semibold text-amber-300">Breakout Monitor: </span>
            {analysis.breakout.description}
          </div>

          {analysis.structure.reversal_warning && (
            <div className="flex items-start gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-200">
              <Flame className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
              <span>{analysis.structure.reversal_warning}</span>
            </div>
          )}

          {analysis.patterns.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {analysis.patterns.map((p, idx) => (
                <span
                  key={idx}
                  title={p.description}
                  className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold ${
                    p.bias === "BULLISH"
                      ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-300"
                      : p.bias === "BEARISH"
                        ? "border-red-500/35 bg-red-500/10 text-red-300"
                        : "border-slate-700 bg-slate-800 text-slate-300"
                  }`}
                >
                  {p.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
