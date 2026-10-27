# Roadmap

What's planned next and what's known to be imperfect. The aim is one place an investor can trust for a company, so
precision comes before breadth: every number from a filing, every claim tied to a quote, and a clear note when
something couldn't be read.

## Planned

### Options backtesting
Options are paper traded live today. Backtesting them needs real past prices for every strike, which nobody keeps for
expired options, and StratLab won't stand in a pricing model. So it records the NIFTY, BANKNIFTY, FINNIFTY,
MIDCPNIFTY and SENSEX option chains every 5 minutes (the Positioning page's chain history is read from the same
recordings). Backtesting opens once enough of that history has built up.

### Indian currency derivatives (CDS)
Futures on USDINR, EURINR, GBPINR, JPYINR and the cross pairs EURUSD, GBPUSD and USDJPY, and options on USDINR,
EURINR, GBPINR and JPYINR, are built (futures are a market of their own; the options are in the Options builder).

Still to do:
- Options on the cross pairs (rarely traded).

### International payments
Prices in 18 currencies (each with its own fixed price, set from the rupee price on 24 October 2026 and changeable in
Admin → Money → Prices) and a GST invoice for every payment (domestic, and exports under the LUT) are built.

Still to do:
- Create the Razorpay plans for the currencies that should be charged locally. Until then those visitors are charged
  the rupee price and their card converts it.

### Checking everything StratLab offers
The goal: nobody needs to open another site to check something StratLab already covers. The tests on every change, the
daily **Check every feature**, the whole-market audit and the load test are in place (see "Tests" in the README).
Still open:
- **Every feature on real data at scale:** the AI reads (business model, plans, industry measures, report card) on
  the Nifty 500 and every industry, not just a few names; options on every underlying.
- **Compare against the source of truth:** costs against a broker's contract note, and filings against the exchange's
  page. Log every mismatch.
- **Data audits after each big change:** the daily check covers every feature, and the whole-market audit checks every
  company monthly and every new listing for its first 10 days, but the company data audit by set (a group, a sector, an
  index) still runs only when started from Admin.
- **Gaps list:** anything a user would still have to look up elsewhere becomes a roadmap item here.

## Precision: known gaps
Found while checking live companies. Each shows a note on the page today instead of a wrong number.

- **Audio- or video-only calls:** no transcript to read.
- **Investor sites built entirely in JavaScript:** when a filing has no link, the company's own pages are searched
  for the document; sites that draw everything with JavaScript show nothing to read.
- **EV/EBITDA cash:** when the balance sheet's Other Assets breakdown can't be read, cash isn't subtracted, and the
  note says so.
- **Industry measures** (occupancy, NIM, ARPU and the rest) depend on the company stating them in its presentations,
  calls or, for US companies, its 10-K and earnings releases.
- **US companies:** no call transcripts are filed with the SEC, so the report card reads targets from earnings
  releases only. Red flags cover the S&P 500's 8-K items (bankruptcy, delisting or a listing notice, a change of auditor,
  earlier statements not to be relied on, director or officer changes), not every US filer or every kind of filing.
- **The strategy library's own strategies** are a handful per market (three groups each outside India and the US), so a
  market's page is a sample of how the checks come out there, not a survey.
- **Briefs** are written once, after each market's close (India 4:15 PM IST, US 4:50 PM New York time); there is no
  morning or intraday brief, and the My stocks brief is written only on a day something changed for your stocks.
- **Zerodha for every user** is built and switched off until Zerodha approves a multi-user app; until then only the
  admins can connect it, and everyone else uploads the holdings file or uses the statement inbox.

## Done recently
Moved here from the plan above; details in the [changelog](../CHANGELOG.md).

- **Strategy library for every market:** StratLab's own entries now cover all ten markets the backtester reads, with one
  calm card face, a market filter that lists only markets that have samples, and a start-up run that seeds only what is
  missing.
- **Delete my account:** Account, Your data erases every store and the sign-in account; invoices are kept as tax law asks.
- **Mutual funds page:** one list of schemes with each scheme's details folded under its row, in place of four tables.
- **The UI checker:** 25 layout rules measured on every page at three widths, run in CI in strict mode
  ([UI_CHECKER.md](UI_CHECKER.md)), and the layout problems the visual review and the checker found fixed across My space,
  the homes, notebooks, Positioning, the F&O desk, Paper, Find stocks, Market view, Money and Plans.
- **Notebook and Positioning layout:** Lab notes as a tab on the bottom edge, one column like every page, and Positioning's
  cards spread across the page.
- **IPO tracking:** one row per issue across both exchanges' lists, withdrawn issues apart, drafts not yet listed
  flagged for a check in Admin, and a daily completeness check against the exchanges' and SEBI's lists.
- **IPOs** for India and the US: lists in stages, each issue's page with bids by category, its offer document's facts
  and its trading since listing, a quote-checked summary and alerts on Basic, and a daily check of the lists against the
  exchanges' and regulators' own.
- **Trade tools:** a forward test from TradingView or Chartink alerts, chart replay, the closing auction and paper
  trading that follows it, a market events calendar, stock futures, strikes picked by delta or premium and an India VIX
  filter for options sessions.
