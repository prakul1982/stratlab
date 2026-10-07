# StratLab design guide

Short and practical. The approved reference is the design kit; the live version is the page `/dev/kit` (admins, and dev builds).
Everything lives in `src/components/kit/` (import from `../components/kit`), its CSS in the "kit" section at the end of
`src/styles.css` (every class starts `k-`), and numbers come from `src/lib/format.ts`.

## The 12 rules (the owner's standard)

1. **Everything lines up.** One-line labels, boxes on one baseline, the main button on its own row, the answer right below.
2. **No clutter.** Essentials first; the rest behind "More" or (i). One card, one job. No duplicated tab rows.
3. **Easy to find.** Grouped by what the person is doing. Everything is in ⌘K.
4. **Plain words.** No jargon or internal words ("30 trading days stored"). A calendar looks like a calendar.
5. **Inviting inputs.** Suggestions as you type, tiles instead of long dropdowns, friendly empty states, smart defaults.
6. **One visual language.** One number font (sans), Indian units, the same spacing and card shapes, controls in card header rows.
7. **No surprises.** Buttons go where you expect; useful sections open by default.
8. **Automatic first.** Connect once; typing is the fallback.
9. **Same care outside the app.** Emails, exports and admin use these same pieces.
10. **You sign off.** Mockups first for big changes; before/after screenshots for every redesigned page.
11. **Same thing, same look.** One component per job. No one-off versions on a single page.
12. **Every state checked.** Empty, loading, error, long names, phone (400px), dark and light.

Also, always: facts and arithmetic only (no advice, no "good/bad" colour on a number where a rise is not good news), and never a data provider's name in anything a user sees.

## Tokens (top of `styles.css`)

| | |
|---|---|
| Spacing | `--s1..--s7` = 4, 8, 12, 16, 24, 32, 48 px. Use these for every gap and padding. |
| Radii | `--r-card` 14px (cards), `--r-ctl` 10px (buttons, inputs, seg) |
| Controls | `--ctl` 44px (inputs, main buttons), `--ctl-sm` 34px (`.btn.sm`) |
| Type | `--t-h1` page title (serif 600), `--t-card` 20px card title (serif), `--t-stat` 28px big number (sans 600), `--t-result` 38px calculator answer (serif), `--t-lede` 17px, `--t-body` 15px, `--t-label` 13.5px, `--t-note` 13px, `--t-eyebrow` 12px (mono, uppercase) |
| Fonts | `--serif` Fraunces (titles), `--sans` IBM Plex Sans (everything else, **including numbers**), `--mono` only for the eyebrow and code |
| Up / down | `--up`, `--up-soft`, `--down`, `--down-soft` (both themes). `--red-ink` is an alias of `--down`. |
| Other colours | `--blue` links, focus and "real"; `--orange` warnings; never use orange or blue to mean a loss or a gain |

The dark values are written twice in `styles.css` (explicit dark and "follow the system"); `unit/tokens.test.mjs` fails if they differ. Change both.

## Which component for which job

