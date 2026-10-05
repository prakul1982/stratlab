# Changelog

What shipped, newest first, grouped by month. Built from the git history.

## October 2026

### 5 October 2026: small fixes

- **Audit price check (India):** a company page's price that matches any of our last 5 daily closes now agrees, since a thinly traded stock's page can be several sessions old. A price that matches none is still flagged.

### 5 October 2026: strikes picked by delta or premium, and India VIX

**Trade**
- **Strikes picked by rule (Pro):** an options leg can take the strike nearest a model delta, inside a delta range, nearest (or at least, or at most) a rupee premium, or nearest a share of the at-the-money straddle, resolved on the live quotes at entry and at each re-centre. The builder's preview shows what each rule picks now (every plan), and the order log says why under each order.
- **India VIX (every plan):** a panel on Positioning and a tile on the Trade home's positioning card: the value and change, the day's range, where it sits among the past year's closes, NIFTY ATM IV beside it, today's line and the year's chart. India VIX and its change % are rule values in notebooks, and the verdict's nearby-settings check nudges a VIX cut-off.
- **India VIX entry filter (Basic):** options sessions can enter only while India VIX is inside a band; the session page lists the entries it held back.
### 5 October 2026: business updates in numbers and named holders above 1%

**Invest**
- **Business updates, read into numbers:** automakers' monthly sales and lenders' quarterly deposits and advances, found among each company's exchange filings and read into figures, each kept only when its line is found in the filed document (with the page). A **Business updates** panel on Indian company pages and the deep dive shows the change on the month (or quarter) and on the year and a 24-month chart; **Business updates** (`/invest/business-updates`) lists a sector's latest figures alphabetically; an alert when a company files a new update. The filings list is for everyone; the figures, sector view and alert are Basic.
- **Named holders above 1%:** each company's latest shareholding pattern (the exchange's XBRL) names its promoter group and every public holder above 1%; a **Named holders** panel shows them by stake with the change since the quarter before (every plan). **Named holders** (`/invest/holders`, Basic) searches a name across companies, alphabetically, with new and dropped lines, lets you untick spellings that aren't the same holder, and follow one for a message when a new quarter's filing changes them.
### 5 October 2026: stock futures, stock lending fees and margin funding

- **Stock futures** (Trade, a Positioning tab at `/trade/positioning/stocks`): every F&O stock's price and open-interest change with the buildup words, OI by expiry, the share in later expiries (rollover), the basis and its annualised figure, and MWPL use with the ban line, from the exchange's evening files. Sort and filter, no ranking. Today for everyone; each stock's history and an alert when MWPL use crosses 80% (Basic). F&O values (OI change, rollover, basis) can be used in rules on Indian stocks' daily candles.
- **Stock lending fees** (Invest, `/invest/stock-lending`): lending fees that traded on the exchange's SLB segment for your holdings and watchlist over 30 and 90 days, annualised against the share price, how often anything traded, eligibility, and how lending works. Every plan.
- **Margin funding** (Invest, `/invest/margin-funding`): the market's MTF book and each stock's margin-funded amount as a percent of shares issued and of market value, with day and 30-day changes, and a calculator for your own MTF position's interest, cost-covering price and margin breach price. Today and the calculator for everyone; history and an alert on a funded level (Basic).
### 5 October 2026: fund behaviour, stock and ETF SIP tests, fixed-income rates and floating-rate loans

**Money**
- **Your return against each fund's** on Mutual funds: your XIRR beside the fund's own NAV return over the same dates and the gap in points (every plan); the gap in rupees, your SIP record (months paid, missed and stopped, the longest unbroken run), redemptions made after a 10% fall from the high with those units at today's NAV (hindsight, labelled), how long redeemed units were held and how much of today's value is over 3 years old (Basic). From your statement and the public NAV history.
- **Test a SIP** (`/money/sip-test`, and a "Test a SIP" button on Indian company and ETF pages): an amount (or a number of shares) every day, week or month into one stock or ETF or a split across up to 10, with a yearly step-up, on past closes with the charges of every purchase: money put in, value, XIRR, the deepest fall, the longest time below the money put in, and the same money as a lump sum on day one (every plan). Dip rules (only on dips, or extra on dips) beside the plain SIP, and the same SIP from every start month as the spread of XIRRs with the dip rule's luck check (Basic). The rule in plain words to copy.
- **Rates** (`/money/rates`): the last T-bill auction cut-offs, benchmark government bond yields and the repo rate from the Reserve Bank, this quarter's small savings rates with their tax treatment and 80C, the RBI floating rate bond, and your own fixed and recurring deposits from Net worth, each with its yield after tax at a slab you pick (every plan) or at the marginal rate from your own tax estimate, rebate, surcharge and cess included (Basic). With a TDS note.
- **Floating-rate loan check** in Net worth: a loan can now carry its rate type (repo-linked, T-bill-linked, MCLR or another rate), spread, reset period, last reset and the rate on your statement, with reset dates in the money calendar (every plan). For a repo-linked loan, the rate expected after the last reset (repo then plus spread) beside your statement's, with any gap in points and rupees a year; for every floating loan, what each change did, as a new EMI or the same EMI for more or fewer months, with the interest left each way (Basic). The RBI's August 2026 loan pricing draft is shown as a draft, with where a difference can be raised.

### 5 October 2026: price charts, options Greeks and what-if, F&O changes, ETF vs NAV, fund costs and a self-healing AI

**Everywhere**
- **StratLab in your AI assistant (Pro):** a remote MCP server for Claude, ChatGPT and other assistants, with revocable keys on **Account → AI assistant**. It reads your watchlist, holdings, a company's facts, the watchlist scan, alerts and paper sessions; a key you allow can open and close positions in your own paper sessions. No real orders, ever; rate-limited, and every call is in a log you can see. Facts only.
- **Space homes, one shape:** Trade, Invest and Money each open with a short heading, the next step (start a first notebook, pick up where you left off, or find a company), one row of four tool cards, the live panels with placeholders while they load, then the rest of the space's tools.
- **Our own price chart** on company pages, experiments and paper sessions: candles, hollow candles, Heikin-Ashi, OHLC bars, line, area or baseline; 5-minute to daily candles, scrolling back for older ones; normal, log or % scale; volume and indicators (SMA, EMA, Bollinger bands, VWAP, Supertrend, Stage, 52-week high and low, RSI, MACD); drawings (trend line, level, ray, rectangle, Fibonacci, note) kept on your account; compare another symbol on a % scale; fullscreen, PNG and a table view. An experiment's chart marks each trade's entry and exit; a paper session's updates the forming candle with its stop and target.
- **One chart system for every other chart:** a crosshair and tooltip by mouse, keyboard or tap, drag or pinch to zoom with a Reset, range buttons, legends that switch series on and off, linked charts that share a crosshair, Index to 100 and a table view. Colours checked for colour-blind readers in light and dark.
- **Wide tables fit a laptop:** My Holdings, the tax report's sales and lots below cost, Positioning's participant table and Admin's Users and prices show their main columns first, with the rest under **More columns** (remembered per table), so nothing needs a sideways swipe at 1280px. Positioning's put-call ratio card puts each expiry under the index's name.

