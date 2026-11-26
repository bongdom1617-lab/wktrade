import type {
  BacktestReport,
  BacktestRequestPayload,
  CandleSeriesResponse,
  DashboardSnapshot,
  PerformanceOverviewResponse,
  RiskPreviewResponse,
  Timeframe,
} from "./types";

const ENV_API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
const ENV_WS_URL = process.env.NEXT_PUBLIC_WS_URL || "";

export function getApiBase(): string {
  if (ENV_API_BASE) return ENV_API_BASE;
  if (typeof window !== "undefined") {
    const { hostname, port } = window.location;
    const isDirectNextDev = (hostname === "localhost" || hostname === "127.0.0.1") && port === "3000";
    if (isDirectNextDev) {
      return "http://127.0.0.1:8000";
    }
    // Same-origin relative path when served via Cloudflare Tunnel or local gateway (:8080)
    return "";
  }
  return "http://127.0.0.1:8000";
}

export function getWsUrl(): string {
  if (ENV_WS_URL) return ENV_WS_URL;
  if (ENV_API_BASE) return ENV_API_BASE.replace(/^http/, "ws") + "/ws/market";
  if (typeof window !== "undefined") {
    const { hostname, port, protocol, host } = window.location;
    const isDirectNextDev = (hostname === "localhost" || hostname === "127.0.0.1") && port === "3000";
    if (isDirectNextDev) {
      return "ws://127.0.0.1:8000/ws/market";
    }
    const wsProto = protocol === "https:" ? "wss:" : "ws:";
    return `${wsProto}//${host}/ws/market`;
  }
  return "ws://127.0.0.1:8000/ws/market";
}

export async function fetchDashboard(): Promise<DashboardSnapshot> {
  const res = await fetch(`${getApiBase()}/api/dashboard`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Dashboard fetch failed (${res.status})`);
  return res.json();
}

export async function fetchCandles(timeframe: Timeframe): Promise<CandleSeriesResponse> {
  const res = await fetch(`${getApiBase()}/api/candles/${timeframe}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Candles fetch failed (${res.status})`);
  return res.json();
}

export async function triggerForceRefresh(): Promise<DashboardSnapshot> {
  const res = await fetch(`${getApiBase()}/api/refresh`, { method: "POST" });
  if (!res.ok) throw new Error(`Refresh failed (${res.status})`);
  return res.json();
}

export async function fetchRiskPreview(params: {
  direction: "BUY" | "SELL";
  account_balance: number;
  risk_percent: number;
  min_rr: number;
}): Promise<RiskPreviewResponse> {
  const qs = new URLSearchParams({
    direction: params.direction,
    account_balance: String(params.account_balance),
    risk_percent: String(params.risk_percent),
    min_rr: String(params.min_rr),
  });
  const res = await fetch(`${getApiBase()}/api/risk-preview?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Risk preview failed (${res.status})`);
  return res.json();
}

export async function fetchPerformanceOverview(): Promise<PerformanceOverviewResponse> {
  const res = await fetch(`${getApiBase()}/api/performance/overview`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Performance overview failed (${res.status})`);
  return res.json();
}

export async function runHistoricalBacktest(
  payload: BacktestRequestPayload
): Promise<BacktestReport> {
  const res = await fetch(`${getApiBase()}/api/backtest/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || `Backtest execution failed (${res.status})`);
  }
  return res.json();
}

export async function fetchBacktestRunDetail(runUid: string): Promise<BacktestReport> {
  const res = await fetch(`${getApiBase()}/api/backtest/runs/${encodeURIComponent(runUid)}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Backtest run fetch failed (${res.status})`);
  return res.json();
}
