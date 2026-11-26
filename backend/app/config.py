from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
IS_VERCEL = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
DEFAULT_SQLITE_PATH = Path("/tmp/gold_ai.db") if IS_VERCEL else (BASE_DIR / "gold_ai.db")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GOLD AI — Real-Time XAUUSD Trading Analyzer"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8000
    is_vercel: bool = IS_VERCEL
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Database (supports PostgreSQL / Supabase / Neon via DATABASE_URL; falls back to /tmp/gold_ai.db on Vercel or local SQLite)
    database_url: str = f"sqlite:///{DEFAULT_SQLITE_PATH}"

    # Market data providers (all optional API keys stay strictly server-side)
    # Primary default: BiQuote public Spot XAUUSD REST API + Swissquote BBO failover/cross-check
    # Optional enterprise upgrade: Twelve Data API key for XAU/USD
    twelve_data_api_key: Optional[str] = None
    preferred_provider: str = "auto"  # auto | biquote | twelvedata

    # Freshness / staleness thresholds (seconds)
    quote_delayed_threshold_sec: int = 20
    quote_disconnected_threshold_sec: int = 120
    candle_poll_m1_sec: int = 15
    candle_poll_m5_sec: int = 30
    candle_poll_mid_sec: int = 60
    candle_poll_high_sec: int = 120
    quote_poll_sec: float = 2.0

    # Risk & Signal parameters
    min_risk_reward: float = 2.0
    max_normal_spread_usd: float = 1.50
    signal_dedup_cooldown_sec: int = 900  # 15 minutes unless prior setup resolves
    signal_min_confidence: int = 62

    # Optional LLM narrative enrichment (strictly bounded to verified quant metrics; never invents numbers)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    def cors_origin_list(self) -> list:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
