from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.analysis.risk_calculator import calculate_smart_risk_plan
from app.backtesting.engine import (
    execute_and_persist_backtest,
    list_backtest_runs,
    load_backtest_report,
)
from app.backtesting.forward_tracker import build_forward_test_report
from app.config import settings
from app.database import init_db
from app.market_data.base import ALL_TIMEFRAMES, MarketDataError, utc_now_iso
from app.monitor.engine import RealTimeMonitor
from app.schemas import (
    AlertItem,
    BacktestReport,
    BacktestRequest,
    BacktestRunSummaryItem,
    CandleSeriesResponse,
    DashboardSnapshot,
    FeedHealthResponse,
    ForwardTestReport,
    LiveQuote,
    MtfSynthesis,
    PerformanceOverviewResponse,
    SignalHistoryItem,
    Timeframe,
    TradingSignal,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("gold_ai.api")

monitor = RealTimeMonitor()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.is_vercel:
        monitor.init_serverless()
        yield
        await monitor.market.close()
    else:
        await monitor.start()
        yield
        await monitor.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Independent Real-Time XAUUSD (Gold) Market Analyzer & AI Trading Decision Engine. "
        "No Exness, MT5, or broker account credentials required. Analytical decision-support only."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list() + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _ensure_serverless(need_analysis: bool = True, target_tf: Optional[Timeframe] = None) -> None:
    if settings.is_vercel:
        init_db()
        await monitor.ensure_fresh_serverless(need_analysis=need_analysis, target_tf=target_tf)


@app.get("/api/health", response_model=FeedHealthResponse)
async def get_health() -> FeedHealthResponse:
    await _ensure_serverless(need_analysis=False)
    return monitor.market.get_health()


@app.get("/api/dashboard", response_model=DashboardSnapshot)
async def get_dashboard() -> DashboardSnapshot:
    await _ensure_serverless(need_analysis=True)
    return monitor.get_dashboard_snapshot()


@app.get("/api/quote", response_model=Optional[LiveQuote])
async def get_quote() -> Optional[LiveQuote]:
    await _ensure_serverless(need_analysis=False)
    return monitor.market.latest_quote


@app.get("/api/candles/{timeframe}", response_model=CandleSeriesResponse)
async def get_candles(timeframe: Timeframe) -> CandleSeriesResponse:
    if timeframe not in ALL_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")
    await _ensure_serverless(need_analysis=True, target_tf=timeframe)
    return monitor.get_candles_response(timeframe)


@app.get("/api/analysis/mtf", response_model=Optional[MtfSynthesis])
async def get_mtf_analysis() -> Optional[MtfSynthesis]:
    await _ensure_serverless(need_analysis=True)
    return monitor.mtf


@app.get("/api/signal", response_model=Optional[TradingSignal])
async def get_current_signal() -> Optional[TradingSignal]:
    await _ensure_serverless(need_analysis=True)
    return monitor.current_signal


@app.post("/api/refresh", response_model=DashboardSnapshot)
async def force_refresh() -> DashboardSnapshot:
    """Trigger an immediate live external quote + candlestick refresh and AI recalculation."""
    await monitor.market.refresh_all_timeframes()
    await monitor.market.refresh_quote()
    await monitor.recalculate_analysis(trigger="manual_refresh")
    snap = monitor.get_dashboard_snapshot()
    await monitor.broadcast({"type": "snapshot", "data": snap.model_dump()})
    return snap


@app.get("/api/risk-preview")
async def preview_risk_calculator(
    direction: str = Query("BUY", pattern="^(BUY|SELL)$"),
    account_balance: float = Query(10000.0, gt=0),
    risk_percent: float = Query(1.0, gt=0.05, le=10.0),
    min_rr: float = Query(2.0, ge=1.5, le=5.0),
) -> Dict[str, Any]:
    """
    Preview Smart SL/TP calculation and position sizing for educational risk planning.
    Always clearly notes whether the preview matches the current AI primary recommendation.
    """
    await _ensure_serverless(need_analysis=True)
    quote = monitor.market.latest_quote
    mtf = monitor.mtf
    if quote is None or mtf is None:
        raise HTTPException(status_code=503, detail="Live market data not yet available.")
    plan = calculate_smart_risk_plan(
        direction=direction,  # type: ignore[arg-type]
        quote=quote,
        mtf=mtf,
        min_rr=min_rr,
    )
    risk_amount_usd = round(account_balance * (risk_percent / 100.0), 2)
    # 1 standard XAUUSD lot = 100 troy oz -> $1 move = $100 per 1.00 lot
    ounces = round(risk_amount_usd / plan.risk_usd, 3) if plan.risk_usd > 0 else 0.0
    standard_lots = round(ounces / 100.0, 3)
    return {
        "matches_ai_signal": bool(monitor.current_signal and monitor.current_signal.action == direction),
        "current_ai_action": monitor.current_signal.action if monitor.current_signal else "WAIT",
        "account_balance": account_balance,
        "risk_percent": risk_percent,
        "risk_amount_usd": risk_amount_usd,
        "suggested_ounces": ounces,
        "suggested_lots": standard_lots,
        "potential_profit_tp1_usd": round(ounces * plan.reward_tp1_usd, 2),
        "potential_profit_tp2_usd": round(ounces * plan.reward_tp2_usd, 2),
        "potential_profit_tp3_usd": round(ounces * plan.reward_tp3_usd, 2),
        "risk_plan": plan.model_dump(),
    }


@app.get("/api/signals/history", response_model=List[SignalHistoryItem])
async def get_signals_history(limit: int = Query(30, ge=1, le=200)) -> List[SignalHistoryItem]:
    return monitor.get_recent_signals(limit=limit)


@app.get("/api/alerts", response_model=List[AlertItem])
async def get_alerts(limit: int = Query(50, ge=1, le=200)) -> List[AlertItem]:
    return monitor.get_recent_alerts(limit=limit)


# ---------------------------------------------------------------------------
# AI Signal Performance, Historical Backtesting & Forward-Testing Endpoints
# (All trade execution remains permanently disabled.)
# ---------------------------------------------------------------------------

@app.get("/api/performance/overview", response_model=PerformanceOverviewResponse)
async def get_performance_overview(
    initial_balance: float = Query(10000.0, gt=0),
    risk_percent: float = Query(1.0, ge=0.1, le=5.0),
) -> PerformanceOverviewResponse:
    """Returns strictly separated Live Forward-Testing and Historical Backtesting performance."""
    if settings.is_vercel:
        init_db()
    provider = monitor.market.get_health().active_quote_provider or "BiQuote Spot XAUUSD"
    forward = build_forward_test_report(
        active_provider=provider,
        initial_balance=initial_balance,
        risk_percent=risk_percent,
    )
    latest_bt = load_backtest_report(run_uid=None)
    runs = list_backtest_runs(limit=15)
    return PerformanceOverviewResponse(
        generated_at=utc_now_iso(),
        execution_disabled=True,
        forward_test=forward,
        latest_backtest=latest_bt,
        backtest_runs=runs,
    )


@app.get("/api/performance/forward", response_model=ForwardTestReport)
async def get_forward_performance(
    initial_balance: float = Query(10000.0, gt=0),
    risk_percent: float = Query(1.0, ge=0.1, le=5.0),
) -> ForwardTestReport:
    """Returns strictly live, non-executing Forward-Test statistics calculated from verifiable completed signals."""
    provider = monitor.market.get_health().active_quote_provider or "BiQuote Spot XAUUSD"
    return build_forward_test_report(
        active_provider=provider,
        initial_balance=initial_balance,
        risk_percent=risk_percent,
    )


@app.post("/api/backtest/run", response_model=BacktestReport)
async def run_historical_backtest(req: BacktestRequest) -> BacktestReport:
    """
    Execute a zero-lookahead historical XAUUSD backtest on real external OHLC candles
    including spread and slippage costs. Persists every timestamped trade for auditability.
    """
    if settings.is_vercel:
        init_db()
    try:
        return await execute_and_persist_backtest(req, live_cache=monitor.market.candles)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/backtest/runs", response_model=List[BacktestRunSummaryItem])
async def get_backtest_runs(limit: int = Query(15, ge=1, le=50)) -> List[BacktestRunSummaryItem]:
    return list_backtest_runs(limit=limit)


@app.get("/api/backtest/runs/{run_uid}", response_model=BacktestReport)
async def get_backtest_run_detail(run_uid: str) -> BacktestReport:
    report = load_backtest_report(run_uid=run_uid)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Backtest run {run_uid} not found")
    return report


@app.websocket("/ws/market")
async def ws_market(ws: WebSocket) -> None:
    await monitor.register_ws(ws)
    try:
        while True:
            # Keep socket alive and respond to client pings or timeframe chart requests
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        monitor.unregister_ws(ws)
    except Exception:
        monitor.unregister_ws(ws)