**Trade**
- **Closing auction** (`/trade/closing-auction`): F&O stocks' 15:15-15:35 auction, live: each stock's reference price, indicative and final price and the gap between them, the indices' indicative close, the day's timetable, and on expiry days the settlement method and your paper option positions at the indicative settlement. Free; 60 days of history on Basic.
- **Paper trading follows the closing auction (from 3 Aug 2026):** in stocks with derivatives, continuous fills stop at 15:15; an intraday square-off after that fills at the auction's closing price, and daily candles close on the official close. Futures and options trade to 15:40, and options still open at expiry settle at their intrinsic value against the underlying's official close. India's session times live in one dated table, with the circulars, in the rates and rules register.
- **Chart replay practice** (`/trade/replay`, Basic): a past stretch of any instrument's candles on our own price chart with the future hidden; step or play at 1×, 5× or 20×, go long or short, flat, and set a stop and target by typing or clicking the chart. Fills at the close shown, stops and targets on later candles (gaps at the open), charges at the published rates. "Random stock and date" hides a NIFTY 50 stock and the dates until the end. Finished sessions go to the trade journal as practice trades, with a Real / Practice / Both switch there.
- **Signal forward test** (`/trade/signals`, Pro): a per-user secret webhook URL for TradingView or Chartink alerts (shown once, stored as a hash, replace or turn off any time) that moves your own signal paper sessions. Each signal fills at StratLab's live price with charges, never the alert's; every one is logged with its arrival time and fill, late, refused or repeated, with the reason. Strict JSON, 2 KB a signal, 30 a minute and 1,000 a day per URL. The daily report counts late and refused signals, and the verdict's checks run after 30 trades. Paper only.
- **Market events calendar (every plan; reminders on Basic):** Trade → Market events lists RBI policy decisions and minutes, India's CPI, IIP and GDP releases, US Fed decisions and the US CPI and jobs reports (with India times), index changes with the stocks going in and out, monthly and NIFTY weekly expiries and exchange holidays, each from the official calendar, with the published figure once it is out. Index badges on company pages, the next events on the Invest home, reminders by phone, Telegram or email, and an opt-in to show them in the Money calendar and its feed.
- **Options builder, after charges (every plan):** the charges to open and close, breakevens before and after them, the premium kept, and the exact most it can make and lose, before and after charges.
- **Greeks and the payoff today (every plan):** each strike's IV and Greeks in the chain's **IV and Greeks** view, each leg's and the position's delta, gamma, theta and vega, and the payoff today beside the one at expiry, on the builder and an options session's page. Model estimates, shown with their inputs.
- **What-if sliders and a roll preview (Pro):** move the underlying, shift IV and pass days; preview closing one leg and opening another strike or expiry, with the premium difference, both orders' charges and the net Greeks before and after.
- **F&O changes** (`/trade/fo-changes`): stocks leaving F&O with their last series, entries, lot-size revisions and changes to expiry days and sessions, in one dated list from the exchange's own files, read twice a trading day. Badges on the watchlist, company pages and session cards. Free to view; an alert when a change touches your watchlist or running paper sessions (Basic).

**Invest**
- **ETF vs NAV** (`/invest/etf-gaps`, also a Scans tab): each Indian ETF's price against its last published NAV, widest gap first, with 30 trading days of history, a badge in My Holdings and on the ETF's company page. Free to view; an alert when the gap passes your level (Basic).

**Money**
- **Fund costs** on Mutual funds: each fund's TER and what it comes to in rupees a year on your value (every plan); its parts, the direct and regular plans side by side with the gap in rupees, the TER since you bought, and category changes (Basic).

**Plans**
- New paid features, each named on its plan card and in the Plans grid: fund costs in rupees, ETF gap alerts and F&O change alerts on Basic; options what-if sliders and the roll preview on Pro. Prices unchanged.

**Running StratLab**
- **AI that heals itself:** each provider's models are listed, filtered and given a short test every few hours (and on demand); the ones that answer correctly and fast are used, fast first for quick jobs and strong first for research. Every reply is checked, an empty or cut-off one is retried once, failing models and providers pause and the next is asked, rate limits are respected until their reset, each request has a time budget, and repeated questions are answered from a cache. Errors users see never name a provider.
- **More free AI providers:** Cloudflare Workers AI, Z.ai, Hugging Face, Vercel AI Gateway, GitHub Models and the NVIDIA API catalog join the existing ones, each optional.
- **Admin → Services → AI:** each provider's state, quota and reset, models in use with success rate and median time, the order each job uses, and **Test every provider**, **Re-rank models**, **Pin** and **Block**; missing providers list their free limit, a key link and the Railway variables.
- **Admin → Data checks → Fund costs (TER)** with **Read now**, and a **Fund costs (TER)** row in Check every feature. `POST /admin/fo-changes/refresh` reads the F&O sources on demand.
- **India market audit:** waits (paused: **offline**) while the day's market data login isn't done, instead of marking every company "not checked yet"; rows not checked yet are retried 20 an hour, or all at once with **Re-check the N not checked yet**. Earnings calls are counted apart from one-on-one investor meetings, and a missing investor presentation is a fact. Companies with no sales get "N checks can't be judged without sales"; P/E is worked out from market value and profit when missing, and capex from the cash flow breakdown; margins above 100% are explained by nil sales or costs written back. ETFs, trusts and new or untraded listings are handled. The admin guide says to log in each day before the India audit.

**Landing page and docs**
- The landing page lists price charts, ETF vs NAV, Greeks and what-if, breakevens after charges, F&O changes and fund costs in their spaces, with the new alerts; the plan cards and Plans grid match `plans.py`. The README, feature guide, admin guide (AI keys and Re-rank, TER **Read now**, the F&O refresh, `OPTION_SNAPSHOTS`), setup guide and roadmap match.

### 4–5 October 2026: three spaces, the Money space, positioning, breadth and the trade journal

**Three spaces**
- **Trade, Invest and Money:** a switcher at the top of the menu picks which space's menu shows (or **All**, every group folded). Each space has a home page: Trade with Options first, paper sessions, the journal, the library, import, today's positioning and your notebooks; Invest with company search, your watchlist, today's results, market breadth and red flags; Money with your holdings, this year's capital gains tax estimate and a card per Money tool. The welcome question now asks what brings you here, and your answer picks the space you start in.
- **A slimmer sidebar:** one scrolling menu in short groups, Scans and the watchlist as tabbed pages, and a two-line footer: "N of M markets open" opens the markets list, and your initials open Account, Admin, dark mode, the tour and sign-out.
- **Current first, the past folded:** running paper sessions first and stopped ones under one line; today's orders first and earlier ones folded; alerts fired today, then earlier; the money calendar's next 90 days, with the past week folded; results days gone by this week and corporate actions of the last two weeks folded. Nothing is deleted.
- **Tidier pages:** numbers right-aligned in tables, figures in a row sharing one line, centred empty states, one content width for every space home.

**Trade**
- **Positioning** (beside Options): the exchange's participant-wise open interest and volume for clients, DIIs, FIIs and proprietary traders, in index or stock futures and options, with each side's long and short share and the change from the day before; FII and DII cash market flows; the put-call ratio of NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY and SENSEX; and one index's chain facts (max pain, open interest by strike, ATM IV). Each section says where its numbers come from and how much history is stored, and a missing number says why. Today's numbers for everyone; the history and the IV percentile on Basic.
- **FINNIFTY and MIDCPNIFTY** chains are recorded every 5 minutes too, so options backtesting and the positioning history have five indices to draw on.
- **Trade journal:** bring your broker's tradebook or tax P&L, equity and F&O. Every trade is paired into round trips after charges, with your notes, tags, feelings and mistakes; breakdowns by day, hour, setup and more; and the verdict's honesty checks run on what you really did, with paper vs real per setup. Free keeps your last 50 trades with the basic stats; Basic keeps everything.
- **Options sessions read today first:** the open trade with its orders folded under it, then the trades closed today (or one line such as "No trades today. Next entry 09:30."), then the earlier trades under one line with their total after costs. Tap a trade to see its orders, grouped by the moment they were sent, with readable contract names.
- **Rates:** F&O STT at the Finance Act 2026 levels from 1 April 2026 (futures 0.05%, options 0.15% of premium on sells), NSE charges with the IPFT contribution, BSE index options at their own rate, the 2026 SEC and FINRA fees, and NSE's new freeze limits from 5 October.

**Invest**
- **Market breadth:** for all NSE stocks, the NIFTY 50, NIFTY 500, Midcap 150, Smallcap 250 or US large caps, how many stocks rose or fell, sit above their 20, 50 and 200-day averages and made new highs or lows each day, with the A/D line, McClellan, breadth thrust and TRIN, a table by sector, and an alert when the share above the 50-day average crosses your level. Today's numbers for everyone; the history and charts on Basic.
- **Company suggestions while you type** a symbol, in My Holdings and the alert form.

**Money**
- **Net worth:** your holdings and funds plus PF, PPF, NPS, deposits, gold, property, cash and the rest, minus loans, each valued with its rule and date; EMIs, interest this year and what a prepayment would change; an insurance register; a monthly history on Basic.
- **Mutual funds** from the CAMS or KFintech CAS PDF (read once, never stored, nor its password): each scheme's value, XIRR, mix by category and capital gains per year (Basic). Fund sales join the tax report.
- **Tax tools:** dividends with the TDS on them, advance tax due by each date with the interest if it falls short (Pro) and reminders a week and a day before (everyone), and how much of the long-term exemption is used, lot by lot on Pro.
- **The year's total tax estimate** in the tax report: F&O, commodity and currency results from the tax P&L ZIP, other income, the regime, your age band and residency, with the rebate, surcharge, cess and set-off.
- **US stocks in Indian tax:** each sale in rupees at the rate the Income-tax Rules use, the 24-month rule, US dividends with the foreign tax credit, and Schedule FA. Year totals for everyone; the workings on Pro.
- **ITR-ready export:** your year laid out like the ITR-2 and ITR-3 schedules, as a spreadsheet or one PDF for your CA (Pro). Not a filed return.
- **Money calendar:** tax due dates, results and dividends for your stocks, maturities, premiums, EMIs and your own dates, with a private link for Google or Apple Calendar and reminders on Basic.
- **My Holdings** keeps US stocks (valued in dollars and counted in the rupee total) and labels ETFs, REITs, InvITs and gold bonds, which the tax report puts under their own heads.

