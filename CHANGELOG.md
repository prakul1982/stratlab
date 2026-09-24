# Changelog

## September 2026

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
