"use client";

import React, { useEffect, useState } from "react";
import { Calculator, ShieldCheck } from "lucide-react";
import { fetchRiskPreview } from "@/lib/api";
import type { RiskPreviewResponse, TradingSignal } from "@/lib/types";
import { fmtPrice, fmtUsd } from "@/lib/format";

interface RiskCalculatorPanelProps {
  signal: TradingSignal | null;
}

export default function RiskCalculatorPanel({ signal }: RiskCalculatorPanelProps) {
  const defaultDir: "BUY" | "SELL" = signal?.action === "SELL" ? "SELL" : "BUY";
  const [direction, setDirection] = useState<"BUY" | "SELL">(defaultDir);
  const [balance, setBalance] = useState<string>("10000");
  const [riskPct, setRiskPct] = useState<string>("1.0");
  const [minRr, setMinRr] = useState<string>("2.0");
  const [preview, setPreview] = useState<RiskPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (signal?.action === "BUY" || signal?.action === "SELL") {
      setDirection(signal.action);
    }
  }, [signal?.action]);

  useEffect(() => {
    const bal = parseFloat(balance);
    const rp = parseFloat(riskPct);
    const rr = parseFloat(minRr);
    if (!bal || bal <= 0 || !rp || rp <= 0 || !rr || rr < 1.5) return;

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetchRiskPreview({
          direction,
          account_balance: bal,
          risk_percent: rp,
          min_rr: rr,
        });
        setPreview(res);
      } catch {
        // ignore transient errors while live feed bootstraps
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [direction, balance, riskPct, minRr, signal?.market_price]);

  const rp = preview?.risk_plan;

  return (
    <div className="terminal-panel flex flex-col p-4 md:p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <Calculator className="h-4 w-4 text-amber-400" />
          <h2 className="text-sm font-bold tracking-wide text-slate-100">
            Smart SL / TP & Position Risk Calculator
          </h2>
        </div>
        <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
          ATR + Swings + S/R
        </span>
      </div>

      {/* Inputs */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <div>
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Scenario Side
          </label>
          <div className="mt-1 grid grid-cols-2 gap-1 rounded-lg border border-slate-800 bg-[#070b12] p-0.5">
            {(["BUY", "SELL"] as const).map((side) => (
              <button
                key={side}
                type="button"
                onClick={() => setDirection(side)}
                className={`rounded-md py-1 font-mono text-xs font-bold transition ${
                  direction === side
                    ? side === "BUY"
                      ? "bg-emerald-500 text-slate-950"
                      : "bg-red-500 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {side}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Account ($)
          </label>
          <input
            type="number"
            min="100"
            step="500"
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2.5 py-1.5 font-mono text-xs text-white focus:border-amber-400/60 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Risk % / Trade
          </label>
          <input
            type="number"
            min="0.1"
            max="5"
            step="0.25"
            value={riskPct}
            onChange={(e) => setRiskPct(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2.5 py-1.5 font-mono text-xs text-white focus:border-amber-400/60 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Min R:R (TP2)
          </label>
          <input
            type="number"
            min="1.5"
            max="4.0"
            step="0.25"
            value={minRr}
            onChange={(e) => setMinRr(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-800 bg-[#070b12] px-2.5 py-1.5 font-mono text-xs text-white focus:border-amber-400/60 focus:outline-none"
          />
        </div>
      </div>

      {/* Alignment Notice */}
      {preview && !preview.matches_ai_signal && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-200">
          Planning preview for <strong>{direction}</strong>. Primary AI recommendation is currently{" "}
          <strong>{preview.current_ai_action}</strong> — never enter against AI risk filters.
        </div>
      )}

      {/* Calculated Results */}
      {rp ? (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 font-mono tabular-nums">
            <div className="rounded-lg border border-slate-800 bg-[#080d16] p-2.5">
              <div className="text-[10px] text-slate-400">Max Risk ($)</div>
              <div className="mt-0.5 text-sm font-bold text-red-400">{fmtUsd(preview.risk_amount_usd, 2)}</div>
              <div className="text-[10px] text-slate-500">SL dist ${rp.risk_usd.toFixed(2)}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-[#080d16] p-2.5">
              <div className="text-[10px] text-slate-400">Position Size</div>
              <div className="mt-0.5 text-sm font-bold text-amber-300">{preview.suggested_lots.toFixed(2)} Lots</div>
              <div className="text-[10px] text-slate-500">{preview.suggested_ounces.toFixed(2)} oz XAU</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-[#080d16] p-2.5">
              <div className="text-[10px] text-slate-400">TP2 Target P&L</div>
              <div className="mt-0.5 text-sm font-bold text-emerald-400">
                +{fmtUsd(preview.potential_profit_tp2_usd, 2)}
              </div>
              <div className="text-[10px] text-slate-500">1:{rp.rr_tp2.toFixed(2)} R:R</div>
            </div>
          </div>

          <div className="space-y-1.5 rounded-xl border border-slate-800 bg-[#070b12] p-3 text-[11px]">
            <div className="flex items-center gap-1.5 font-semibold text-slate-200">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              Level Selection Breakdown {loading && <span className="text-slate-500">(updating...)</span>}
            </div>
            {rp.rationales.map((r) => (
              <div key={r.level_name} className="leading-relaxed text-slate-400">
                <span className="font-mono font-semibold text-slate-200">
                  {r.level_name} (${fmtPrice(r.price, 2)}
                  {r.risk_reward ? ` • 1:${r.risk_reward.toFixed(2)}` : ""}):
                </span>{" "}
                {r.reason}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-xs text-slate-500">Waiting for live ATR & swing data to compute risk plan...</div>
      )}
    </div>
  );
}
