# Lane c-f2 report: Peers, Financial statements and Shareholding history (company page and deep dive, India and US)

Branch `lane/c-f2-company`. No pull request opened (as instructed).

## What was built

Three new cards, one under the other, on every company page (`/research/{IN|US}/{symbol}`, after "Last quarters") and on the deep dive
(`/research/{IN|US}/{symbol}/deep`, before the checklist). Both pages get them through one new component, `CompanyTables`.

1. **Peers** (`CompanyPeers.tsx`). Companies of the same industry in the stored classification (widened to the sector when the industry
   has fewer than 3 others), the same market, and for the US the same kind of filer (foreign filers only beside foreign filers). They are
   ordered by how close their market value is to the company's own: the theme code's "own sector, similar market value" comparison
   (`theme_data.comparable_peers`), without its 10-company minimum. Columns: market value, sales growth (3-year CAGR), EBITDA margin, net
   margin, ROCE (ROE for a bank or lender, with no EBITDA column), P/E. The company's own row comes first and is bold. A median row of the
   peers shown sits underneath, and each peer links to its own page. Every figure is the stored screens index's
   (`screens.load_index`); nothing is fetched per peer.
2. **Financial statements** (`CompanyStatements.tsx`). Profit and loss, balance sheet, cash flow and ratios by year (every stored year, up
   to 12), plus the last 12 quarters. The views are chips: P&L, Balance sheet, Cash flow, Ratios, Quarters. India offers standalone and
   consolidated (a switch) when the source holds both for the same company, checked by the same name and the same latest year. The data
   comes from the fundamentals pages the company page and deep dive already read: the Indian page tables, and the SEC-built tables for the
   US. The ratios table's own rows are kept. Missing usual ratios are worked out from two figures of the same year and marked with a "·":
   sales growth, EBITDA margin, net margin, return on equity at year-end equity, and debt to equity (lenders get neither EBITDA margin nor
   debt to equity). A period with no figure shows "–", and a note appears under any table that has one. No figure is filled in.
3. **Shareholding history** (`ShareholdingHistory.tsx`). India: promoters, FIIs, DIIs, government and public, and the number of
   shareholders, by quarter (up to the last 12). It has a small stacked SVG bar chart in the kit's series colours, with an aria-label that
   gives the latest quarter in words, and a line on each group's change in points. Source: the fundamentals page's quarterly shareholding
   table (the same table "Who owns it" shows the latest quarter of). US: a clear note that US companies file no such pattern and StratLab
   stores no institutional or insider ownership shares, pointing to "Holders above 5%" on the same page.

## Endpoints (new `app/company_tables.py`, router included from `main.py`)

| Endpoint | Free | Basic (`tables`) | Pro (`export`) |
|---|---|---|---|
| `GET /research/company/{region}/{symbol}/peers` | 3 nearest peers + own row + median of those 3; lock naming Basic | up to 10, sortable; note that CSV is Pro | + `can_export` |
| `GET …/peers.csv` | 402 | 402 | CSV (own row, peers, median; cells that start like a formula are quoted) |
| `GET …/statements?basis=consolidated\|standalone` | latest 3 years of P&L only; lock lists what Basic adds | every section, every year, 12 quarters, both bases | + `can_export` |
| `GET …/statements.xlsx` / `.csv` | 402 | 402 | workbook (a sheet per statement and Quarters, via `xlsx_write`) or one CSV |
| `GET …/shareholding` | latest quarter; lock naming Basic; pledge note | 12 quarters + chart | same |

All endpoints are signed-in only (`current_profile`). The trimming happens on the server, so locked figures never reach the browser. Lock
words come from `plans.py` (`FEATURE_PLAN`) and appear with the kit's `PlanNote` (price + plan button). Sources that are down return the
existing 502/503 `source_error`. No new data source, job or paid service. Nothing new is stored: the endpoints read caches the sources
already keep (the fundamentals pages for 6 h, the screens index in memory).

## Plan gating (consistent across plans.py, plans.ts, planFeatures.ts; test_plan_copy passes)

- New Basic feature **`tables`**: every peer and sorting, every year and statement, quarters, both bases, 12 quarters of shareholding and
  the chart. Basic card (planFeatures.ts): "…every peer and ten years of statements and shareholding on company pages…". FLAGS row: "All
  company tables". ELSEWHERE (gates.ts) says where it lives.
- **Pro downloads use Pro's existing `export` feature** (until now a notebook's export). The Pro card now reads "Export a notebook's rules
  and trades, a company's statements to Excel, …". ELSEWHERE for `export` names the company page too.
- Why not a separate `company_export` feature: the landing page's JS budget (`e2e/review-r5.spec.ts`, under 450 KB) had **58 bytes** of
  room at the base commit (460,742 of 460,800 bytes). Every plan row in `plans.ts` is in that download. A first version with two features
  and longer copy came to 461,076 and failed. The final version is 460,797 and passes. **The landing download grew by 55 bytes**, the
  smallest cost of a plan row that test_plan_copy requires. I didn't find a way to add a feature at zero bytes without changing other
  lanes' copy. The coordinator should know the budget has 3 bytes left: the next lane that adds a plan feature will need a plans.ts split
  (FLAGS / FLAG_GROUP / EVERYONE are only used by PlanCompare and gates, and could leave the landing chunk) or a higher budget.

