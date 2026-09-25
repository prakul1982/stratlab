<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo-dark.png">
  <img alt="StratLab" src="docs/images/logo-light.png" width="340">
</picture>

**Test your trading idea before your money does.**

Research a company, describe a strategy in plain English, test it honestly on Indian, US, UK, European and Japanese stocks, forex or crypto, then paper trade it on live prices with fake money.

### [🌐 stratlab.studio](https://stratlab.studio)

![Python 3.11](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=white)
![React](https://img.shields.io/badge/React_18-20232A?logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white)
![License: proprietary](https://img.shields.io/badge/license-proprietary-555)

</div>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/verdict-dark.png">
  <img alt="A verdict page: 'No edge here', with four honesty checks: unseen data, nearby settings, bad-luck drawdown and enough trades" src="docs/images/verdict-light.png">
</picture>

## What makes it different

Most backtesting tools show a flattering chart. StratLab tells you whether the edge is **real or luck**.

- **A verdict on every experiment.** Each test ends in one plain answer: *Likely a real edge*, *Mixed evidence*, *Probably luck*, *Not enough evidence* or *No edge here*. Four checks back it up:
  - **Unseen data:** the rules are tested separately on the last 30% of the period, which they were never tuned on.
  - **Nearby settings:** 25 variations of your indicator lengths. If only your exact numbers make money, that's a lucky fit.
  - **Bad-luck drawdown:** your trades reshuffled 1,000 times, to show how deep the losses could realistically get.
  - **Enough trades:** under 15 trades, luck dominates.
- **Two deeper checks, one tap each.**
  - **Walk-forward test:** re-tunes your settings on a stretch of the past, trades them on the next stretch the tuning never saw, slides forward and repeats. It shows what re-tuning as you go would really have earned, without hindsight.
  - **Does it work on similar stocks?** Runs the same rules on about 10 similar instruments from the same market. Real patterns travel; lucky charts don't.
- **Real costs, in the market's own currency.** India: STT, exchange and SEBI fees, stamp duty, GST, plus a capital-gains estimate. US: SEC and FINRA fees. UK: stamp duty on share buys. Forex: the spread. Crypto: exchange fees. Slippage on every fill. You see what you'd actually keep.
- **Lab notebooks.** Each idea is a notebook: a question, the rules written as sentences, numbered experiments you can compare side by side, and your own lab notes.
- **A full toolkit.** Buy, sell short, or trade both ways with separate long and short rules. Stops in %, points, ATR or the recent swing low/high; targets in %, points or R-multiples; trailing stops and time limits. 20+ indicators (moving averages, RSI, MACD, Bollinger Bands, VWAP, Supertrend, ADX, Stochastic, ATR, Donchian, volume) plus the candle itself (open, high, low, body, wicks, range) and the trading day (previous close, day open/high/low, day change %). Any value can be taken N candles ago, multiplied, or computed on a higher timeframe.
- **Options, live.** A separate Options tab paper trades straddles, strangles, iron flies, condors, spreads or any structure up to 8 legs on live NSE, BSE and MCX option quotes, filling at the real bid and ask. It covers timed entries, MTM stops and targets, trailing, per-leg stops, daily caps, re-centring, margin-based sizing and freeze-limit slicing. Options backtesting is coming soon.
- **Test on a whole group.** Run the rules on a ready-made group (NIFTY 50, Bank NIFTY, liquid F&O stocks, US mega caps, large coins) or your own list of up to 50, sharing one pot of capital with a limit on positions open at once. The verdict breaks the result down member by member.
- **Built for intraday.** An entry window, a square-off time, a cap on trades per day, a cooldown after each trade and a daily loss cap. Entry rules can be combined as a weighted conviction score. Size by risk or by fixed capital per trade with leverage; Indian intraday trades use MIS costs.
- **Any market.** Indian stocks, indices and F&O (Zerodha Kite), US, UK, European and Japanese stocks and ETFs and forex (Yahoo Finance), crypto (Coinbase), or upload a CSV of candles from anywhere. No extra keys needed.
- **Research built in.** Company pages for India and the US: live price and chart, valuation and growth with context, sales and profit history, results against estimates, who owns it, insider trades, news, and an AI read whose trading ideas open as a notebook in one click. Plus AI theme maps, a daily market pulse, side-by-side comparisons and a watchlist.
- **Plain-English builder.** Describe the idea; the AI turns it into rules and asks only about what you left out. It tries several free AI services in turn (Groq, Cerebras, Gemini, Mistral, SambaNova, OpenRouter), with Claude as an optional paid fallback, and a simple built-in converter if all of them are down.
- **Paper trading in every market.** Run the rules on live prices with fake money: India, the US, UK, Europe, Japan and forex during their market hours, crypto around the clock.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/walkforward-dark.png">
  <img alt="A walk-forward test: re-tuned on the past and traded on unseen blocks, it made money in 5 of 5, with the settings picked at each step" src="docs/images/walkforward-light.png">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/notebook-dark.png">
  <img alt="A notebook: the question being tested, rules written as editable sentences, and lab notes" src="docs/images/notebook-light.png">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/research-dark.png">
  <img alt="A research page for Reliance Industries: price chart, 52-week range and a button to test a strategy on it" src="docs/images/research-light.png">
</picture>

## Everything you can do, and where to find it

New here? A short tour pops up the first time you sign in. You can reopen it any time from **Tour** at the bottom of the sidebar. Hover (or tap) a market under **Markets now** to see when it opens or closes.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/tour-dark.png">
  <img alt="The feature tour: step 3 of 9, 'Research a company first', with where to find it" src="docs/images/tour-light.png">
</picture>

| You want to… | Where it is |
| --- | --- |
| Find an idea | **Research** in the sidebar: a company's AI read ends with ideas to test in one click |
| Explore a sector | **Research → Themes**: a map of who's involved, where the margin sits, and a ranked shortlist |
| See the market's mood | **Research → Market pulse**: index levels, headlines and an AI read of what's moving |
| Keep an eye on companies | **Watch** on a company page; they're listed under **Research → Watchlist** |
| Test a new idea | **New notebook**: pick the market first, then describe the idea or start from a classic one |
| Bring a strategy you already have | **Import a strategy** in the sidebar (or on New notebook): it sets up a notebook, a group notebook or an Options structure depending on what you bring; a StratLab export, TradingView Pine Script, Python, MetaTrader, AmiBroker or plain words |
| Keep favourites at the top | **Pin** on a notebook (or the pin on its card); pinned notebooks lead the sidebar and the list |
| Find a notebook | Search and sort (recent, name, best verdict) on **All notebooks**; the dot beside each name in the sidebar is its last verdict |
| Try a variation without losing the original | **More → Make a copy** at the top of a notebook (Export and Delete are there too) |
| Rename a notebook | Click its name at the top of the notebook |
| Choose or change the market | Step 1 on a new notebook, or the **Testing on** button at the top of any notebook |
| Rewrite the idea from scratch | **Describe the idea again** at the top of a notebook |
| Tweak a rule | Tap any highlighted word (marked ▾) in **The rules**: indicator, length, condition or number |
| Run a test | **Run experiment** in a notebook (or press Ctrl/⌘ + Enter); each run is saved and numbered so you can compare |
| Short instead of buy, or trade both ways | Tap **Buy** at the start of the rules and pick **Sell short** or **Trade both ways** |
| Trade intraday | Pick 5- or 15-minute or 1-hour candles; a **During the day** line appears for the entry window, square-off, trades a day, cooldown and daily loss cap |
| Use the candle's shape, an earlier candle or a higher timeframe | Tap a value in a rule → **More**: candles ago, multiply by, timeframe |
| Score your entry conditions | Tap **all of these** and pick **enough of these**: each rule gets a weight and the trade needs a minimum score |
| Trail the stop or cap how long a trade lasts | The **Trail the stop by … and close any trade after …** line in **The rules** |
| Compare two runs | **Compare experiments →** in a notebook, or **Compare with the previous run** on a verdict |
| Check a tuned idea without hindsight | **Walk-forward test** on a verdict: re-tunes on the past, trades the next unseen stretch, and repeats |
| Check it isn't one lucky chart | **Does it work on similar stocks?** on a verdict runs the same rules on about 10 similar instruments |
| Understand a number | Every check, stat and setting has an **(i)** button that explains it in plain words |
| Decide what to do next | The **Next** bar on a verdict: change the rules, try another market, paper trade, write a lab note |
| Test on a whole group of stocks | **Testing on → Or test on a group**: a ready-made group (NIFTY 50, Bank NIFTY, F&O stocks, US mega caps, large coins) or your own list, with a limit on positions open at once; **Paper trade** runs the whole group live on intraday candles |
| Paper trade options | **Options** in the sidebar: pick the underlying, expiry and structure, press **Price it now** for live fills, payoff and margin, then **Start paper trading**; stops, targets, re-centring and sizing are under **More settings** |
| Paper trade | **Paper trade** at the top of a notebook or verdict; running sessions are under **Paper trading** |
| Share or save | **Share verdict** saves an image; **Export** saves the rules as a file |
| Check that everything's connected | **Account → Connection check** shows market data and each AI provider |
| Read at night | **Night mode** at the bottom of the sidebar |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/new-dark.png">
  <img alt="The New notebook page: choose the market and instrument first, then describe the idea" src="docs/images/new-light.png">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/landing-dark.png">
  <img alt="The landing page: 'Is your trading idea real, or just lucky?', with an example idea, the rules StratLab reads from it, and its verdict" src="docs/images/landing-light.png">
</picture>

<sub>Screenshots use synthetic sample prices, not real market data.</sub>

## How it works

```mermaid
flowchart LR
    UI["Frontend<br/>React + Vite"] -- "REST, Supabase JWT" --> API["FastAPI backend"]
    UI -- "Google sign-in" --> SB[("Supabase<br/>Auth + Postgres")]
    API --> SB
    API -- "India: candles, live ticks" --> KITE["Zerodha Kite Connect"]
    API -- "crypto: candles, prices" --> CB["Coinbase public data"]
    API -- "US, UK, EU, Japan, forex; charts" --> YF["Yahoo Finance"]
    API -- "research: US companies" --> FH["Finnhub"]
    API -- "research: Indian fundamentals, news" --> SC["Screener.in, Google News, Wikipedia"]
    API -- "subscriptions (coming soon)" --> RZP["Razorpay"]
    RZP -- "webhooks" --> API
    API --> AI["AI provider chain<br/>Groq, Cerebras, Gemini, Mistral,<br/>SambaNova, OpenRouter, Claude"]
    API --> ALERT["Telegram / email alerts"]
```

The browser only talks to the backend. The backend owns every secret: the Supabase service key, Kite and Razorpay credentials, and the AI keys. Backtests, verdict checks and live paper trading all use the same engine, so a strategy behaves the same everywhere.

## Repository layout

```
stratlab/
├── backend/                  FastAPI app (deploys to Railway)
│   ├── app/
│   │   ├── main.py           API routes
│   │   ├── engine/
│   │   │   ├── core.py       rule evaluation and the trading engine
│   │   │   ├── indicators.py SMA, EMA, RSI, MACD, Bollinger, VWAP, Supertrend, ADX, Stochastic, Donchian
│   │   │   ├── costs.py      per-market trading costs and tax estimates
│   │   │   ├── verdict.py    the four honesty checks and the verdict
│   │   │   ├── portfolio.py  group tests: one pot of capital across many instruments
│   │   │   └── walkforward.py walk-forward test: re-tune on the past, trade the unseen next block
│   │   ├── options/          Options tab: contracts, chains, quotes and margin from Kite; the options engine and sessions
│   │   ├── universes.py      ready-made groups of stocks and coins
│   │   ├── group_live.py     paper trading a whole group with one pot of capital
│   │   ├── basket.py         "does it work on similar stocks?": same rules on ~10 similar instruments
│   │   ├── data/             market data: markets list, Coinbase (crypto), Yahoo (US, UK, EU, Japan, forex)
│   │   ├── intel/            research: Finnhub, Yahoo, Screener.in, news, Wikipedia, AI reads, /research API
│   │   ├── research.py       load candles, run an experiment, keep a compact record
│   │   ├── live.py           paper trading on live ticks (India) or polled candles (every other market)
│   │   ├── kite_service.py   Zerodha Kite Connect
│   │   ├── kite_auto.py      optional automatic daily Kite login
│   │   ├── admin.py          owner-only admin page API
│   │   ├── billing.py        Razorpay subscriptions
│   │   ├── plans.py          plan limits and prices (Pro features open to all until payments go live)
│   │   ├── ai_writer.py      plain English → strategy rules
│   │   ├── ai_providers.py   the AI provider chain and its order for quick jobs and research reads
│   │   └── alerts.py         Telegram and email alerts
│   ├── tests/                pytest suite
│   └── .env.example          every setting the server reads
├── frontend/                 React + TypeScript app built with Vite (deploys to Vercel)
│   ├── public/               config.js (API URL, Supabase public key), favicon, app icons, link-preview image
│   └── src/
│       ├── pages/            notebook, verdict, markets, research, paper trading, options, plans, account, admin
│       ├── components/       rules editor, charts, sidebar, feature tour, logo, share image
│       └── lib/              API client, formatting, rule parser, CSV import, (i) help texts, brand
└── supabase/
    └── schema.sql            tables, row-level security, sign-up trigger
```

## Quick start

```bash
# backend
cd stratlab/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in Supabase, Kite, Razorpay and AI keys
uvicorn app.main:app --reload --port 8000

# frontend (in another terminal)
cd stratlab/frontend
npm install
npm run dev                   # open http://localhost:5500
```

Run the tests with `cd stratlab/backend && pytest`, and check the frontend with `cd stratlab/frontend && npm run build`.

The **[setup guide](stratlab/README.md)** covers Supabase, Kite Connect (including the automatic daily login), Razorpay, the AI writer, deployment, and how the engine and the verdict work.

## Plans

**Early access: StratLab is free, and every feature is unlocked for everyone** (all indicators, all markets including Indian F&O, walk-forward, alerts and export). Monthly limits still apply. The paid plans below switch on automatically once Razorpay is connected.

| | Free | Basic · ₹1,999/mo | Pro · ₹4,900/mo |
|---|---|---|---|
| Experiments (each with a full verdict) | 5 / month | 50 / month | Unlimited |
| AI strategy builds | 10 / month | 100 / month | Unlimited |
| Research AI reads | 60 / day | 60 / day | 60 / day |
| Paper trading | 24-hour trial | 1 strategy | 5 strategies |
| Markets | All, except Indian F&O | same | + Indian F&O |
| Indicators | Price, SMA, EMA, RSI | Price, SMA, EMA, RSI | All 20+ |
| Alerts, export | – | – | ✓ |

Limits live in [`plans.py`](stratlab/backend/app/plans.py) and are enforced on the server.

## What's new

See the [changelog](CHANGELOG.md).

## Disclaimer

StratLab is a research and paper trading tool. It places no real orders and gives no investment advice, and past backtest results don't predict future returns.

## License

Proprietary. © 2026 Prakul Bansal. All rights reserved. See [LICENSE](LICENSE).
