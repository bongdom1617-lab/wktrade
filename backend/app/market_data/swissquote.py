from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.market_data.base import BaseMarketProvider, MarketDataError, utc_now, utc_now_iso
from app.schemas import LiveQuote


class SwissquoteBboProvider(BaseMarketProvider):
    """Swissquote Institutional Public BBO XAU/USD Feed (Secondary Quote Verification & Failover)."""

    name = "Swissquote BBO XAU/USD"
    role = "secondary"
    supports_candles = False
    ENDPOINT = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"

    def __init__(self, timeout: float = 8.0) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "GoldAI-Analyzer/1.0",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_quote(self) -> LiveQuote:
        t0 = time.perf_counter()
        try:
            resp = await self._client.get(self.ENDPOINT)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status_code != 200:
                raise MarketDataError(f"Swissquote HTTP {resp.status_code}")
            payload = resp.json()
        except Exception as exc:
            self.mark_error(str(exc))
            raise MarketDataError(f"Swissquote BBO fetch failed: {exc}") from exc

        if not isinstance(payload, list) or not payload:
            self.mark_error("Empty Swissquote BBO array")
            raise MarketDataError("Empty Swissquote BBO array")

        # Select the freshest entry and tightest institutional spread profile (elite/prime/premium)
        best_entry = max(payload, key=lambda e: int(e.get("ts") or 0))
        profiles = best_entry.get("spreadProfilePrices") or []
        if not profiles:
            self.mark_error("Missing spreadProfilePrices in Swissquote BBO")
            raise MarketDataError("Missing spreadProfilePrices in Swissquote BBO")

        preferred_order = {"elite": 0, "prime": 1, "premium": 2, "standard": 3}
        chosen = sorted(
            profiles,
            key=lambda p: preferred_order.get(str(p.get("spreadProfile", "")).lower(), 99),
        )[0]

        try:
            bid = float(chosen["bid"])
            ask = float(chosen["ask"])
            ts_ms = int(best_entry["ts"])
        except (KeyError, TypeError, ValueError) as exc:
            self.mark_error(f"Malformed Swissquote entry: {exc}")
            raise MarketDataError(f"Malformed Swissquote entry: {exc}") from exc

        if bid <= 0 or ask <= 0:
            raise MarketDataError(f"Invalid Swissquote bid/ask: {bid}/{ask}")

        mid = (bid + ask) / 2.0
        spread = max(0.0, ask - bid)
        spread_bps = round((spread / mid) * 10000.0, 2) if mid > 0 else 0.0

        quote_dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        age_sec = max(0.0, (utc_now() - quote_dt).total_seconds())

        self.mark_success(elapsed_ms)
        return LiveQuote(
            symbol="XAUUSD",
            bid=round(bid, 3),
            ask=round(ask, 3),
            mid=round(mid, 3),
            spread=round(spread, 3),
            spread_bps=spread_bps,
            provider=self.name,
            quote_timestamp=quote_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            fetched_at=utc_now_iso(),
            quote_age_seconds=round(age_sec, 1),
            market_state="open",
            status="LIVE",
        )
