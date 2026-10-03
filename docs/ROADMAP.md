# Roadmap

What's planned next and what's known to be imperfect. The aim is one place an investor can trust for a company, so
precision comes before breadth: every number from a filing, every claim tied to a quote, and a clear note when
something couldn't be read.

## Planned

### Company deep dive for US companies
*Done (first part):* the deep dive, checklist, valuation and deck for US companies, from the SEC's filings
(XBRL numbers in 10-K and 10-Q reports): ten years of revenue, profit, operating margin, reported capex, cash flow,
debt and cash; the last twelve quarters; industry from the SIC code; and links to the annual, quarterly and earnings
filings. The AI read covers US companies too: the business, risks and industry measures from the latest 10-K (cut to
Business, Risk Factors and Management's Discussion), and plans and outlook from it and the latest earnings releases
(exhibit 99 of the 8-K). Ratios that need a price use the latest share price and the share count on the latest report. Admin → Data
audit runs on US sets, and Admin → Whole market: US checks every company filing with the SEC.

Still to do:
- Report card from guidance in earnings releases (US call transcripts aren't filed with the SEC): needs the periods
  handled per company's own fiscal year, not India's April to March.
- Insider ownership in the checklist instead of promoter holding.

### Indian currency derivatives (CDS)
*Done:* USDINR, EURINR, GBPINR and JPYINR futures as a market of their own (front month, rolled three days before
expiry, whole lots of 1,000 units or 100,000 yen): daily backtests on years of stitched history, intraday on the
current contract, paper trading, costs without STT (exchange fees, stamp duty, GST), 09:00 to 17:00 IST, and the
segment's own holiday list read from the exchange each day.

Still to do:
- The cross pairs (EURUSD, GBPUSD, USDJPY): their profit is in dollars, not rupees.
- USDINR options in the Options tab.

### International payments
*Done:* international cards are on in Razorpay, so anyone abroad can subscribe. The Plans page shows prices in the
visitor's currency (from their country; they can switch) for 18 currencies, following the rupee price at the day's
exchange rate, rounded to a tidy amount (rates read daily), so changing the rupee price changes them all; Admin →
Prices outside India can fix any of them instead. A currency is charged in that
currency once its Razorpay plans are created and their IDs pasted there; until then it is charged in rupees and the
page says so. Admin → Check payments setup checks those plans too.

Still to do:
- Set the final prices per country, and create the Razorpay plans for the currencies that should be charged locally.
- Taxes and invoices for overseas customers (GST rules for export of services: usually zero-rated with a letter of
  undertaking), with an accountant.

### Extreme stress test: one stop for everything StratLab offers
The goal: nobody needs to open another site to check something StratLab already covers. A structured test, feature
by feature, against what people would otherwise use:
- *Done:* Admin → Data audit (the deep dive for up to 300 companies, against their sources) and Admin → Check every
  feature (prices, backtests, scans, rotation, options, filings, company pages, news, database, calendar on live data);
  tests that call every route with hostile input, break every source in every way, run the app at 16 tricky moments
  (holidays, expiries, midnight IST, clock changes, past the known calendar), and load the real server with hundreds
  of users. Also done: the NIFTY 500, Next 50, Midcap 150 and Smallcap 250 sets from the exchange's own lists, and
  Admin → Whole market, which checks every NSE company (and every company filing with the SEC) in the background,
  new listings first. Still to do: re-running the admin checks after each big change.
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
