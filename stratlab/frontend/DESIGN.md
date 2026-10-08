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

Also, always: facts and arithmetic only (no advice), and never a data provider's name in anything a user sees. Colour on a number follows the sign and nothing else: see "Colour on numbers" below.

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
| A headline number | `Stat` in a `StatRow` (sans, with note, optional `Delta`; a signed value gets `tone={signTone(v)}`) | `Fig` / `.space-fig` (mono) |
| A change | `Delta` (▲/▼ pill, green or red). `tone="neutral"` where a rise is not good news by nature | a grey change |
| A signed figure inside a sentence, table cell or readout | `Signed` (`<Signed value={v} fmt={signed} />`, or the finished text as children): green above zero, red below, plain at zero | a hand-made `k-up` / `k-down` span, or a plain `signed(v)` |
| A service or feed's health | `HealthGrid` + `HealthTile` (green, amber or red light, always with its word OK / Check / Problem); `StatusList` + `StatusRow` for a card's own rows | colour-only dots |
| A status | `Badge` (`ok`, `warn`, `plain`, `live`), always with its word | colour alone |
| 2 to 4 choices | `Seg` | 5+ buttons; stretched full-width segs |
| Many choices (timeframes, ranges) | `ChipBar` (`custom` adds "+ Custom", remembered per `storageKey`) | rows of fixed buttons |
| A form | `FormGrid` + `Field` + `FormActions` | `.field` inside ad-hoc flex rows |
| A time of day | `TimeInput` (24-hour, `zone="IST"` beside it; `small` inside a sentence) | `<input type="time">` |
| A slider | `Range` (kit track and thumb, its value in words beside it) | a bare `<input type="range">` |
| A stock / company box | `StockPicker` (`value`, `onPick(symbol, region)`) | a bare text input; `CompanyCombobox` in new code |
| A choice among types | `TilePicker` | long `<select>`s |
| A table | `DataTable`. A long table scrolls with the page (never in a box of its own); `stack` turns each row into a card on a phone (give it to a table whose figures all matter, like Positions); `pinHead` keeps the header of a table that fits its card in view | a raw `<table>`, a table in a `max-height` box |
| A long page | `PageNav` (jump links to the main cards, which carry an `id`) and the detail behind `Disclosure` | a page of ten cards with no way round it |
| A chart | `ChartFrame` (title, range, Table switch in the header row) around `LineChart`/`XYChart` with `ranges={false} table={false}` | a chart in a bare card |
| Nothing / failed / loading | `EmptyState`, `ErrorState`, `Skeleton` (each can carry one action button) | `Empty`, `Loading` spinner, a bare `.banner` |
| Anything that floats over the page | `Dialog` (or `ConfirmDialog`) for a modal; `useDialogFocus` on your own modal box (the palette, the phone menu); `usePopover` for a menu or an editor that opens from a button | a hand-made focus trap or Esc handler |
| A calculator's answer | `ResultBlock` | a row of `Fig`s |
| Money and percentages | `lib/format.ts` | `toLocaleString` and per-file `inr` copies |

If nothing fits, add the piece to the kit and to `/dev/kit` first; do not build it inside a page.

## Numbers

`inr(v, dp=0)` full rupees (`₹1,00,000`; `inr(1849.3, 2)` is `₹1,849.30`). `inrCompact(v)` Indian units (`₹925`, `₹5.2 lakh`, `₹3,472 cr`, `₹1.51 lakh cr`). `signedInrCompact(v)` adds a `+`. `axisInr(v)` for chart axes (`₹1.45L cr`). `pct(v)` signed, `pctPlain(v)` unsigned, `signed(v)` plain signed number (put it in `Signed` to colour it). `num(v, dp)` a plain number with fixed decimals. Never `toFixed` or `toLocaleString` on a figure that can be negative: they print a hyphen; `minus(text)` fixes a string, and `Stat` and `DataTable` cells fix what they are given. All take **rupees** (multiply crore by `CRORE`), print `–` for missing values and a real minus (−). Exact figures belong in the tooltip and the Table view, not on the axis.

## Colour on numbers

