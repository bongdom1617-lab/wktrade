# GOLD AI — Real-Time XAUUSD Trading Analyzer

An independent, institutional-grade AI web application that analyzes live spot Gold (**XAUUSD**) in real time across 7 timeframes (`M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D1`) and generates transparent, risk-managed trading recommendations (**BUY / SELL / WAIT**).

**Key Guarantees:**
- **No Exness, MT5, or broker account credentials required.**
- **No automatic trade execution** and **never guarantees profits**.
- **Zero simulated or fake prices** — explicitly detects and warns on delayed, market-closed, or disconnected feeds, automatically suspending BUY/SELL signals when live data is degraded.
- **Evidence-based WAIT discipline** — never forces trades when timeframes conflict, spread is wide, momentum is exhausted, or Risk-to-Reward falls below `1:2.0`.

---

## Architecture

- **Frontend (`/frontend`)**: Next.js 15, TypeScript, Tailwind CSS v4, TradingView Lightweight Charts v5 (synchronized candlesticks + EMAs/BB/VWAP/S&R/Signal overlays + RSI 14 + MACD panels), WebSocket real-time streaming.
- **Backend (`/backend`)**: Python FastAPI, Uvicorn, WebSocket (`/ws/market`), Pandas/NumPy quantitative indicator & structure engine, SQLAlchemy ORM (PostgreSQL / Supabase via `DATABASE_URL`, automatic local SQLite fallback).
- **Live Market Data Layer (`/backend/app/market_data`)**:
  - Primary Live Feed: **BiQuote Spot XAUUSD** (`Bid`, `Ask`, `Spread`, and real-time `M1`–`D1` candlesticks) — works out-of-the-box with zero API keys.
  - Secondary Verification & Failover Feed: **Swissquote Institutional BBO XAU/USD** (cross-checks quote integrity and auto-fails over if primary stalls).
  - Optional Enterprise Provider: **Twelve Data** (`TWELVE_DATA_API_KEY` in `backend/.env`).

---

## Quick Start

### 1. Run Everything Together
```bash
./start.sh
```
- Frontend Dashboard: `http://localhost:3000`
- Backend API & Docs: `http://127.0.0.1:8000/docs`
- Live WebSocket Stream: `ws://127.0.0.1:8000/ws/market`

### 2. Manual Startup

**Backend:**
```bash
cd backend
cp .env.example .env   # Optional: configure PostgreSQL/Supabase DATABASE_URL or TWELVE_DATA_API_KEY
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Frontend:**
```bash
cd frontend
npm run dev
```

### 3. Run Automated Tests
```bash
cd backend
.venv/bin/pytest -s -v
```
