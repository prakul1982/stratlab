# StratLab setup guide

[← Back to the project overview](../README.md)

A research notebook for traders: describe a strategy in plain words, test it on real market data, get an honest verdict (real edge or luck), then paper trade it with fake capital.

- **Frontend:** `frontend/`, a React + TypeScript app built with Vite. Supabase login, Razorpay Checkout, charts drawn as SVG.
- **Backend:** `backend/`, built with FastAPI. It handles market data (Kite for India, Coinbase for crypto, Yahoo Finance for the US, UK, Europe, Japan and forex, uploaded CSVs), company research, the backtest engine, the verdict checks, trading costs, live paper trading, billing, alerts and the AI writer.
- **Database and login:** Supabase (Postgres plus Google sign-in). The schema is in `supabase/schema.sql`.

## Plans (edit in `backend/app/plans.py`)

| | Free | Basic, ₹1,999/mo | Pro, ₹4,900/mo |
|---|---|---|---|
| Experiments (backtest + verdict; walk-forward and the similar-stocks check count as one each) | 5 per month | 50 per month | Unlimited |
| Live paper trading | 24-hour trial from first use, 1 strategy | 1 strategy at a time | 5 at a time |
| Indicators | Price, SMA, EMA, RSI | Price, SMA, EMA, RSI | All 20+ |
| Markets | Every market except Indian F&O | same | + Indian F&O (futures and options) |
| AI strategy builds | 10 per month | 100 per month | Unlimited |
| Alerts, export | – | – | Yes |

Monthly counts reset on the 1st of each month (IST). Limits are enforced on the server; the frontend only mirrors them.

**Early access:** while Razorpay isn't configured (`RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` empty), every plan gets the Pro features (all indicators, F&O, alerts, export), because nobody can buy Pro yet. The monthly limits above still apply. As soon as the Razorpay keys are set, the Pro features lock to the Pro plan again, with no code change.

---

## Setup

### 1. Supabase
1. Create a project at supabase.com.
2. Open **SQL Editor**, paste `supabase/schema.sql` and run it.
3. Under **Authentication > Providers > Google**, enable Google. Create an OAuth client in Google Cloud Console and paste its ID and secret into Supabase.
4. Under **Authentication > URL Configuration**, add your frontend URL, for example `http://localhost:5500` and your production domain (`https://stratlab.studio`).
5. Copy these from **Project settings > API**:
   - the project URL and `anon` key go into `frontend/config.js`
   - the `service_role` key goes into `backend/.env`. It must stay on the server only.

### 2. Kite Connect
1. In the Kite developer console, set the app's redirect URL to `https://YOUR-BACKEND/admin/kite/callback`.
2. Put the API key and secret in `backend/.env`.
3. Log in once by hand: open `https://YOUR-BACKEND/admin/kite/login?key=YOUR_ADMIN_KEY` and log in with Zerodha. This also authorises the app for the automatic login.
4. Kite access tokens expire every morning. After a login the server restarts itself (it exits and the host starts it again), because the Kite ticker can't switch to a new token inside a running process. Live sessions are saved first and resume after the restart.

#### Automatic daily login (optional)
Set these and the server logs in to Kite by itself every day at `KITE_AUTO_LOGIN_AT` (IST, default `08:00`):
- `KITE_USER_ID`: your Zerodha client ID
- `KITE_PASSWORD`: your Zerodha password
- `KITE_TOTP_SECRET`: the secret key shown when you set up an authenticator app for Kite 2FA (the text under the QR code, not a 6-digit code). If you already set up 2FA without saving it, reset external 2FA in Kite to get a new one.
- `ADMIN_TELEGRAM_CHAT_ID` (optional): your Telegram chat ID, to get a message if the login fails

To test the credentials straight away, send a POST request to `https://YOUR-BACKEND/admin/kite/auto-login?key=YOUR_ADMIN_KEY`. `/admin/status` shows the last result.

> **Read before enabling.** Zerodha's Kite Connect terms expect the daily login to be done by hand, so automating it risks your API key or account being restricted. Your password and TOTP secret also give full trading access to your Zerodha account: keep them only in the host's environment variables and never commit them. If Zerodha rejects the password or code, the server doesn't retry until the next day, so it can't lock your account with repeated attempts. Leave these variables empty to keep logging in by hand.

