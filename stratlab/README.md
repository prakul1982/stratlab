# StratLab

A web app for Indian retail traders to build trading strategies, backtest them on NSE data and paper trade them on the live market with fake capital.

- **Frontend:** `frontend/`, a static site with plain HTML/JS, Chart.js, Supabase login and Razorpay Checkout.
- **Backend:** `backend/`, built with FastAPI. It handles Kite Connect data, the backtest engine, live paper trading, billing, alerts and the AI writer.
- **Database and login:** Supabase (Postgres plus Google sign-in). The schema is in `supabase/schema.sql`.

## Plans (edit in `backend/app/plans.py`)

| | Free | Basic, ₹1,999/mo | Pro, ₹4,900/mo |
|---|---|---|---|
| Backtests | 5 per month | 50 per month | Unlimited |
| Live paper trading | 24-hour trial from first use, 1 strategy | 1 strategy at a time | 5 at a time |
| Indicators | Price, SMA, EMA, RSI | Price, SMA, EMA, RSI | + MACD, Bollinger, VWAP, Supertrend |
| Instruments | Nifty 50, Bank Nifty, any NSE stock | same | + F&O (futures and options) |
| AI strategy writer, alerts, export | – | – | Yes |

Monthly backtest counts reset on the 1st of each month (IST). Limits are enforced on the server; the frontend only mirrors them.

---

## Setup

### 1. Supabase
1. Create a project at supabase.com.
2. Open **SQL Editor**, paste `supabase/schema.sql` and run it.
3. Under **Authentication > Providers > Google**, enable Google. Create an OAuth client in Google Cloud Console and paste its ID and secret into Supabase.
4. Under **Authentication > URL Configuration**, add your frontend URL, for example `http://localhost:5500` and your production domain.
5. Copy these from **Project settings > API**:
   - the project URL and `anon` key go into `frontend/config.js`
   - the `service_role` key goes into `backend/.env`. It must stay on the server only.

### 2. Kite Connect
1. In the Kite developer console, set the app's redirect URL to `https://YOUR-BACKEND/admin/kite/callback`.
2. Put the API key and secret in `backend/.env`.
3. **Every trading day**, open `https://YOUR-BACKEND/admin/kite/login?key=YOUR_ADMIN_KEY` and log in with Zerodha. Kite access tokens expire each morning.
4. If the server was already running with the previous day's token, restart it after logging in. The Kite ticker library can't reconnect with a new token inside the same process. A scheduled restart just after your morning login works.

> **Data licensing:** this build serves data from your single Kite subscription. Before charging users, confirm with Zerodha that this is allowed. Redistributing exchange data usually needs a licence. All data access is in `backend/app/kite_service.py`, so you can swap in a licensed vendor without touching the rest.

### 3. Razorpay
1. In the dashboard, create two **monthly plans**: Basic ₹1,999 and Pro ₹4,900. Put their plan IDs in `.env`.
2. Enable **Subscriptions** on your account.
3. Add a webhook to `https://YOUR-BACKEND/billing/webhook` with a secret, and put that secret in `.env`. Subscribe to these events:
   - `subscription.activated`
   - `subscription.charged`
   - `subscription.resumed`
   - `subscription.cancelled`
   - `subscription.completed`
   - `subscription.halted`
   - `subscription.paused`
4. Test everything in Test Mode first.

### 4. AI writer and alerts (Pro)
- **AI writer:** uses Google Gemini by default: set `GEMINI_API_KEY` (`GEMINI_MODEL=auto` picks the newest Flash model). To use Claude instead, set `AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`; the model is set in `ANTHROPIC_MODEL`.
- **Telegram:** create a bot with @BotFather and set `TELEGRAM_BOT_TOKEN`. Users press Start on your bot and paste their chat ID on the Account page.
- **Email:** fill in the SMTP settings. For Gmail, use an app password. Port 465 uses SSL, 587 uses STARTTLS.

### 5. Run locally
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill it in
uvicorn app.main:app --reload --port 8000
```
```bash
cd frontend
python -m http.server 5500   # then open http://localhost:5500
```
Set `FRONTEND_ORIGIN` in `.env` to match the frontend URL, for CORS. To allow several (say production and localhost), separate them with commas.

Run the tests with:
```bash
cd backend
pip install pytest
pytest
```

### 6. Deploy
- **Backend:** Render, Railway or a small VPS. Run it as **one process**, e.g. `uvicorn app.main:app --host 0.0.0.0 --port 8000` with no multiple workers. Live sessions and the tick feed live in memory in that process.
- **Frontend:** Netlify, Vercel or Cloudflare Pages. Update `config.js` with the production API URL.

---

## How it works

- **Engine** (`backend/app/engine/`): long-only and candle-based. Each candle it checks the stop loss first, then the target, then the exit rules; entries fill at the candle's close.
  - Position size = (capital × risk %) ÷ (price × stop %), capped by max capital per trade.
  - F&O quantities round down to whole lots.
  - Brokerage and slippage apply on every order.
  - About 210 extra candles are loaded before the test period so indicators are warmed up.
- **Live paper trading** (`backend/app/live.py`):
  - One KiteTicker connection feeds every session.
  - Ticks become candles for your timeframe (market hours 09:15–15:30 IST).
  - On each closed candle, the same engine decides whether to trade.
  - Session state is saved every 30 seconds and resumes after a restart.
  - Free trials and plan limits are re-checked every minute.
- **API routes:** see `backend/app/main.py`. The browser only ever talks to this API; it never touches the database or Kite directly.

## Known limits
- Long only; no short selling yet.
- Historical data for **expired** option and futures contracts isn't available from Kite, so F&O backtests only work on currently listed contracts. Continuous data is used for daily futures candles.
- Backtests don't model intra-candle order (if stop and target fall in the same candle, the stop is assumed to hit first).
- This is a paper trading tool: no real orders are placed. If you add live execution later, review SEBI's retail algo trading framework first.
