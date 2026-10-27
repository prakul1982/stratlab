# The UI checker

[← Back to the project overview](../README.md)

A layout checker that looks at every page the way a person does and fails the build when a page has the kind of problem
that is easy to miss one page at a time: a card with a hole in it, a button floating away from its row, a label wrapping
inside a pill, the same figure said three times. It runs on every pull request, so a new layout problem stops the merge
instead of waiting for someone to notice.

It was written after a visual review found these by eye. Each rule below is one of those findings turned into a
measurement.

## What it does

`stratlab/frontend/e2e/ui-lint.spec.ts` is a Playwright test with its own project, so the normal browser runs skip it.

1. It fills a throwaway copy of the app with a Pro user's data (`ui-lint-world.ts`: holdings, funds, net worth, a notebook
   with experiments, paper sessions, alerts, IPOs and so on), so no page is measured while empty. Nothing real is used.
2. It opens every page a person can reach, signed in and signed out, at **1440 × 900**, **1280 × 800** and **390 × 844**
   (a phone, with touch), in the dark theme. `UI_LINT_LIGHT=1` adds the light theme at 1440.
3. It waits until the page has drawn (no spinner, no loading skeleton, fonts loaded), opens every folded part of the page
   so a problem inside one counts, and measures the page against the rules in `ui-lint-rules.ts`.
4. It writes `report.md` and `report.json` and a screenshot of every page that has a problem, with the offending boxes
   outlined. The first test in the file checks the rules themselves: each fires on a layout known to be bad and stays
   quiet on a good one.

By default it only reports. With `UI_LINT_STRICT=1` any problem that is not accepted in the allowlist fails the run.

## The rules

| Rule | What it finds |
| --- | --- |
| R1 | Dead space beside a short card: cards in one row where one has more than 60 px, and over a quarter of the row's height, empty under its content |
| R2 | A sparse wide card: a card wider than 900 px whose content covers less than 55% of its width, or a row of tiles that fills less than 60% of the row |
| R3 | A floating control: a button or chip that is not level with the chips beside it, or an end control more than 48 px from its row |
| R4 | Text wrapping onto two lines inside a button, chip, switch option or tab |
| R5 | An uneven row: a control well off its row's height, or fields and figures that do not line up with their neighbours |
| R6 | A squeezed hint: a field's hint text narrower than 40% of its row and three lines or more |
| R7 | A double highlight: two highlighted items in one menu, or two selected options in one switch |
| R8 | A repeated figure: the same money or percent figure three or more times in one card (tables and charts are left out) |
| R9 | An orphan row: a grid of four or more equal cards whose last line holds one card alone |
| R10 | Overflow and clipping: the page scrolls sideways, text is cut off by a box, or two lines of text overlap |
| R11 | A tiny tap target on a phone, under 32 px tall |
| R12 | Caption clutter: a small "Dots: ..." or "Colours: ..." caption under a list or menu |
| R13 | An empty band inside a box: any card 140 px or taller with a gap of over 70 px (and a quarter of its height) at the bottom or between two blocks of content |
| R14 | An overlay on content: a fixed or sticky box (not the menu, a dialog or a toast) covering text or a control, checked with the page scrolled to the top, middle and bottom |
| R15 | An icon glued to its label: an (i) or icon button less than 3 px from the text beside it, or overlapping it |
| R16 | An uneven stat row: a word among numbers, a value wrapped over two lines, or labels of different heights, in one row of figures |
| R17 | A page whose frame differs: its title or its right edge sits more than 2 px from where most pages put theirs at that width |
| R18 | A clipped scroller on a phone: a sideways row with an item cut by the edge, or a table showing fewer than all its columns |
| R19 | A wrapped badge: a pill, tag or badge whose text runs onto a second line |
| R20 | An orphan end control: a lone control at the end of a row of text, more than 250 px from where the text ends |
| R21 | A gap under the page header: more than 56 px of nothing between the header and the first card |
| R22 | Row tags out of column: rows of a tag and a name whose names start at different positions (over 4 px apart) |
| R23 | Header wrap mismatch: cards side by side whose headers differ in height because one header's controls wrapped |
| R24 | A faint checkbox: an unchecked box or radio whose border and fill are both under 3:1 against what is behind them |
| R25 | The same sentence twice: one sentence of 30 characters or more said twice in one card (table rows are left out) |

The thresholds live in `ui-lint-rules.ts`; the table above is the same text as the rule list at the top of
`ui-lint.spec.ts`, which is what the report prints.

## Running it

From `stratlab/frontend`, with the backend's Python environment available (the test starts its own fake-world server):

```bash
npm run build
npm run ui-lint                        # report only: always passes, writes the report
UI_LINT_STRICT=1 npm run ui-lint       # fails on any problem the allowlist does not accept
```

The report is `test-results/ui-lint/report.md` (rules with their counts, then each problem with its page, width and
element; problems that show on three or more pages are listed once as one shared component), with the screenshots in
`test-results/ui-lint/shots/`.

Options, all environment variables:

| Variable | Effect |
| --- | --- |
| `UI_LINT_STRICT=1` | Fail on any problem not in the allowlist |
| `UI_LINT_ROUTES=<regex>` | Only the pages whose label matches, for a quick check of one page |
| `UI_LINT_WIDTHS=1440,390` | Only these widths (any of 1440, 1280, 390) |
| `UI_LINT_LIGHT=1` | Also measure 1440 in the light theme |
| `UI_LINT_LANES=6` | Pages measured at once (CI uses 3) |
| `UI_LINT_SHOTS=0` | No screenshots |
| `UI_LINT_OUT=<folder>` | Where the report goes |
| `E2E_API_PORT`, `E2E_WEB_PORT` | Move the test servers, as in the other browser tests |

## The allowlist

`stratlab/frontend/e2e/ui-lint.allow.json` lists layout problems accepted on purpose. An entry names the page (a route such
as `/plans`, or `*` for every page), the rule (`R1` to `R25`), a piece of the element's label as the report prints it,
and a **reason**. An entry without a reason does nothing. The report still lists an accepted problem, marked allowed, so
the list stays honest.

Use it rarely and say why. The one entry today is the Free plan's card on `/plans` at 1280 px: the three plan cards are a
comparison, Free lists fewer features than Basic, and stretching it would only move the blank space inside the card.
Fixing the layout is almost always the better answer.

## In CI

The `ui-lint` job in `.github/workflows/tests.yml` runs after the frontend build, in parallel with the browser tests
(about four minutes). It builds the site, installs Chromium and runs `npm run ui-lint` with `UI_LINT_STRICT=1` and three
lanes. The report and screenshots are uploaded as the `ui-lint-report` artifact whether it passed or failed, so a failure
shows what and where. Claude's own pull requests merge themselves only after this job has passed along with the backend,
frontend and browser jobs.
