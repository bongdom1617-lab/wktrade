from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.analysis.indicators import format_chart_overlays
from app.analysis.mtf import synthesize_mtf
from app.analysis.signal_engine import evaluate_trading_signal
from app.backtesting.forward_tracker import (
    close_forward_signal,
    record_forward_signal_open,
    sync_existing_live_signals_to_forward_ledger,
    update_forward_signal_milestone,
)
from app.config import settings
from app.database import SessionLocal
from app.market_data.base import ALL_TIMEFRAMES, utc_now, utc_now_iso
from app.market_data.manager import MarketDataManager
from app.models import AlertEvent, CandleCache, SignalRecord
from app.schemas import (
    AlertItem,
    CandleSeriesResponse,
    DashboardSnapshot,
    FeedStatus,
    LiveQuote,
    MtfSynthesis,
    SignalHistoryItem,
    Timeframe,
    TradingSignal,
)


logger = logging.getLogger("gold_ai.monitor")


class RealTimeMonitor:
    """
    Continuously monitors live XAUUSD quotes and M1..D1 candlesticks:
    - Recalculates technical indicators & MTF synthesis on startup, new candle close, and periodic cadence.
    - Generates deduplicated BUY/SELL/WAIT recommendations.
    - Tracks active signal Entry, TP1, TP2, TP3, SL, and structural invalidation in real time.
    - Streams live quotes, snapshots, and alerts to connected WebSocket clients.
    """

    def __init__(self) -> None:
        self.market = MarketDataManager()
        self.mtf: Optional[MtfSynthesis] = None
        self.indicator_series: Dict[Timeframe, Dict[str, Any]] = {}
        self.current_signal: Optional[TradingSignal] = None
        self.active_signal_uid: Optional[str] = None
        self.active_signal_state: Optional[Dict[str, Any]] = None

        self._ws_clients: Set[WebSocket] = set()
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._last_feed_status: Optional[FeedStatus] = None
        self._last_tf_fetch: Dict[Timeframe, float] = {tf: 0.0 for tf in ALL_TIMEFRAMES}
        self._last_analysis_ts: float = 0.0
        self._last_quote_ts: float = 0.0
        self._last_prune_ts: float = 0.0
        self._serverless_lock: Optional[asyncio.Lock] = None
        self._last_emitted_dir: Optional[str] = None
        self._last_emitted_time: float = 0.0
        self._last_emitted_price: float = 0.0
        self._initialized: bool = False

    def init_serverless(self) -> None:
        """Lightweight startup for Vercel Serverless (no infinite background loop)."""
        sync_existing_live_signals_to_forward_ledger()
        self._load_active_signal_from_db()

    async def ensure_fresh_serverless(
        self,
        need_analysis: bool = True,
        target_tf: Optional[Timeframe] = None,
    ) -> None:
        """
        On-demand live refresh with short TTL cache for Vercel Serverless deployments.
        Guarantees fresh real XAUUSD quotes (~3s TTL) and multi-timeframe analysis (~20s TTL)
        without requiring a long-running daemon process.
        """
        if self._serverless_lock is None:
            self._serverless_lock = asyncio.Lock()

        async with self._serverless_lock:
            now_m = time.monotonic()
            missing_tfs = [tf for tf in ALL_TIMEFRAMES if len(self.market.get_candles(tf)) == 0]
            candles_stale = (now_m - self._last_analysis_ts) >= 20.0

            if need_analysis and (not self._initialized or missing_tfs or candles_stale):
                await self.market.refresh_all_timeframes()
                for tf in ALL_TIMEFRAMES:
                    if len(self.market.get_candles(tf)) > 0:
                        self._last_tf_fetch[tf] = now_m
                await self.market.refresh_quote()
                self._last_quote_ts = now_m
                if self.market.latest_quote is not None and self.market.get_health().status == "LIVE":
                    self._monitor_active_signal_tick(self.market.latest_quote)
                await self.recalculate_analysis(trigger="serverless_sync")
                self._initialized = True
                return

            if target_tf is not None and (
                len(self.market.get_candles(target_tf)) == 0
                or (now_m - self._last_tf_fetch.get(target_tf, 0.0)) >= 20.0
            ):
                try:
                    await self.market.refresh_candles(target_tf)
                    self._last_tf_fetch[target_tf] = now_m
                except Exception as exc:
                    logger.warning("Serverless candle refresh warning (%s): %s", target_tf, exc)

            if self.market.latest_quote is None or (now_m - self._last_quote_ts) >= 3.0:
                quote = await self.market.refresh_quote()
                self._last_quote_ts = now_m
                if quote is not None and self.market.get_health().status == "LIVE":
                    if self._monitor_active_signal_tick(quote):
                        await self.recalculate_analysis(trigger="serverless_signal_event")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        sync_existing_live_signals_to_forward_ledger()
        self._load_active_signal_from_db()
        # Run initial live synchronization immediately (non-blocking if external network briefly hiccups)
        try:
            await self.bootstrap()
        except Exception as exc:
            logger.error("Initial bootstrap error: %s", exc)
        self._task = asyncio.create_task(self._monitor_loop(), name="gold-ai-monitor")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.market.close()

    async def bootstrap(self) -> None:
        """Fetch all 7 timeframes and live quote concurrently, then run initial AI analysis."""
        await self.market.refresh_all_timeframes()
        now_m = time.monotonic()
        for tf in ALL_TIMEFRAMES:
            # Only stamp last_tf_fetch when real candles loaded; if Mac booted before Wi-Fi
            # connected, empty timeframes will retry automatically within seconds.
            if len(self.market.get_candles(tf)) > 0:
                self._last_tf_fetch[tf] = now_m
        await self.market.refresh_quote()
        await self.recalculate_analysis(trigger="startup")
        self._initialized = True

    def _load_active_signal_from_db(self) -> None:
        db: Session = SessionLocal()
        try:
            rec = (
                db.query(SignalRecord)
                .filter(
                    SignalRecord.action.in_(["BUY", "SELL"]),
                    SignalRecord.status.in_(["ACTIVE", "ENTRY_TRIGGERED", "TP1_HIT", "TP2_HIT"]),
                )
                .order_by(SignalRecord.created_at.desc())
                .first()
            )
            if rec:
                self.active_signal_uid = rec.signal_uid
                self.active_signal_state = self._record_to_monitor_dict(rec)
                self._last_emitted_dir = rec.action
                self._last_emitted_price = rec.entry_price or rec.market_price_at_signal
                self._last_emitted_time = rec.created_at.timestamp() if rec.created_at else 0.0
        except Exception as exc:
            logger.warning("Could not restore active signal from DB: %s", exc)
        finally:
            db.close()

    def _record_to_monitor_dict(self, rec: SignalRecord) -> Dict[str, Any]:
        return {
            "signal_uid": rec.signal_uid,
            "action": rec.action,
            "status": rec.status,
            "confidence": rec.confidence,
            "entry_price": rec.entry_price,
            "entry_zone_low": rec.entry_zone_low,
            "entry_zone_high": rec.entry_zone_high,
            "stop_loss": rec.stop_loss,
            "tp1": rec.tp1,
            "tp2": rec.tp2,
            "tp3": rec.tp3,
            "rr_tp1": rec.risk_reward_tp1,
            "rr_tp2": rec.risk_reward_tp2,
            "rr_tp3": rec.risk_reward_tp3,
            "created_at": rec.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if rec.created_at else utc_now_iso(),
            "tp1_reached": rec.status in ("TP1_HIT", "TP2_HIT", "TP3_HIT"),
            "tp2_reached": rec.status in ("TP2_HIT", "TP3_HIT"),
            "tp3_reached": rec.status == "TP3_HIT",
            "entry_filled": rec.status in ("ENTRY_TRIGGERED", "TP1_HIT", "TP2_HIT", "TP3_HIT"),
        }

    def _tf_refresh_interval(self, tf: Timeframe) -> int:
        if tf == "M1":
            return settings.candle_poll_m1_sec
        if tf == "M5":
            return settings.candle_poll_m5_sec
        if tf in ("M15", "M30"):
            return settings.candle_poll_mid_sec
        return settings.candle_poll_high_sec

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                loop_start = time.monotonic()

                # 1. Refresh live quote every 2 seconds
                quote = await self.market.refresh_quote()
                health = self.market.get_health()

                # Detect feed health transitions (LIVE <-> DELAYED / DISCONNECTED / MARKET_CLOSED)
                if self._last_feed_status != health.status:
                    if self._last_feed_status is not None:
                        sev = "INFO" if health.status == "LIVE" else ("CRITICAL" if health.status == "DISCONNECTED" else "WARNING")
                        self._save_alert(
                            severity=sev,
                            category="FEED",
                            title=f"Market Feed Status: {health.status}",
                            message=health.message,
                            price=quote.mid if quote else None,
                        )
                    self._last_feed_status = health.status

                # 2. Check active tracked signal levels against every live tick
                signal_transitioned = False
                if quote is not None and health.status == "LIVE":
                    signal_transitioned = self._monitor_active_signal_tick(quote)

                # 3. Refresh due candlestick timeframes (or retry empty timeframes rapidly after Mac cold boot)
                now_m = time.monotonic()
                due_tfs = [
                    tf for tf in ALL_TIMEFRAMES
                    if (
                        len(self.market.get_candles(tf)) == 0
                        and (now_m - self._last_tf_fetch.get(tf, 0.0)) >= 5.0
                    )
                    or (now_m - self._last_tf_fetch.get(tf, 0.0)) >= self._tf_refresh_interval(tf)
                ]
                any_new_candle = False
                newly_hydrated = False
                closed_tfs: List[Timeframe] = []
                if due_tfs:
                    had_empty = any(len(self.market.get_candles(tf)) == 0 for tf in due_tfs)
                    results = await asyncio.gather(
                        *(self.market.refresh_candles(tf) for tf in due_tfs),
                        return_exceptions=True,
                    )
                    for tf, res in zip(due_tfs, results):
                        self._last_tf_fetch[tf] = now_m
                        if not isinstance(res, Exception):
                            bars, closed = res
                            if had_empty and len(bars) > 0:
                                newly_hydrated = True
                            if closed:
                                any_new_candle = True
                                closed_tfs.append(tf)

                # 4. Recalculate technical analysis on new candle close, hydration, signal transition, or every 15s
                if any_new_candle or newly_hydrated or signal_transitioned or (now_m - self._last_analysis_ts) >= 15.0:
                    trigger = f"candle_close:{','.join(closed_tfs)}" if closed_tfs else ("signal_event" if signal_transitioned else "periodic")
                    await self.recalculate_analysis(trigger=trigger, closed_tfs=closed_tfs)
                    await self.broadcast({"type": "snapshot", "data": self.get_dashboard_snapshot().model_dump()})
                else:
                    # Lightweight real-time quote broadcast every 2 seconds
                    await self.broadcast(
                        {
                            "type": "quote_tick",
                            "data": {
                                "timestamp": utc_now_iso(),
                                "quote": quote.model_dump() if quote else None,
                                "feed_health": health.model_dump(),
                                "active_trade_monitor": self._enrich_active_monitor(quote),
                            },
                        }
                    )

                # 5. Periodic DB housekeeping (once per hour) to prevent unbounded growth over 24/7 uptime
                if (now_m - self._last_prune_ts) >= 3600.0:
                    self._last_prune_ts = now_m
                    self._prune_old_records()

                elapsed = time.monotonic() - loop_start
                await asyncio.sleep(max(0.4, settings.quote_poll_sec - elapsed))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Monitor loop exception: %s", exc)
                await asyncio.sleep(3.0)

    def _prune_old_records(self) -> None:
        """Keep DB compact over long 24/7 uptime while preserving all signals, forward tests & backtests."""
        db: Session = SessionLocal()
        try:
            for tf in ALL_TIMEFRAMES:
                keep_rows = (
                    db.query(CandleCache.id)
                    .filter(CandleCache.symbol == "XAUUSD", CandleCache.timeframe == tf)
                    .order_by(CandleCache.open_time.desc())
                    .limit(800)
                    .all()
                )
                if len(keep_rows) == 800:
                    keep_ids = {r[0] for r in keep_rows}
                    db.query(CandleCache).filter(
                        CandleCache.symbol == "XAUUSD",
                        CandleCache.timeframe == tf,
                        ~CandleCache.id.in_(keep_ids),
                    ).delete(synchronize_session=False)

            keep_alerts = db.query(AlertEvent.id).order_by(AlertEvent.created_at.desc()).limit(500).all()
            if len(keep_alerts) == 500:
                keep_a_ids = {r[0] for r in keep_alerts}
                db.query(AlertEvent).filter(~AlertEvent.id.in_(keep_a_ids)).delete(synchronize_session=False)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Periodic DB prune skipped: %s", exc)
        finally:
            db.close()

    async def recalculate_analysis(self, trigger: str = "manual", closed_tfs: Optional[List[Timeframe]] = None) -> None:
        self._last_analysis_ts = time.monotonic()
        quote = self.market.latest_quote
        health = self.market.get_health()

        candles_map = {tf: self.market.get_candles(tf) for tf in ALL_TIMEFRAMES}
        if any(len(v) >= 25 for v in candles_map.values()):
            mtf, series_map = synthesize_mtf(candles_map)
            self.mtf = mtf
            self.indicator_series = series_map
        else:
            mtf = None

        # Log significant candle close or breakout alert
        if closed_tfs and mtf is not None and quote is not None:
            for tf in closed_tfs:
                if tf in ("M15", "M30", "H1", "H4") and tf in mtf.timeframes:
                    tfa = mtf.timeframes[tf]
                    if tfa.breakout.status != "NONE":
                        self._save_alert(
                            severity="WARNING" if "FALSE" in tfa.breakout.status else "INFO",
                            category="BREAKOUT",
                            title=f"{tf} {tfa.breakout.status.replace('_', ' ')}",
                            message=tfa.breakout.description,
                            price=quote.mid,
                            timeframe=tf,
                        )

        # Evaluate invalidation of currently open signal against fresh MTF structure
        if mtf is not None and quote is not None and self.active_signal_state is not None:
            self._check_structural_invalidation(mtf, quote)

        # Evaluate disciplined BUY / SELL / WAIT recommendation
        new_signal = evaluate_trading_signal(quote=quote, health=health, mtf=mtf)
        self.current_signal = new_signal

        # Deduplicated persistence & alerting for actionable BUY / SELL signals
        if new_signal.action in ("BUY", "SELL") and new_signal.risk_plan is not None:
            self._handle_actionable_signal(new_signal)

    def _handle_actionable_signal(self, sig: TradingSignal) -> None:
        assert sig.risk_plan is not None
        now_epoch = time.time()
        m15_atr = sig.risk_plan.atr_reference or 4.0

        # Deduplication rule 1: If an active signal in the SAME direction is already being monitored, do not duplicate!
        if self.active_signal_state is not None and self.active_signal_state["action"] == sig.action:
            return

        # Deduplication rule 2: Cooldown window for identical direction near the same price zone
        if (
            self._last_emitted_dir == sig.action
            and (now_epoch - self._last_emitted_time) < settings.signal_dedup_cooldown_sec
            and abs(sig.risk_plan.entry_price - self._last_emitted_price) < max(m15_atr * 0.65, 3.0)
        ):
            return

        # If an opposing direction active signal exists, mark previous as SUPERSEDED
        if self.active_signal_state is not None and self.active_signal_state["action"] != sig.action:
            self._resolve_active_signal(
                new_status="SUPERSEDED",
                price=sig.market_price,
                note=f"Superseded by fresh opposing {sig.action} setup ({sig.signal_uid}).",
            )

        # Persist new verified signal in DB
        db: Session = SessionLocal()
        try:
            rp = sig.risk_plan
            rec = SignalRecord(
                signal_uid=sig.signal_uid,
                symbol=sig.symbol,
                action=sig.action,
                status="ACTIVE",
                confidence=sig.confidence,
                setup_timeframe=sig.setup_timeframe,
                entry_price=rp.entry_price,
                entry_zone_low=rp.entry_zone_low,
                entry_zone_high=rp.entry_zone_high,
                stop_loss=rp.stop_loss,
                tp1=rp.tp1,
                tp2=rp.tp2,
                tp3=rp.tp3,
                risk_reward_tp1=rp.rr_tp1,
                risk_reward_tp2=rp.rr_tp2,
                risk_reward_tp3=rp.rr_tp3,
                market_price_at_signal=sig.market_price,
                data_provider=sig.data_provider,
                summary=sig.explanation.decision_headline,
                invalidation_conditions=json.dumps(sig.explanation.invalidation_conditions),
                explanation_json=sig.explanation.model_dump_json(),
                mtf_snapshot_json=json.dumps(
                    {tf: {"trend": a.trend, "score": a.trend_score} for tf, a in (self.mtf.timeframes.items() if self.mtf else [])}
                ),
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)

            self.active_signal_uid = rec.signal_uid
            self.active_signal_state = self._record_to_monitor_dict(rec)
            self._last_emitted_dir = sig.action
            self._last_emitted_time = now_epoch
            self._last_emitted_price = rp.entry_price
            record_forward_signal_open(sig, self.market.latest_quote)

            self._save_alert(
                severity="SIGNAL",
                category="SIGNAL",
                title=f"NEW {sig.action} SIGNAL ({sig.confidence}% Confidence)",
                message=(
                    f"Entry ${rp.entry_price:,.2f} (Zone ${rp.entry_zone_low:,.2f}–${rp.entry_zone_high:,.2f}) | "
                    f"SL ${rp.stop_loss:,.2f} | TP1 ${rp.tp1:,.2f} | TP2 ${rp.tp2:,.2f} (1:{rp.rr_tp2:.2f} R:R) | "
                    f"TP3 ${rp.tp3:,.2f}"
                ),
                price=sig.market_price,
                timeframe=sig.setup_timeframe,
            )
        except Exception as exc:
            db.rollback()
            logger.error("Failed persisting signal %s: %s", sig.signal_uid, exc)
        finally:
            db.close()

    def _monitor_active_signal_tick(self, quote: LiveQuote) -> bool:
        st = self.active_signal_state
        if not st:
            return False
        action = st["action"]
        # Use executable prices: BUY fills on Ask and exits on Bid; SELL fills on Bid and exits on Ask
        fill_px = quote.ask if action == "BUY" else quote.bid
        exit_px = quote.bid if action == "BUY" else quote.ask
        changed = False

        # Entry zone activation check
        if not st["entry_filled"]:
            if st["entry_zone_low"] <= fill_px <= st["entry_zone_high"]:
                st["entry_filled"] = True
                st["status"] = "ENTRY_TRIGGERED"
                self._update_signal_status_db(st["signal_uid"], "ENTRY_TRIGGERED")
                self._save_alert(
                    severity="INFO",
                    category="TARGET",
                    title=f"{action} Entry Zone Reached",
                    message=f"Live price (${fill_px:,.2f}) entered {st['signal_uid']} zone (${st['entry_zone_low']:,.2f}–${st['entry_zone_high']:,.2f}).",
                    price=fill_px,
                )
                changed = True

        # Check Stop Loss & Take Profits
        if action == "BUY":
            if exit_px <= st["stop_loss"]:
                self._resolve_active_signal("SL_HIT", exit_px, f"Stop Loss ${st['stop_loss']:,.2f} hit at Bid ${exit_px:,.2f}.")
                return True
            if exit_px >= st["tp3"] and not st["tp3_reached"]:
                st["tp3_reached"] = True
                self._resolve_active_signal("TP3_HIT", exit_px, f"Full runner TP3 ${st['tp3']:,.2f} reached at Bid ${exit_px:,.2f}!")
                return True
            if exit_px >= st["tp2"] and not st["tp2_reached"]:
                st["tp2_reached"] = True
                st["status"] = "TP2_HIT"
                self._update_signal_status_db(st["signal_uid"], "TP2_HIT")
                self._save_alert(
                    severity="SIGNAL",
                    category="TARGET",
                    title=f"BUY TP2 Reached (${st['tp2']:,.2f})",
                    message=f"{st['signal_uid']} reached primary TP2 (1:{st['rr_tp2']:.2f} R:R) at Bid ${exit_px:,.2f}.",
                    price=exit_px,
                )
                changed = True
            elif exit_px >= st["tp1"] and not st["tp1_reached"]:
                st["tp1_reached"] = True
                st["status"] = "TP1_HIT"
                self._update_signal_status_db(st["signal_uid"], "TP1_HIT")
                self._save_alert(
                    severity="INFO",
                    category="TARGET",
                    title=f"BUY TP1 Reached (${st['tp1']:,.2f})",
                    message=f"{st['signal_uid']} hit TP1 at Bid ${exit_px:,.2f} — consider protecting stop to breakeven.",
                    price=exit_px,
                )
                changed = True
        else:  # SELL
            if exit_px >= st["stop_loss"]:
                self._resolve_active_signal("SL_HIT", exit_px, f"Stop Loss ${st['stop_loss']:,.2f} hit at Ask ${exit_px:,.2f}.")
                return True
            if exit_px <= st["tp3"] and not st["tp3_reached"]:
                st["tp3_reached"] = True
                self._resolve_active_signal("TP3_HIT", exit_px, f"Full runner TP3 ${st['tp3']:,.2f} reached at Ask ${exit_px:,.2f}!")
                return True
            if exit_px <= st["tp2"] and not st["tp2_reached"]:
                st["tp2_reached"] = True
                st["status"] = "TP2_HIT"
                self._update_signal_status_db(st["signal_uid"], "TP2_HIT")
                self._save_alert(
                    severity="SIGNAL",
                    category="TARGET",
                    title=f"SELL TP2 Reached (${st['tp2']:,.2f})",
                    message=f"{st['signal_uid']} reached primary TP2 (1:{st['rr_tp2']:.2f} R:R) at Ask ${exit_px:,.2f}.",
                    price=exit_px,
                )
                changed = True
            elif exit_px <= st["tp1"] and not st["tp1_reached"]:
                st["tp1_reached"] = True
                st["status"] = "TP1_HIT"
                self._update_signal_status_db(st["signal_uid"], "TP1_HIT")
                self._save_alert(
                    severity="INFO",
                    category="TARGET",
                    title=f"SELL TP1 Reached (${st['tp1']:,.2f})",
                    message=f"{st['signal_uid']} hit TP1 at Ask ${exit_px:,.2f} — consider protecting stop to breakeven.",
                    price=exit_px,
                )
                changed = True

        return changed

    def _check_structural_invalidation(self, mtf: MtfSynthesis, quote: LiveQuote) -> None:
        st = self.active_signal_state
        if not st or st["tp1_reached"]:
            return
        h1 = mtf.timeframes.get("H1")
        m30 = mtf.timeframes.get("M30")
        if not h1 or not m30:
            return
        opp = "BEARISH" if st["action"] == "BUY" else "BULLISH"
        if h1.trend == opp and m30.trend == opp:
            self._resolve_active_signal(
                "INVALIDATED",
                quote.mid,
                f"Setup structurally invalidated: both H1 and M30 reversed to {opp} before TP1.",
            )

    def _update_signal_status_db(self, signal_uid: str, status: str) -> None:
        db: Session = SessionLocal()
        try:
            rec = db.query(SignalRecord).filter(SignalRecord.signal_uid == signal_uid).first()
            if rec:
                rec.status = status
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Failed updating signal status %s: %s", signal_uid, exc)
        finally:
            db.close()
        update_forward_signal_milestone(signal_uid, status, self.market.latest_quote)

    def _resolve_active_signal(self, new_status: str, price: float, note: str) -> None:
        st = self.active_signal_state
        if not st:
            return
        uid = st["signal_uid"]
        action = st["action"]
        db: Session = SessionLocal()
        try:
            rec = db.query(SignalRecord).filter(SignalRecord.signal_uid == uid).first()
            if rec:
                rec.status = new_status
                rec.resolved_at = utc_now()
                rec.resolution_price = round(price, 3)
                rec.resolution_note = note
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Failed resolving signal %s: %s", uid, exc)
        finally:
            db.close()

        exit_spread = self.market.latest_quote.spread if self.market.latest_quote else 0.20
        close_forward_signal(
            signal_uid=uid,
            outcome=new_status,
            exit_price=price,
            exit_spread_usd=exit_spread,
            note=note,
        )

        sev = "WARNING" if new_status in ("SL_HIT", "INVALIDATED") else "SIGNAL"
        cat = "INVALIDATION" if new_status == "INVALIDATED" else "TARGET"
        self._save_alert(
            severity=sev,
            category=cat,
            title=f"{action} Signal {new_status.replace('_', ' ')}",
            message=f"{uid}: {note}",
            price=price,
        )
        self.active_signal_uid = None
        self.active_signal_state = None

    def _save_alert(
        self,
        severity: str,
        category: str,
        title: str,
        message: str,
        price: Optional[float] = None,
        timeframe: Optional[str] = None,
    ) -> None:
        db: Session = SessionLocal()
        try:
            ev = AlertEvent(
                severity=severity,
                category=category,
                title=title,
                message=message,
                price=round(price, 3) if price is not None else None,
                timeframe=timeframe,
            )
            db.add(ev)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Failed saving alert: %s", exc)
        finally:
            db.close()

    def _enrich_active_monitor(self, quote: Optional[LiveQuote]) -> Optional[Dict[str, Any]]:
        if not self.active_signal_state:
            return None
        info = dict(self.active_signal_state)
        if quote is not None and info.get("entry_price") and info.get("stop_loss"):
            cur = quote.bid if info["action"] == "BUY" else quote.ask
            pnl_usd = round((cur - info["entry_price"]) if info["action"] == "BUY" else (info["entry_price"] - cur), 2)
            risk = max(abs(info["entry_price"] - info["stop_loss"]), 0.5)
            info["current_exit_price"] = cur
            info["floating_pnl_usd"] = pnl_usd
            info["floating_r"] = round(pnl_usd / risk, 2)
        return info

    def get_recent_signals(self, limit: int = 25) -> List[SignalHistoryItem]:
        db: Session = SessionLocal()
        try:
            rows = db.query(SignalRecord).order_by(SignalRecord.created_at.desc()).limit(limit).all()
            return [
                SignalHistoryItem(
                    id=r.id,
                    signal_uid=r.signal_uid,
                    action=r.action,  # type: ignore[arg-type]
                    status=r.status,
                    confidence=r.confidence,
                    setup_timeframe=r.setup_timeframe,
                    entry_price=r.entry_price,
                    entry_zone_low=r.entry_zone_low,
                    entry_zone_high=r.entry_zone_high,
                    stop_loss=r.stop_loss,
                    tp1=r.tp1,
                    tp2=r.tp2,
                    tp3=r.tp3,
                    risk_reward_tp2=r.risk_reward_tp2,
                    market_price_at_signal=r.market_price_at_signal,
                    data_provider=r.data_provider,
                    summary=r.summary,
                    created_at=r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if r.created_at else utc_now_iso(),
                    resolved_at=r.resolved_at.strftime("%Y-%m-%dT%H:%M:%SZ") if r.resolved_at else None,
                    resolution_price=r.resolution_price,
                    resolution_note=r.resolution_note,
                )
                for r in rows
            ]
        finally:
            db.close()

    def get_recent_alerts(self, limit: int = 40) -> List[AlertItem]:
        db: Session = SessionLocal()
        try:
            rows = db.query(AlertEvent).order_by(AlertEvent.created_at.desc()).limit(limit).all()
            return [
                AlertItem(
                    id=r.id,
                    severity=r.severity,
                    category=r.category,
                    title=r.title,
                    message=r.message,
                    price=r.price,
                    timeframe=r.timeframe,
                    created_at=r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if r.created_at else utc_now_iso(),
                )
                for r in rows
            ]
        finally:
            db.close()

    def get_candles_response(self, timeframe: Timeframe) -> CandleSeriesResponse:
        bars = self.market.get_candles(timeframe)
        series = self.indicator_series.get(timeframe)
        overlays = format_chart_overlays(series) if series else {}
        health = self.market.get_health()
        return CandleSeriesResponse(
            symbol="XAUUSD",
            timeframe=timeframe,
            provider=self.market.candle_providers.get(timeframe) or (health.active_candle_provider or "Unavailable"),
            status=health.status,
            last_updated=self.market.candle_updated_at.get(timeframe) or utc_now_iso(),
            bar_count=len(bars),
            candles=bars,
            overlays=overlays,
        )

    def get_dashboard_snapshot(self) -> DashboardSnapshot:
        return DashboardSnapshot(
            timestamp=utc_now_iso(),
            quote=self.market.latest_quote,
            feed_health=self.market.get_health(),
            mtf=self.mtf,
            signal=self.current_signal,
            active_trade_monitor=self._enrich_active_monitor(self.market.latest_quote),
            recent_signals=self.get_recent_signals(limit=25),
            recent_alerts=self.get_recent_alerts(limit=40),
        )

    async def register_ws(self, ws: WebSocket) -> None:
        await ws.accept()
        self._ws_clients.add(ws)
        # Immediately push full snapshot upon connection
        await ws.send_json({"type": "snapshot", "data": self.get_dashboard_snapshot().model_dump()})

    def unregister_ws(self, ws: WebSocket) -> None:
        self._ws_clients.discard(ws)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        if not self._ws_clients:
            return
        dead: List[WebSocket] = []
        for ws in list(self._ws_clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)
