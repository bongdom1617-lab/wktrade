"use client";

import React, { useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Crosshair,
  Info,
  PauseCircle,
  Shield,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { ActiveTradeMonitor, TradingSignal } from "@/lib/types";
import { fmtPrice, fmtTimeLocal, fmtUsd } from "@/lib/format";

interface PrimarySignalCardProps {
  signal: TradingSignal | null;
  activeMonitor: ActiveTradeMonitor | null;
}

export default function PrimarySignalCard({ signal, activeMonitor }: PrimarySignalCardProps) {
  const [showRationale, setShowRationale] = useState(false);

  if (!signal) {
    return (
      <div className="terminal-panel flex h-full min-h-[420px] flex-col items-center justify-center p-6 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
        <p className="mt-3 text-sm font-medium text-slate-300">Synchronizing live XAUUSD analysis...</p>
        <p className="mt-1 text-xs text-slate-500">Computing M1–D1 indicators & multi-timeframe confluence</p>
      </div>
    );
  }

  const isBuy = signal.action === "BUY";
  const isSell = signal.action === "SELL";
  const isWait = signal.action === "WAIT";
  const rp = signal.risk_plan;

  const glowClass = isBuy ? "buy-glow" : isSell ? "sell-glow" : "wait-glow";
  const accentText = isBuy ? "text-emerald-400" : isSell ? "text-red-400" : "text-amber-400";
  const badgeBg = isBuy
    ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300"
    : isSell
      ? "bg-red-500/15 border-red-500/40 text-red-300"
      : "bg-amber-500/15 border-amber-500/40 text-amber-300";

  const confColor =
    signal.confidence >= 75
      ? "bg-emerald-500"
      : signal.confidence >= 60
        ? "bg-amber-400"
        : "bg-slate-500";

  return (
    <div className={`terminal-panel ${glowClass} flex h-full flex-col justify-between p-4 md:p-5`}>
      <div className="space-y-4">
        {/* Card Header */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              <span>Primary AI Recommendation</span>
              <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                {signal.setup_timeframe} Setup
              </span>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <div className={`flex items-center gap-2 rounded-xl border px-4 py-2 ${badgeBg}`}>
                {isBuy && <TrendingUp className="h-6 w-6" />}
                {isSell && <TrendingDown className="h-6 w-6" />}
                {isWait && <PauseCircle className="h-6 w-6" />}
                <span className="font-mono text-2xl font-black tracking-wider">{signal.action}</span>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-400">
                  {isWait ? "Setup Readiness" : "Confluence Score"}
                </div>
                <div className={`font-mono text-2xl font-bold tabular-nums ${accentText}`}>
                  {signal.confidence}%
                </div>
                {!isWait && (
                  <div className="text-[9px] text-slate-500">Indicator alignment (not win %)</div>
                )}
              </div>
            </div>
          </div>

          <div className="text-right font-mono text-[10px] text-slate-500">
            <div>{signal.signal_uid}</div>
            <div className="mt-0.5 flex items-center justify-end gap-1">
              <Clock className="h-3 w-3" />
              {fmtTimeLocal(signal.generated_at)}
            </div>
          </div>
        </div>

        {/* Confidence Bar */}
        <div className="space-y-1">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full rounded-full transition-all duration-500 ${confColor}`}
              style={{ width: `${Math.max(4, Math.min(100, signal.confidence))}%` }}
            />
          </div>
          <p className="text-xs leading-relaxed text-slate-300">{signal.explanation.decision_headline}</p>
        </div>

        {/* Valid BUY/SELL Risk Plan Levels */}
        {rp ? (
          <div className="space-y-2.5">
            {/* Entry Zone */}
            <div className="rounded-xl border border-amber-400/25 bg-amber-500/[0.06] p-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-300">
                  <Crosshair className="h-3.5 w-3.5" />
                  Valid Entry Zone
                </span>
                <span className="font-mono text-[11px] text-slate-400">
                  ATR ${rp.atr_reference.toFixed(2)} • {rp.volatility_regime}
                </span>
              </div>
              <div className="mt-1 flex items-baseline justify-between">
                <span className="font-mono text-xl font-bold text-white tabular-nums">
                  ${fmtPrice(rp.entry_price, 2)}
                </span>
                <span className="font-mono text-xs text-amber-200/90 tabular-nums">
                  Zone ${fmtPrice(rp.entry_zone_low, 2)} – ${fmtPrice(rp.entry_zone_high, 2)}
                </span>
              </div>
            </div>

            {/* Stop Loss */}
            <div className="flex items-center justify-between rounded-xl border border-red-500/30 bg-red-500/[0.07] px-3 py-2.5">
              <div>
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-red-400">
                  <Shield className="h-3.5 w-3.5" />
                  Stop Loss (SL)
                </div>
                <div className="mt-0.5 text-[11px] text-slate-400">Structural & ATR invalidation</div>
              </div>
              <div className="text-right font-mono tabular-nums">
                <div className="text-base font-bold text-red-300">${fmtPrice(rp.stop_loss, 2)}</div>
                <div className="text-[11px] text-red-400/80">Risk ${rp.risk_usd.toFixed(2)} (1.0R)</div>
              </div>
            </div>

            {/* TP1 / TP2 / TP3 Grid */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "TP1", sub: "Partial", price: rp.tp1, rr: rp.rr_tp1, rew: rp.reward_tp1_usd, primary: false },
                { label: "TP2", sub: "Primary", price: rp.tp2, rr: rp.rr_tp2, rew: rp.reward_tp2_usd, primary: true },
                { label: "TP3", sub: "Runner", price: rp.tp3, rr: rp.rr_tp3, rew: rp.reward_tp3_usd, primary: false },
              ].map((tp) => (
                <div
                  key={tp.label}
                  className={`rounded-xl border p-2.5 ${
                    tp.primary
                      ? "border-emerald-400/45 bg-emerald-500/[0.12]"
                      : "border-emerald-500/20 bg-emerald-500/[0.05]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-emerald-300">{tp.label}</span>
                    <span className="rounded bg-emerald-500/20 px-1 py-0.5 font-mono text-[10px] font-semibold text-emerald-200">
                      1:{tp.rr.toFixed(1)}
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-sm font-bold text-white tabular-nums">
                    ${fmtPrice(tp.price, 2)}
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-emerald-400/80 tabular-nums">
                    +${tp.rew.toFixed(2)} • {tp.sub}
                  </div>
                </div>
              ))}
            </div>

            {/* Toggle Per-Level Rationale */}
            <button
              type="button"
              onClick={() => setShowRationale((v) => !v)}
              className="flex w-full items-center justify-between rounded-lg border border-slate-800 bg-[#080d16] px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-amber-400/40 hover:text-amber-200"
            >
              <span className="flex items-center gap-1.5">
                <Info className="h-3.5 w-3.5 text-amber-400" />
                {showRationale ? "Hide Smart SL/TP Selection Rationale" : "Why Were These Entry, SL & TP Levels Selected?"}
              </span>
              <span className="font-mono text-[10px] text-slate-500">{showRationale ? "▲" : "▼"}</span>
            </button>

            {showRationale && (
              <div className="space-y-1.5 rounded-xl border border-slate-800 bg-[#070b12] p-3 text-[11px] text-slate-300">
                {rp.rationales.map((r) => (
                  <div key={r.level_name} className="leading-relaxed">
                    <strong className="text-amber-300">{r.level_name}</strong>{" "}
                    <span className="font-mono text-slate-400">(${fmtPrice(r.price, 2)}):</span> {r.reason}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          /* WAIT Disciplined State + Objective Watchlist Levels */
          <div className="space-y-3">
            <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-3.5">
              <div className="text-xs font-semibold text-amber-300">No Forced Trade — Stand Aside</div>
              <p className="mt-1 text-xs leading-relaxed text-slate-300">
                {signal.explanation.why_decision}
              </p>
            </div>

            {signal.watchlist_levels && (
              <div className="rounded-xl border border-slate-800 bg-[#070b12] p-3">
                <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  <span>Key Watchlist Trigger Levels</span>
                  <span className="text-amber-400/80">Monitoring Only</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-xs tabular-nums">
                  <div className="rounded-lg border border-slate-800/80 bg-slate-900/50 p-2">
                    <div className="flex items-center gap-1 text-[10px] text-emerald-400">
                      <ArrowUpRight className="h-3 w-3" /> Bullish Breakout
                    </div>
                    <div className="mt-0.5 font-semibold text-slate-100">
                      {signal.watchlist_levels.bullish_breakout_trigger
                        ? `$${fmtPrice(signal.watchlist_levels.bullish_breakout_trigger, 2)}`
                        : "—"}
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-800/80 bg-slate-900/50 p-2">
                    <div className="flex items-center gap-1 text-[10px] text-red-400">
                      <ArrowDownRight className="h-3 w-3" /> Bearish Breakdown
                    </div>
                    <div className="mt-0.5 font-semibold text-slate-100">
                      {signal.watchlist_levels.bearish_breakdown_trigger
                        ? `$${fmtPrice(signal.watchlist_levels.bearish_breakdown_trigger, 2)}`
                        : "—"}
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-800/80 bg-slate-900/50 p-2">
                    <div className="text-[10px] text-slate-400">M15 EMA 20</div>
                    <div className="mt-0.5 font-semibold text-slate-200">
                      {signal.watchlist_levels.m15_ema20 ? `$${fmtPrice(signal.watchlist_levels.m15_ema20, 2)}` : "—"}
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-800/80 bg-slate-900/50 p-2">
                    <div className="text-[10px] text-slate-400">M15 ATR (14)</div>
                    <div className="mt-0.5 font-semibold text-slate-200">
                      {signal.watchlist_levels.m15_atr ? `$${signal.watchlist_levels.m15_atr.toFixed(2)}` : "—"}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Active Persisted Trade Monitor (tracks open signal even if current tick enters cooldown/WAIT) */}
        {activeMonitor && (
          <div className="rounded-xl border border-sky-500/30 bg-sky-500/[0.06] p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-sky-300">
                <Target className="h-3.5 w-3.5" />
                Live Tracked Setup: {activeMonitor.action} ({activeMonitor.status.replace("_", " ")})
              </div>
              {activeMonitor.floating_pnl_usd !== undefined && (
                <span
                  className={`font-mono text-xs font-bold tabular-nums ${
                    activeMonitor.floating_pnl_usd >= 0 ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {fmtUsd(activeMonitor.floating_pnl_usd, 2, true)} ({activeMonitor.floating_r !== undefined ? `${activeMonitor.floating_r >= 0 ? "+" : ""}${activeMonitor.floating_r.toFixed(2)}R` : ""})
                </span>
              )}
            </div>
            <div className="mt-2 grid grid-cols-4 gap-1.5 font-mono text-[10px]">
              {[
                { label: "Entry", done: activeMonitor.entry_filled, px: activeMonitor.entry_price },
                { label: "TP1", done: activeMonitor.tp1_reached, px: activeMonitor.tp1 },
                { label: "TP2", done: activeMonitor.tp2_reached, px: activeMonitor.tp2 },
                { label: "TP3", done: activeMonitor.tp3_reached, px: activeMonitor.tp3 },
              ].map((m) => (
                <div
                  key={m.label}
                  className={`rounded border px-1.5 py-1 text-center ${
                    m.done
                      ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                      : "border-slate-800 bg-slate-900/60 text-slate-400"
                  }`}
                >
                  <div className="flex items-center justify-center gap-0.5 font-semibold">
                    {m.done && <CheckCircle2 className="h-2.5 w-2.5" />}
                    {m.label}
                  </div>
                  <div className="tabular-nums">${fmtPrice(m.px, 1)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer Risk Discipline Note */}
      <div className="mt-4 border-t border-slate-800/80 pt-2.5 text-[10px] leading-relaxed text-slate-500">
        <strong className="text-amber-300/90">Risk Reality:</strong> Confluence score measures indicator alignment,{" "}
        <strong className="text-slate-300">not guaranteed win probability</strong> (even disciplined Gold strategies
        lose ~45–55% of trades). Always honor the Stop Loss and risk ≤1% per trade. {signal.disclaimer}
      </div>
    </div>
  );
}