| Job | Use | Not |
|---|---|---|
| Top of a page | `PageHeader` (eyebrow "Space · Group", title, one-line lede, "Data up to" badge + (i)) | a bare `h1.page-title` |
| A box of content | `Card` + `CardHead` (title, (i), actions on the right in the same row); `compact` when it has little to say | `section.card` + `h2.h3` |
| A headline number | `Stat` in a `StatRow` (sans, with note, optional `Delta`) | `Fig` / `.space-fig` (mono) |
| A change | `Delta` (▲/▼ pill). `tone="neutral"` where a rise is not good news | colouring the number |
| A service or feed's health | `HealthGrid` + `HealthTile` (green, amber or red light, always with its word OK / Check / Problem); `StatusList` + `StatusRow` for a card's own rows | colour-only dots |
| A status | `Badge` (`ok`, `warn`, `plain`, `live`), always with its word | colour alone |
| 2 to 4 choices | `Seg` | 5+ buttons; stretched full-width segs |
| Many choices (timeframes, ranges) | `ChipBar` (`custom` adds "+ Custom", remembered per `storageKey`) | rows of fixed buttons |
| A form | `FormGrid` + `Field` + `FormActions` | `.field` inside ad-hoc flex rows |
| A stock / company box | `StockPicker` (`value`, `onPick(symbol, region)`) | a bare text input; `CompanyCombobox` in new code |
| A choice among types | `TilePicker` | long `<select>`s |
| A table | `DataTable` | a raw `<table>` |
| A chart | `ChartFrame` (title, range, Table switch in the header row) around `LineChart`/`XYChart` with `ranges={false} table={false}` | a chart in a bare card |
| Nothing / failed / loading | `EmptyState`, `ErrorState`, `Skeleton` (each can carry one action button) | `Empty`, `Loading` spinner, a bare `.banner` |
| A calculator's answer | `ResultBlock` | a row of `Fig`s |
| Money and percentages | `lib/format.ts` | `toLocaleString` and per-file `inr` copies |

If nothing fits, add the piece to the kit and to `/dev/kit` first; do not build it inside a page.

## Numbers

`inr(v, dp=0)` full rupees (`₹1,00,000`; `inr(1849.3, 2)` is `₹1,849.30`). `inrCompact(v)` Indian units (`₹925`, `₹5.2 lakh`, `₹3,472 cr`, `₹1.51 lakh cr`). `signedInrCompact(v)` adds a `+`. `axisInr(v)` for chart axes (`₹1.45L cr`). `pct(v)` signed, `pctPlain(v)` unsigned, `signed(v)` plain signed number. All take **rupees** (multiply crore by `CRORE`), print `–` for missing values and a real minus (−). Exact figures belong in the tooltip and the Table view, not on the axis.

## Do and don't

- **Do** put the label on one line and the detail behind (i): `Your margin (i)`. **Don't** write "Your part of the buy value (%)".
- **Do** put the unit inside the box (`₹`, `%`, `% / yr`) and say `· optional` on optional fields. **Don't** put units in the label.
- **Do** put the main button on its own row under the grid, left-aligned, then the result. **Don't** float it beside a field.
- **Do** put range, Table and other card controls in the card's header row. **Don't** add a second row of controls inside the card.
- **Do** write "₹1.51 lakh cr". **Don't** write "₹150.0k cr" or "₹1,51,134 crore".
- **Do** give an empty state a sentence and, if there is something to do, one button. **Don't** leave a big empty box.
- **Do** use `Delta tone="neutral"` for market-wide quantities. **Don't** paint a number green or red when the direction is not good or bad.
- **Don't** add inline `style={{}}` for spacing or font; use the tokens and kit classes.
- **Don't** hard-code colours (`#b42318`); use tokens.

## Drawing tools on the price chart

One shared price chart (`src/charts/price/`) serves company pages, backtests, paper trading and chart replay, so the drawing tools live there once.
Left rail on desktop (groups with fly-outs, magnet, hide all, drawings list), a "Draw" bottom sheet on a phone, undo/redo and the (i) shortcut list in the top bar,
and a small bar for the selected drawing (colour, line style, lock, duplicate, delete, note text, a position's risk amount).
Maths is in `drawGeo.ts` (tested in `unit/drawings.test.mjs`); drawings are saved per user, market and symbol at `/me/drawings/{region}/{symbol}`, with this browser as the fallback.
A long or short position is the person's own planning box: label it with facts only (target, stop, risk : reward, quantity for their risk amount), never advice. In chart replay a drawing shows only once the replay has reached the candle it was drawn on.

## Checklist before a page is done

Desktop 1300px and phone 400px, dark and light; empty, loading, error, long names; no sideways page scroll; keyboard reaches every control; screenshots saved (`E2E_SHOTS=<folder> npx playwright test e2e/kit.spec.ts` does `/dev/kit` and Margin funding).
