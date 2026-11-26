# GOLD AI — Real-Time XAUUSD Trading Analyzer

An independent, all-in-one full-stack AI platform that analyzes live spot Gold (**XAUUSD**) in real time across 7 timeframes (`M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D1`), provides disciplined **BUY / SELL / WAIT** recommendations with Smart SL/TP (`>= 1:2.0` R:R), and includes **Historical XAUUSD Backtesting** and **Live Non-Executing Forward Testing**.

- **Zero broker login / Exness / MT5 credentials required**
- **Zero `.env` files required** — works out-of-the-box locally and on Vercel
- **Zero fake prices & trading execution permanently disabled**

---

## One-Click Vercel Deployment (Everything in One Piece)

This repository is structured as a unified full-stack Vercel project at repo root (`.`):
- **Next.js 15 Frontend:** `package.json` + `src/` at repo root
- **Python FastAPI Backend:** `api/index.py` + `backend/app/` + `requirements.txt` at repo root
- **Unified Routing:** `vercel.json` routes `/api/*`, `/docs`, and `/openapi.json` → Python FastAPI (`/api/index`), and all pages → Next.js

### Deploy Steps
1. Open https://vercel.com/new and import **`bongdom1617-lab/wktrade`**.
2. Leave **Root Directory** as `.` and **Environment Variables** completely empty.
3. Click **Deploy** — both frontend and backend deploy together on one URL with live 3s quote sync and 15s multi-timeframe AI analysis.

---

## Local Development

```bash
./start.sh
```
- Dashboard: `http://localhost:3000`
- FastAPI Docs: `http://127.0.0.1:8000/docs`

### Run Backend Tests
```bash
cd backend
.venv/bin/pytest -s -v
```
