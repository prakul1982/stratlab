# StratLab setup guide

[← Back to the project overview](../README.md)

How to run StratLab on your own machine for development. What StratLab does is in [docs/FEATURES.md](../docs/FEATURES.md).

- **Frontend:** `frontend/`, a React + TypeScript app built with Vite.
- **Backend:** `backend/`, a FastAPI app: market data, company research, the backtest engine, the verdict checks, trading
  costs, live paper trading and the money tools.
- **Database and sign-in:** Postgres, with Google sign-in through Supabase. The schema is in `supabase/schema.sql`.

## Setup

### 1. Supabase
1. Create a project at supabase.com.
2. Open **SQL Editor**, paste `supabase/schema.sql` and run it. It only adds what is missing, so it is safe to run again.
3. Under **Authentication > Providers > Google**, enable Google with your own Google Cloud OAuth client.
4. Under **Authentication > URL Configuration**, add your frontend URL, for example `http://localhost:5500`.
5. From **Project settings > API**, put the project URL and the public `anon` key in `frontend/public/config.js`, and the
   `service_role` key in `backend/.env` (it stays on the server only).

### 2. Optional services
Everything else is optional; each part of the app that needs a key says so when it's missing. `backend/.env.example`
lists every setting by name: a broker market-data API for Indian prices, payments, AI providers for the AI builder and
research summaries, email and Telegram for alerts, and error and usage reporting. Never commit real values.

### 3. Run locally
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill it in
uvicorn app.main:app --reload --port 8000
```
```bash
cd frontend
npm install
npm run dev                  # then open http://localhost:5500
```
The frontend reads `public/config.js` at runtime (the API address and the Supabase public key). Set `FRONTEND_ORIGIN` in
`.env` to the frontend's address, for CORS.

Run the checks with:
```bash
cd backend && pip install pytest pytest-xdist && pytest -n auto    # backend tests (synthetic data only)
cd frontend && npm run build                                       # typecheck and production build
cd frontend && npm run test:unit                                   # unit tests
cd frontend && npm run ui-lint                                     # the layout checker, after a build
```
The layout checker's rules are in [docs/UI_CHECKER.md](../docs/UI_CHECKER.md).

## Known limits
- Short selling is simulated without borrowing fees or margin interest. In India, cash-market shorts must be closed the same day; holding a short overnight is only possible through futures, so treat multi-day shorts on Indian stocks as a what-if.
- Historical data for **expired** option and futures contracts isn't available from the broker, so F&O backtests only work on currently listed contracts. Continuous data is used for daily futures candles.
- Backtests don't model intra-candle order (if stop and target fall in the same candle, the stop is assumed to hit first).
- European costs cover your brokerage only (no local transaction taxes such as France's), and Japanese costs likewise.
- Tax figures are estimates to check with a chartered accountant, not tax advice: they cover only the income entered or imported, and StratLab files no return.
- The broker's Python client (even its latest release) pins `autobahn==19.11.2`, which has known advisories, so security scanners will keep flagging it until the broker updates the package. StratLab only uses it for the outgoing connection to the broker's price feed, not to serve anything. Replacing its live-feed client with our own is the way to clear it if needed.
- Options run as live paper trading only: backtesting them needs historical prices for every strike, which the broker doesn't provide for expired contracts. Group paper trading exits on closed candles; only Indian groups with faster entries enter between candles.
- This is a paper trading tool: no real orders are placed. If you add live execution later, review SEBI's retail algo trading framework first.
