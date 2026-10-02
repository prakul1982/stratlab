# Changelog

## October 2026

### Built around what you came for
- **One question at the start: investing, trading or both.** It sets what the menu, the home page and the examples show first; nothing is hidden, and it can be changed on the Account page. People who already answered the experience question are asked this once.
- **An investor home page:** "Which company do you want to look into?" with the company search, popular names, and four starting questions (leading sectors, Stage 2 stocks in NIFTY 50, red flags, the watchlist at a glance). Notebooks move to their own page for investors.
- **The investing tools are in the menu:** Companies, Investor home, Stage 2 scan, Sector rotation, Red flags and Watchlist each one tap away, under Investing; the trading tools under Trading. Whichever you came for is on top, and the main button follows it (Look up a company / New notebook).
- **The home page is grouped by goal** (find stocks, understand a company, test an idea, trade with fake money) instead of a wall of equal cards.
- **Search understands investor questions:** "deep dive Apollo Hospitals", "which sectors are leading?", "red flags in my watchlist", "Stage 2 stocks in NIFTY 50" and "compare TCS and Infosys" open the right page directly.
- **Placeholders show real examples,** rotating every few seconds and matched to what you came for, instead of "Search…".
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