**Colour a number when its sign is its meaning.** Any signed change, P&L, return or net figure (day changes, "from the day before" lines, change rows under a table cell, net positions, P&L in holdings, paper, backtests and tax, "today" moves, sparkline badges, breadth counts that are explicitly up against down) is **green above zero (`--up`), red below it (`--down`), and plain at zero**. This holds for raw market-positioning numbers too (a participant's net long or short, open interest added or cut): the direction is a fact, so it is coloured.

**Keep neutral:** levels, prices, totals, open interest itself, counts, volumes, market values and any figure without a sign. Where a rise is not good news by nature, the change keeps its arrow or sign but not its colour (`Delta tone="neutral"`, `Spark tone="neutral"`): the market's margin-funded book, India VIX, currency pairs and gold, TRIN, a fund's expense ratio, a loan rate gap, a premium or discount to NAV, a futures basis, the distance below a 52-week high, option Greeks.

**How:** `Signed` in a sentence, a table cell or a tooltip; `Stat tone={signTone(v)}` for the big number and `Signed` in its `note`; `Delta` for a pill; `upDown(v)` / `signCls(v)` where you need only the class; `XYChart signedTip` for a chart whose tooltip numbers are changes or nets. Pass the finished text when you have it (`<Signed value={d}>{pct(d, 2)}</Signed>`): a figure that rounds to nothing ("0.0%") stays plain, so the colour always agrees with the sign that is printed.

**Always keep the sign or the ▲/▼ in the text.** Colour is a second signal, never the only one (colour-blind readers, screen readers, a printout). `--up` and `--down` pass 4.5:1 on the page, a card, a hovered row, a highlighted row and a chip in both themes (`unit/tokens.test.mjs`); a new token beside them is added to that test. Never use blue or orange for a gain or a loss.

## Dates

One format, day first, as My space shows it: `fmtDate(v)` gives "6 Oct 2026", `fmtDate(v, { year: false })` "6 Oct", `{ weekday: true }` "Tue 6 Oct 2026"; `fmtDateTime(v)` adds a 24-hour clock ("6 Oct 2026, 14:05"), `fmtTime(v)` is the clock alone. A plain `YYYY-MM-DD` is a calendar day and is never moved by a time zone. **Don't** call `toLocaleDateString` in a page, write "Oct 6", "2:45 PM", a two-digit year or a zero-padded day.

Time zones: **a market's times are in the market's own zone, with the zone's name.** Pass `tz` (`IST`, `ET`, `marketTz(region)`) and `zone: true`: "7 Oct 2026, 13:26 IST", "09:30 ET". `asOf(iso)` (and so `PageHeader asOf`, `AsOf`) does this by default, in India's zone; give `asOfTz={marketTz(region)}` on a page that can show US data. The reader's own events (a trial's end, a signal arriving) may be in the reader's zone, and are labelled the same way (`zone: true` with no `tz`). A chart given `tz` names the zone on its last clock tick and in its tooltip. Data from an earlier day is never titled "Today": say the day it is from. A time a person types goes in `TimeInput` (24-hour, its zone beside the box), never the browser's `type="time"`, which follows the reader's locale.

## Do and don't

- **Do** put the label on one line and the detail behind (i): `Your margin (i)`. **Don't** write "Your part of the buy value (%)".
- **Do** put the unit inside the box (`₹`, `%`, `% / yr`) and say `· optional` on optional fields. **Don't** put units in the label.
- **Do** put the main button on its own row under the grid, left-aligned, then the result. **Don't** float it beside a field.
- **Do** put range, Table and other card controls in the card's header row. **Don't** add a second row of controls inside the card.
- **Do** write "₹1.51 lakh cr". **Don't** write "₹150.0k cr" or "₹1,51,134 crore".
- **Do** give an empty state a sentence and, if there is something to do, one button. **Don't** leave a big empty box.
- **Do** colour a signed figure with `Signed`, `Delta`, `Stat tone` or `upDown`/`signCls` (green `--up`, red `--down`). **Don't** colour a level, price, total, count, volume or size, or a figure with no sign.
- **Do** keep the sign (+ / −) or the ▲/▼ in the text beside the colour. **Don't** let colour be the only thing that says up or down.
- **Don't** add inline `style={{}}` for spacing or font; use the tokens and kit classes.
- **Don't** hard-code colours (`#b42318`); use tokens.

## Accessibility

- **Dialogs** (`components/kit/Dialog.tsx`): one behaviour everywhere. Focus moves in (`data-autofocus` picks the first stop), Tab and Shift+Tab go round inside, Esc closes, and focus goes back to what opened it; when that has gone (a removed row), to the `fallback` you pass (its neighbour), else the page heading. Dialogs stack: only the top one listens. A dangerous `ConfirmDialog` starts on Cancel.
- **Pop-ups** (`usePopover`): focus goes into the menu or editor, Esc and a click outside close it, and focus returns to its button. Something inside that handles Esc itself calls `preventDefault()`, and the dialog behind leaves it alone.
- **(i) buttons** are named after what they explain ("About Markets"; `CardHead` does it from the title) and sit beside a heading, never inside it.
- **Names start with the visible words** ("owner Pro plan, account menu"); add words after, in `.sr-only`, rather than an `aria-label` that says something else.
- **A table column with no heading** (Edit buttons) still gets one for screen readers: `DataTable` writes "Actions".
- **Space for late cards:** a card that arrives after the page should not push what's already on screen. Give its loading state the height it will have (`Skeleton` lines, a `min-height`), or keep the cards below it waiting (Holdings does this for its dividends card).
- `e2e/a11y.spec.ts` runs axe-core on the main pages (serious and critical problems fail) and checks the keyboard behaviour above.

## Drawing tools on the price chart

One shared price chart (`src/charts/price/`) serves company pages, backtests, paper trading and chart replay, so the drawing tools live there once.
Left rail on desktop (groups with fly-outs, magnet, hide all, drawings list), a "Draw" bottom sheet on a phone, undo/redo and the (i) shortcut list in the top bar,
and a small bar for the selected drawing (colour, line style, lock, duplicate, delete, note text, a position's risk amount).
Maths is in `drawGeo.ts` (tested in `unit/drawings.test.mjs`); drawings are saved per user, market and symbol at `/me/drawings/{region}/{symbol}`, with this browser as the fallback.
A long or short position is the person's own planning box: label it with facts only (target, stop, risk : reward, quantity for their risk amount), never advice. In chart replay a drawing shows only once the replay has reached the candle it was drawn on.

## Checklist before a page is done

Desktop 1300px and phone 400px, dark and light; empty, loading, error, long names; no sideways page scroll; keyboard reaches every control; screenshots saved (`E2E_SHOTS=<folder> npx playwright test e2e/kit.spec.ts` does `/dev/kit` and Margin funding).
