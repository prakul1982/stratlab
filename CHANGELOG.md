# Changelog

## September 2026

### Docs brought up to date
- README and setup guide now cover everything built this month: short selling, trailing stops and time limits, 20+ indicators, walk-forward, the similar-stocks check, paper trading in every market, the AI order for each kind of job, and early access (Pro features open to everyone until payments go live). New screenshots, including the landing page and walk-forward.
- The Plans page and the feature tour say the same.

### Walk-forward testing
- **Walk-forward test** on every verdict: the period is cut into blocks; each step tries 25 nearby settings on the past, keeps the best, and trades it on the next block the tuning never saw, then slides forward. You get the stitched return with no hindsight, next to your fixed settings and buy and hold, the settings picked at each step, and how much of the tuned return survived. It counts as one experiment and is saved with the verdict.
- ADX, Stochastic, ATR %, Donchian and volume-average lengths can now be nudged by the Nearby settings check and re-tuned by walk-forward.
- Paper trading's page now says what was already true: it works in every market (India, crypto, US, UK, Europe, Japan, forex), not only India and crypto.

### Tidy up old runs
- **Paper trading:** a stopped session has a **Delete** button, and **Clear stopped sessions** removes them all at once. Running sessions can't be deleted until they're stopped.
- **Experiments:** **Delete this experiment** on a verdict page removes one run and keeps the notebook and its other experiments.

### Smarter AI ordering
- Quick jobs (the idea builder) ask the fastest provider first; long research reads ask the providers with the biggest free allowance first (Cerebras, Mistral), saving Groq's daily token cap for quick jobs. Anthropic, the paid one, is always last.
- Admin → AI builder shows both orders and which keys are still missing.

### A real landing page
- The sign-in screen is now a full landing page: a hero with a live example (the idea you write, the rules StratLab reads, the verdict), the problem with most backtests, how it works, the four honesty checks with small illustrations, the "similar stocks" check, Research, the toolkit, all 7 markets, FAQ and a final call to action. Works in light and dark, and on phones.

### Polish
- **Pro features are open to everyone until payments go live.** Advanced indicators, F&O and alerts work on every plan while Razorpay isn't set up, and lock again on their own once it is.
- The idea examples and placeholder on **New notebook** now follow the market and instrument you picked (pick NVDA, the examples are about NVDA). "Your own data" moved to the end of the market row.
- Research pages: cards line up in even rows with no gaps, the yearly bars carry their numbers, the results chart no longer wastes half its height, the price sits on the left on phones, and compare tables line up both columns.
- Dependencies: FastAPI, httpx, pandas, razorpay and the GitHub Actions updated.

### More from every strategy
- **Short selling**: tap *Buy* in the rules to switch to *Sell short*. Stops, targets, costs and paper trading all work the other way round.
- **Trailing stop**: the stop follows the best price and locks in gains. **Time limit**: close a trade after N candles if nothing else has.
- New indicators: **ADX** (trend strength), **Stochastic %K**, **ATR as % of price**, **Donchian channel** breakouts (highest high / lowest low of the previous N candles), and **Volume** with its average.
- **Compare experiments**: any two runs side by side: what changed in plain words, both return curves on one chart, and every stat with the better one in bold.
- **Does it work on similar stocks?**: one tap on a verdict runs the same rules over the same period on about 10 well-known instruments from the same market and counts how many make money. It counts as one experiment and is saved with the verdict.
- The idea builder (AI and the simple converter) understands "short", "trailing stop" and "exit after N days".

### Research, and every market live
- **Research a company** (India and US): live price and chart, where it sits in its 52-week range, key numbers with an industry-range dot, sales and profit by year, quarterly results, results against estimates, analyst ratings, insider trades, shareholding, Screener's strengths and concerns, news, and what the company does.
- An **AI read** on every company: scores, valuation, bull and bear cases, segments, what to watch, and three **ideas to test** that open as a notebook with the market, company and rules filled in.
- **Themes** (AI map of a sector with a ranked shortlist), **Market pulse** (index levels, headlines and the day's mood), **Compare** two companies with an AI verdict, and a **Watchlist** saved to your account.
- **US, UK, European and Japanese stocks and ETFs, and forex** are now live for backtests and paper trading, with UK stamp duty and forex spread in the costs.
- Two more free AI providers (SambaNova, Mistral) join the chain; research answers are cached and shared.
- Fixed: backtests on markets with daylight saving time.

### Admin page
- An **Admin** page for the site owner (set by `ADMIN_EMAILS`): server and Kite status, Kite login button, live AI test, user list with usage, plan grants by hand, and running paper sessions with a Stop button.

### AI builder you can diagnose
- **Account → Connection check** now tests every AI provider live and shows exactly what's wrong with any that fail.
- Keys pasted with quotes or a `NAME=` prefix still work.
- If a model's JSON mode fails, it retries without it; on OpenRouter, a rate-limited free model moves on to the next free model.

### New logo
- The S-candlestick logo across the app, the favicon, phone home-screen icons, link previews and the share image.

### Features you can find
- New notebooks start with **Where do you want to test it?**: pick India, crypto or your own CSV first.
- A **Testing on** button at the top of every notebook to change the market, plus a toolbar: describe the idea again, paper trade, export, delete.
- A **Next** bar on every verdict: change the rules, try another market, paper trade, write a lab note.
- Rule words show a ▾ and a "tap to edit" hint.
- A feature tour on first sign-in, reopenable from **What can I do here?** in the sidebar.

### Reliable AI and clearer screens
- The idea builder tries several free AI providers in turn (Groq, Cerebras, Gemini, OpenRouter, then Claude) and falls back to a built-in converter.
- **(i)** buttons explain every check, number and setting in plain words.
- Roomier spacing, a centred new-idea page, and security updates for dependencies.

### The lab notebook redesign
- Each idea is a notebook with numbered experiments and lab notes.
- Every experiment ends in an honest verdict backed by four checks: unseen data, nearby settings, bad-luck drawdown and enough trades.
- Real costs in each market's own currency, including Indian taxes and fees.
- Global markets: India (Zerodha Kite), crypto (Coinbase) and any market through a CSV upload.
- A new React and TypeScript frontend with charts drawn as SVG, in light and night modes.

### Foundations
- Automatic daily Kite login (optional) with safe retries, and a self-restart for the price feed.
- Paid plans show "Coming soon" until Razorpay is connected.
- Fixes to billing, alerts, the live loop and data handling, with a pytest suite and CI.
- Proprietary license.
