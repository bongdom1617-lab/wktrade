"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  ShieldAlert,
  Wifi,
  WifiOff,
} from "lucide-react";
import type { FeedHealthResponse, LiveQuote } from "@/lib/types";
import { fmtPct, fmtPrice, fmtTimeLocal, fmtUsd, fmtUtcClock } from "@/lib/format";

interface TopMarketHeaderProps {
  quote: LiveQuote | null;
  health: FeedHealthResponse | null;
  wsConnected: boolean;
  streamMode?: "ws" | "polling" | "reconnecting";
  refreshing: boolean;
  onRefresh: () => void;
}

export default function TopMarketHeader({
  quote,
  health,
  wsConnected,
  streamMode = "ws",
  refreshing,
  onRefresh,
}: TopMarketHeaderProps) {
  const prevMidRef = useRef<number | null>(null);
  const [flashClass, setFlashClass] = useState<string>("");

  useEffect(() => {
    if (quote?.mid === undefined || quote?.mid === null) return;
    if (prevMidRef.current !== null && prevMidRef.current !== quote.mid) {
      setFlashClass(quote.mid > prevMidRef.current ? "animate-flash-up" : "animate-flash-down");
      const timer = setTimeout(() => setFlashClass(""), 650);
      prevMidRef.current = quote.mid;
      return () => clearTimeout(timer);
    }
    prevMidRef.current = quote.mid;
  }, [quote?.mid]);

  const status = health?.status || quote?.status || "DISCONNECTED";
  const isLive = status === "LIVE";
  const isDelayed = status === "DELAYED";
  const isClosed = status === "MARKET_CLOSED";
  const isDisconnected = status === "DISCONNECTED";

  const changeUp = (quote?.change_usd ?? 0) >= 0;

  return (
    <header className="w-full space-y-2.5">
      {/* Main Ticker Bar */}
      <div className="terminal-panel gold-glow px-4 py-3.5 md:px-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          {/* Brand + Instrument */}
          <div className="flex flex-wrap items-center gap-3.5">
            <div className="flex items-center gap-2.5">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-amber-400/35 bg-gradient-to-br from-amber-400/20 via-amber-500/10 to-transparent shadow-inner">
                <span className="font-mono text-sm font-black tracking-tight text-amber-300">Au</span>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-base font-bold tracking-wider text-slate-50">
                    GOLD <span className="text-amber-400">AI</span>
                  </h1>
                  <span className="rounded bg-amber-400/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wider text-amber-300 border border-amber-400/25">
                    XAUUSD SPOT
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Independent Real-Time Quantitative Gold Analyzer • Zero Broker Login
                </p>
              </div>
            </div>

            <div className="hidden h-9 w-px bg-slate-800 md:block" />

            {/* Live Spot Mid + 24h Change */}
            <div className={`rounded-lg px-2.5 py-1 transition-colors ${flashClass}`}>
              <div className="flex items-baseline gap-2.5">
                <span className="font-mono text-2xl font-bold tracking-tight text-white tabular-nums md:text-3xl">
                  {quote && !isDisconnected ? `$${fmtPrice(quote.mid, 2)}` : "UNAVAILABLE"}
                </span>
                {quote && !isDisconnected && quote.change_usd !== null && (
                  <span
                    className={`rounded-md px-2 py-0.5 font-mono text-xs font-semibold tabular-nums ${
                      changeUp
                        ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25"
                        : "bg-red-500/15 text-red-400 border border-red-500/25"
                    }`}
                  >
                    {fmtUsd(quote.change_usd, 2, true)} ({fmtPct(quote.change_percent, 2)})
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex items-center gap-3 font-mono text-[11px] text-slate-400 tabular-nums">
                <span>
                  24H H: <strong className="text-slate-200">{quote ? fmtUsd(quote.day_high, 2) : "—"}</strong>
                </span>
                <span>
                  24H L: <strong className="text-slate-200">{quote ? fmtUsd(quote.day_low, 2) : "—"}</strong>
                </span>
                {quote?.prev_close && (
                  <span className="hidden sm:inline">
                    Prev D1: <strong className="text-slate-300">{fmtUsd(quote.prev_close, 2)}</strong>
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Bid / Ask / Spread Strip */}
          <div className="grid grid-cols-3 gap-2 sm:flex sm:items-center sm:gap-2.5">
            <div className="rounded-lg border border-slate-800 bg-[#070b12] px-3 py-1.5">
              <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Bid (Sell)</div>
              <div className="font-mono text-sm font-semibold text-red-400 tabular-nums">
                {quote && !isDisconnected ? fmtPrice(quote.bid, 2) : "—"}
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-[#070b12] px-3 py-1.5">
              <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Ask (Buy)</div>
              <div className="font-mono text-sm font-semibold text-emerald-400 tabular-nums">
                {quote && !isDisconnected ? fmtPrice(quote.ask, 2) : "—"}
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-[#070b12] px-3 py-1.5">
              <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Spread</div>
              <div className="font-mono text-sm font-semibold text-amber-300 tabular-nums">
                {quote && !isDisconnected ? `$${quote.spread.toFixed(2)}` : "—"}
                {quote && !isDisconnected && (
                  <span className="ml-1 text-[10px] text-slate-400">({quote.spread_bps.toFixed(1)}bp)</span>
                )}
              </div>
            </div>
          </div>

          {/* Feed Provider, Freshness & Controls */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Live Status Pill */}
            <div
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold ${
                isLive
                  ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-300"
                  : isDelayed
                    ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                    : isClosed
                      ? "border-slate-600 bg-slate-800/70 text-slate-300"
                      : "border-red-500/45 bg-red-500/15 text-red-300"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  isLive
                    ? "bg-emerald-400 animate-pulse"
                    : isDelayed
                      ? "bg-amber-400 animate-pulse"
                      : isClosed
                        ? "bg-slate-400"
                        : "bg-red-500"
                }`}
              />
              <span>{status.replace("_", " ")}</span>
              {quote && (
                <span className="font-mono text-[10px] opacity-80 tabular-nums">
                  {quote.quote_age_seconds.toFixed(0)}s
                </span>
              )}
            </div>

            {/* Transport Status (WebSocket on Local/Tunnel or Live HTTP Polling on Serverless Vercel) */}
            <div
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium ${
                wsConnected || streamMode === "polling"
                  ? "border-sky-500/30 bg-sky-500/10 text-sky-300"
                  : "border-amber-500/30 bg-amber-500/10 text-amber-300"
              }`}
            >
              {wsConnected || streamMode === "polling" ? (
                <Wifi className="h-3.5 w-3.5" />
              ) : (
                <WifiOff className="h-3.5 w-3.5" />
              )}
              <span>
                {wsConnected ? "WS Live" : streamMode === "polling" ? "Live Sync" : "Reconnecting"}
              </span>
            </div>

            {/* Jump to Backtest & Performance Module */}
            <a
              href="#performance"
              className="flex items-center gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/10 px-2.5 py-1.5 text-xs font-semibold text-amber-300 transition hover:bg-amber-400/20"
            >
              <span>Backtest & Stats</span>
            </a>

            {/* Refresh Button */}
            <button
              onClick={onRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/90 px-2.5 py-1.5 text-xs font-medium text-slate-200 transition hover:border-amber-400/50 hover:text-amber-200 disabled:opacity-50"
              title="Force live external quote & multi-timeframe recalculation"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin text-amber-400" : ""}`} />
              <span>Sync</span>
            </button>
          </div>
        </div>

        {/* Provider & Verification Metadata Strip */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/80 pt-2.5 text-[11px] text-slate-400">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5 text-amber-400" />
              Provider: <strong className="text-slate-200">{quote?.provider || health?.active_quote_provider || "Connecting..."}</strong>
            </span>
            {quote?.secondary_provider && (
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                Cross-check: <strong className="text-slate-300">{quote.secondary_provider}</strong>
                {quote.provider_discrepancy_usd !== null && (
                  <span className="font-mono text-[10px] text-slate-400 tabular-nums">
                    (Δ ${quote.provider_discrepancy_usd.toFixed(2)})
                  </span>
                )}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono tabular-nums">
            <span className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-slate-500" />
              Last Quote: <strong className="text-slate-200">{fmtUtcClock(quote?.quote_timestamp || health?.last_update)}</strong>
              <span className="text-slate-500">({fmtTimeLocal(quote?.quote_timestamp || health?.last_update)} local)</span>
            </span>
          </div>
        </div>
      </div>

      {/* Explicit Data Integrity Warning Banner (Delayed / Disconnected / Closed / Divergence) */}
      {(isDelayed || isDisconnected || isClosed || quote?.warning) && (
        <div
          className={`flex items-center gap-3 rounded-xl border px-4 py-2.5 text-xs ${
            isDisconnected
              ? "border-red-500/45 bg-red-950/50 text-red-200"
              : "border-amber-500/40 bg-amber-950/40 text-amber-200"
          }`}
        >
          {isDisconnected ? (
            <ShieldAlert className="h-4 w-4 shrink-0 text-red-400" />
          ) : (
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
          )}
          <div className="flex-1">
            <strong className="font-semibold uppercase tracking-wide">
              {isDisconnected
                ? "Live Market Feed Disconnected — No Simulated Prices Shown: "
                : isDelayed
                  ? "Delayed Market Data Detected: "
                  : isClosed
                    ? "Market Closed: "
                    : "Feed Notice: "}
            </strong>
            <span>{quote?.warning || health?.message}</span>
          </div>
        </div>
      )}
    </header>
  );
}
