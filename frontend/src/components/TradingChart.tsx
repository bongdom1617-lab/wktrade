"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type {
  ActiveTradeMonitor,
  CandleSeriesResponse,
  Timeframe,
  TimeframeAnalysis,
  TradingSignal,
} from "@/lib/types";
import { fmtPrice } from "@/lib/format";

const TIMEFRAMES: Timeframe[] = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

interface TradingChartProps {
  timeframe: Timeframe;
  onTimeframeChange: (tf: Timeframe) => void;
  candleData: CandleSeriesResponse | null;
  liveMid: number | null;
  tfAnalysis: TimeframeAnalysis | null;
  signal: TradingSignal | null;
  activeMonitor: ActiveTradeMonitor | null;
  loading: boolean;
}

export default function TradingChart({
  timeframe,
  onTimeframeChange,
  candleData,
  liveMid,
  tfAnalysis,
  signal,
  activeMonitor,
  loading,
}: TradingChartProps) {
  const mainContainerRef = useRef<HTMLDivElement | null>(null);
  const rsiContainerRef = useRef<HTMLDivElement | null>(null);
  const macdContainerRef = useRef<HTMLDivElement | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lastCandleRef = useRef<{ time: Time; open: number; high: number; low: number; close: number } | null>(null);

  const [toggles, setToggles] = useState({
    ema9: true,
    ema20: true,
    ema50: true,
    ema100: false,
    ema200: true,
    bb: false,
    vwap: true,
    sr: true,
    signalLevels: true,
  });

  const toggle = (k: keyof typeof toggles) =>
    setToggles((prev) => ({ ...prev, [k]: !prev[k] }));

  useEffect(() => {
    const mainEl = mainContainerRef.current;
    const rsiEl = rsiContainerRef.current;
    const macdEl = macdContainerRef.current;
    if (!mainEl || !rsiEl || !macdEl || !candleData || candleData.candles.length === 0) {
      return;
    }

    const commonLayout = {
      background: { type: ColorType.Solid, color: "#080c14" },
      textColor: "#94a3b8",
      fontFamily: "var(--font-mono), ui-monospace, monospace",
      fontSize: 11,
    };

    const commonGrid = {
      vertLines: { color: "rgba(30, 41, 59, 0.45)" },
      horzLines: { color: "rgba(30, 41, 59, 0.45)" },
    };

    const mainChart: IChartApi = createChart(mainEl, {
      width: mainEl.clientWidth,
      height: 365,
      layout: commonLayout,
      grid: commonGrid,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#1e293b", scaleMargins: { top: 0.08, bottom: 0.16 } },
      timeScale: { borderColor: "#1e293b", timeVisible: true, secondsVisible: timeframe === "M1" },
    });

    const rsiChart: IChartApi = createChart(rsiEl, {
      width: rsiEl.clientWidth,
      height: 108,
      layout: commonLayout,
      grid: commonGrid,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#1e293b", scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor: "#1e293b", visible: false, timeVisible: true },
    });

    const macdChart: IChartApi = createChart(macdEl, {
      width: macdEl.clientWidth,
      height: 118,
      layout: commonLayout,
      grid: commonGrid,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#1e293b", scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { borderColor: "#1e293b", timeVisible: true, secondsVisible: false },
    });

    // 1. Candlesticks
    const candleSeries = mainChart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    const mappedCandles = candleData.candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeries.setData(mappedCandles);
    candleSeriesRef.current = candleSeries;
    lastCandleRef.current = mappedCandles.length > 0 ? { ...mappedCandles[mappedCandles.length - 1] } : null;

    // 2. Tick Volume histogram on lower overlay scale
    const volSeries = mainChart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    mainChart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.84, bottom: 0 },
    });
    volSeries.setData(
      candleData.candles.map((c) => ({
        time: c.time as Time,
        value: c.volume,
        color: c.close >= c.open ? "rgba(16, 185, 129, 0.22)" : "rgba(239, 68, 68, 0.22)",
      }))
    );

    // 3. Technical Overlays (EMA 9/20/50/100/200, BB, VWAP)
    const ov = candleData.overlays || {};
    const addLine = (
      points: { time: number; value: number }[] | undefined,
      color: string,
      width: 1 | 2 | 3 | 4 = 1,
      style: LineStyle = LineStyle.Solid,
      title = ""
    ) => {
      if (!points || points.length === 0) return;
      const s = mainChart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: false,
        title,
      });
      s.setData(points.map((p) => ({ time: p.time as Time, value: p.value })));
    };

    if (toggles.ema9) addLine(ov.ema_9, "#38bdf8", 1);
    if (toggles.ema20) addLine(ov.ema_20, "#f5b82e", 2);
    if (toggles.ema50) addLine(ov.ema_50, "#a855f7", 2);
    if (toggles.ema100) addLine(ov.ema_100, "#fb7185", 1, LineStyle.Dashed);
    if (toggles.ema200) addLine(ov.ema_200, "#e2e8f0", 2);
    if (toggles.bb) {
      addLine(ov.bb_upper, "rgba(148, 163, 184, 0.55)", 1, LineStyle.Dotted);
      addLine(ov.bb_lower, "rgba(148, 163, 184, 0.55)", 1, LineStyle.Dotted);
    }
    if (toggles.vwap && ov.vwap && ov.vwap.length > 0) {
      addLine(ov.vwap, "#22d3ee", 2, LineStyle.Dashed);
    }

    // 4. Support & Resistance Price Lines
    if (toggles.sr && tfAnalysis) {
      tfAnalysis.resistance_levels.slice(0, 2).forEach((lv, idx) => {
        candleSeries.createPriceLine({
          price: lv.price,
          color: "rgba(239, 68, 68, 0.55)",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `R${idx + 1}`,
        });
      });
      tfAnalysis.support_levels.slice(0, 2).forEach((lv, idx) => {
        candleSeries.createPriceLine({
          price: lv.price,
          color: "rgba(16, 185, 129, 0.55)",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `S${idx + 1}`,
        });
      });
    }

    // 5. Active AI Signal Levels (Entry, SL, TP1, TP2, TP3)
    const activePlan = signal?.risk_plan || (activeMonitor ? {
      entry_price: activeMonitor.entry_price,
      stop_loss: activeMonitor.stop_loss,
      tp1: activeMonitor.tp1,
      tp2: activeMonitor.tp2,
      tp3: activeMonitor.tp3,
    } : null);

    if (toggles.signalLevels && activePlan) {
      candleSeries.createPriceLine({
        price: activePlan.entry_price,
        color: "#f5b82e",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "ENTRY",
      });
      candleSeries.createPriceLine({
        price: activePlan.stop_loss,
        color: "#ef4444",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "SL",
      });
      candleSeries.createPriceLine({
        price: activePlan.tp1,
        color: "#34d399",
        lineWidth: 1,
        lineStyle: LineStyle.LargeDashed,
        axisLabelVisible: true,
        title: "TP1",
      });
      candleSeries.createPriceLine({
        price: activePlan.tp2,
        color: "#10b981",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "TP2",
      });
      candleSeries.createPriceLine({
        price: activePlan.tp3,
        color: "#059669",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: "TP3",
      });
    }

    // 6. RSI 14 Panel (aligned 1:1 with candle timestamps using whitespace points for warmup bars)
    if (ov.rsi_14 && ov.rsi_14.length > 0) {
      const rsiSeries: ISeriesApi<"Line"> = rsiChart.addSeries(LineSeries, {
        color: "#c084fc",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const rsiMap = new Map<number, number>(ov.rsi_14.map((p) => [p.time, p.value]));
      const alignedRsiData = candleData.candles.map((c) => {
        const val = rsiMap.get(c.time);
        return val !== undefined
          ? { time: c.time as Time, value: val }
          : { time: c.time as Time };
      });
      rsiSeries.setData(alignedRsiData);
      rsiSeries.createPriceLine({
        price: 70,
        color: "rgba(239, 68, 68, 0.55)",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "OB 70",
      });
      rsiSeries.createPriceLine({
        price: 50,
        color: "rgba(148, 163, 184, 0.3)",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: false,
        title: "",
      });
      rsiSeries.createPriceLine({
        price: 30,
        color: "rgba(16, 185, 129, 0.55)",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "OS 30",
      });
    }

    // 7. MACD (12, 26, 9) Panel
    if (ov.macd_hist && ov.macd_hist.length > 0) {
      const histSeries = macdChart.addSeries(HistogramSeries, {
        priceLineVisible: false,
      });
      histSeries.setData(
        ov.macd_hist.map((p) => ({
          time: p.time as Time,
          value: p.value,
          color: p.value >= 0 ? "rgba(16, 185, 129, 0.65)" : "rgba(239, 68, 68, 0.65)",
        }))
      );
    }
    if (ov.macd_line && ov.macd_line.length > 0) {
      const ml = macdChart.addSeries(LineSeries, {
        color: "#38bdf8",
        lineWidth: 1,
        priceLineVisible: false,
      });
      ml.setData(ov.macd_line.map((p) => ({ time: p.time as Time, value: p.value })));
    }
    if (ov.macd_signal && ov.macd_signal.length > 0) {
      const ms = macdChart.addSeries(LineSeries, {
        color: "#f59e0b",
        lineWidth: 1,
        priceLineVisible: false,
      });
      ms.setData(ov.macd_signal.map((p) => ({ time: p.time as Time, value: p.value })));
    }

    // Fit initial visible range to recent ~95 bars for clean institutional readability
    const total = candleData.candles.length;
    const fromIdx = Math.max(0, total - 95);
    mainChart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: total + 4 });
    rsiChart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: total + 4 });
    macdChart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: total + 4 });

    // Synchronize scroll & zoom across Main, RSI, and MACD charts
    let syncing = false;
    const syncRange = (source: IChartApi, targets: IChartApi[]) => {
      source.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return;
        syncing = true;
        targets.forEach((t) => {
          try {
            t.timeScale().setVisibleLogicalRange(range);
          } catch {
            // ignore transient range mismatch
          }
        });
        syncing = false;
      });
    };
    syncRange(mainChart, [rsiChart, macdChart]);
    syncRange(rsiChart, [mainChart, macdChart]);
    syncRange(macdChart, [mainChart, rsiChart]);

    // Responsive resize observer
    const observer = new ResizeObserver(() => {
      if (mainEl) mainChart.applyOptions({ width: mainEl.clientWidth });
      if (rsiEl) rsiChart.applyOptions({ width: rsiEl.clientWidth });
      if (macdEl) macdChart.applyOptions({ width: macdEl.clientWidth });
    });
    observer.observe(mainEl);

    return () => {
      observer.disconnect();
      candleSeriesRef.current = null;
      lastCandleRef.current = null;
      mainChart.remove();
      rsiChart.remove();
      macdChart.remove();
    };
  }, [candleData, tfAnalysis, signal, activeMonitor, toggles, timeframe]);

  // Smooth in-place candle tick update on every live WebSocket price tick (zero chart flicker / zoom preserved)
  useEffect(() => {
    if (liveMid === null || !candleSeriesRef.current || !lastCandleRef.current) return;
    const updated = {
      ...lastCandleRef.current,
      close: liveMid,
      high: Math.max(lastCandleRef.current.high, liveMid),
      low: Math.min(lastCandleRef.current.low, liveMid),
    };
    lastCandleRef.current = updated;
    try {
      candleSeriesRef.current.update(updated);
    } catch {
      // ignore if chart unmounted during timeframe transition
    }
  }, [liveMid]);

  const indicatorButtons: { key: keyof typeof toggles; label: string; dot: string }[] = [
    { key: "ema9", label: "EMA 9", dot: "bg-sky-400" },
    { key: "ema20", label: "EMA 20", dot: "bg-amber-400" },
    { key: "ema50", label: "EMA 50", dot: "bg-purple-400" },
    { key: "ema100", label: "EMA 100", dot: "bg-rose-400" },
    { key: "ema200", label: "EMA 200", dot: "bg-slate-200" },
    { key: "bb", label: "BB", dot: "bg-slate-400" },
    { key: "vwap", label: "VWAP", dot: "bg-cyan-400" },
    { key: "sr", label: "S/R", dot: "bg-emerald-400" },
    { key: "signalLevels", label: "SL/TP", dot: "bg-amber-300" },
  ];

  return (
    <div className="terminal-panel flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/90 px-4 py-2.5">
        {/* Timeframe Switcher */}
        <div className="flex items-center gap-1 rounded-lg bg-[#070b12] p-1 border border-slate-800">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => onTimeframeChange(tf)}
              className={`rounded-md px-2.5 py-1 font-mono text-xs font-semibold transition ${
                timeframe === tf
                  ? "bg-amber-400 text-slate-950 shadow"
                  : "text-slate-400 hover:bg-slate-800/80 hover:text-slate-100"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Indicator Toggle Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          {indicatorButtons.map((b) => (
            <button
              key={b.key}
              type="button"
              onClick={() => toggle(b.key)}
              className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium transition ${
                toggles[b.key]
                  ? "border-slate-600 bg-slate-800/90 text-slate-100"
                  : "border-slate-800/80 bg-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${b.dot} ${toggles[b.key] ? "opacity-100" : "opacity-30"}`} />
              {b.label}
            </button>
          ))}
        </div>
      </div>

      {/* Live Overlay Values Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/60 bg-[#080c14] px-4 py-1.5 font-mono text-[11px] text-slate-400 tabular-nums">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-semibold text-slate-200">
            XAUUSD • {timeframe} ({tfAnalysis?.role || "Chart"})
          </span>
          {tfAnalysis && (
            <>
              <span className="text-sky-400">E9: {fmtPrice(tfAnalysis.ema.ema_9, 2)}</span>
              <span className="text-amber-400">E20: {fmtPrice(tfAnalysis.ema.ema_20, 2)}</span>
              <span className="text-purple-400">E50: {fmtPrice(tfAnalysis.ema.ema_50, 2)}</span>
              <span className="text-slate-200">
                E200: {fmtPrice(tfAnalysis.ema.ema_200, 2)}
                {!tfAnalysis.ema.ema_200_warmed && (
                  <span className="ml-1 text-[10px] text-amber-400/80">({tfAnalysis.ema.bars_used} bars)</span>
                )}
              </span>
              {tfAnalysis.vwap.applicable && tfAnalysis.vwap.value && (
                <span className="text-cyan-400">VWAP: {fmtPrice(tfAnalysis.vwap.value, 2)}</span>
              )}
            </>
          )}
        </div>
        <div className="text-[10px] text-slate-500">
          {candleData ? `${candleData.bar_count} real bars • ${candleData.provider}` : "Loading..."}
        </div>
      </div>

      {/* Main Candlestick Chart */}
      <div className="relative bg-[#080c14]">
        {loading && !candleData && (
          <div className="flex h-[365px] items-center justify-center text-xs text-slate-400">
            Loading live {timeframe} XAUUSD candlesticks...
          </div>
        )}
        <div ref={mainContainerRef} className="w-full" />
      </div>

      {/* RSI 14 Sub-Panel */}
      <div className="border-t border-slate-800/80 bg-[#080c14]">
        <div className="flex items-center justify-between px-4 py-1 font-mono text-[11px]">
          <span className="font-semibold text-purple-300">
            RSI (14):{" "}
            <strong className="text-white tabular-nums">
              {tfAnalysis?.rsi.value !== null && tfAnalysis?.rsi.value !== undefined
                ? tfAnalysis.rsi.value.toFixed(2)
                : "—"}
            </strong>
          </span>
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-slate-400">
              Zone: <strong className="text-slate-200">{tfAnalysis?.rsi.zone.replace("_", " ") || "—"}</strong>
            </span>
            {tfAnalysis?.rsi.divergence && (
              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-amber-300">
                {tfAnalysis.rsi.divergence.replace("_", " ")}
              </span>
            )}
          </div>
        </div>
        <div ref={rsiContainerRef} className="w-full" />
      </div>

      {/* MACD Sub-Panel */}
      <div className="border-t border-slate-800/80 bg-[#080c14]">
        <div className="flex items-center justify-between px-4 py-1 font-mono text-[11px]">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-sky-300">
              MACD (12, 26, 9):{" "}
              <strong className="text-white tabular-nums">
                {tfAnalysis?.macd.macd !== null && tfAnalysis?.macd.macd !== undefined
                  ? tfAnalysis.macd.macd.toFixed(2)
                  : "—"}
              </strong>
            </span>
            <span className="text-amber-300 tabular-nums">
              Sig:{" "}
              {tfAnalysis?.macd.signal !== null && tfAnalysis?.macd.signal !== undefined
                ? tfAnalysis.macd.signal.toFixed(2)
                : "—"}
            </span>
            <span
              className={`tabular-nums ${
                (tfAnalysis?.macd.histogram ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"
              }`}
            >
              Hist:{" "}
              {tfAnalysis?.macd.histogram !== null && tfAnalysis?.macd.histogram !== undefined
                ? tfAnalysis.macd.histogram.toFixed(2)
                : "—"}
            </span>
          </div>
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-slate-400">
              {tfAnalysis?.macd.momentum_state.replace("_", " ") || "—"}
            </span>
            {tfAnalysis?.macd.crossover && (
              <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-sky-300">
                {tfAnalysis.macd.crossover.replace("_", " ")}
              </span>
            )}
          </div>
        </div>
        <div ref={macdContainerRef} className="w-full" />
      </div>
    </div>
  );
}
