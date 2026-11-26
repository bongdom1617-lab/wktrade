"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import TopMarketHeader from "@/components/TopMarketHeader";
import PrimarySignalCard from "@/components/PrimarySignalCard";
import TradingChart from "@/components/TradingChart";
import MtfMatrixTable from "@/components/MtfMatrixTable";
import AiExplanationPanel from "@/components/AiExplanationPanel";
import TechnicalMetricsGrid from "@/components/TechnicalMetricsGrid";
import RiskCalculatorPanel from "@/components/RiskCalculatorPanel";
import SignalHistoryPanel from "@/components/SignalHistoryPanel";
import AlertsFeedPanel from "@/components/AlertsFeedPanel";
import PerformanceBacktestModule from "@/components/PerformanceBacktestModule";
import ErrorBoundary from "@/components/ErrorBoundary";
import { fetchCandles, fetchDashboard, getWsUrl, triggerForceRefresh } from "@/lib/api";
import type {
  ActiveTradeMonitor,
  CandleSeriesResponse,
  DashboardSnapshot,
  FeedHealthResponse,
  LiveQuote,
  Timeframe,
} from "@/lib/types";

function playAlertBeep() {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.value = 0.08;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.16);
  } catch {
    // browser autoplay policy may block audio until gesture
  }
}

