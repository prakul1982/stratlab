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
| Live paper trading | 5 market days (Mon–Fri) from first use, 1 strategy | 1 strategy at a time | 5 at a time |
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
2. Open **SQL Editor**, paste `supabase/schema.sql` and run it. It is safe to run again after an update: it only adds what is missing. (The `option_snapshots` table added in September 2026 needs this.)
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

**Other programs on the same Zerodha account.** If your own trading bots also log in to this Zerodha account:
- Give StratLab its **own Kite Connect app** (its own API key). A new login to the same app cancels the previous token. If StratLab and a bot share an API key, whichever logs in last knocks the other out. StratLab notices a cancelled token, goes offline with a clear message and sends a Telegram alert, but it deliberately doesn't log in again by itself, so the two don't fight.
- Keep `KITE_AUTO_LOGIN_AT` a few minutes away from the other logins. Two logins in the same 30-second window use the same 2FA code, and Zerodha refuses the second. StratLab retries once with the next code, then stops for the day.

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
- **Daily report:** anyone with alerts on also gets a short report a few minutes after each market closes (15:40 in India, 16:10 New York, 23:55 UTC for crypto). It lists each paper trading session in that market: trades closed that day, their P&L, what's still open, and the result since the start. People can turn it off on the Account page. Nothing extra to set up.

### Recording option chains (for options backtesting)
Kite has no price history for expired options, so StratLab records its own.
- **What it saves:** every 5 minutes in Indian market hours it saves the chain of NIFTY, BANKNIFTY and SENSEX: the current and next expiry, and 15 strikes either side of the money, with bid, ask, last price and open interest for each call and put, plus the spot price.
- **Storage:** that's about 1 MB a day in the `option_snapshots` table, so the free Supabase tier holds more than a year.
- **Settings:**
  - `OPTION_SNAPSHOTS` picks the underlyings, for example `NFO:NIFTY,NFO:BANKNIFTY,NFO:FINNIFTY,BFO:SENSEX`. Set it to an empty value to turn recording off.
  - `OPTION_SNAPSHOT_MINUTES` sets how often it records.
- **Status:** the Admin page shows what is recorded, how many were saved today and any problem.
- The longer it runs, the more history options backtests will have, so it is worth starting early.

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
- **Public verdict links:** a shared link looks like `https://your-site/v/abc123`. The `/v/…` rewrite in `vercel.json` and `netlify.toml` passes it to the backend, which serves the preview that WhatsApp, X and LinkedIn read (title, summary and the card as the image), then sends people to the page at `/verdict/abc123`. If your backend isn't at `stratlab-production-ca25.up.railway.app`, change that address in both files. Set `PUBLIC_SITE_URL` on the backend to your site's address (default `https://stratlab.studio`). A public link holds a copy of the verdict, never the rules, and turning it off or deleting the experiment removes it.

### 9. Admin page
Set `ADMIN_EMAILS` to your Google email (several can be comma-separated) and redeploy. Signed in with that account, you get an **Admin** link in the sidebar with:
- Kite status and a **Log in to Kite** button (no more typing `?key=` URLs), plus a button to run the automatic login now.
- A live test of every AI provider, the order each kind of job asks them in, which keys are missing, whether the Finnhub key is set, and whether payments are set up.
- Users, their plan and this month's usage, with **Change plan** to grant Basic or Pro by hand (for 30 days, 90 days, a year or with no end date).
- Paper trading sessions running now (single instruments, groups and options), each with a Stop button.
- **Recent server errors**: every unexpected error shows users a short code, like "(GET /notebooks, ref 3FA9C1)". This table lists the last 25 with the request, the error and the line of code, and keeps them across restarts.