> **Data licensing:** this build serves data from your single Kite subscription. Before charging users, confirm with Zerodha that this is allowed. Redistributing exchange data usually needs a licence. All data access is in `backend/app/kite_service.py`, so you can swap in a licensed vendor without touching the rest.

### 3. Razorpay (optional, for paid plans)
Leave the Razorpay settings empty and the Plans page shows the paid plans as "Coming soon", with everyone on Free. To take payments:
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

### 4. AI builder (all plans) and alerts (Pro)
- **AI strategy builder and research reads:** set a key for one or more providers. They're tried in order until one answers, so a rate limit or outage at one moves on to the next (the order for each kind of job is below). All but Anthropic have free tiers. Two or three free keys are plenty: Research answers are cached and shared between users, so a popular stock costs one AI call a day.
  - `GROQ_API_KEY` from console.groq.com: free and the fastest. A good first choice.
  - `CEREBRAS_API_KEY` from cloud.cerebras.ai: free and very fast.
  - `SAMBANOVA_API_KEY` from cloud.sambanova.ai: free tier, fast Llama 70B.
  - `MISTRAL_API_KEY` from console.mistral.ai: free "Experiment" plan.
  - `GEMINI_API_KEY` from aistudio.google.com: free tier.
  - `OPENROUTER_API_KEY` from openrouter.ai: with `OPENROUTER_MODEL=auto` only free models are used.
  - `ANTHROPIC_API_KEY`: paid. Set `AI_PROVIDER=anthropic` to try Claude first.
  - Each `<NAME>_MODEL=auto` picks a suitable chat model from that provider's list; set a model id to pin one. `AI_PROVIDERS=groq,gemini` sets your own order. Quick jobs (the idea builder) default to Groq → Cerebras → Gemini → Mistral → SambaNova → OpenRouter → Anthropic; long research reads default to Cerebras → Mistral → Gemini → SambaNova → Groq → OpenRouter → Anthropic, to save Groq's daily token cap. `AI_PROVIDERS_RESEARCH` overrides the research order.
  - **Account → Connection check** sends a tiny test request to every provider with a key and shows the result for each: the model that answered and how fast, or the exact error (key rejected, out of free quota, no suitable model). With no provider working, the app falls back to its simple offline converter.
  - Paste only the key itself as the value. Stray quotes or a leading `GROQ_API_KEY=` are forgiven, but a key from the wrong account or a revoked key is not. After changing variables in Railway, redeploy so the server picks them up.
- **Telegram:** create a bot with @BotFather and set `TELEGRAM_BOT_TOKEN`. Users press Start on your bot and paste their chat ID on the Account page.
- **Email:** fill in the SMTP settings. For Gmail, use an app password. Port 465 uses SSL, 587 uses STARTTLS.

### 5. Crypto, global markets and uploaded data
Nothing to set up. Crypto prices come from Coinbase's public market data. US, UK, European and Japanese stocks and ETFs, and forex pairs, come from Yahoo Finance's public chart data (London prices are converted from pence to pounds). Neither needs an account or key. Yahoo keeps about 2 years of hourly and 60 days of 15- and 5-minute candles, so intraday tests on those markets are shorter. Uploaded CSVs are read in the browser and sent with each test; they aren't stored on the server.

### 6. Research
The **Research** section (company pages, themes, market pulse, compare, watchlist) needs one key for US companies:
- `FINNHUB_API_KEY` from finnhub.io (free, 60 calls a minute). Company pages are cached (profiles for a day, fundamentals for 6 hours, prices for a minute), and peer and watchlist prices come from Yahoo, so the free limit goes a long way.
- Indian companies need no key: fundamentals come from Screener.in's public pages, prices from Kite (or Yahoo when Kite is offline), and news from Google News.
- AI reads use the provider chain above. `RESEARCH_AI_PER_DAY` (default 60) caps fresh AI reads per user per day; cached reads don't count.