export default function GoldAiTerminalPage() {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [selectedTf, setSelectedTf] = useState<Timeframe>("M15");
  const [candleData, setCandleData] = useState<CandleSeriesResponse | null>(null);
  const [candleLoading, setCandleLoading] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);

  const lastAlertIdRef = useRef<number | null>(null);
  const soundEnabledRef = useRef(soundEnabled);
  soundEnabledRef.current = soundEnabled;
  const selectedTfRef = useRef<Timeframe>(selectedTf);
  selectedTfRef.current = selectedTf;

  const loadCandles = useCallback(async (tf: Timeframe) => {
    setCandleLoading(true);
    try {
      const data = await fetchCandles(tf);
      setCandleData(data);
    } catch (err) {
      console.error("Failed loading candles:", err);
    } finally {
      setCandleLoading(false);
    }
  }, []);

  // Initial REST hydration with automatic self-healing retry if backend is still starting
  useEffect(() => {
    let active = true;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const hydrate = () => {
      fetchDashboard()
        .then((snap) => {
          if (!active) return;
          setSnapshot(snap);
          setBackendError(null);
          if (snap.recent_alerts.length > 0) {
            lastAlertIdRef.current = snap.recent_alerts[0].id;
          }
        })
        .catch((err) => {
          if (!active) return;
          setBackendError(err instanceof Error ? err.message : "Backend API unreachable");
          retryTimer = setTimeout(hydrate, 3500);
        });
    };

    hydrate();
    return () => {
      active = false;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, []);

  // Fetch candlesticks when selected timeframe changes + refresh on 20s cadence
  useEffect(() => {
    loadCandles(selectedTf);
    const interval = setInterval(() => {
      loadCandles(selectedTf);
    }, 20000);
    return () => clearInterval(interval);
  }, [selectedTf, loadCandles]);

  // Real-time WebSocket stream with automatic reconnection
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;
    let unmounted = false;

    const connect = () => {
      if (unmounted) return;
      try {
        ws = new WebSocket(getWsUrl());
      } catch {
        reconnectTimer = setTimeout(connect, 3000);
        return;
      }

      ws.onopen = () => {
        setWsConnected(true);
        setBackendError(null);
        pingTimer = setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "snapshot" && msg.data) {
            const nextSnap = msg.data as DashboardSnapshot;
            setSnapshot(nextSnap);
            // Play chime on brand-new high-priority alert
            if (nextSnap.recent_alerts.length > 0) {
              const newest = nextSnap.recent_alerts[0];
              if (
                lastAlertIdRef.current !== null &&
                newest.id > lastAlertIdRef.current &&
                (newest.severity === "SIGNAL" || newest.severity === "CRITICAL") &&
                soundEnabledRef.current
              ) {
                playAlertBeep();
              }
              lastAlertIdRef.current = newest.id;
            }
            // Refresh chart candles when full snapshot updates
            loadCandles(selectedTfRef.current);
          } else if (msg.type === "quote_tick" && msg.data) {
            const tick = msg.data as {
              timestamp: string;
              quote: LiveQuote | null;
              feed_health: FeedHealthResponse;
              active_trade_monitor: ActiveTradeMonitor | null;
            };
            setSnapshot((prev) =>
              prev
                ? {
                    ...prev,
                    timestamp: tick.timestamp,
                    quote: tick.quote,
                    feed_health: tick.feed_health,
                    active_trade_monitor: tick.active_trade_monitor,
                  }
                : prev
            );
          }
        } catch {
          // ignore malformed WS frames
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        if (pingTimer) clearInterval(pingTimer);
        if (!unmounted) {
          reconnectTimer = setTimeout(connect, 2500);
        }
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();
    return () => {
      unmounted = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pingTimer) clearInterval(pingTimer);
      ws?.close();
    };
  }, [loadCandles]);

  const handleForceRefresh = async () => {
    setRefreshing(true);
    try {
      const snap = await triggerForceRefresh();
      setSnapshot(snap);
      await loadCandles(selectedTf);
      setBackendError(null);
    } catch (err) {
      setBackendError(err instanceof Error ? err.message : "Failed to refresh live data");
    } finally {
      setRefreshing(false);
    }
  };

  const selectedTfAnalysis = snapshot?.mtf?.timeframes?.[selectedTf] ?? null;

  return (
    <div className="min-h-screen bg-[#06090f] text-slate-100">
      <div className="mx-auto max-w-[1680px] space-y-4 px-3 py-3 md:px-5 md:py-4">
        {/* Top Live XAUUSD Market Header */}
        <TopMarketHeader
          quote={snapshot?.quote ?? null}
          health={snapshot?.feed_health ?? null}
          wsConnected={wsConnected}
          refreshing={refreshing}
          onRefresh={handleForceRefresh}
        />

        {backendError && (
          <div className="rounded-xl border border-red-500/40 bg-red-950/50 px-4 py-3 text-xs text-red-200">
            <strong>Backend Connection Notice:</strong> {backendError}. Ensure the FastAPI backend is running on{" "}
            <code className="font-mono text-amber-300">http://127.0.0.1:8000</code>.
          </div>
        )}

        {/* Row 1: TradingView Live Chart (Left 8) + Primary AI Signal Verdict (Right 4) */}
        <section className="grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-8">
            <ErrorBoundary label="Live XAUUSD Chart">
              <TradingChart
                timeframe={selectedTf}
                onTimeframeChange={setSelectedTf}
                candleData={candleData}
                liveMid={snapshot?.feed_health?.status === "LIVE" ? (snapshot?.quote?.mid ?? null) : null}
                tfAnalysis={selectedTfAnalysis}
                signal={snapshot?.signal ?? null}
                activeMonitor={snapshot?.active_trade_monitor ?? null}
                loading={candleLoading}
              />
            </ErrorBoundary>
          </div>
          <div className="xl:col-span-4">
            <ErrorBoundary label="Primary AI Signal">
              <PrimarySignalCard
                signal={snapshot?.signal ?? null}
                activeMonitor={snapshot?.active_trade_monitor ?? null}
              />
            </ErrorBoundary>
          </div>
        </section>

        {/* Row 2: Multi-Timeframe Matrix + Structured AI Explanation (8 Questions) */}
        <section className="grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-6">
            <MtfMatrixTable
              mtf={snapshot?.mtf ?? null}
              selectedTf={selectedTf}
              onSelectTf={setSelectedTf}
            />
          </div>
          <div className="xl:col-span-6">
            <AiExplanationPanel signal={snapshot?.signal ?? null} />
          </div>
        </section>

        {/* Row 3: Deep Technical Indicators & Structure + Smart SL/TP Risk Calculator */}
        <section className="grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-7">
            <TechnicalMetricsGrid timeframe={selectedTf} analysis={selectedTfAnalysis} />
          </div>
          <div className="xl:col-span-5">
            <RiskCalculatorPanel signal={snapshot?.signal ?? null} />
          </div>
        </section>

        {/* Row 4: Persisted Signal History + Real-Time Alerts Feed */}
        <section className="grid gap-4 xl:grid-cols-12">
          <div className="xl:col-span-7">
            <SignalHistoryPanel signals={snapshot?.recent_signals ?? []} />
          </div>
          <div className="xl:col-span-5">
            <AlertsFeedPanel
              alerts={snapshot?.recent_alerts ?? []}
              soundEnabled={soundEnabled}
              onToggleSound={() => setSoundEnabled((v) => !v)}
            />
          </div>
        </section>

        {/* Row 5: AI Signal Performance, Historical XAUUSD Backtesting & Live Forward Testing */}
        <ErrorBoundary label="Performance & Backtesting Module">
          <PerformanceBacktestModule
            syncKey={`${snapshot?.recent_signals?.length ?? 0}-${snapshot?.recent_signals?.[0]?.status ?? ""}-${wsConnected}`}
          />
        </ErrorBoundary>

        {/* Footer Disclaimer */}
        <footer className="rounded-xl border border-slate-800/70 bg-[#080c14] px-4 py-3 text-[11px] text-slate-500 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <strong className="text-slate-300">GOLD AI — Independent XAUUSD Market Analyzer.</strong> Operates without
            Exness, MT5, or any broker credentials. No automated order execution.
          </div>
          <div className="text-slate-500">
            Analytical software only — never guarantees profits. Trading leveraged Gold carries significant risk.
          </div>
        </footer>
      </div>
    </div>
  );
}
