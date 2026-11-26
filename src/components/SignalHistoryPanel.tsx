"use client";

import React from "react";
import { History } from "lucide-react";
import type { SignalHistoryItem } from "@/lib/types";
import { fmtDateTime, fmtPrice } from "@/lib/format";

interface SignalHistoryPanelProps {
  signals: SignalHistoryItem[];
}

export default function SignalHistoryPanel({ signals }: SignalHistoryPanelProps) {
  const statusStyle = (status: string) => {
    if (status === "TP3_HIT" || status === "TP2_HIT" || status === "TP1_HIT")
      return "bg-emerald-500/15 text-emerald-300 border-emerald-500/35";
    if (status === "SL_HIT" || status === "INVALIDATED")
      return "bg-red-500/15 text-red-300 border-red-500/35";
    if (status === "ACTIVE" || status === "ENTRY_TRIGGERED")
      return "bg-sky-500/15 text-sky-300 border-sky-500/35";
    return "bg-slate-800 text-slate-300 border-slate-700";
  };

  return (
    <div className="terminal-panel flex flex-col p-4 md:p-5">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-amber-400" />
          <h2 className="text-sm font-bold tracking-wide text-slate-100">
            Verified Signal History & Outcome Log
          </h2>
        </div>
        <span className="font-mono text-[11px] text-slate-400">{signals.length} recorded</span>
      </div>

      {signals.length === 0 ? (
        <div className="py-10 text-center text-xs text-slate-400">
          No actionable BUY/SELL setups recorded yet. GOLD AI only logs deduplicated, high-confluence signals that pass
          all multi-timeframe and 1:2 R:R gates.
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                <th className="py-2 pr-2">Timestamp</th>
                <th className="px-2 py-2">Signal</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Entry</th>
                <th className="px-2 py-2">Stop Loss</th>
                <th className="px-2 py-2">TP1 / TP2 / TP3</th>
                <th className="px-2 py-2">R:R</th>
                <th className="pl-2 py-2 text-right">Conf</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono tabular-nums">
              {signals.map((s) => (
                <tr key={s.signal_uid} className="hover:bg-slate-800/30">
                  <td className="py-2 pr-2 text-[11px] text-slate-400">
                    <div>{fmtDateTime(s.created_at)}</div>
                    <div className="text-[10px] text-slate-500">{s.signal_uid}</div>
                  </td>
                  <td className="px-2 py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-[11px] font-bold ${
                        s.action === "BUY"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-red-500/20 text-red-300"
                      }`}
                    >
                      {s.action}
                    </span>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <span className={`inline-block whitespace-nowrap rounded border px-2 py-0.5 text-[10px] font-semibold ${statusStyle(s.status)}`}>
                      {s.status.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-amber-200">${fmtPrice(s.entry_price, 2)}</td>
                  <td className="px-2 py-2 text-red-300">${fmtPrice(s.stop_loss, 2)}</td>
                  <td className="px-2 py-2 text-[11px] text-emerald-300">
                    ${fmtPrice(s.tp1, 1)} / ${fmtPrice(s.tp2, 1)} / ${fmtPrice(s.tp3, 1)}
                  </td>
                  <td className="px-2 py-2 text-slate-200">
                    {s.risk_reward_tp2 ? `1:${s.risk_reward_tp2.toFixed(1)}` : "—"}
                  </td>
                  <td className="pl-2 py-2 text-right font-semibold text-slate-200">{s.confidence}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