Admin → AI builder shows whether the Finnhub key is set, and each company page lists any source that didn't answer.

### 7. Run locally
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
The frontend reads `public/config.js` at runtime (API URL and the Supabase public key), so changing servers doesn't need a rebuild.
Set `FRONTEND_ORIGIN` in `.env` to match the frontend URL, for CORS. To allow several (say production and localhost), separate them with commas.

Run the checks with:
```bash
cd backend && pip install pytest && pytest     # backend tests
cd frontend && npm run build                   # typecheck and production build
```

### 8. Deploy
- **Backend:** Railway (Hobby plan, about $5 a month) or a small always-on VPS. Run it as **one process**, e.g. `uvicorn app.main:app --host 0.0.0.0 --port 8000` with no multiple workers. Live sessions, the tick feed and the daily Kite login live in memory in that process, so hosts that sleep when idle (free tiers of Render, Cloud Run) break paper trading.
- **Frontend:** Vercel or Netlify, with the project's root directory set to `stratlab/frontend`. `vercel.json` and `netlify.toml` set the build (`npm run build`, output `dist`) and send every page to `index.html`, so links like `/n/…` work on refresh. On Vercel, clear any Build Command or Output Directory overrides in the project settings so `vercel.json` applies. Put the production API URL in `public/config.js`.

### 9. Admin page
Set `ADMIN_EMAILS` to your Google email (several can be comma-separated) and redeploy. Signed in with that account, you get an **Admin** link in the sidebar with:
- Kite status and a **Log in to Kite** button (no more typing `?key=` URLs), plus a button to run the automatic login now.
- A live test of every AI provider, the order each kind of job asks them in, which keys are missing, whether the Finnhub key is set, and whether payments are set up.
- Users, their plan and this month's usage, with **Change plan** to grant Basic or Pro by hand (for 30 days, 90 days, a year or with no end date).
- Paper trading sessions running now, each with a Stop button.

Everyone else gets a 403 from the `/admin` API and never sees the link. The older `?key=ADMIN_KEY` URLs keep working.

### 10. Logo and icons
The logo's shapes and colours live in one place, `frontend/src/lib/brand.ts`, which feeds the in-app logo (`components/Logo.tsx`) and the share image. The static files in `frontend/public/` (`favicon.svg`, `logo.svg`, `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`, `og-image.png`) are rendered from the same shapes; regenerate them if the logo changes.

---

## How it works

- **Engine** (`backend/app/engine/core.py`): candle-based, long or short. Each candle it checks the stop loss first (a trailing stop once it has moved), then the target, then the time limit, then the exit rules; entries fill at the candle's close.
  - Short strategies sell first and buy back later: stops sit above the entry, targets below, and costs are charged on each side as the market charges them.
  - A trailing stop follows the best price since entry by the set percentage and never moves back. A time limit closes a trade after N candles.
  - Position size = (capital × risk %) ÷ (price × stop %), using the trailing stop when there's no fixed stop, capped by max capital per trade.
  - Quantities round down to the instrument's step: 1 share, a whole F&O lot, or a fraction of a coin.
  - About 210 extra candles are loaded before the test period so indicators are warmed up.
- **Costs** (`engine/costs.py`): every order pays your brokerage plus the market's own charges. India equity: STT 0.1% each side, exchange and SEBI fees, stamp duty 0.015% on buys, GST on brokerage and fees; futures and options use their own rates. US: SEC and FINRA fees on sells. Crypto: 0.1% exchange fee each side. Slippage applies to every fill. For Indian equity there's also a tax estimate (20% short-term, 12.5% long-term above ₹1.25 lakh). Rates change from time to time and all live in this one file.
- **Verdict** (`engine/verdict.py`): four checks on every experiment, all after costs.
  - *Unseen data:* the period is split 70/30 and each part traded with fresh capital. Passes if the last 30% still makes money.
  - *Nearby settings:* the first two indicator lengths are nudged to 60–140% of their values (up to 25 combinations). Passes if 60% or more make money; under 40% fails.
  - *Bad-luck drawdown:* the closed trades are reshuffled 1,000 times (same seed every time). Warns if the 95th-percentile drawdown is well above the backtest's; fails above 35%.
  - *Enough trades:* 30+ passes, 15–29 warns, under 15 fails.
  - The verdict: under 15 trades is *not enough evidence*; a loss after costs is *no edge*; a failed unseen-data or nearby-settings check is *probably luck*; passing both (with no failed drawdown check) is *likely a real edge*; anything else is *mixed*.
