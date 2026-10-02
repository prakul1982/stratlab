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

## Precision: known gaps (India)
Found while checking live companies. Each shows a note on the page today instead of a wrong number.

- **Transcripts hosted off the company's own domain** (investor-relations providers): not fetched, for safety. Could
  allow a short list of known IR hosts.
- **Filings that link to a web page instead of a PDF** ("see our Investors page"): the PDF isn't found. Could read
  that page for its transcript link, on the company's own site only.
- **Scanned (image-only) PDFs**: no text without OCR.
- **Audio- or video-only calls**: no transcript to read.
- **EV/EBITDA without cash**: EV is market value plus borrowings; cash isn't subtracted because the fundamentals
  source doesn't give it, so cash-rich companies read slightly high.
- **Hospital and other industry measures** depend on the company stating them in its presentation or calls.
- **Wider live testing**: so far checked on Reliance, HDFC Bank and Apollo Hospitals. Next: an IT company (Infosys),
  consumer (Titan), cement, a small cap, an insurer and a holding company.
