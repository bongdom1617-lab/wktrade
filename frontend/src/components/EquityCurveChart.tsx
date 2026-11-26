"use client";

import React, { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type Time,
} from "lightweight-charts";
import type { EquityPoint } from "@/lib/types";

interface EquityCurveChartProps {
  points: EquityPoint[];
  initialBalance: number;
  label: string;
}

export default function EquityCurveChart({
  points,
  initialBalance,
  label,
}: EquityCurveChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || points.length === 0) return;

    const lastEq = points[points.length - 1].equity_usd;
    const isProfit = lastEq >= initialBalance;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 210,
      layout: {
        background: { type: ColorType.Solid, color: "#070b12" },
        textColor: "#94a3b8",
        fontFamily: "var(--font-mono), ui-monospace, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(30, 41, 59, 0.35)" },
        horzLines: { color: "rgba(30, 41, 59, 0.35)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#1e293b", scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { borderColor: "#1e293b", timeVisible: true, secondsVisible: false },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: isProfit ? "#10b981" : "#ef4444",
      topColor: isProfit ? "rgba(16, 185, 129, 0.28)" : "rgba(239, 68, 68, 0.28)",
      bottomColor: isProfit ? "rgba(16, 185, 129, 0.02)" : "rgba(239, 68, 68, 0.02)",
      lineWidth: 2,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });

    let lastTs = 0;
    const data = points.map((p, i) => {
      const parsed = Math.floor(Date.parse(p.timestamp) / 1000);
      const safeTs = Number.isFinite(parsed) && parsed > lastTs ? parsed : lastTs + 60 + i;
      lastTs = safeTs;
      return { time: safeTs as Time, value: p.equity_usd };
    });

    series.setData(data);
    series.createPriceLine({
      price: initialBalance,
      color: "rgba(245, 184, 46, 0.55)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Start",
    });

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (el) chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [points, initialBalance]);

  if (points.length === 0) {
    return (
      <div className="flex h-[210px] flex-col items-center justify-center rounded-xl border border-slate-800 bg-[#070b12] px-4 text-center">
        <p className="text-xs font-medium text-slate-400">{label} — No Completed Signals Yet</p>
        <p className="mt-1 text-[11px] text-slate-500">
          Equity curve renders strictly from closed, verifiable completed signals (never simulated or fabricated).
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-[#070b12]">
      <div className="flex items-center justify-between border-b border-slate-800/70 px-3 py-1.5 font-mono text-[11px] text-slate-400">
        <span className="font-semibold text-slate-200">{label} — Realized Equity Curve (Net of Costs)</span>
        <span className="tabular-nums">{points.length} completed signals plotted</span>
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