- **Walk-forward test** (`engine/walkforward.py`, run from a verdict page): the tradeable period is cut into 8 blocks. In each of 5 steps, up to 25 nearby settings of the first two indicator lengths are tried on 3 blocks of the past, the best is kept, and it trades the next block with fresh capital. The unseen blocks are compounded into one return and compared with the fixed settings and buy and hold. It fails if that return is a loss, passes if 60%+ of blocks are profitable and the unseen yearly return is at least half the tuned one, and warns otherwise (or when there were fewer than 10 unseen trades).
- **Does it work on similar stocks?** (`basket.py`, run from a verdict page): the same rules and period on about 10 well-known instruments from the same market (four at a time), skipping any the market no longer lists. 60%+ profitable passes; under 40% fails.
- **Import** (`backend/app/importer.py`, `POST /import/strategy`): the format is detected from the text (and file name). A StratLab export loads exactly, with no AI. Pine Script, Python, MetaTrader, AmiBroker and plain words go to the AI builder, told which language it's reading and to list what it couldn't express; that uses one AI build. If the AI is unavailable, Pine Script is read by a small built-in parser (SMA, EMA and RSI, crossovers and comparisons, entries, exits and percent stops). A script that trades both ways is imported in its main direction, with the opposite entry used as the exit.
- **Notebooks** (`/notebooks` routes): stored in the existing `strategies` table, so no database migration is needed. A notebook can be pinned (`PUT` with `pinned`; pinned ones list first) and copied (`POST /notebooks/{id}/duplicate`, which copies the rules, market and notes but not the experiments). Each experiment keeps a compact record (up to 240 chart points, the trades, costs and verdict), capped at 50 per notebook.
- **Live paper trading** (`backend/app/live.py`):
  - India: one KiteTicker connection feeds every session, and ticks become candles for your timeframe (market hours 09:15–15:30 IST).
  - Every other market (crypto, US, UK, Europe, Japan, forex): each session checks its source (Coinbase, or Yahoo Finance) every 15 seconds for newly closed candles. Yahoo prices can run a few minutes behind.
  - On each closed candle, the same engine decides whether to trade.
  - Session state is saved every 30 seconds and resumes after a restart.
  - Free trials and plan limits are re-checked every minute.
- **API routes:** see `backend/app/main.py`. The browser only ever talks to this API; it never touches the database or Kite directly.

## Known limits
- Short selling is simulated without borrowing fees or margin interest. In India, cash-market shorts must be closed the same day; holding a short overnight is only possible through futures, so treat multi-day shorts on Indian stocks as a what-if.
- Historical data for **expired** option and futures contracts isn't available from Kite, so F&O backtests only work on currently listed contracts. Continuous data is used for daily futures candles.
- Backtests don't model intra-candle order (if stop and target fall in the same candle, the stop is assumed to hit first).
- Yahoo Finance and Screener.in are public but unofficial sources: they can change without notice, and their terms don't cover commercial redistribution. Before charging users for data from them, move to a licensed vendor; each source lives in one file (`app/data/yahoo_markets.py`, `app/intel/*.py`), so it's a contained swap. The AI's company and theme reads are opinions for research, not investment advice.
- European costs cover your brokerage only (no local transaction taxes such as France's), and Japanese costs likewise.
- The tax figure is a rough estimate for Indian equity only, not tax advice.
- `kiteconnect` (even its latest release, 5.2.2) pins `autobahn==19.11.2`, which has known advisories, so security scanners will keep flagging it until Zerodha updates the package. StratLab only uses it for the outgoing connection to Zerodha's own price feed, not to serve anything. Replacing Kite's ticker client with our own is the way to clear it if needed.
- This is a paper trading tool: no real orders are placed. If you add live execution later, review SEBI's retail algo trading framework first.