## Shared files touched (small, self-contained edits)

- `backend/app/main.py`: 5 lines after `research_routes.public_facts = …` (setup + `include_router`).
- `backend/app/plans.py`: `tables` in Basic/Pro features and FEATURES, and a comment.
- `frontend/src/lib/plans.ts`: `tables` in both feature lists and one FLAGS row.
- `frontend/src/lib/planFeatures.ts`: words on the Basic and Pro cards (each card still 8 lines of at most 34 words).
- `frontend/src/lib/gates.ts`: ELSEWHERE entries.
- `frontend/src/pages/Research.tsx` (company page): one import, one `<CompanyTables …/>` after "Last quarters", and two PageNav entries
  (Peers, Statements). The phone layout and the AI read are not touched.
- `frontend/src/pages/DeepDive.tsx`: one import, one `<CompanyTables … ids="dd" />`.
- `backend/tests/visual_server.py`: `company_tables_world(mp)`, which gives the peers three more Commodities companies the demo world has
  pages for. The screens index and every other page are unchanged.
- `backend/tests/fake_db.py`: lane accounts `cf2-0..23` (Free 0-7, Basic 8-15, Pro 16-23).
- `docs/FEATURES.md`: three rows.
- Tests changed on purpose (marked "(updated on purpose)"): `test_plan_gates.py` (Basic's feature set includes `tables`),
  `test_gate_matrix.py` (the two downloads added to the route matrix under `export`; `tables` listed as trimmed rather than refused),
  `test_plan_copy.py` (CARD_WORDS for `tables`). No test was skipped, weakened or deleted.

New files: `backend/app/company_tables.py`, `backend/tests/test_company_tables.py`, `frontend/src/lib/companyTables.ts`,
`frontend/src/components/{CompanyTables,CompanyPeers,CompanyStatements,ShareholdingHistory}.tsx`,
`frontend/src/components/companyTables.css` (tokens only, loaded with the cards, not on the landing page),
`frontend/unit/company-tables.test.mjs`, `frontend/e2e/company-tables.spec.ts`.

## Tests and totals

- Backend `tests/test_company_tables.py`: 17 tests (fixtures only, no network). Peer set and ordering, sector widening, foreign filers,
  lender → ROE, median, peers/statements/shareholding by plan (Free, Basic, Pro, signed out), CSV/XLSX Pro-only with contents, CSV formula
  quoting, statement alignment (no TTM, half-year column dropped, None kept), worked ratios, lender ratios, the other basis offered only for
  the same company, the US statements and note, and no advice words. They fail without the module and pass with it.
- **Full backend suite on the final code: 7,255 passed, 17 skipped (pre-existing), 0 failed** (`pytest -q -n 4`). An earlier run had 7,256;
  the one fewer is the per-feature parametrised test, now over one new feature instead of two.
- Frontend: `npm ci`, `npx tsc --noEmit` clean, **unit 1,815 passed / 0 failed** (8 new in `unit/company-tables.test.mjs`), `npm run build`
  ok.
- Browser: `e2e/company-tables.spec.ts` **10/10** on desktop 1440 and phone (Pixel 7, ~412 wide). It covers Free (3 peers + own row +
  locks, 3 years of P&L, 1 quarter), Basic (7 rows, sorting by header on desktop and the "Sort by" control on a phone, every view, the "–"
  note on cash flow, the chart), Pro (CSV and Excel downloads), US AAPL (statements, the shareholding note), and the deep dive's three
  cards. Also run and passing: landing, plans-gate, holders-updates, a11y-axe, pages-research, and review-r5 (landing budget, after the
  fix).
- **ui-lint**: `UI_LINT=1 UI_LINT_STRICT=1 UI_LINT_LIGHT=1 UI_LINT_ROUTES='/research/(IN|US)/'` gives **0 violations** at 1440, 1280 and
  390, dark plus 1440 light (company pages RELIANCE, TCS, AAPL and both deep dives). A first run found R18: tables clipped on a phone. Peers
  now stack as cards on a phone and shareholding is a period grid.
- I checked screenshots by eye: desktop peers (Basic), phone peers (Free with lock; Basic as cards with "Sort by"), desktop and phone
  statements, desktop shareholding with the chart.

## Skipped, and why

- **Promoter pledge %**: it isn't stored. The stored shareholding filings (`shareholders.py`) keep only named holders above 1%, the last 4
  quarters, and the fundamentals page's table has no pledge row. The card says so and points to the pledge disclosures under "Deals and
  insider trades". Storing it would mean changing the shared XBRL parser and its stored format (a `PARSER` bump), which is out of scope.
- **Visitors (signed out)**: the app's company page and deep dive are signed-in pages, so the endpoints need sign-in. The public SEO page
  (`/stocks/{in|us}/SYMBOL`, `stock_pages.render`) was not changed. Adding the teaser there means editing that large shared renderer, so I
  left it for a follow-up.
- **US institutional or insider ownership %**: not stored, so the card shows a note (as the task allows).
- The **TTM column** is left out of the yearly statements (it isn't a year). The last 12 quarters carry the recent figures.
- **Ratios over two years** (ROE on average equity, debtor days for the US) aren't worked out. Only ratios built from two figures of the
  same column are, so nothing is estimated.
