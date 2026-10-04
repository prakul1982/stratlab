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
EURINR, GBPINR and JPYINR, are built (see the README).

Still to do:
- Options on the cross pairs (rarely traded).

### International payments
Prices in 18 currencies, following the rupee price at the day's exchange rate, and a GST invoice for every payment
(domestic, and exports under the LUT) are built.

Still to do:
- Set the final prices per country, and create the Razorpay plans for the currencies that should be charged locally.
  Until then those visitors are charged the rupee price and their card converts it.

### Checking everything StratLab offers
The goal: nobody needs to open another site to check something StratLab already covers. The tests on every change, the
daily **Check every feature**, the whole-market audit and the load test are in place (see "Tests" in the README).
Still open:
- **Every feature on real data at scale:** the AI reads (business model, plans, industry measures, report card) on
  the Nifty 500 and every industry, not just a few names; options on every underlying.
- **Compare against the source of truth:** costs against a broker's contract note, and filings against the exchange's
  page. Log every mismatch.
- **Data audits after each big change:** the daily check covers every feature, but the company data audit still runs
  only when started from Admin.
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
  releases only, and there is no filings-and-red-flags feed for US companies.

## Done recently
Moved here from the plan above; details in the [changelog](../CHANGELOG.md).

- **Three spaces:** Trade, Invest and Money, each with its own menu and home page, and a switcher at the top of the
  menu.
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
- **Checks:** the whole-market audit (India NSE and BSE-only, US SEC) checks new listings daily; **Check every
  feature** runs by itself at 4:50 pm IST, retries failures and emails the admins; a security sweep; a load test (about
  150 requests a second on one server process); browser tests on desktop and phone; every pull request waits for
  the owner's approval before it merges.
- **Admin** in tabs: Overview with **Needs your attention**, Services, Data checks, Users and Billing.

## Waiting on the owner
Things only the account owner can do:
- Backups: the secrets are set and the nightly backup runs (first copy 4 Oct 2026); do one test restore some time
  ([ADMIN.md → Backups](ADMIN.md#backups)).
- Storage: add the second database (`MARKET_DATABASE_URL`) when Admin → Data checks → Storage nears its limit.
- Vercel Pro before taking real payments.
- The launch offer (Admin → launch offer) when ready.
- Invoices: fill the seller's details in Admin → Invoices, file the yearly LUT on the GST portal, and have the
  accountant confirm the setup.
- Email: add `BREVO_API_KEY` (or `RESEND_API_KEY`) in Railway, then **Send a test email** from Admin → Services. A
  sending domain must be verified with that service before mail reaches anyone but the account's own address. Set
  `PUBLIC_API_URL` if the backend's public address isn't the Railway domain, so newsletter unsubscribe and confirm
  links work.
- Open one downloaded deck in PowerPoint, and the PDF, to check their look.
- Update the GitHub repository's About text to mention investing and US companies.