- **Invest tools:** stock lending fees, margin funding, business updates read into numbers and named holders above 1%.
  **Money tools:** a SIP test, fixed-income rates after tax, a floating-rate loan check and what your timing cost
  against each fund's.
- **My space, Connected accounts and the AI assistant:** a home of your own with pinned pages, a statement inbox, a
  Zerodha and an Interactive Brokers connection, EPF, NPS and AIS uploads, and keys that let Claude or ChatGPT read your
  StratLab and place paper orders (Pro).
- **US stocks tax** takes a realised-gains report such as Vested's yearly one; **Net worth** has an add button and
  one-tap chips.
- **Running it:** memory kept in check (heavy background jobs take turns, the caches share one budget, `/admin/memory`),
  Admin's **View as** a plan, and a page per job in **Data and jobs** with a Run now.
- **Charts:** StratLab's own price chart (candles, Heikin-Ashi, bars, indicators, drawings kept on the account,
  compare) on company pages, experiments and paper sessions, and one shared chart system for every other chart.
- **Options:** Greeks, the payoff today beside the one at expiry, what-if sliders and a roll preview, and breakevens
  and the most it can make or lose after charges. **F&O changes:** exits, lot sizes and expiry days in one dated list.
- **Invest:** ETF price against NAV. **Money:** what each fund costs in rupees.
- **AI that heals itself:** models measured and ranked per provider, failing ones paused, more free providers, and an
  admin AI panel.
- **Spaces:** Trade, Invest and Money, each with its own menu and home page, and My space, with a switcher at the top
  of the menu.
- **Money:** net worth with loans and policies, mutual funds from the CAS, tax tools (dividends, advance tax, the
  long-term exemption), the year's total tax estimate, US stocks in Indian tax, an ITR-ready export, a money calendar
  with a private feed, and ETFs, REITs, InvITs, gold bonds and US stocks in My Holdings.
- **Trade:** derivatives positioning (participants, FII/DII flows, PCR, max pain, OI by strike, ATM IV) and a journal of
  real trades judged by the verdict's checks. **Invest:** market breadth by group and sector.
- **Running it:** a storage panel with an optional second database for market data, a nightly encrypted database
  backup, a daily watch of the official sources for rates and rules, and the whole-market audit's monthly full check.
- **US company deep dive** from the SEC's filings: ten years of numbers, the AI read of the 10-K and earnings
  releases, the management report card from earnings releases in the company's own fiscal year, and insiders'
  open-market buying and selling in the checklist instead of promoter holding.
- **Indian documents:** letters with no link (or a dead one) are matched to a PDF on the company's own investor
  pages; scanned PDFs are read by OCR; cash is subtracted in EV/EBITDA.
- **BSE-only companies** work like NSE ones: search, company page, charts, backtests, groups and paper trading;
  filings and red flags from BSE's feed; deep dive documents, report card and slides.
- **Deep dive:** a look-back of 1 to 5 years for the document read and the report card; targets the numbers can't
  settle are settled from what the company said later; slides as PowerPoint and PDF; large amounts in $ billion or
  ₹ lakh crore.
- **Checks:** the whole-market audit (India NSE and BSE-only, US SEC) checks every company monthly and each new listing
  for its first 10 days; **Check every feature** runs by itself at 4:50 pm IST, retries failures and emails the admins; a security sweep; a load test (about
  150 requests a second on one server process); browser tests on desktop and phone; Claude's pull requests merge
  themselves when every check passes.
- **Admin** in seven sections: Overview with **Needs your attention**, Users and growth, Money, Data and jobs, Quality,
  System and Email previews.

## Waiting on the owner
Things only the account owner can do:
- Backups: the secrets are set and the nightly backup runs (first copy 4 Oct 2026); do one test restore some time
  ([ADMIN.md → Backups](ADMIN.md#backups)).
- Storage: add the second database (`MARKET_DATABASE_URL`) when Admin → Data and jobs → Storage nears its limit.
- Vercel Pro before taking real payments.
- The launch offer (Admin → Users and growth → Launch offer) when ready.
- Invoices: fill the seller's details in Admin → Money → Invoice details, file the yearly LUT on the GST portal, and have the
  accountant confirm the setup.
- Email: add `BREVO_API_KEY` (or `RESEND_API_KEY`) in Railway, then **Send a test email** from Admin → System. A
  sending domain must be verified with that service before mail reaches anyone but the account's own address. Set
  `PUBLIC_API_URL` if the backend's public address isn't the Railway domain, so newsletter unsubscribe and confirm
  links work.
- Connect once: set `CONNECT_SECRET_KEY` and the statement inbox's `INBOUND_*` settings (and ask Zerodha to approve a
  multi-user app, then set `KITE_MULTIUSER_APPROVED`), as in [ADMIN.md → Connect once](ADMIN.md#connect-once-settings--connected-accounts).
- Open one downloaded deck in PowerPoint, and the PDF, to check their look.
- Update the GitHub repository's About text to mention investing and US companies.