**Plans and invites**
- Basic ₹699 a month or ₹6,999 a year, Pro ₹1,999 a month or ₹19,999 a year, GST included. The plan cards and the Plans grid name every new tool on the plan that adds it.
- **Invite rewards:** you earn a month of Basic for each of your first 2 friends a year who become active, and for each of your first 2 who subscribe; after that, every friend who subscribes adds 25% of a month. A refunded payment takes its reward back.

**Running StratLab**
- **Admin → Data checks:** a **Storage** panel (how full the database is, the biggest tables, and a one-click move of the bulky market data to an optional second database), **Market breadth** with **Run now** per market, **Rates and rules** (every hard-coded rate with its source and review date, and a daily read of the official sources), exchange holidays for every market, and a whole-market audit with start, pause, reset, a monthly full check and a re-check per company.
- **A nightly encrypted copy of the database**, kept 7 days (the weekly full copy 28 days), with restore steps in the admin guide.
- **Steadier server:** data caches are bounded by memory size, which stops the whole-market audit from running the server out of memory, and a failed read after a restart no longer wipes the audit's stored results.
- **Behind the scenes:** the site deploys on Vercel only (the unused Netlify config is gone); tests run on Node 22, in parallel, and a newer push cancels the run before it; shared helpers and dead code cleaned up.

**Landing page and docs**
- The landing page lists everything above in its space, the plan cards match the server's plans line for line (a test fails if a paid tool is missing from its card), and the FAQ covers files you can import, the total tax estimate, the ITR export, who can see your money data, the five recorded option chains and the Positioning page. The README, feature guide, admin guide and setup guide match, with new screenshots of the space homes, Positioning and an options session.
- **Fix:** on Positioning, the long/short bar no longer draws over the change line under it.

### Landing page and docs brought up to date
- **The landing page is grouped the way the product is:** Research, Portfolio and tax, Strategy testing and Alerts, each listing what ships today (results calendar, corporate actions, deals, surveillance lists, holdings import, the tax report, share cards and invites among them), then the plans and a refreshed FAQ. The separate "problem", "beyond one chart" and "for investors" sections are folded in; the markets list adds Indian currency futures.
- **Plans on the landing page match the server exactly:** Free, Basic and Pro come from one shared file (`frontend/src/lib/plans.ts`, also used by Plans), priced in the visitor's currency; a backend test fails if it drifts from `plans.py`, and a browser test checks the cards against the server's plans.
- **FAQ:** what StratLab does and doesn't tell you, holdings files, the tax report, invite rewards and public company pages; the data-source answer no longer names any source.
- **Phone:** FAQ questions are 36px tall, so each is easy to tap.
- **Docs:** a rewritten README (features, architecture, an environment variable table, tests and deploys), `docs/FEATURES.md` (every feature and where it lives), `docs/ADMIN.md` (the Admin page, Check every feature, the data audit, email, PostHog and Sentry), and landing screenshots in `docs/screenshots`.

### Tax report
- **Capital gains on listed Indian shares, as an estimate:** tradebooks and tax P&L files from Zerodha, Groww, Upstox, Angel One, ICICI Direct, HDFC Securities or a plain CSV, combined without duplicates and matched first in, first out per company. Per financial year: short and long term split at the 23 July 2024 rate change, the ₹1 lakh / ₹1.25 lakh exemption, set-off and carry forward, grandfathering at the 31 January 2018 price, intraday kept apart, and bonus and split adjustments. Open lots below cost at today's prices, CSV and PDF downloads, and one-step delete.
- **The broker's tax P&L ZIP:** read as it comes (a CSV per segment and the summary sheet), with only the equity files used and everything skipped listed with why; the summary's totals are checked against what was read. Each tax P&L line keeps the buy the broker matched it with. Uploads up to 10 MB a file, with strict limits on what a ZIP may unpack to.

### Exchange surveillance lists
- **ASM (long and short term, with stages), GSM, ESM, trade-to-trade, price-band changes and the F&O ban,** read twice a trading day, each list kept with its own date. Badges with a plain explanation on company pages, the watchlist, holdings, screens and paper trading; a block on the public company pages; a Screens filter; a stock alert for entering or leaving a list; and a line in My Stocks.

### New prices and plan limits
- **Basic ₹699 and Pro ₹1,999 a month (₹6,999 and ₹19,999 a year), GST included** ($8 and $20; €8 and €19; £7 and £16). All indicators, alerts, scans, watchlist red flags and Watchlist at a glance on Basic; Indian F&O on Pro. Deep dives and decks are counted once per company a month. Sector rotation and red flags on a company page are open to everyone, and the weekly newsletters are free.

### Plain numbers instead of scores
- **The AI read on a company page shows fact rows, not 0-100 scores:** growth, price trend, debt and cash, margins and returns, worked out from reported results and prices, never by AI. Old cached reads lose their scores too. Deal, corporate-action and holdings badges use one neutral style.

### Analytics on, and email fixes
- **PostHog is live** on the US cloud, with the host allowed in the CSP and described on the privacy page.
- **A Brevo IP-block error** says where in Brevo to turn the block off.
- **Whole-market audit fixes:** a source turning a check away is "not checked yet" and retried, not a company error; facts about a company (a new listing, no revenue yet) are kept apart from gaps; more US filing concepts are read.

### QA round: new features at every screen size, and a security pass
- **Made-up tickers can't fill the database:** a company page's corporate actions for a ticker with nothing on record are remembered in memory only, and a ticker must start with a letter or digit (or ^ for an index), so "..", "-x" and the like never reach a data source's address.
- **The landing page's research example** shows the AI read's four opinion scores (Moat, Growth, Momentum, Health) with no overall score and no valuation score, and no longer mentions analyst ratings, which the company page doesn't show.
- **A free month is judged at the time it's given:** whether someone pays (so the month is banked) is read at the reward's own time, not the server's clock, so the daily check and the tests agree on any date.
- **Wording:** the welcome question's Investing choice reads "Research companies for the long term", not "Find good companies and hold them".
- **My Holdings' dividends:** the two tables are headed "Ex-date ahead" and "Last 12 months (estimated)", and an amount a share reads ₹0.50, not ₹0.5000.
- **A new user's first session** is a browser test now: the invite link, the welcome question, first steps, a backtest and paper trading, a company's deals and corporate actions, an alert, holdings with a bonus applied and undone, a screen, newsletters, the invite link and the plans, on desktop and phone.
- **Every route at every screen size** now includes the corporate-actions calendar (both scopes, India and US), a company with a bonus and dividend ahead and deals, and the invite link in Account; `E2E_ALL_SIZES=1` sweeps ten sizes from 320px to 1920px, each in light and dark.

### Corporate actions and dividends
- **Research → Corporate actions:** dividends, bonus issues, splits, buybacks, rights issues and demergers by ex-date, for your stocks or every company, with a message when one of your stocks announces one and the evening before its ex-date. A panel on each company page lists those ahead and the last three years'.
- **My Holdings:** dividends ahead and of the last 12 months (estimated), and a bonus or split since your holdings were saved offered as a one-click **Apply** or **Already in my file**, with **Undo**. Never changed without you.

### Deals and insider trades (India)
- **On every Indian company page and deep dive:** promoters', directors' and key staff's own trades and pledges, substantial acquisitions, and bulk and block deals, from exchange disclosures, as filed. The checklist adds promoter and insider open-market buying and selling over six months; screens can filter on a promoter or insider purchase in the last N days; alerts can fire on new disclosures; My Stocks lists them.

### Usage analytics (off until a key is set)
- **PostHog, only with POSTHOG_KEY in config.js:** page views and a few funnel events by internal user id, with no emails, names, symbols or amounts, no session recording and no autocapture; Do Not Track is respected. The server records a completed payment once per payment.

