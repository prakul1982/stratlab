# Roadmap

What's planned next and what's known to be imperfect. The aim is one place an investor can trust for a company, so
precision comes before breadth: every number from a filing, every claim tied to a quote, and a clear note when
something couldn't be read.

## Planned

### Company deep dive for US companies
Today the deep dive, management report card, investor checklist and deck cover Indian (NSE) companies only. A US
version would use the SEC's free EDGAR filings:

| Part | US source | Note |
|---|---|---|
| 10+ years of numbers | XBRL financial data in 10-K and 10-Q filings | Capex is reported directly, no estimate needed |
| Business model and risks | 10-K Item 1 (Business) and Item 1A (Risk Factors) | Required and detailed |
| Industry | SIC code on every filing | Drives industry rules, measures and valuation |
| Report card | Guidance in earnings press releases (8-K, exhibit 99) | US call transcripts aren't filed with the SEC |
| Checklist | Same rules in dollars and US fiscal years | Insider ownership instead of promoter holding |

Reuses the page, checklist, report card checks, industry measures, valuation and deck; new work is the EDGAR client
and the filing readers.

### Indian currency derivatives (CDS)
NSE's currency segment: USDINR, EURINR, GBPINR and JPYINR futures and options, plus the cross pairs (EURUSD, GBPUSD,
USDJPY) traded in India. Today only the USDINR spot rate is available, through the forex market.
- Backtests on futures (continuous daily series stitched across expiries, as for MCX) and on the current contract
  intraday; paper trading the front month with a roll before expiry.
- Lot sizes, tick sizes and costs for the segment (exchange fees, stamp duty, GST; no STT on currency).
- Market hours 9:00 am to 5:00 pm IST, and the currency segment's own holiday list.
- Options on USDINR in the Options tab, priced on live bid and ask like index options.

### International payments
Payments are in rupees through Razorpay today. To let people outside India subscribe:
- Turn on international cards in the Razorpay dashboard (needs Razorpay's approval). *Done:* Admin → Check payments
  setup reports whether international cards are on, when Razorpay's answer says so.
- Prices per currency (at least USD, plus GBP and EUR), shown by the visitor's country, with the matching Razorpay plans.
- Taxes and invoices for overseas customers (GST rules for export of services), and the legal pages updated.
- A clear note on what works for people outside India: Indian market data, US and other markets, the deep dive.

### Extreme stress test: one stop for everything StratLab offers
The goal: nobody needs to open another site to check something StratLab already covers. A structured test, feature
by feature, against what people would otherwise use:
- *Done:* Admin → Data audit (the deep dive for up to 300 companies, against their sources) and Admin → Check every
  feature (prices, backtests, scans, rotation, options, filings, company pages, news, database, calendar on live data);
  tests that call every route with hostile input, break every source in every way, run the app at 16 tricky moments
  (holidays, expiries, midnight IST, clock changes, past the known calendar), and load the real server with hundreds
  of users. Still to do: a Nifty 500 list for the audit, and re-running both admin checks after each big change.
- **Every feature on real data at scale:** the deep dive, report card, checklist and measures on the Nifty 500 (not
  just a few names), every industry; the scan and rotation on every set; backtests and paper trading in every market;
  options on every underlying.
- **Compare against the source of truth:** numbers against the company's own results, prices against the exchange,
  costs against a broker's contract note, filings against the exchange's page. Log every mismatch.
- **Load:** many users at once (backtests, deep-dive reads, live sessions, options quotes), to find the limits of the
  single server and the free AI services, and how the app behaves at those limits.
- **Failure:** each data source and AI service down or slow, market holidays, expiry days, half days, bad PDFs, odd
  symbols; every case should show a clear note, never a wrong number or a blank page.
- **Gaps list:** anything a user would still have to look up elsewhere becomes a roadmap item here.

## Precision: known gaps (India)
Found while checking live companies. Each shows a note on the page today instead of a wrong number.

- **Letters with no link at all** ("available on the website of the Company"): about a fifth of large companies in
  the first audit. Could look up the company's investor page from its website, but that's guesswork per site.
- **Scanned (image-only) PDFs**: no text without OCR.
- **Audio- or video-only calls**: no transcript to read.
- **EV/EBITDA without cash**: EV is market value plus borrowings; cash isn't subtracted because the fundamentals
  source doesn't give it, so cash-rich companies read slightly high.
- **Hospital and other industry measures** depend on the company stating them in its presentation or calls.
- **Wider live testing**: so far checked on Reliance, HDFC Bank and Apollo Hospitals. Next: an IT company (Infosys),
  consumer (Titan), cement, a small cap, an insurer and a holding company.

## Waiting on the owner
Things only the account owner can do:
- Vercel Pro before taking real payments.
- The launch offer (Admin → launch offer) when ready.
- Admin → Save real prices for testing, then commit the file to `stratlab/backend/tests/fixtures/real_prices.json.gz`.
- Re-check Admin → Check filings feed after each deploy that touches documents.
- Open one downloaded deck in PowerPoint to check its look.
- Update the GitHub repository's About text to mention investing.