**Error alerts by Sentry (optional):** make a free project at sentry.io (platform: Python/FastAPI) and copy its DSN.
- Backend: set `SENTRY_DSN` in Railway (`SENTRY_ENV` defaults to `production`). Every server error then reaches Sentry tagged with the same ref code users see, along with errors in the paper trading loop and failed Kite auto-logins. Sentry emails you, or pings your phone through its app.
- Frontend: add `SENTRY_DSN: "…"` to `public/config.js` for errors in people's browsers. You can use a second Sentry project (platform: Browser JavaScript). The Sentry code only downloads when a DSN is set.
- Nothing personal is sent: no emails, IP addresses or request bodies.

Everyone else gets a 403 from the `/admin` API and never sees the link. The older `?key=ADMIN_KEY` URLs keep working.

### 10. Logo and icons
The logo's shapes and colours live in one place, `frontend/src/lib/brand.ts`, which feeds the in-app logo (`components/Logo.tsx`) and the share image. The static files in `frontend/public/` (`favicon.svg`, `logo.svg`, `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`, `og-image.png`) are rendered from the same shapes; regenerate them if the logo changes.

---

## How it works

- **Engine** (`backend/app/engine/core.py`): candle-based, long, short or both ways. Each candle it checks the stop loss first (a trailing stop once it has moved), then the target, then the time limit, then the exit rules; entries fill at the candle's close.
  - Short strategies sell first and buy back later: stops sit above the entry, targets below, and costs are charged on each side as the market charges them.
  - A trailing stop follows the best price since entry by the set percentage and never moves back. A time limit closes a trade after N candles.
  - Position size by risk = (capital × risk %) ÷ stop distance, capped by max capital per trade; or fixed capital per trade × leverage (the margin can't exceed current equity).
  - Stops can be % of price, price points, a multiple of ATR(14), or the swing low/high of the last N candles; targets can be %, points or an R-multiple of the stop distance.
  - "Both ways" strategies keep long rules in `entry`/`exit` and short rules in `shortEntry`/`shortExit`; whichever entry fires first opens the trade.
  - Entry rules combine as all, any, or a weighted score (`w` on each rule, `minScore` to enter).
  - Rule values include the candle (open, high, low, body, wicks, range, ATR in points) and the trading day (previous close, day open/high/low so far, day change %). Any value can be shifted N candles back (`ago`), multiplied (`k`), or computed on a higher timeframe (`tf`: 15m, 1h, daily). Higher-timeframe values only use completed candles: a 15-minute candle sees the last finished hour, never the one in progress. Hourly buckets start at each session's open (09:15 in India).
  - Options (`backend/app/options/`, live paper trading only): `OptionsData` loads NFO, BFO and MCX option contracts from Kite each day. It prices legs with `kite.quote` depth (sell at the best bid, buy at the best ask) and gets basket margins from `basket_order_margins`. `OptionsEngine` is a pure state machine stepped every 5 seconds by the live manager with the spot, the contracts and the quotes. It handles entry, square-off, whole-position stop/target (money or % of premium), trailing, per-leg stops, the daily cap, re-centring, margin sizing and freeze-limit slices. Quotes older than 2 minutes block entries and pause exits. Sessions are stored in `live_sessions` with `instrument.type = "OPTIONS"`. Group sessions (`group_live.py`) take optional `fast` settings, stored on the session's instrument:
- `ticks` (India only) re-checks a flat member's entry rules on the forming candle every 15 seconds. It uses `Engine.enter_now` and enters at the live price; exits still wait for the candle to close.
- `maxSpreadPct` (India only) subscribes those members' ticks in Kite's full mode for the order book. Once the rules hold, it skips the entry when the bid-ask spread is wider than that % of price, or unknown.
- `minPrice` skips instruments below a price.

Skips go through the engine's `veto` hook, so they're counted only when the rules actually fired.

With `strategy.signal` set, entries follow a notebook's rules instead of the clock. `options/signal.SignalFeed` runs those rules on the underlying's own Kite candles, fetched every 20 seconds, so they see what a backtest sees. It uses a notional account so sizing never rounds to zero. The engine enters on a long signal, enters the same legs with calls and puts swapped on a short one (or stays out), and exits when the rules exit or flip. Each signal is traded once, so a stopped trade isn't re-entered until the rules signal again. Routes: `GET /options/underlyings`, `GET /options/chain`, `POST /options/preview`, `POST /options/sessions`, `POST /options/import`.
  - Groups (`group` on a notebook: `{id, name, market, members: [{id?, symbol}], maxOpen}`, presets from `GET /groups?market=`): one engine per member on a shared timeline and one pot of capital. An entry is skipped when `maxOpen` positions are already open; the daily loss cap counts the whole group and closes everything. Unseen data uses a 70/30 split of the shared timeline; the nearby-settings check, walk-forward and the similar-stocks check are skipped. Size by fixed capital per trade, since risk sizing sizes each trade against the full capital.
  - Intraday session (`session`): no entries on candles that close outside the entry window; any open trade closes on the candle that ends at the square-off time (or at the next day's open if the data skips it); a cap on trades per day, a cooldown in candles after each trade, and a daily loss cap (% of capital, including the open trade, which is closed when the cap is hit). Times are the exchange's local time and refer to when a candle closes. With a square-off time, Indian cash trades use intraday (MIS) costs: STT 0.025% on sells, stamp duty 0.003% on buys.
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
- **Import** (`backend/app/importer.py`, `POST /import/strategy`, the **Import a strategy** page): the format is detected from the text (and file name). Option structures (a straddle, strangle, condor and so on, spotted by `options/importer.is_options`) are translated into an options strategy and open in the Options tab. A strategy that trades a list of instruments comes back with a `universe`: a preset such as the liquid F&O stocks, or its own symbols, plus the most positions open at once. The frontend saves that as the new notebook's group. A StratLab export loads exactly, with no AI. Pine Script, Python, MetaTrader, AmiBroker and plain words go to the AI builder, told which language it's reading and to list what it couldn't express; that uses one AI build. If the AI is unavailable, Pine Script is read by a small built-in parser (SMA, EMA and RSI, crossovers and comparisons, entries, exits and percent stops). A script that trades both ways is imported in its main direction, with the opposite entry used as the exit.
- **Notebooks** (`/notebooks` routes): stored in the existing `strategies` table, so no database migration is needed. A notebook can be pinned (`PUT` with `pinned`; pinned ones list first) and copied (`POST /notebooks/{id}/duplicate`, which copies the rules, market and notes but not the experiments). Each experiment keeps a compact record (up to 240 chart points, the trades, costs and verdict), capped at 50 per notebook.
- **Live paper trading** (`backend/app/live.py`):
  - India: one KiteTicker connection feeds every session, and ticks become candles for your timeframe (market hours 09:15–15:30 IST).
  - Every other market (crypto, US, UK, Europe, Japan, forex): each session checks its source (Coinbase, or Yahoo Finance) every 15 seconds for newly closed candles. Yahoo prices can run a few minutes behind.
  - On each closed candle, the same engine decides whether to trade.
  - Groups (`backend/app/group_live.py`, `POST /live/groups`): one engine and candle builder per member, fed by ticks (India) or polled a few members at a time (other markets). There's one pot of capital, a cap on positions open at once, and a group-wide daily loss cap that closes everything. Groups need intraday candles.
  - Options sessions (`backend/app/options/session.py`) are polled every 5 seconds on live quotes; see Options above.
  - Session state is saved every 30 seconds and resumes after a restart. A session keeps running until the user or the admin stops it, or the free trial or plan limit ends it. Indian sessions show as paused until the day's Kite login.
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
- Options run as live paper trading only: backtesting them needs historical prices for every strike, which Kite doesn't provide for expired contracts. Group paper trading decides on each closed candle, not on every tick, and has no spread filter.
- This is a paper trading tool: no real orders are placed. If you add live execution later, review SEBI's retail algo trading framework first.