### Invite rewards: a free month of Basic for both
- **When a friend joins through your invite link and becomes active, you both get a free month of Basic.** Active means they used the app on 3 different days in their first 14: a backtest, a watchlist add, a deep dive, starting paper trading or importing holdings.
- **Caps:** up to 12 free months for the one inviting, ever; once for the friend; nothing when both addresses reach the same mailbox. Free months stack onto free time already running.
- **Paying users keep it for later:** someone on Basic or Pro banks the month, and it starts if their paid plan stops. Paying again later changes nothing.
- **Told by email and phone note** (an account email, so it goes even with tips turned off). Account shows "N friends joined · M free months earned" and the plan card shows free Basic's end date.
- **Admin → Users** shows each user's free months, and an Invite rewards panel: more than 5 sign-ups through one link in a day wait there for review (the sign-ups themselves go through). A daily check from 6 am India time gives rewards and closes invites whose 14 days ran out.

### Security review of screens, cards and invite links
- **Share images must be real card pictures:** a whole PNG, no bigger than the card's own size each way, with nothing hidden after it, so a tiny file can't unpack into a huge picture for whoever previews the link. Verdict share cards follow the same rule.
- **Shared company cards don't pile up:** each person keeps links to the 50 companies they shared most recently (sharing one more takes down the oldest), and sharing is limited to 30 cards an hour. Trying invite codes is limited to 10 an hour.
- **The weekly screen email lists only companies that started meeting a screen,** not ones the background job had only just gathered, and one person's trouble no longer stops the others' emails.
- **Check every feature judges each market's prices by that market's own date,** so a check run after midnight in India no longer reports the US feed as stale while New York's day is still running.
- Tests that depended on the day or time they ran no longer do (checked by running the whole suite as if on other dates and times).

### Stock screens, and "as of" everywhere
- **Research → Screens:** filter India or US companies by sector, size band, 3-year revenue growth, margins, debt to equity, ROE and ROCE, dividend yield, P/E, Stage, price against the 52-week high and recent red-flag filings. Alphabetical by default and sortable by any column; nothing is scored or ranked. Screens read an index gathered in the background from the public company pages, never a data source or AI per request.
- **Saved screens** (Free 1, Basic 5, Pro 25) can send a weekly email on Saturday morning with the companies that newly meet them, to a confirmed address, with one-click unsubscribe.
- **"As of" lines** on the company page, deep dive, holdings, at a glance, screens, newsletters and the News page say when the prices and numbers are from.

### Share company cards, and invite links
- **Share** on a company page or the deep dive draws a card with the company's price, 1-year range and four key numbers, and makes a public link (`/c/…`) that previews as the card on WhatsApp, X and LinkedIn and opens the company's public page. Facts from that page only, never AI.
- **Invite friends** in Account: your own link, and how many friends joined through it. An account counts once, only when it's new, never for your own link or mailbox. No reward is given yet.

### Stock alerts
- **Set alert** on a company page, the deep dive or the watchlist: a price level, a day's move, crossing a moving average, RSI, a Stage change, or a 52-week high or low, for India and US stocks. Each fires once (or at most once a day), in plain words; all of them are on **Investing → Alerts**.
- At most 5 messages an hour and 20 a day per person; extra alerts wait and go together. Email only to a confirmed address. Free 3 alerts, Basic 20, Pro 100.

### My Holdings
- **Import your holdings** from Zerodha (Console or Kite), Groww, Upstox, Angel One, ICICI Direct or HDFC Securities, or any CSV with symbol (or ISIN), quantity and average price: value, P&L, today's change, sectors, and each stock's trend, red flags, filings and results date. Add, edit or remove lines by hand; **Delete my holdings** removes everything.
- Free keeps 30 stocks, Basic 100, Pro 300. Holdings count in the My Stocks newsletter.

### Results calendar
- **Research → Results:** India's board meetings for results and US results dates, from a week back to four weeks ahead. Once results are filed it links the filing and the numbers it states.
- A message on results day and when the results are out, for the companies you follow, and a section in My Stocks.

### Public company pages
- **`/stocks/in/SYMBOL` and `/stocks/us/SYMBOL`:** a page per listed company for search engines, with the price, 1-year range, key numbers, five years of results, the trend and recent filings. Facts only, never AI; links to test a strategy on it or open the deep dive. Sitemaps and robots.txt list them.

