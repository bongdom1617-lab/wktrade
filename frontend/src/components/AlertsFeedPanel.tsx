"use client";

import React from "react";
import { Bell, BellOff, Radio } from "lucide-react";
import type { AlertItem } from "@/lib/types";
import { fmtDateTime, fmtPrice } from "@/lib/format";

interface AlertsFeedPanelProps {
  alerts: AlertItem[];
  soundEnabled: boolean;
  onToggleSound: () => void;
}

export default function AlertsFeedPanel({
  alerts,
  soundEnabled,
  onToggleSound,
}: AlertsFeedPanelProps) {
  const sevStyle = (sev: string) => {
    if (sev === "SIGNAL") return "border-emerald-500/35 bg-emerald-500/10 text-emerald-200";
    if (sev === "CRITICAL") return "border-red-500/40 bg-red-500/15 text-red-200";
    if (sev === "WARNING") return "border-amber-500/35 bg-amber-500/10 text-amber-200";
    return "border-slate-800 bg-[#080d16] text-slate-300";
  };

  return (
    <div className="terminal-panel flex flex-col p-4 md:p-5">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 text-amber-400" />
          <h2 className="text-sm font-bold tracking-wide text-slate-100">Real-Time Alerts Feed</h2>
        </div>
        <button
          type="button"
          onClick={onToggleSound}
          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
            soundEnabled
              ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
              : "border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200"
          }`}
        >
          {soundEnabled ? <Bell className="h-3.5 w-3.5" /> : <BellOff className="h-3.5 w-3.5" />}
          <span>{soundEnabled ? "Chime On" : "Muted"}</span>
        </button>
      </div>

      <div className="mt-3 max-h-[340px] space-y-2 overflow-y-auto pr-1">
        {alerts.length === 0 ? (
          <div className="py-10 text-center text-xs text-slate-500">
            Monitoring live XAUUSD market events — new signals, target hits, invalidations, breakouts, and feed alerts
            will stream here automatically.
          </div>
        ) : (
          alerts.map((a) => (
            <div key={a.id} className={`rounded-lg border p-2.5 text-xs ${sevStyle(a.severity)}`}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 font-semibold">
                  <span className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider">
                    {a.category}
                  </span>
                  <span>{a.title}</span>
                </div>
                <span className="shrink-0 font-mono text-[10px] opacity-75 tabular-nums">
                  {fmtDateTime(a.created_at)}
                </span>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed opacity-90">{a.message}</p>
              {a.price !== null && (
                <div className="mt-1 font-mono text-[10px] opacity-75 tabular-nums">
                  XAUUSD @ ${fmtPrice(a.price, 2)}
                  {a.timeframe ? ` • ${a.timeframe}` : ""}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
