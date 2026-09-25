# Changelog

## September 2026

### A longer free trial, a daily report, and error alerts
- **Free trial:** the free plan's paper trading trial now lasts **5 market days** (Monday to Friday, counted from the day you start) instead of 24 hours. Starting on a weekend doesn't use any of it.
- **Daily report:**
  - People with alerts on get a short Telegram or email report a few minutes after each market closes.
  - For each paper trading session in that market it lists the trades closed that day and their profit or loss, what's still open, and the result since the start.
  - You can turn it off under **Account → Trade alerts**.
- **Fixed: trade alerts never arrived** for anyone without a paid Pro plan. While payments aren't live, everyone can switch alerts on, but they were only ever sent to paid Pro accounts.
- **Error alerts (optional):**
  - Set a Sentry DSN and every server error goes to Sentry with the same ref code users see.
  - So do errors in the paper trading loop, failed Kite auto-logins and, if you add the DSN to the frontend config, errors in people's browsers.

### A new share card, and public links to a verdict
- **The share card** now shows:
  - an equity chart against buy and hold, with the unseen years shaded
  - all four honesty checks, each marked passed, failed, warning or skipped
  - the timeframe, dates and side
  - a disclaimer
- Long names and questions end in "…" instead of being cut off mid-word.
- **Group verdicts get their own card:** the group's name, the number of positions allowed at once, and how many members made money.
- **Sharing on a phone:** **Share verdict** opens the phone's share sheet, so the card goes straight to WhatsApp, X or anywhere else. On a computer it saves the image and copies it where the browser allows.
- **Public links:**
  - **Share verdict → Make a public link** copies a link anyone can open without an account.
  - The page shows the verdict, the chart, the checks and, for groups, each member's result. It never shows your rules.
  - In chats and on social sites the link previews with the card.
  - **Turn off the public link** removes it, and so does deleting the experiment or the notebook.

### Docs, landing page and tour brought up to date
- **Landing page:**
  - A new **Beyond one chart** section covers options (live paper trading, with backtesting coming soon), whole-group tests and paper trading, and importing any strategy, and the top menu links to it.
  - The toolkit and FAQ now cover option structures, groups and imports from your own bots.
- **README:**
  - It covers **Import any strategy**, and paper trading groups and option structures.
  - New screenshots of the Options tab and the Import page, and the rest are re-shot on the current design.
- **Setup guide:**
  - How to run StratLab next to your own bots on the same Zerodha account: a separate Kite Connect app, and a different login time.
  - The Admin page's recent-errors list.
  - How imports route to groups and options.
  - Group and options paper trading, and when a paper session stops.
- **The in-app tour** has a new step for groups, options and importing.

### Fixed: Admin page error while an options session runs
- The Admin page's "Paper trading now" list crashed while any options session was running ("Something went wrong on our side (GET /admin/sessions)"). Options sessions now report their market like other sessions, and one broken session can no longer hide the whole list.

### Easier to trace server errors
- An unexpected server error now shows a short reference code, like "Something went wrong on our side (ref 3FA9C1)".
- The Admin page lists recent errors: the code, when it happened, which request, the error, and where in the code it failed. You can match a user's report to its cause without digging through the host's logs.
- The error message also names the request that failed (for example "GET /notebooks"). The list is saved in the database, so a restart no longer wipes it.

### A full UI pass
- Narrow pages (Options, Import) now sit in the middle of the screen instead of hugging the left edge.
- Every dropdown in the app has one look in every browser. Safari had been drawing its own boxes, on Compare, in the rules editor and on Options.
- The time and number labels on the Options form line up.
- **Duplicates removed:**
  - **Sidebar:** Research and Import a strategy are now ordinary links in the menu instead of two more big buttons, and New notebook stays the one main button.
  - **Your notebooks page:** the Import button there is gone, since the sidebar has it.
  - **Notebook page:** the "Paper trading" side card is gone, since the toolbar has Paper trade. Make a copy, Export and Delete moved into a **More** menu, so the toolbar fits on one line.
  - **Options page:** its own import box is gone, since Import a strategy sends option structures there. The "Live paper trading" pill repeated the line above it.
  - **Account page:** the "Look" card is gone, since the sidebar has the Night mode switch.
- On phones, the verdict page's long suggestions now wrap instead of running off the screen.

### Tidier Options controls, market hours in the sidebar
- On the Options page, every control is the same height, so the rows line up. The **More…** menus now look like the other buttons in every browser (Safari showed a plain box before) and fill in when you've picked from them. The Stop loss and Target labels line up.
- **Markets now** shows when a closed market opens ("opens 6h 31m", "opens Mon"). Hover or tap a market for its hours in exchange time and in your time, and how long until it opens or closes.
- The big **What can I do here?** button is now a small **Tour** link beside Night mode.

### Import any strategy, and paper trade whole groups
- A new **Import a strategy** tab in the sidebar takes any strategy (a config file, Pine Script, Python, MetaTrader, AmiBroker, a StratLab export or plain words) and sets it up in the right place:
  - rules on one instrument become a notebook
  - rules that scan a list of stocks become a notebook already set up on that group
  - option structures open in the Options tab