### Lifecycle emails, first steps and the offer countdown
- **Emails that follow an account:** a welcome right after signing up, a nudge on day 2 to test a first strategy (only if they haven't), a reminder the day before and on the last day of the free paper-trading trial and of the launch offer, and what's new after 14 quiet days. Each goes once per person, at most one a day, from 8 am to 9 pm India time. **Tips and reminders** can be turned off in Account or from the link in each email; payment receipts and a note when a paid plan stops always go.
- **Admin → Services** previews each of these emails, or sends one to you as a test.
- **Your first steps** on Home for a new account: run a backtest, add a stock to the watchlist, open a deep dive, start paper trading, set up newsletters or phone alerts. Each ticks itself from what you've done; hide it any time, and it goes by itself when everything's done.
- **The launch offer counts down** on Home and Plans while it runs.

### Newsletters, and research reads that stay factual
- **Newsletters:** the Market Brief for India and the US after each close (or a weekly digest on Saturday morning), and My Stocks with what changed for the stocks in your watchlist, notebooks and paper trading. Choose daily, weekly or off in **Account → Newsletters**; past issues are on the **News** page. The weekly Market Brief is free, the daily one is on Basic and My Stocks on Pro.
- **Email you can trust:** newsletters go only to an address confirmed from a link, every email has a one-click unsubscribe (the page asks first, so mail scanners opening links don't unsubscribe anyone), and email can go through Brevo as well as Resend or SMTP.
- **Research reads state facts, not advice:** no buy or sell calls, price targets, cheap or expensive labels, overall ratings or ranked stock lists; themes list the companies along the chain in value-chain order.
- **A weekly summary email for the owner** every Monday at 9:00 IST.

### BSE-only companies, and a phone pass
- **Companies listed only on BSE work like NSE ones:** search, the company page, charts, quotes, backtests, groups and paper trading take them by BSE symbol or code. Their filings and red flags come from BSE's own announcements feed, and the deep dive reads their presentations and call transcripts from BSE, so the document read, report card and slides work too. A daily check of BSE's feed joins **Check every feature**.
- **Phones:** wide tables keep their first column in place and show an edge when there's more to the side; menus, checkboxes and buttons are bigger to tap. The browser tests now fail if any control on any page is too small to tap on a phone.

### Admin in tabs, alerts by email
- **Admin is split into tabs:** Overview (what **Needs your attention**, worst first, each item opening the tab where it's fixed), Services, Data checks, Users and Billing.
- **Admin alerts are emailed** to the admin's sign-in address. Email goes through Resend over HTTPS when its key is set, since the host blocks outgoing mail ports; **Send a test email** in Admin → Services shows the server's reason when it can't send.
- **Whole-market audit:** the list of listed companies is read daily and only new listings are checked.
- **Pull requests from Claude merge themselves** once the backend, frontend and browser tests have passed and the preview has built.

### Slides as PDF, and how far back to read
- **The deck is redesigned** (a summary slide, styled charts, tables and cards) and comes as a PDF too: **Slides (PowerPoint)** and **Slides (PDF)** on the deep dive show the same slides.
- **Years of analysis:** the document read and the report card look back over the last 1 to 5 years (default 2); the report card reads 4, 6, 9 or 12 calls.
- **Targets the numbers can't settle** (a bank's loan-to-deposit ratio, a retail mix) are settled from what the company said after the period ended, kept only when the quote is in that document word for word, contains the number, and came after the period.
- **Whole-market audit (India)** adds companies listed only on BSE.

### Full check: security, load and a daily check
- **Check every feature runs by itself** every day at 4:50 pm IST, tries anything that failed once more, and alerts the admins only about what still fails. The whole-market audit retries a company whose source was down.
- **Security sweep:** only the intended routes answer without sign-in, every admin route refuses ordinary users, and nobody can touch another user's notebooks, sessions or invoices. Admin is only for an address proven by Google sign-in.
- **Load:** about 150 requests a second on one server process, with no errors at 300 very active users. Backtests run in worker processes so pages stay quick.
- **Investor home works for US watchlist companies too**, with an India / US switch.

### Amounts in the unit people use; Indian document gaps closed
- **$ billion and ₹ lakh crore:** a chart or table switches to the larger unit only when the numbers are large and every one still shows within 1%, so a small loss never prints as 0.00. The same rule in the deep dive, company page charts, report card, AI reads, plans and the deck. Reads saved before the change are tidied when shown.
- **Letters with no link** (or a dead one): the company's own investor pages are searched for a PDF of the same kind naming the same quarter.
- **Scanned PDFs** are read by OCR.
- **EV/EBITDA for Indian companies subtracts cash**, from the balance sheet's Other Assets breakdown.
- **Currency cross pairs:** EURUSD, GBPUSD and USDJPY futures, priced in dollars or yen, with rupee brokerage converted at the day's rate.

### US companies: the full deep dive
- **US deep dive from the SEC's filings:** ten years of revenue, profit, operating margin, reported capex, cash flow, debt and cash; twelve quarters; industry from the SIC code; ratios from today's price. The checklist, valuation and deck use the company's own currency.
- **The AI read for US companies:** the business, risks and industry measures from the latest 10-K, and plans and outlook from it and the latest earnings releases, with the same exact-quote checks.
- **US management report card:** targets from up to six earnings releases over two years, checked against the SEC numbers, with periods in the company's own fiscal year.
- **Insiders instead of promoters:** the US checklist shows insiders' open-market buying and selling over six months.
- **Audits:** the data audit runs on US sets, and Admin → Whole market: US checks every company filing with the SEC.

### Indian currency derivatives
- **Currency futures (NSE CDS):** USDINR, EURINR, GBPINR and JPYINR as a market of their own, front month rolled three days before expiry, in whole lots, with daily backtests on years of stitched history, intraday on the current contract and paper trading. Costs without STT; 9:00 am to 5:00 pm IST; the segment's own holidays read from the exchange daily.
- **Currency options in the Options tab:** USDINR, EURINR, GBPINR and JPYINR, priced against the nearest currency future.

### Payments from anywhere, with GST invoices
- **Prices in the visitor's currency:** 18 currencies, following the rupee price at the day's exchange rate, rounded to a tidy amount. Admin can fix any of them.
- **A GST invoice for every payment:** CGST and SGST within the state, IGST across states, exports zero-rated under the LUT. Account → Invoices lists them, printable, with your name, address and GSTIN for future ones; Admin → Invoices holds the seller's details and a CSV per financial year.

### Whole-market audit and browser tests
- **Admin → Whole market** checks every listed NSE company in the background, new listings first, with progress, findings by area and a CSV.
- **Exchange holidays are read automatically** from the exchange's own list; the data audit covers the NIFTY 500, Next 50, Midcap 150 and Smallcap 250.
- **Browser tests** open every main page on desktop and phone on every pull request: no errors, nothing wider than the screen, no broken numbers, loss bars below the zero line, US deep dives in dollars.

### Stress test, rounds 4 and 5: every feature live, many people at once
- **Admin → Check every feature:** runs each part of StratLab once on the live server with live data and says pass, check or fail with the reason: prices in every market and whether they're up to the last trading day, a two-year backtest per market (verdict and costs present), the NIFTY 50 and US scans, sector rotation in both markets, the NIFTY option chain (no expired or closed-day expiry, prices on every strike), exchange filings, company pages, news, the database and how far ahead the holiday calendar runs. No AI is used; about a minute.
- **Load test:** the real server (one worker, as in production) under hundreds of simulated people doing what people do. With 300 people at a normal pace, pages answer in 0.2 to 0.5 seconds (slowest 2.4 s) and backtests, scans and the sector chart in 5 to 8 seconds, with no errors; with 100 people clicking every half second, pages still answer within 1.5 seconds. A short version runs on every change.
- **Fixed from it:** heavy work (backtests, scans, the sector chart, document reads, starting paper trading) now takes turns, a couple at a time, so ordinary pages never queue behind it; one that waits more than 90 seconds is told the server is busy. The bad-luck drawdown check in every verdict is 6 times faster (same answers). After a restart or the morning broker login the server fills its shared caches (instrument lists, scans, sector rotation, option contracts) before people need them.

### Stress test, round 3: every tricky moment
- **The whole app is run at 16 moments that trip trading apps up**: a holiday on the weekly expiry day and the moved expiry the day before, a minute after an expiry's close, 1 am India time (the server's UTC date is still yesterday), either side of the broker's 6 am token reset, the open, a weekend, Diwali, the US and UK clock changes, MCX's late session, year end, and days past the known holiday calendar. Every page and action runs, paper sessions and alert jobs tick, and the option chain must never offer an expired or closed-day expiry.
- **The holiday calendar no longer runs out:** the installed calendar ends with 2026, after which every weekday would have counted as a trading day. India's fixed national holidays now close the market in any year, and Admin → Exchange holidays shows how far ahead holidays are known (with a warning under 60 days) and takes the exchange's yearly list pasted as it's published.
- **Fixed from it:** between midnight and 5:30 am India time the option chain, MCX contracts, the risk view, company pages and the report card used the server's UTC date (yesterday), so the chain could offer a contract that expired the day before; and with alerts on, a paper trade that opens with a sale (short selling or writing an option) didn't send its alert.

### Stress test, round 2: every source failing
- **Each data source, the broker feed, the database and the AI are broken on purpose**, one at a time and in every way they fail in real life (down, timing out, server errors, rate limits, refusals, a web page instead of data, an empty answer), while every page and action is used. Each must answer with what it can still show or a clear message: never a crash, broken data, a number that isn't a number, or a provider's name. Runs on every change.
- **A source that's down is skipped for a minute** after three failures in a row, instead of every page waiting up to 8 seconds behind it. Applies to every research source and the exchange feed.
- **Database or sign-in down:** a clear "isn't answering right now, nothing you saved is lost" instead of "something went wrong", and nobody is told their session expired because the sign-in service was unreachable.
- **Fixed from it:** junk from the crypto price source crashed backtests; a broker failure while starting paper trading, or while loading the sector chart's benchmark, crashed the request (now "couldn't load prices, nothing was started"); a block page from the company-data site could have been remembered as "no such company" for six hours; two AI model-list readers crashed on a non-data reply. Any other failure inside a data-source call now says "a market data source failed, try again" and is still listed on the admin page.
- **The data audit can be stopped** from Admin; the rows so far are kept.

### Stress test, round 1: every route, every input
- **A fuzz test now calls all 90 server routes** signed out and as each kind of user, with realistic requests (every strategy feature, every market, options, groups, paper trading, research, admin) and then with each field broken: empty, huge, negative, not-a-number, wrong type, hostile text. The AI answers well, with junk, fails or is busy in turn. Nothing may crash, answer with broken data or take over 10 seconds; it runs on every change.
- **Fixed from it:** granting a plan to a user who doesn't exist crashed (now "No user with that ID"); payment webhook errors now use the same format as every other error; a mistyped Indian symbol took up to 18 seconds (it now answers at once, checked against the exchange's own list, and misses are remembered); a 20-stock US scan or US sector chart took 12 to 14 seconds (the lookup and the price history now share one download).
- **From the second audit:** presentations filed as a "fact sheet", "quarterly report" or "investor release" (TCS, HCL, Bharti and others) are recognised; when a letter links several PDFs the transcript or deck is tried first; links split across two lines are joined; decks up to 30 MB are read; the audit checks prices against the broker's live exchange quote (the exchange's website turns servers away); finance companies aren't flagged for margins above 100%; a renamed symbol is only followed when the rename is known (a site search once matched LTIM to a different company), and LTIM is out of the IT group until its new symbol is confirmed.

