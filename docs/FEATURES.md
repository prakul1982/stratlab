# What StratLab does, and where to find it

[← Back to the project overview](../README.md)

Everything that ships today, grouped the way the landing page groups it. Plan limits are in the
[README's plans table](../README.md#plans) and in [`plans.py`](../stratlab/backend/app/plans.py), which is the only
place they are set.

StratLab reports facts: reported numbers, exchange filings, prices and how a set of rules would have done in the past.
It never says buy, sell or hold, gives no price targets, ratings or scores, and never ranks companies as better or
worse. Public pages, emails and the app never name where market data comes from.

## Getting around

| You want to… | Where it is |
| --- | --- |
| Get started | New accounts see a **first steps** checklist on Home: run a backtest, add to the watchlist, open a deep dive, start paper trading, set up newsletters or alerts. Each step ticks itself when you really do it; the list goes once it's done, dismissed or the account is a month old |
| Take the tour | A short tour opens the first time you sign in; **Tour** at the bottom of the sidebar reopens it |
| Ask or do anything | **Ask** at the top of the sidebar or Home, or **Ctrl+K** (⌘K). "deep dive Apollo Hospitals", "which sectors are leading?", "red flags in my watchlist", "compare TCS and Infosys" open the right page; "Test: buy NIFTY when RSI drops below 30" builds the rules and runs the test; "what is walk-forward?" is answered in place. Pasting a strategy imports it |
| See which markets are open | **Markets now** at the bottom of the sidebar: how many are open, each one's next open or close, and **weekend** or **holiday** when an exchange is shut |
| Put investing or trading first | **Account → What you're here for** (asked once at sign-up). It orders the menu, Home and the examples; nothing is hidden |
| Read at night | **Night mode** at the bottom of the sidebar |
| Put it on your phone | **Account → On your phone**: install to the home screen and turn on notifications |

## Research

| You want to… | Where it is |
| --- | --- |
| Look up a company | **Investing → Companies**, or search. India (NSE, and BSE-only companies) and the US: price and chart, key numbers, results against estimates, who owns it, news, and an AI read whose facts are plain numbers (growth, price trend, debt and cash, margins and returns) and whose ideas open as a notebook in one click |
| Read a company's facts without signing in | The public pages at `stratlab.studio/stocks/in/SYMBOL` and `/stocks/us/SYMBOL`, built for search engines and listed in the sitemaps |
| Understand the business and its plans | **Deep dive** on any company page: ten years of sales, profit, margins, capex and free cash flow, the last twelve quarters, then the business model and capex and growth plans read from the company's own presentations and call transcripts (India) or 10-K and earnings releases (US). Every quote is checked against its document. Pick how far back to read, from the last year to the last 5 years |
| Measure it the way its industry is measured | In the deep dive: industry measures (occupancy for hospitals, NIM and NPAs for banks, RevPAR for hotels, EBITDA per tonne for cement), and valuation on EV/EBITDA, price to book or P/E, whichever its industry uses |
| See whether management delivered | **Check past calls** (US: **Check past releases**) in the deep dive builds the **management report card**: each stated target against the reported result, met, missed or not due yet, with the quote and source |
| Run fixed checks | The **investor checklist** in the deep dive: pass, watch or fail on trend, growth, returns, margins, debt, cash conversion, promoter or insider activity, filings and the report card, adjusted to the industry, with the number behind each |
| Take it away as slides | **Slides (PowerPoint)** or **Slides (PDF)** in the deep dive |
| Know when companies report | **Research → Results**: Indian results board meetings and US results dates, from a week back to four weeks ahead |
| Know when dividends, bonuses and splits go ex | **Research → Corporate actions**: dividends, bonus issues, splits, consolidations, buybacks, rights issues and demergers by ex-date and record date, for your stocks or every company, India or US. Each company page has a panel of those ahead and the last three years' |
| See who traded a company's shares | **Deals and insider trades** on any Indian company page and deep dive: promoters', directors' and key staff's trades and pledges, substantial acquisitions, and bulk and block deals, as filed |
| Check exchange surveillance | Badges on Indian company pages, search results, screens, holdings and paper trading: long- and short-term ASM with the stage, GSM stage, ESM, trade-to-trade (BE/BZ), price-band changes and the F&O ban, each with an (i) saying what the measure does and the list's date |
| Check filings for red flags | **Investing → Red flags** for the India watchlist, or **Filings and red flags** on any Indian company page: fund raises, promoter pledges, auditor and director resignations, defaults, regulator action and rating downgrades, each linked to the filing |
| Filter companies by plain facts | **Research → Screens**: sector, size, 3-year revenue growth, margins, debt to equity, ROE and ROCE, dividend yield, P/E, Stage, distance from the 52-week high, red-flag filings, promoter or insider buying and surveillance. **Save this screen** keeps it and emails new matches on Saturday morning |
| Find Stage 2 stocks with the Supertrend up | **Investing → Stage 2 trend scan** on your watchlist or a ready-made group; **Backtest ST S2 on this group** makes a notebook in one click |
| See which sectors are leading | **Investing → Sector rotation**: sectors, size and style indices or US industries as Leading, Weakening, Lagging or Improving, with a trail and **Animate**; **Stocks →** shows a sector's biggest stocks against it |
| Keep a watchlist | **Watch** on a company page; **Investing → Watchlist**, and **Watchlist at a glance** for trend, rotation, red flags, checklist and report card per company |
| Explore a theme or the market's mood | **Research → Themes** and **Research → Market pulse**; **Research → Compare** for two companies side by side |
| Read past newsletters | **News** |
| Share a company's facts | **Share** on a company page or deep dive: a card with price, 1-year range and key numbers, and a link that previews as the card on WhatsApp, X and LinkedIn and opens the public page |
| Know how fresh the numbers are | Every page with company numbers says when its prices and numbers are from |

## Portfolio and tax

| You want to… | Where it is |
| --- | --- |
| See your own portfolio | **Investing → My Holdings**: import the holdings file from Zerodha, Groww, Upstox, Angel One, ICICI Direct or HDFC Securities (CSV, Excel or the broker's HTML `.xls`), or any file with a column for the stock (symbol, ISIN or name) and one for the quantity, or type them in. Value, gain or loss, sector mix, and each stock's trend, filings, results date and surveillance flags. Seen only by you; **Delete** removes everything |
| Track dividends and corporate actions on what you hold | In **My Holdings**: dividends with an ex-date ahead and those of the last 12 months (estimated), and a bonus or split since the holdings were saved, offered as **Apply** or **Already in my file**, with **Undo** |
| Estimate capital gains | **Tax report**: upload tradebooks, tax P&L files, or the broker's ZIP of tax P&L files (up to 10 MB a file). Buys and sales are matched first in, first out per company (a tax P&L line keeps the buy the broker matched it with); short and long term at the rates for the sale date (the 23 July 2024 change included); the long-term exemption per financial year; 2018 grandfathering; intraday shown apart; set-off rules applied. Open lots below cost are listed with how long each is held. **Download CSV** and **Download PDF summary** keep a copy. An estimate to check with a CA, not tax advice |
| Invite a friend | **Account → Invite friends**: your link, who joined and the free months earned. When a friend uses the app on 3 different days in their first 14, you both get a month of Basic (up to 12 for the one inviting). Paying users bank the month for later |

## Strategy testing

| You want to… | Where it is |
| --- | --- |
| Test a new idea | **New notebook**: pick the market, then describe the idea in plain words or start from a classic one |
| Bring a strategy you already have | **Import a strategy**: a StratLab export, a config file, TradingView Pine Script, Python, MetaTrader, AmiBroker or plain words. It sets up a notebook, a group notebook or an Options structure and lists anything it couldn't carry over |
| Tweak a rule | Tap any highlighted word in **The rules**; **×** removes a rule, **+ Add** adds one, **Edit in words** rebuilds them |
| Short, trade both ways, or trade intraday | Tap **Buy** at the start of the rules; pick 5- or 15-minute or hourly candles for the **During the day** line (entry window, square-off, trades a day, cooldown, daily loss cap) |
| Fine-tune | **More settings** under the rules: trailing stop, time limit, costs, sizing, weighted entry scores, higher timeframes, values N candles ago |
| Run a test | **Run experiment** (Ctrl/⌘ + Enter). Each run is saved, numbered and ends in a verdict backed by four checks: unseen data, nearby settings, bad-luck drawdown and enough trades |
| Check a tuned idea without hindsight | **Walk-forward test** on a verdict |
| Check it isn't one lucky chart | **Does it work on similar stocks?** on a verdict |
| Compare two runs | **Compare experiments →** in a notebook |
| Test on a whole group | **Testing on → Or test on a group**: NIFTY 50, Bank NIFTY, F&O stocks, US mega caps, large coins or your own list, with one pot of capital |
| Paper trade | **Paper trade** on a notebook or verdict; **Paper trading** shows every session and what's at stake across them, per currency |
| Paper trade options | **Options**: underlying, expiry and structure (up to eight legs), **Price it now**, then **Start paper trading**; enter at a set time or when a notebook's rules signal |
| Borrow or publish a strategy | **Strategy library**: rules published with their verdict, luck included; **Copy and re-test** |
| Share a verdict | **Share verdict**: a card with the chart and the four checks, or a public link that never shows your rules |
| Save the rules | **Export** in a notebook (Pro) |

Markets: India (NSE and BSE stocks, indices and F&O), Indian currency futures, Indian commodities (MCX), crypto, the
US, UK, Europe, Japan, forex, global commodities, and any CSV of candles. Each uses its own hours, currency,
holidays, fees and taxes.

## Alerts and email

| You want to… | Where it is |
| --- | --- |
| Get told when a stock does something | **Set alert** on a company page, the deep dive or the watchlist: a price level, a day's move, crossing a moving average, an RSI level, a Stage change, a new 52-week high or low, and for Indian stocks new insider trades, deals or surveillance changes. All are on **Investing → Alerts** |
| Hear about results and corporate actions | Results-day and results-out messages for companies you follow; a message when one announces a dividend, bonus or split, and the evening before its ex-date |
| Hear about red flags and scans | The evening red-flag alert for the watchlist and the daily Stage 2 scan alert (Basic and Pro) |
| Get every paper trade | Turn on alerts in **Account**: each trade as it happens and a short report after each market closes (Basic and Pro) |
| Get the market and your stocks by email | **Account → Newsletters**: the Market Brief (India or US) and My Stocks, daily (Basic and Pro) or weekly (everyone) |
| Choose where alerts arrive | **Account**: phone notifications, Telegram, or email to an address confirmed from a link. **Account → Emails from StratLab** for tips and reminders. Every email has a one-click unsubscribe |

## Account and billing

| You want to… | Where it is |
| --- | --- |
| See your plan, usage or upgrade | **Account → Plan and usage** and **Plans** |
| Get a GST invoice | **Account → Invoices**: every payment's invoice, and the name, address and GSTIN for future ones |
| Check the connections | **Account → Connection check**: market data and each AI provider |
