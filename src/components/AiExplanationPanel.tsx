"use client";

import React from "react";
import {
  AlertOctagon,
  Ban,
  BrainCircuit,
  CheckCircle2,
  Compass,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import type { TradingSignal } from "@/lib/types";

interface AiExplanationPanelProps {
  signal: TradingSignal | null;
}

export default function AiExplanationPanel({ signal }: AiExplanationPanelProps) {
  if (!signal) {
    return (
      <div className="terminal-panel p-5 text-center text-xs text-slate-400">
        Generating structured quantitative AI explanation...
      </div>
    );
  }

  const exp = signal.explanation;
  const actionColor =
    signal.action === "BUY"
      ? "text-emerald-400"
      : signal.action === "SELL"
        ? "text-red-400"
        : "text-amber-400";

  return (
    <div className="terminal-panel flex flex-col p-4 md:p-5 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <BrainCircuit className="h-4 w-4 text-amber-400" />
          <h2 className="text-sm font-bold tracking-wide text-slate-100">
            AI Market Analysis & Decision Rationale
          </h2>
        </div>
        <span className="rounded-md border border-amber-400/25 bg-amber-400/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-300">
          {exp.engine_mode}
        </span>
      </div>

      {/* 1 & 2: What is Gold doing right now? & Market Direction */}
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-300">
            <Sparkles className="h-3.5 w-3.5" />
            1. What Is Gold Doing Right Now?
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-slate-200">{exp.what_is_gold_doing}</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-sky-300">
            <Compass className="h-3.5 w-3.5" />
            2. Current Market Direction
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-slate-200">{exp.market_direction}</p>
        </div>
      </div>

      {/* 3: Why BUY / SELL / WAIT? */}
      <div className="rounded-xl border border-slate-800 bg-[#080d16] p-3.5">
        <div className={`text-[11px] font-bold uppercase tracking-wider ${actionColor}`}>
          3. Why {signal.action}?
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-slate-200">{exp.why_decision}</p>
      </div>

      {/* 4 & 5: Confirmations vs Missing / Warnings */}
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
            <CheckCircle2 className="h-3.5 w-3.5" />
            What Confirms the Market Context ({exp.confirmations.length})
          </div>
          {exp.confirmations.length > 0 ? (
            <ul className="mt-2 space-y-1.5 text-xs text-slate-300">
              {exp.confirmations.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 leading-relaxed">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-slate-500">No active entry confirmations currently satisfied.</p>
          )}
        </div>

        <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.04] p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-300">
            <AlertOctagon className="h-3.5 w-3.5" />
            Missing Confirmations & Risk Blockers ({exp.missing_or_warnings.length})
          </div>
          {exp.missing_or_warnings.length > 0 ? (
            <ul className="mt-2 space-y-1.5 text-xs text-slate-300">
              {exp.missing_or_warnings.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 leading-relaxed">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-emerald-300/80">
              All core quantitative filters and Risk-to-Reward gates passed cleanly.
            </p>
          )}
        </div>
      </div>

      {/* 6 & 7: Invalidation Conditions & When to Avoid Entering */}
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-red-500/20 bg-red-500/[0.04] p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-red-300">
            <ShieldAlert className="h-3.5 w-3.5" />
            Setup Invalidation Conditions
          </div>
          <ul className="mt-2 space-y-1.5 text-xs text-slate-300">
            {exp.invalidation_conditions.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2 leading-relaxed">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-slate-700/70 bg-slate-900/50 p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-300">
            <Ban className="h-3.5 w-3.5 text-rose-400" />
            When Should You Avoid Entering?
          </div>
          <ul className="mt-2 space-y-1.5 text-xs text-slate-300">
            {exp.when_to_avoid.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2 leading-relaxed">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