### Checking the data at scale (admin)
- **Data audit:** Admin → Data audit runs every company in a set (NIFTY 50, NIFTY Bank, the liquid F&O stocks, or every sector's main stocks, about 180) through the deep dive on the live server, with no AI. Each company's P/E is recomputed from market cap and trailing profit, trailing revenue is checked against the last four quarters, the last close against the exchange's own price, and profit, margins and capex for impossible values; missing industry, valuation, checklist answers, presentations and transcripts are listed as gaps, and optionally whether each document can actually be read. Results by area, a CSV download, and the last run kept across restarts.
- **Fixes from the first audit (about 180 companies):**
  - Call transcripts and presentations that a company's filing links to on a CDN or a separate investor site are now read (still only public addresses, size-capped, PDFs only); a letter that points to an investor web page has that page opened and its matching PDF read.
  - The exchange's own quote is now asked for the way its quote page asks, so the price check and the industry fallback work from the server.
  - Companies whose consolidated accounts are new (a subsidiary set up recently) show their longer standalone history, with a note saying so. Renamed symbols are looked up (Tata Motors → TMPV in the ready-made groups).
  - When a group's net profit includes minority shareholders' share or one-off gains (Bajaj Finserv, Grasim, Siemens and others), the deep dive says so and shows earnings per share growth.
  - Loss-making companies say why there's no P/E; P/B is worked out from the balance sheet when the page has no book value.
  - The audit no longer flags real but unusual years (a loss bigger than sales, profit above sales from other income), and reports one exchange refusal instead of one per company.
- **International cards in the payments check:** Check payments setup now says whether Razorpay takes cards issued outside India (or where to look when Razorpay's answer doesn't say) and which currencies the plans are priced in.

### Built around what you came for
- **One question at the start: investing, trading or both.** It sets what the menu, the home page and the examples show first; nothing is hidden, and it can be changed on the Account page. People who already answered the experience question are asked this once.
- **An investor home page:** "Which company do you want to look into?" with the company search, popular names, and four starting questions (leading sectors, Stage 2 stocks in NIFTY 50, red flags, the watchlist at a glance). Notebooks move to their own page for investors.
- **The investing tools are in the menu:** Companies, Investor home, Stage 2 scan, Sector rotation, Red flags and Watchlist each one tap away, under Investing; the trading tools under Trading. Whichever you came for is on top, and the main button follows it (Look up a company / New notebook).
- **The home page is grouped by goal** (find stocks, understand a company, test an idea, trade with fake money) instead of a wall of equal cards.
- **Search understands investor questions:** "deep dive Apollo Hospitals", "which sectors are leading?", "red flags in my watchlist", "Stage 2 stocks in NIFTY 50" and "compare TCS and Infosys" open the right page directly.
- **Placeholders show real examples,** rotating every few seconds and matched to what you came for, instead of "Search…".
- **The landing page speaks to both:** "Know the company. Test the idea.", with For investors and For traders buttons, the research and investor sections moved up to follow the opening, a card on industry measures and valuation, and a page title and link preview that cover investing too.
- **The next step where you need it:** a Deep dive link on every scan result and every red-flag company; on a company page, Deep dive comes first for investors.

## September 2026

### Company deep dive
- **Deep dive on every Indian company page (Pro):** ten years of sales, profit and operating margin, sales and profit growth over 3 and 5 years, the last 12 quarters with growth on a year earlier, and a capex and cash table (capex, capex as a share of sales, cash from operations, free cash flow, debt). Capex is the change in fixed assets and work in progress plus depreciation.
- **From the company's own documents:** the AI reads its latest investor presentation and two latest earnings-call transcripts from the exchange, then lays out the business model (segments and their share) and every capex and growth plan (what, how much, by when, status) with the management's own words and a link to the document. Facts only, never advice; kept for a week, and counts toward the daily research AI limit.
- **Management report card:** the AI reads up to six earnings-call transcripts from the last two years for the targets management gave (revenue and profit growth, operating margin, capex, and promises without a number), and each is checked against the reported annual or quarterly results: **met**, **missed**, **not due yet** or **can't check**. A target repeated on later calls counts once, and a later change is shown. Targets stated after the period had ended are ignored.
- **Investor checklist** on every deep dive: fixed, written-down rules with pass, watch or fail and the number behind each: Stage 2 and Supertrend, 3-year sales and profit growth, the latest quarter, return on capital, margin trend, debt to equity, cash from operations against profit, free cash flow, promoter holding and its change over a year, red-flag filings and fund raises, and management's record from the report card.
- **Research → Investor home (Pro):** every India watchlist company on one page with its trend, its sector's place in the rotation, red flags, checklist and report card, the ones that need a look first.
- **Download as slides:** the deep dive as a PowerPoint deck (numbers and charts, business model, plans, report card, checklist and sources).
- **Admin → Check filings feed** now also tries to read one company document from the server.
- **Banks and lenders:** the deep dive, checklist, report card and deck use return on equity and revenue, and leave out capex, free cash flow, operating margin and debt to equity, which don't describe a lender.
- **Industry-aware checks:** the checklist now reads each company's industry and uses the rules that fit it. Insurers and holding companies are judged on return on equity like banks; for power, telecom and infrastructure, real estate and cyclicals (metals, cement, chemicals) the checks their industry would always fail (debt, cash flow, growth through the cycle) show as watch with the reason. The rule set used is shown above the checklist.
- **Industry measures, from the company:** the presentation read now pulls the numbers each industry is judged on, such as revenue per occupied bed and occupancy for hospitals, NIM and NPAs for banks, RevPAR for hotels, ARPU for telecom, EBITDA per tonne for cement and metals, pre-sales for real estate, with the quote and source. They have their own panel and slide. Lenders, insurers and holding companies show P/B instead of P/E in the deck.
- **Call transcripts read more reliably:** each earnings call is now read in its own request, from its passages richest in guidance (legal disclaimers left out); only management's words count, never an analyst's question; "this year" and "next year" are turned into financial years from the call date; every quote must really appear in the document it's credited to, or the item is dropped; and a reply cut off midway keeps what it had. Earlier reads are redone on the next press of the button.
- **Transcripts on the company's website:** many companies file only a one-page letter with a link to the transcript on their own website. That link is now followed (only to a PDF on the company's own site, never another site or a private address). If no call can be read, the report card says why and no AI read is used.
- **Rupee sign fixed:** company PDFs that draw ₹ with an odd font came out as ¥, X or % (for example "¥186,630"); the ₹ is put back.
- **Capex plans:** amounts must carry a unit (₹ crore) and sizes (beds, tonnes, MW) are shown apart, so bare table numbers like "%70" or "2230" no longer appear; the outlook keeps only what management expects, not results already reported; the plans are a list that fits a phone.
- **Promoter holding:** a low stake (below 30%) now fails only when it is also falling; low but steady, as at professionally run companies, shows as watch.
- **Valued the way the industry is:** a "How it's valued" panel and deck tile show EV/EBITDA for hospitals, hotels, telecom, cement, metals, power and airlines; price to book for lenders, insurers, holding companies and developers; P/E for the rest, with P/E always alongside.
- **The exchange's own industry** fills in when the company page has no classification, so fewer companies fall back to the general rules.
- **Industry measures from earnings calls too:** when the presentation leaves out a measure (occupancy, NIM, ARPU…), the latest call transcripts are searched for it.
- **Cover letters skipped:** a filing that attaches only a short cover letter instead of the presentation or transcript is passed over for the next one.

