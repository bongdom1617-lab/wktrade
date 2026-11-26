"use client";

import React from "react";
import { AlertTriangle, CheckCircle2, Layers } from "lucide-react";
import type { MtfSynthesis, Timeframe } from "@/lib/types";

const ORDERED_TFS: Timeframe[] = ["D1", "H4", "H1", "M30", "M15", "M5", "M1"];

interface MtfMatrixTableProps {
  mtf: MtfSynthesis | null;
  selectedTf: Timeframe;
  onSelectTf: (tf: Timeframe) => void;
}

export default function MtfMatrixTable({ mtf, selectedTf, onSelectTf }: MtfMatrixTableProps) {
  if (!mtf) {
    return (
      <div className="terminal-panel p-5 text-center text-xs text-slate-400">
        Awaiting multi-timeframe candlestick synchronization...
      </div>
    );
  }

  const biasBadge = (bias: string) => {
    if (bias === "BULLISH")
      return "bg-emerald-500/15 text-emerald-300 border-emerald-500/35";
    if (bias === "BEARISH")
      return "bg-red-500/15 text-red-300 border-red-500/35";
    return "bg-slate-700/40 text-slate-300 border-slate-600/50";
  };

  return (
    <div className="terminal-panel flex flex-col p-4 md:p-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-800/80">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-amber-400" />
            <h2 className="text-sm font-bold tracking-wide text-slate-100">
              Multi-Timeframe Analysis Matrix
            </h2>
          </div>
          <p className="mt-0.5 text-[11px] text-slate-400">
            Simultaneous H4 → M1 institutional confluence & conflict detector (click any row to inspect chart)
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className={`rounded-lg border px-2.5 py-1 font-mono text-xs font-bold ${biasBadge(mtf.overall_bias)}`}>
            {mtf.overall_bias} ({mtf.weighted_score >= 0 ? "+" : ""}
            {mtf.weighted_score.toFixed(1)})
          </span>
          <span className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 font-mono text-xs text-slate-200 tabular-nums">
            Align {mtf.alignment_score.toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Conflict Alerts Banner */}
      {mtf.conflicts.length > 0 ? (
        <div className="mt-3 space-y-1.5">
          {mtf.conflicts.map((c, i) => (
            <div
              key={`${c.code}-${i}`}
              className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${
                c.severity === "HIGH"
                  ? "border-red-500/35 bg-red-500/10 text-red-200"
                  : c.severity === "MODERATE"
                    ? "border-amber-500/35 bg-amber-500/10 text-amber-200"
                    : "border-slate-700 bg-slate-800/50 text-slate-300"
              }`}
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <div>
                <span className="font-mono text-[10px] font-bold uppercase tracking-wider opacity-90">
                  [{c.severity} • {c.timeframes.join("/")}]
                </span>{" "}
                {c.description}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          <span>No timeframe conflicts detected — multi-timeframe trend structure is aligned.</span>
        </div>
      )}

      {/* Matrix Table */}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[600px] border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              <th className="py-2 pr-3">TF & Role</th>
              <th className="px-2 py-2">Trend</th>
              <th className="px-2 py-2">Score</th>
              <th className="px-2 py-2">EMA Stack</th>
              <th className="px-2 py-2">RSI 14</th>
              <th className="px-2 py-2">ADX 14</th>
              <th className="px-2 py-2">Structure</th>
              <th className="pl-2 py-2 text-right">ATR Vol</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono tabular-nums">
            {ORDERED_TFS.map((tf) => {
              const row = mtf.timeframes[tf];
              if (!row) return null;
              const isSelected = selectedTf === tf;
              return (
                <tr
                  key={tf}
                  onClick={() => onSelectTf(tf)}
                  className={`cursor-pointer transition ${
                    isSelected
                      ? "bg-amber-400/10 text-white"
                      : "hover:bg-slate-800/40 text-slate-300"
                  }`}
                >
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-block w-9 rounded py-0.5 text-center text-[11px] font-bold ${
                          isSelected
                            ? "bg-amber-400 text-slate-950"
                            : "bg-slate-800 text-slate-200"
                        }`}
                      >
                        {tf}
                      </span>
                      <span className="font-sans text-[11px] text-slate-400">{row.role}</span>
                    </div>
                  </td>
                  <td className="px-2 py-2.5">
                    <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${biasBadge(row.trend)}`}>
                      {row.trend}
                    </span>
                  </td>
                  <td className="px-2 py-2.5">
                    <span
                      className={`font-semibold ${
                        row.trend_score > 15
                          ? "text-emerald-400"
                          : row.trend_score < -15
                            ? "text-red-400"
                            : "text-slate-400"
                      }`}
                    >
                      {row.trend_score >= 0 ? "+" : ""}
                      {row.trend_score.toFixed(0)}
                    </span>
                  </td>
                  <td className="px-2 py-2.5 font-sans text-[11px] text-slate-300">
                    {row.ema.alignment.replace("_", " ")}
                  </td>
                  <td className="px-2 py-2.5">
                    <span
                      className={
                        (row.rsi.value ?? 50) >= 70
                          ? "text-red-400"
                          : (row.rsi.value ?? 50) <= 30
                            ? "text-emerald-400"
                            : "text-slate-200"
                      }
                    >
                      {row.rsi.value !== null ? row.rsi.value.toFixed(1) : "—"}
                    </span>
                  </td>
                  <td className="px-2 py-2.5 text-slate-300">
                    {row.adx.adx !== null ? row.adx.adx.toFixed(1) : "—"}
                  </td>
                  <td className="px-2 py-2.5 font-sans text-[11px]">
                    <span className="text-slate-200">{row.structure.pattern.replace("_", "/")}</span>
                    {row.structure.bos && (
                      <span className="ml-1 rounded bg-sky-500/20 px-1 py-0.5 font-mono text-[9px] text-sky-300">
                        BOS
                      </span>
                    )}
                    {row.structure.choch && (
                      <span className="ml-1 rounded bg-amber-500/20 px-1 py-0.5 font-mono text-[9px] text-amber-300">
                        CHoCH
                      </span>
                    )}
                  </td>
                  <td className="pl-2 py-2.5 text-right">
                    <span className="text-slate-200">${row.atr.value?.toFixed(2) ?? "—"}</span>
                    <span
                      className={`ml-1.5 rounded px-1 py-0.5 font-sans text-[9px] font-semibold ${
                        row.atr.regime === "EXTREME"
                          ? "bg-red-500/20 text-red-300"
                          : row.atr.regime === "HIGH"
                            ? "bg-amber-500/20 text-amber-300"
                            : row.atr.regime === "LOW"
                              ? "bg-slate-700 text-slate-300"
                              : "bg-emerald-500/15 text-emerald-300"
                      }`}
                    >
                      {row.atr.regime}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