- Imports recognise **universes**: "F&O stocks" maps to the liquid F&O group, "NIFTY 50 stocks" to NIFTY 50, and a source that lists its symbols becomes your own group. The "max concurrent" setting becomes positions open at once.
- **Paper trade a group live**:
  - one pot of capital, a limit on positions open at once, and a group-wide daily loss cap that closes everything
  - India uses live ticks for every member; other markets are polled a few members at a time
  - the session page shows open positions with stops and targets, today's P&L, every member and all orders
  - it needs intraday candles

### A simpler Options page
- One column instead of two, and no sticky panel overlapping the option chain.
- The main choices sit up front: what to trade, expiry, structure, times, units, stop and target. Legs open with **Edit legs**. Caps, trailing, re-centring, sizing and costs moved into **More settings**.
- Less common structures and underlyings moved into **More…** menus. The payoff numbers use the full width, and the page no longer scrolls sideways on phones.

### Kite login reliability
- If Zerodha rejects the automatic login's 2FA code, it now tries once more with the next code. The usual cause is another program using the same code on the account moments earlier. A rejected password still stops for the day, so the account can't get locked.
- If Zerodha cancels today's token mid-day, StratLab now notices. That usually happens when another login to the same Kite Connect app replaces it. Indian data goes offline with a clear message instead of failing every request, the admin page says what happened, and a Telegram alert goes out. It doesn't log in again by itself, which would cancel the other program's token in turn.
- The last automatic-login result is saved, so it's still on the admin page after a restart.

### Options tab (live paper trading)
- A new **Options** tab for NSE, BSE and MCX options: NIFTY, BANKNIFTY, SENSEX, FINNIFTY, MIDCPNIFTY, BANKEX, crude, natural gas, gold and silver, plus any stock with options.
- **Structures**: short and long straddle, short strangle, iron fly, iron condor, bull call and bear put spreads, single calls and puts, or custom structures up to eight legs. Legs are placed by strikes or points from the money.
- **Live pricing before you start**: legs priced on the live bid and ask, premium, most it can make or lose, breakevens, a payoff chart and the broker's real margin, hedges included. A live option chain sits alongside.
- **Paper trading on real quotes**: sold legs fill at the bid and bought legs at the ask, with optional extra slippage. Nothing is modelled. It covers:
  - entry time, last entry, square-off, entries a day and cooldown
  - stop and target in rupees or % of premium, trailing, per-leg stops, and a daily loss cap
  - **re-centring** that rolls the sold legs (or all of them) when the market moves
  - fixed lots, or **as much as margin allows** on your capital
  - freeze-limit order slicing with brokerage per slice, STT or CTT, exchange fees, stamp duty and GST
- No entries on stale quotes (holidays, dead feed); open positions wait for live prices.
- **Import**: option-structure configs (like a hedged short straddle) are recognised by the normal importer and open in the Options tab, with a list of anything that couldn't carry over. Options strategies export and import as JSON.
- **Backtesting options is coming soon**: it needs real historical prices for every strike, and we won't stand in a pricing model.

### Test on a group of stocks
- **Groups**: on the market page, pick a ready-made group (NIFTY 50, Bank NIFTY, 25 liquid F&O stocks, 20 US mega caps, 10 large coins) or build your own from search, up to 50. The same rules then run on every member at once.
- One pot of capital, a limit on **positions open at once**, and a daily loss cap that counts the whole group, so a momentum or scanner strategy is tested the way it trades.
- The verdict shows each member's trades, P&L, win rate and buy-and-hold, and the trades list names the symbol. Members the market no longer lists are skipped and named.
- Walk-forward, the similar-stocks check and paper trading still work on one instrument at a time.

### Intraday strategies
- **Trade both ways**: separate long and short rules in one strategy; whichever fires first opens the trade.
- **During the day**: an entry window, a square-off time, a cap on trades per day, a cooldown after each trade, and a daily loss cap. Indian intraday trades use MIS costs.
- **New rule values**: the candle (open, high, low, body, upper and lower wick, range, ATR in points) and the trading day (previous close, day open/high/low, **day change %**). Any value can be taken **N candles ago**, **multiplied** ("lower wick > 1.5 × body"), or computed on a **higher timeframe** ("1-hour close above the 1-hour 7 EMA") using completed candles only.
- **Conviction score**: combine entry rules as "enough of these", each with a weight, and set the score needed to enter.
- **Stops and targets in other units**: points, ATR multiples or the recent swing low/high for stops; points or R-multiples for targets.
- **Fixed capital per trade with leverage**, alongside sizing by risk.
- The AI builder and Import understand all of it, including JSON configs from your own trading systems.
- Live paper trading's unrealised P&L now accounts for short trades.

### Import, pins and small things that add up
- **Import a strategy** you already have: a StratLab export (loads exactly), TradingView Pine Script, Python, MetaTrader, AmiBroker or plain words. Drop a file or paste it; it becomes a notebook, and anything that couldn't be translated is listed there. Pine Script imports even when the AI is down.
- **Pin** notebooks to keep them at the top of the sidebar and the list.
- **Make a copy** of a notebook to try a variation without touching the original. **Rename** a notebook by clicking its name.
- All notebooks: **search**, and **sort** by recent, name or best verdict. The sidebar shows each notebook's last verdict as a coloured dot.
- The sidebar's **Markets now** lists all seven markets, open or closed.
- **Ctrl/⌘ + Enter** runs the next experiment. New notebooks start in the market you used last.

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