### Real prices for tests
- **Admin → Save real prices for testing** downloads about two years of real daily prices (benchmarks, every sector index, the ready-made groups and a few sectors' stocks). Saved as `stratlab/backend/tests/fixtures/real_prices.json.gz`, it makes the test suite also check the calculations on real market data. Prices only: no user data.

### Sector rotation
- **Research → Rotation (Pro):** every sector against the market as **Leading**, **Weakening**, **Lagging** or **Improving**, with the trail it took (1 to 12 weekly or daily points) and an **Animate** replay. A plain-language summary lists which sectors sit in each quadrant and which moved into Leading.
- **More to compare:** NSE sector indices and NSE size and style indices (Next 50, Midcap 100, Smallcap 100, Momentum 30, Quality 30, Alpha 50…) against the Nifty 500; S&P 500 sectors and US industries (semiconductors, software, biotech, regional banks, defense, gold miners, homebuilders…) against SPY; or any scan group and your watchlist.
- **Stocks → on any sector** shows its biggest stocks against the sector itself, so Leading means beating its own sector.
- Readable with 30+ sectors: India shows the 12 main sectors first; faint trails with the latest move in bold; hover or click one to follow it; names never overlap.

### Filings and red flags
- **Research → Red flags (Pro, India):** what your watchlist companies told the exchange in the last 3 months, red flags first, and whether a fund raise was filed.
- **A Filings and red flags panel on every Indian company page:** the 3-month summary and a year of filings, each linked to the exchange's document.
- Fixed rules label each filing: **red flags** (QIP, preferential or rights issue, warrants, fund raise, promoter pledge, auditor resignation, default, insolvency, regulator or tax action, rating downgrade), **look closer** (other resignations, debt raises) and routine items (results, calls, dividends, orders…).
- **Evening alert:** at 8:30 pm IST, new red flags from your watchlist by phone, Telegram or email.
- **Admin → Check filings feed** tries the exchange feed live from the server.

### Room to grow
- **Options paper trading scales:** every options session now shares one paced stream of broker price requests, so about 100 sessions run at once instead of 2 or 3.
- **Storage stays small:** experiments older than a notebook's newest 10 keep their verdict, stats and chart but only their last 30 trades (the page says so), and recorded option chains older than 120 days are cleared daily (`OPTION_SNAPSHOT_KEEP_DAYS`).

### Polish and clean-up
- **Home:** the investor tools (scan, rotation, red flags) and alerts join the "What you can do here" cards; on a phone the cards sit two to a row.
- **Sidebar:** Markets now folds into one line ("7 of 9 open") and opens with a tap, so Night mode and Tour stay in view on smaller screens. It remembers your choice.
- **Landing page:** a new **For investors** section; the pricing answer lists the Pro investor tools and no longer says everything is unlocked.
- **Plans:** Pro lists the scan, rotation and red flags. **Tour:** a step for the investor tools.
- **Options:** when a leg has no price, the message names it ("No price yet for 23400 CE (buy)"), and after hours it says when the next entry is instead of an old message.
- Removed unused styles and exports.


### Stage 2 + Supertrend (ST S2)
- **Stage indicator:** Weinstein's market stage, 1 to 4, from the 150-day average (about 30 weeks) and its 20-day slope. Use it in any rule: "Stage is 2". The new **is** condition works for any whole-number value.
- **Research → Scan (Pro):** scan your watchlist or a ready-made group. Each stock shows its stage, whether the price is above the Supertrend and for how long, and a signal:
  - **Fresh ST S2:** the Supertrend turned up in the last 5 days while in Stage 2
  - **In ST S2**
  - **Stage 2 only**
- **Backtest ST S2 on this group:** one click makes a notebook with the ready-made ST S2 strategy (buy when in Stage 2 and the price is above the Supertrend; sell when it crosses back below) on the scanned group.
- **Daily ST S2 alert (Pro):** after each close (India 4:05 pm IST, US 4:20 pm New York), a message by phone, Telegram or email lists watchlist stocks that just gave an ST S2 signal. At most once a day, even after a restart.
- The AI builder understands "Stage 2" and "ST S2".
- **Fixed:** starting a notebook with a group of stocks from outside the notebook page lost the group.


### Launch offer, and quieter about data sources
- **Launch offer:** from the Admin page, give every user every Pro feature free for a set number of days (10 by default). Users see a banner with the end date. Payments keep working during it, and each user returns to their own plan by themselves when it ends.
- **Data sources aren't named** in the app, on the site, in error messages or in the docs. Research shows plain labels ("Market data", "Fundamentals") and links only to the company's own website and Wikipedia.
- **Policies:** the contact email is set, and refunds cover duplicate or wrong charges only.
- **Fixed:** reporting a library strategy and the admin's moderation buttons sent their request in the wrong format, so they failed.

### Ready for payments
- **Terms, Privacy, Cancellation and refunds, and Contact pages:** public (no sign-in), linked from the landing page, Plans and Account. The business name, email and address come from `config.js`.
- **Payments switch on safely:** paid features lock only once Razorpay's keys *and* plan IDs are set, so a half-finished setup never locks people out. Plan prices on the Plans page come from the server.
- **Checkout** no longer stays stuck on "Opening checkout…" after paying or after a failed payment. Cancelling now names the date your plan ends, correct for yearly plans too.
- **Report a library strategy** as spam, offensive, misleading or personal. Three reports from different people hide it until the site owner reviews it on the Admin page (restore, hide or delete). Re-publishing doesn't clear reports.
- **Tighter site security:** a full Content-Security-Policy (scripts only from StratLab and Razorpay), no inline scripts, and the old `?key=` admin URLs are gone. The Admin page's login buttons replace them.
- **Faster pages:** a signed-in user's profile is cached for 10 seconds, so paper-trading pages that refresh every 3 seconds don't hit the database each time.
- **Upgraded** to React 19, TypeScript 7 and Sentry 11. Sentry sends no cookies, headers, user details or query strings.

### Production hardening
- **Request limits:** API requests are capped at 8 MB and rate-limited per user and per address, generously enough that normal use never notices. Test alerts and test notifications are limited to 5 an hour.
- **Phone notifications** only accept the browsers' own push services (Google, Apple, Mozilla, Microsoft).
- **Alert contacts are checked:** an email or Telegram chat ID that doesn't look right is refused with a clear message.
- **Admin access** needs a verified email as well as being on the admin list.
- **Less on show publicly:** the health check no longer lists AI providers or their errors. Only the admin's connection check tests each AI provider, so the free AI allowance isn't spent by other users' checks.
- **Links from news feeds** open only if they're ordinary web links.
- **Security headers** on the site and the API: no framing by other sites, no content sniffing, a strict referrer policy and HSTS.
- **Tidier on phones:** bigger tap areas for chip ✕ and "Add a rule" buttons; the Themes box and button line up; the admin user table no longer runs into the note below it.
- **Faster first load:** the Options page loads in its own chunk again.

### Commodities, Indian and global, kept apart
- **Indian commodities (MCX):** a new market through the same broker login as Indian stocks.
  - Gold, silver, crude oil and natural gas (with their mini contracts), plus copper, zinc, aluminium and lead futures.
  - Priced in rupees and traded in whole lots, with CTT, MCX fees, stamp duty and GST.
  - Years of daily history, stitched across expiries.
  - Hours 9:00 am to 11:30 pm IST.
- **Global commodities:** a separate market with COMEX, NYMEX, CBOT and ICE futures in dollars, sized per ounce or barrel, with a spread and commission estimate.
  - Gold, silver, platinum, copper, WTI and Brent crude, natural gas, corn, wheat, soybeans, coffee, sugar, cocoa and cotton.
  - Trades Sunday evening to Friday, New York time.
- **Ready-made groups:** MCX mini contracts, MCX main contracts, 14 global commodities, and global metals and energy.
- **Skipped entries are explained:** if a signal is skipped because one lot costs more than your capital allows, the verdict says so and how to fix it.

### Alerts that don't trip over missing setup
- The Account page only offers the channels the server can use. Email appears once SMTP is set up, and Telegram once a bot token is.
- **Send a test** reports each channel on its own, so one failing channel no longer hides the others that worked.
- The daily report only counts channels that can actually deliver.

### Calmer everywhere
- **Account:** one column: Plan, Alerts (what to send, then where), On your phone, Experience, Connection check.
- **Picking a market:** compact tiles, with the chosen market's details on one line underneath.
- **Landing page:** now covers Ask or do anything, the strategy library, the phone app, rewriting rules in words, and exchange holidays.

### Simpler to read, just as powerful
- **The rules are edited in blocks: Entry, Exit, Size.**
  - Every rule has a visible × to remove it, and each list has its own **+ Add** button.
  - **Edit in words** rewrites the whole strategy from a sentence. Your market and capital stay.
- **Detailed settings stay folded away:** trailing stops, time limits, intraday limits, costs and sizing sit in **More settings**. It shows how many are switched on (for example "2 on") and stays open once you've opened it.
- **Options is three steps:** what to trade, the structure, then when and how much risk. Re-centring, trailing, caps, sizing and costs are under **More settings**.
- **"I trade actively" no longer opens everything at once.**

### Ask or do anything
- The search box now does things instead of just finding them. Type a line and press Enter:
  - **"Test: buy NIFTY when RSI drops below 30…"** builds the rules, saves a notebook, runs the test and opens the verdict
  - **"Paper trade a 20/50 EMA cross on Bitcoin"** builds it and starts paper trading
  - **"Research HDFC Bank"** opens its research page
  - **"What is a walk-forward test?"** answers right in the box
  - **"Momentum ideas for bank stocks"** gives ideas you can test in one click
- Each step shows as it happens. If something can't be done (say, your plan's session limit), the reason shows in the box.
- It's in the sidebar as **Ask or do anything**, and as a big bar on your notebooks page (Ctrl+K or ⌘K anywhere). When the AI is unavailable, simple word rules decide what to do.

### Tidier navigation
- **Sidebar:** Research sits under the search box, then All notebooks, Paper trading, Options, Import a strategy, Strategy library and Account. Plans now lives inside Account.
- **Markets now:** it says "weekend" for every exchange that's shut for the weekend, and "holiday" on exchange holidays.
- **Group testing:** "Test on a whole group" works before you have a notebook.
- **Import:** it's a button at the top of New notebook.

### Weekends, holidays and overnight
- **Exchange holidays are known now**, for India (NSE/BSE), the US, UK, Europe and Japan:
  - **Markets now** in the sidebar says **weekend** or **holiday**, and "opens in" skips closed days.
  - The free trial's 5 market days no longer count holidays.
  - The daily report isn't sent on a holiday, and option chains aren't recorded on one.
- **No more "offline" at midnight:** a day's broker login is used until the 6 am token reset, so Indian data stays up overnight.
- **A clearer banner** when Indian data is offline:
  - on a weekend or holiday it says the market is closed and when data reconnects
  - before the morning login it says what time data comes back
  - only a failed login still points you to the connection check

### StratLab on your phone
- **Install it:** StratLab can go on your home screen like an app, with its own icon and no browser bars. Long-press the icon for shortcuts to Test an idea, Paper trading and the Strategy library. On Android or a computer, use **Account → On your phone → Install StratLab** (or the browser's Install app). On an iPhone, tap Share → Add to Home Screen.
- **Notifications without Telegram:** **Turn on notifications** on any device (an iPhone once it's installed) to get each paper trade and the daily report as a phone notification. Tapping one opens the session. **Send a test** checks it works, and each device can be turned off on its own.
- If you lose signal, the app still opens and reconnects when you're back online.

### All your paper trading at once
- The top of **Paper trading** now shows every running session added up, per currency (rupees and dollars are never mixed):
  - what the open positions are worth now, and how much of your paper capital that is
  - today's result, and the result since the start
  - the worst day and the deepest fall for all of them together, which is what you'd feel if this were one account
- A combined P&L chart and a table show each session's share. Tap a row to open that session.

### The strategy library
- **Browse:** a new **Strategy library** in the sidebar lists strategies other traders published, each with the verdict it earned. "Probably luck" is shown as plainly as "Likely a real edge". Filter by market or verdict, search, and sort by best verdict, newest or most copied.
- **Copy and re-test:** puts the rules in a notebook of your own, so you judge them on your own run.
- **Publish:** from any verdict, **Share verdict → Publish to the strategy library**. Add a line on the idea and, if you like, a display name. Your email and notes are never shown, and you can update or take it down any time.
- **Not included:** strategies tested on uploaded data can't be published, because nobody else could re-test them.

### Your experience, your defaults
- After the first sign-in StratLab asks once how much trading you've done: **New to trading**, **I've traded a bit** or **I trade actively**.
- It only changes defaults:
  - Newcomers see the tour and a simpler "What you can do here", without the advanced tools.
  - Active traders get the costs and sizing, and the Options "More settings", open from the start.
- Every tool stays available whatever you pick, including through search. Change it any time under **Account → Experience**.

### Search or ask anything
- **One box for everything:** at the top of the sidebar, the magnifier on phones, or **Ctrl+K** (⌘K) anywhere. It takes:
  - a stock or coin → its research page, or straight to testing an idea on it
  - an idea in plain words → a new notebook with the rules built
  - a question ("momentum ideas for bank stocks") → 4 testable ideas, each one click from a verdict
  - a feature's name ("walk forward", "iron condor", "alerts") → straight there
  - a pasted Pine Script, Python or config file → Import, already filled in
- **"What you can do here":** the home page and the new-notebook page now show every major tool, one tap each, so groups, options on a signal, import and research aren't hidden.
- **A verdict's Next bar** now offers **Test on a group** and, for Indian instruments, **Trade it with options**, which opens Options with that notebook's rules as the signal.

### New plans
- **Prices:** Basic is now **₹999 a month** and Pro **₹2,999 a month**. Yearly billing gives two months free (₹9,990 and ₹29,990).
- **Free:** 5 experiments and 10 AI builds a month, group tests of up to 10 instruments, and 5 market days of paper trading.
- **Basic** adds:
  - 50 experiments and 100 AI builds a month
  - groups of up to 25 instruments
  - 2 paper trading sessions at a time
  - group paper trading
  - options at set times
  - the daily report
- **Pro** adds:
  - unlimited experiments and AI builds
  - groups of up to 50 instruments
  - 10 sessions at a time
  - options on a notebook's signal
  - faster group entries and the spread limit
  - alerts for every trade
  - every indicator, Indian F&O, and export
- **Enforced on the server:** each feature is checked by the server. After a downgrade, a session the new plan doesn't cover is stopped with a clear reason.
- **Early access:** everything stays unlocked until payments go live.

### Faster group entries and a spread limit
- Pressing **Paper trade** on a group now opens a short set of options before it starts:
  - **Faster entries** (India): the entry rules are checked on the live price every 15 seconds, so a momentum signal on hourly candles doesn't wait up to an hour for the candle to close. Exits still wait for the close.
  - **Spread limit** (India): skip an entry when the gap between the best bid and ask is wider than a % of the price, so thin stocks don't eat the edge.
  - **Minimum price** (any market): skip anything cheaper.
- The session page shows which options are on, how many entries were skipped and why, and each member's live spread.

### Options on your own signal
- **Setup:** on the Options tab, set **Enter** to **When a notebook's rules say so** and pick a notebook with rules on 5-minute, 15-minute or hourly candles, for example a 7 EMA crossover.
- **How it trades:**
  - The rules run on the underlying's own candles, the same ones a backtest uses.
  - When they go long, the session enters your structure. Buying the at-the-money call is the default.
  - When they go short, it can enter the mirror (calls and puts swapped, so it buys the put), or stay out.
  - When the rules exit or flip, the options are closed.
- **Limits:** your stop, target and square-off still apply, and a stopped trade isn't re-entered until the rules give a new signal.
- **The session page** shows what the rules are doing: long, short or flat, and their last candle.

### Recording option chains for options backtesting
- The broker keeps no prices for expired options, so StratLab now records its own.
- **What:** every 5 minutes in market hours it saves the NIFTY, BANKNIFTY and SENSEX chains (current and next expiry, 15 strikes either side of the money): bid, ask, last price and open interest for each call and put, plus the spot price. That's about 1 MB a day.
- **Settings:** choose the underlyings and how often with `OPTION_SNAPSHOTS` and `OPTION_SNAPSHOT_MINUTES`.
- **Status:** the Admin page shows what was saved today.
- **One setup step:** run `supabase/schema.sql` again to add the `option_snapshots` table.

### A longer free trial, a daily report, and error alerts
- **Free trial:** the free plan's paper trading trial now lasts **5 market days** (Monday to Friday, counted from the day you start) instead of 24 hours. Starting on a weekend doesn't use any of it.
- **Daily report:**
  - People with alerts on get a short Telegram or email report a few minutes after each market closes.
  - For each paper trading session in that market it lists the trades closed that day and their profit or loss, what's still open, and the result since the start.
  - You can turn it off under **Account → Trade alerts**.
- **Fixed: trade alerts never arrived** for anyone without a paid Pro plan. While payments aren't live, everyone can switch alerts on, but they were only ever sent to paid Pro accounts.
- **Error alerts (optional):**
  - Set a Sentry DSN and every server error goes to Sentry with the same ref code users see.
  - So do errors in the paper trading loop, failed broker auto-logins and, if you add the DSN to the frontend config, errors in people's browsers.

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
  - How to run StratLab next to your own bots on the same broker account: a separate API app, and a different login time.
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

### Broker login reliability
- If the broker rejects the automatic login's 2FA code, it now tries once more with the next code. The usual cause is another program using the same code on the account moments earlier. A rejected password still stops for the day, so the account can't get locked.
- If the broker cancels today's token mid-day, StratLab now notices. That usually happens when another login to the same API app replaces it. Indian data goes offline with a clear message instead of failing every request, the admin page says what happened, and a Telegram alert goes out. It doesn't log in again by itself, which would cancel the other program's token in turn.
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
- **Research a company** (India and US): live price and chart, where it sits in its 52-week range, key numbers with an industry-range dot, sales and profit by year, quarterly results, results against estimates, analyst ratings, insider trades, shareholding, automatic strengths and concerns, news, and what the company does.
- An **AI read** on every company: scores, valuation, bull and bear cases, segments, what to watch, and three **ideas to test** that open as a notebook with the market, company and rules filled in.
- **Themes** (AI map of a sector with a ranked shortlist), **Market pulse** (index levels, headlines and the day's mood), **Compare** two companies with an AI verdict, and a **Watchlist** saved to your account.
- **US, UK, European and Japanese stocks and ETFs, and forex** are now live for backtests and paper trading, with UK stamp duty and forex spread in the costs.
- Two more free AI providers (SambaNova, Mistral) join the chain; research answers are cached and shared.
- Fixed: backtests on markets with daylight saving time.

### Admin page
- An **Admin** page for the site owner (set by `ADMIN_EMAILS`): server and broker data status, a broker login button, live AI test, user list with usage, plan grants by hand, and running paper sessions with a Stop button.

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
- Global markets: India, crypto and any market through a CSV upload.
- A new React and TypeScript frontend with charts drawn as SVG, in light and night modes.

### Foundations
- Automatic daily broker login (optional) with safe retries, and a self-restart for the price feed.
- Paid plans show "Coming soon" until Razorpay is connected.
- Fixes to billing, alerts, the live loop and data handling, with a pytest suite and CI.
- Proprietary license.
