import { Fragment, isValidElement, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { watchSize } from "../../lib/resize";
import { firstDesc, kindOf, sortByValues, valueOf, type SortKind, type SortValue } from "../../lib/tableSort";
import { useScrollRows } from "./ScrollList";
import { useSection } from "./Section";
import { Info } from "../ui";
import { textOf } from "./Card";
import { istToday, minusNode } from "../../lib/format";
import { scrollToEnd } from "../../lib/phoneFit";
import { columnOf, csvName, type CsvValue } from "../../lib/csv";
import { downloadCsv } from "../../lib/csvDownload";
import { Download } from "../Icons";
import { ReportFigure, useReportScope } from "./ReportFigure";

export type Column<R> = {
  key: string;
  header: ReactNode;
  info?: ReactNode;                          // an (i) in the header
  numeric?: boolean;                         // right-aligned, in the header too
  rowHeader?: boolean;                       // the cell that names the row (a stock): read as the row's header
  wrap?: boolean;                            // lets long text in this column wrap (a name with notes under it)
  action?: boolean;                          // the last column's buttons (Edit, Remove): as narrow as they are, right-aligned
  corner?: boolean;                          // with `action`, on a phone card the one button sits at the card's top right beside the name, not alone on a last row (VR2-017)
  /** With the table's own `sort`: the header is a button that sorts by this column. Without one (SORT EVERYWHERE, site88) every column with
   *  a header sorts on a click; false keeps this one out (a chart, a column whose order means nothing). */
  sortable?: boolean;
  /** SORT EVERYWHERE: the value this column sorts by, when the words the cell shows aren't it (a number drawn as a bar). */
  sortValue?: (row: R) => number | string | null;
  cell: (row: R) => ReactNode;
  cardLabel?: string;                        // the figure's name on a phone card when the header isn't plain text (R88-003)
  up?: boolean;                              // on a phone card, this figure comes right under the row's name with its label, ahead of the other columns: the gain, not the ninth figure (VR1-147)
  lead?: boolean;                            // on a phone card (`stack`), this cell comes right under the row's name, across the card: the answer first (DE-004, DE-035)
  /** With the table's `compact`: on a phone this figure sits on the row's first line, right of the name, with no label (a price, the day's move). */
  brief?: boolean;
  /** With `brief`: the figure keeps its short label on the phone's first line (a day: "19 Nov 186", LIVE16A-014: Mood's breadth count on a
   *  phone said "186" with no day beside "17 Nov 75"). */
  briefLabel?: boolean;
  /** With the table's `compact`: false leaves this column off a phone's two-line row (a figure the company page has; the desktop table keeps it). */
  phone?: false;
  /** false leaves this column off when the table is narrower than a wide desktop's (under 900 px: a 1280 or 1024 screen with the menu
   * open), a figure the row's own page has, so the rest stay in view without sideways scrolling (LIVE5-002). The CSV keeps it. */
  narrow?: false;
  /** false leaves this column off when the table is narrower still (under 720 px: a 1024 screen), after the `narrow: false` ones. */
  tight?: false;
  /** EXPORT: a column only the CSV has (a figure the table shows inside another column's cell, LIVE5-002); never drawn. */
  csvOnly?: true;
  /** EXPORT: the cell's value in the table's CSV (a number as a number, a day as "2026-11-04"); null leaves the column out of the file (a
   * trend line, a chart). Without it the file has what the cell shows, a plain number or percent read back as a number. */
  csv?: ((row: R) => CsvValue) | null;
  csvHeader?: string;                        // the column's name in the CSV, with its unit ("Market value (₹ crore)"), when the header isn't it
};

const info = (c: { header?: ReactNode; info?: ReactNode }) => <Info label={`About ${typeof c.header === "string" ? c.header.toLowerCase() : "this column"}`}>{c.info}</Info>;
const cls = (c: { numeric?: boolean; wrap?: boolean; action?: boolean; lead?: boolean; up?: boolean; corner?: boolean; brief?: boolean; briefLabel?: boolean; phone?: false; narrow?: false; tight?: false }) =>
  [c.numeric && "k-num", c.wrap && "k-wrap", c.action && "k-act", c.action && c.corner && "k-corner", c.lead && "k-lead", c.up && "k-first",
    c.brief && "k-brief", c.brief && c.briefLabel && "k-brief-label", c.phone === false && "k-phone-off", c.narrow === false && "k-narrow-off", c.tight === false && "k-tight-off"].filter(Boolean).join(" ") || undefined;

/** A cell that says only "no figure" (a dash, or nothing): a phone card leaves it out instead of a label over a dash (LIVE4-010: every
 * Results card ended "Options imply –"). */
export const dashOnly = (text: string): boolean => /^\s*[–—-]\s*$/.test(text);

/** The one table: a header row, right-aligned numbers, a hover row, and its own horizontal scroll box so a wide table
 * never makes the page scroll sideways. `label` names the table for screen readers. `rowNote` turns a row into its
 * first cell plus one line of words across the rest (a stock with no data). An empty list shows `empty` in one row. */
/** A note column is worth its place only when most rows fill it: at most half of them, and the notes go under the items instead
 * ("no half-empty columns", TABLES EVERYWHERE). */
export const sparseNotes = (withNote: number, rows: number): boolean => withNote * 2 <= rows;

/** Whether the page is at phone width (where a `stack` table is a list of cards). A page offering a shorter card on a
 * phone reads it too (DA-027). */
export function usePhone(): boolean {
  const q = "(max-width: 640px)";
  const [on, setOn] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(q).matches);
  useEffect(() => {
    const m = window.matchMedia?.(q);
    if (!m) return;
    const f = () => setOn(m.matches);
    m.addEventListener?.("change", f);
    return () => m.removeEventListener?.("change", f);
  }, []);
  return on;
}

/** EXPORT: the words a cell shows, for its CSV: text and numbers as they are, an element's children, and a component that draws its own words
 * from its props (a <Signed value> change, a badge) asked for them; one that needs to be drawn on the page (it uses hooks) gives nothing. Sub-lines
 * under a name are kept apart with " · ". */
export function cellText(node: ReactNode, depth = 0): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map((n) => cellText(n, depth)).filter((t) => t !== "").join("");
  if (!isValidElement<{ children?: ReactNode; className?: string }>(node) || depth > 12) return "";
  const { type, props } = node;
  if (props.className?.split(" ").some((c) => c === "sr-only")) return "";
  const sub = props.className?.split(" ").includes("k-sub-line");
  let inner: string;
  if (props.children !== undefined) inner = cellText(props.children, depth + 1);
  else {
    const t = type as unknown as { render?: (p: object, r: null) => ReactNode; type?: unknown } | ((p: object) => ReactNode);
    const fn = typeof t === "function" ? t : typeof t === "object" && t && typeof t.render === "function" ? (p: object) => t.render!(p, null) : null;
    try { inner = fn && !(fn as { prototype?: { isReactComponent?: unknown } }).prototype?.isReactComponent ? cellText(fn(props), depth + 1) : ""; } catch { inner = ""; }
  }
  return sub && inner ? ` · ${inner}` : inner;
}

/** EXPORT: a table as the header and rows of its CSV: every column but the buttons, by `csv` where the column gives it, else by what the
 * cell shows (columnOf: a column of "12.5%" is a column of numbers named "… (%)"). */
export function tableCsv<R>(columns: Column<R>[], rows: R[]): { head: string[]; rows: CsvValue[][] } {
  const cols = columns.filter((c) => !c.action && c.csv !== null).map((c) => {
    const name = c.csvHeader ?? c.cardLabel ?? ((typeof c.header === "string" ? c.header : textOf(c.header).trim()) || c.key);
    if (c.csv) { const f = c.csv; return { name, values: rows.map((r) => f(r)) }; }
    const { suffix, values } = columnOf(rows.map((r) => cellText(c.cell(r))));
    return { name: name + suffix, values };
  });
  return { head: cols.map((c) => c.name), rows: rows.map((_, i) => cols.map((c) => c.values[i])) };
}

/** EXPORT: the one "Download CSV" button: the table's rows (all of them, not only the ones a phone shows so far) as a file named
 * stratlab-<name>-<today>.csv, saved through lib/share.ts download(). Free on every plan: a file holds what the table shows that plan. */
export function CsvButton<R>({ name, label, columns, rows, text = "Download CSV" }: { name: string; label: string; columns: Column<R>[]; rows: R[]; text?: string }) {
  const save = () => { const t = tableCsv(columns, rows); downloadCsv(csvName(name, istToday()), t.head, t.rows); };
  return (
    <button type="button" className="btn quiet sm" data-csv={name} aria-label={`${text}: ${label}`} title="Download this table as a CSV file, to open in a spreadsheet" onClick={save}>
      {/* on a phone the button says "CSV" (its name stays "Download CSV: …"), so it shares the line with the day or title above a table (LIVE4-010) */}
      <Download size={16} />{text === "Download CSV" ? <span><span className="k-csv-verb">Download </span>CSV</span> : text}
    </button>
  );
}

/** A table box's rows, for its scroll height (useScrollRows). */
const bodyRows = (el: HTMLElement): HTMLElement[] => Array.from(el.querySelectorAll<HTMLElement>(":scope > table > tbody > tr"));

export function DataTable<R>({ label, columns: allColumns, rows: allRows, rowKey, empty = "Nothing to show yet.", rowAttrs, rowNote, foot, sticky: _sticky, stack: stackProp, grid, pinHead, sort, scrollEnd, csv, csvInMenu, more, detail, selectAll, compact }: {
  label: string; columns: Column<R>[]; rows: R[]; rowKey: (row: R, index: number) => string; empty?: ReactNode;
  /** EXPORT: a "Download CSV" button over the table, the file named after this (stratlab-<name>-<today>.csv); `rows` when the file
   * holds more than the table shows now (a group showing its first 12). */
  csv?: string | { name: string; rows?: R[] };
  /** EXPORT in the card's "⋯" menu (site87, owner: the watchlist's big "Download CSV" on a row of its own above the table cluttered the
   *  card): the file is one of the card's menu entries, not a button over the table. Needs a Card with a title. */
  csvInMenu?: boolean;
  /** AUTO-LOAD (site87, owner: "no next page, show more or load more"): a list whose server sends it a page at a time. Its next rows are
   *  asked for on their own as the reader nears the end of the rows drawn (in the block's own scroll), and a line says "Loaded N of M". */
  more?: { total: number; load: () => void; busy?: boolean; noun?: string };
  /** No longer used: every table's block is sized to the screen (SCROLL BY SCREEN, site87). Kept so callers need not change. */
  sticky?: boolean;
  /** No longer used (site87): the screen, not a row count, sets when a table scrolls. */
  scrollRows?: number;
  /** No longer used (site87): the Library's list is a block sized to the screen too. */
  noScroll?: boolean;
  /** On a phone, each row becomes a card (the first column as its title, every other cell under its own column name),
   * so nothing is cut off at the edge and the figures that matter are all in view. Desktop is unchanged. */
  stack?: boolean;
  /** CK-2 (R18): a table of 5+ columns is a list of cards on a phone unless it says otherwise, so no figure sits off the edge behind a
   * sideways swipe (a person who does not swipe never saw the gain, VR1-147). A `grid` is read across its row on purpose (an option chain by
   * its strike, a table of periods) and scrolls with its first column in place. */
  grid?: boolean;
  /** A table that fits its card (a few narrow columns) keeps its header row in view while the page scrolls past it. */
  pinHead?: boolean;
  /** A wide table of periods opens scrolled to its right end, where the latest column is (R25-003). The order stays. */
  scrollEnd?: boolean;
  /** Which column the rows are sorted by now, and what a click on a sortable header does. Without it (SORT EVERYWHERE, site88, owner) a
   *  click on any column's header sorts the rows drawn by it: numbers and days high to low first, words A to Z, a second click the other way,
   *  the blanks last; a row's open details stay under it, and an auto-loading list sorts the rows loaded. `false` where the order is the
   *  meaning (a ranked list, a timeline); a `grid` or `scrollEnd` table (read across its rows: a statement's lines) keeps its order too. */
  sort?: { key: string; desc: boolean; onSort: (key: string) => void } | false;
  /** A totals row under the rows: a cell for each column key (the first column's names the row). */
  foot?: Record<string, ReactNode>;
  rowAttrs?: (row: R) => Record<string, string>; rowNote?: (row: R) => ReactNode | undefined;
  /** No longer used (site87, owner: no "Show more" on any list): a phone's cards are a block sized to its screen, scrolling inside. */
  phonePage?: number;
  /** No longer used (site87). */
  pageDesktop?: boolean;
  /** With `stack`: on a phone each row is two short lines, not a card of labelled figures (LIVE4-010: a results day of ten companies was
   *  2,900 px of cards): the name with the `brief` figures at its right, then the other figures in one line, each after a short label; a
   *  column marked `phone: false` and a cell that is only a dash are left out. Desktop is unchanged. */
  compact?: boolean;
  /** A row's details one tap away: a button at the end of the row's name opens them in a row of their own right under it, across the
   * whole table (a phone card: under the card). TABLES EVERYWHERE (owner, 4 Nov): the library's "Rules and details" under its row. */
  detail?: { label: string; render: (row: R) => ReactNode };
  /** Rows that each carry a tick box (in the first column's cell, the page's own): a box in the first column's header ticks or clears every
   *  row given now (so a filter of the rows applies), mixed while some are ticked. On a phone's cards, where the header row is hidden, the same
   *  box sits over the cards (owner, 5 Nov: sector rotation's "Every stock" had no select all). */
  selectAll?: { on: boolean | "mixed"; set: (on: boolean) => void; label?: string };
}) {
  const phone = usePhone();
  const columns = allColumns.filter((c) => !c.csvOnly);
  // a table that does not fit the phone is read as cards, however few its columns (a watchlist's Actions column sat off the edge); `spill` is set after
  // a first look at the drawn table
  const [spill, setSpill] = useState(false);
  const stack = stackProp ?? (!grid && !scrollEnd && (columns.length >= 5 || spill));
  const box = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!phone) { setSpill(false); return; }
    const b = box.current;
    if (stackProp === undefined && !grid && !scrollEnd && !pinHead && !spill && b && b.scrollWidth > b.clientWidth + 2) setSpill(true);
  }, [phone, spill, stackProp, grid, scrollEnd, pinHead, allRows.length, columns.length]);
  // a grid scrolled off its first period says so (data-scrolled): the column half under the row names fades beside them (LIVE9B-015)
  const markScrolled = (el: HTMLElement | null) => { if (el) el.toggleAttribute("data-scrolled", el.scrollLeft > 1); };
  useLayoutEffect(() => { if (scrollEnd) { scrollToEnd(box.current); markScrolled(box.current); } }, [scrollEnd, columns.length, allRows.length]);
  // LIVE5-002 (globally): a list table wider than its box on a desktop (a 1280 screen, a narrow Admin column) lets its words wrap and its
  // cells' padding narrow (`k-fit`), so every column is in view without sideways scrolling; figures stay on one line. Measured again when
  // the box's width changes. A grid read across on purpose (an option chain, periods) keeps its scroll.
  const [fit, setFit] = useState(false);
  const [boxW, setBoxW] = useState(0);
  useEffect(() => {
    const b = box.current;
    if (!b) return;
    return watchSize(b, () => setBoxW((w) => (Math.abs(w - b.clientWidth) > 1 ? b.clientWidth : w)));      // a frame later (R7T-014)
  }, []);
  useLayoutEffect(() => { setFit(false); }, [boxW, columns.length, allRows.length]);
  useLayoutEffect(() => {
    const b = box.current;
    if (!fit && !phone && !grid && !scrollEnd && b && b.scrollWidth > b.clientWidth + 1) setFit(true);      // site87: 2px over is over (ui-lint R29 counts it)
  });
  const [openRows, setOpenRows] = useState<Set<string>>(() => new Set());
  const toggle = (k: string) => setOpenRows((o) => { const n = new Set(o); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const uid = useId();
  const rows = allRows;
  // SORT EVERYWHERE (site88): with no sort of the page's own, the table sorts the rows it has by a clicked column (`auto`)
  const page = sort || null;
  const [auto, setAuto] = useState<{ key: string; desc: boolean } | null>(null);
  const autoOn = sort === undefined && !grid && !scrollEnd && rows.length > 1;
  const headText = (c: Column<R>) => (c.cardLabel ?? (typeof c.header === "string" ? c.header : textOf(c.header))).trim();
  const canSort = (c: Column<R>) => (page ? !!c.sortable : autoOn && !c.action && c.sortable !== false && headText(c) !== "");
  const valuesOf = (c: Column<R>): { kind: SortKind; values: SortValue[] } => {
    if (c.sortValue) { const f = c.sortValue; const values = rows.map((r) => f(r)); return { kind: values.some((v) => typeof v === "string") ? "text" : "number", values }; }
    const texts = rows.map((r) => cellText(c.cell(r)));
    const kind = kindOf(texts, c.numeric);
    return { kind, values: texts.map((t) => valueOf(t, kind)) };
  };
  const kindAt = (c: Column<R>): SortKind => valuesOf(c).kind;
  const sortCol = autoOn && auto ? columns.find((c) => c.key === auto.key && canSort(c)) : undefined;
  // each row with its own place in the list, so a row's key (and its open details) go with it
  const shown = useMemo(() => {
    const at = rows.map((r, i) => ({ r, i }));
    if (!sortCol || !auto) return at;
    return sortByValues(at, valuesOf(sortCol).values, auto.desc);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, auto, sortCol?.key]);
  const autoSort = (c: Column<R>) => setAuto((a) => (a?.key === c.key ? { key: c.key, desc: !a.desc } : { key: c.key, desc: firstDesc(kindAt(c)) }));
  const sortState = page ? { key: page.key, desc: page.desc } : auto;
  const onSort = (c: Column<R>) => (page ? page.onSort(c.key) : autoSort(c));
  const file = typeof csv === "string" ? { name: csv, rows: allRows } : csv ? { name: csv.name, rows: csv.rows ?? allRows } : null;
  const allBox = (withText: boolean) => selectAll && allRows.length > 0 && (
    <label className={withText ? "k-check k-select-all" : "k-tap k-th-check"}>
      <input type="checkbox" checked={selectAll.on === true} aria-checked={selectAll.on === "mixed" ? "mixed" : selectAll.on}
        ref={(el) => { if (el) el.indeterminate = selectAll.on === "mixed"; }} onChange={() => selectAll.set(selectAll.on !== true)}
        aria-label={withText ? undefined : selectAll.label ?? "Select all"} />
      {withText && <span>{selectAll.label ?? "Select all"}</span>}
    </label>);
  const cardsNow = stack && phone;
  // a phone's cards have no header row: the table's own sort is a small "Sort by" select over them (a page sorting its rows itself has its own)
  const sortCols = cardsNow && !page ? columns.filter(canSort) : [];
  const kinds = useMemo(() => Object.fromEntries(sortCols.map((c) => [c.key, kindAt(c)])) as Record<string, SortKind>,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows, sortCols.length]);
  const dirWords = (k: SortKind | undefined, desc: boolean) => (k === "text" ? (desc ? "Z to A" : "A to Z") : k === "date" ? (desc ? "newest first" : "oldest first") : desc ? "high to low" : "low to high");
  const sortBy = sortCols.length > 0 && (
    <label className="k-sort-by">
      <span>Sort by</span>
      <select data-testid="k-sort-by" value={auto && sortCol ? `${auto.key}:${auto.desc ? "d" : "a"}` : ""} onChange={(e) => {
        const [key, d] = e.target.value.split(":");
        setAuto(key ? { key, desc: d === "d" } : null);
      }}>
        <option value="">As listed</option>
        {sortCols.flatMap((c) => {
          const first = firstDesc(kinds[c.key] ?? "text");
          return [first, !first].map((desc) => <option key={`${c.key}:${desc}`} value={`${c.key}:${desc ? "d" : "a"}`}>{headText(c)}, {dirWords(kinds[c.key], desc)}</option>);
        })}
      </select>
    </label>);
  // SCROLL BY SCREEN (owner, site87): a table taller than the screen gives it scrolls inside its block, its header row kept at the top, whole
  // rows at rest and the fade while more is below (the owner's reference: Movers); one that fits is drawn whole. A phone's cards the same.
  // AUTO-LOAD: nearing the end of the rows drawn asks the server for the next ones (no button)
  const loadMore = more && !more.busy && allRows.length < more.total ? more.load : undefined;
  useScrollRows(box, { items: bodyRows, onEnd: loadMore });
  // EXPORT in the card's "⋯" menu (csvInMenu): one entry there, kept up to date with the rows
  const frame = useSection();
  const setExtra = frame?.setExtra;
  const menuCsv = !!csvInMenu && !!frame?.on && !!file && file.rows.length > 0;
  const saveRef = useRef<() => void>(() => undefined);
  saveRef.current = () => { if (file) { const t = tableCsv(allColumns, file.rows); downloadCsv(csvName(file.name, istToday()), t.head, t.rows); } };
  const csvKey = `csv:${label}`;
  useEffect(() => {
    if (!setExtra) return;
    setExtra(csvKey, menuCsv ? { label: "Download CSV", run: () => saveRef.current(), testId: "card-menu-csv" } : null);
    return () => setExtra(csvKey, null);
  }, [setExtra, menuCsv, csvKey]);
  // "Report an error in this figure" (owner, 12 Nov): inside a ReportScope each row's name carries the flag, with the row's figures to pick from
  const scope = useReportScope();
  const figureCols = columns.filter((c) => !c.rowHeader && !c.action && c.numeric);
  const report = (r: R, name: ReactNode) => scope && (
    <ReportFigure label={cellText(name)} choices={() => (figureCols.length ? figureCols : columns.filter((c) => !c.rowHeader && !c.action))
      .map((c): [string, string] => [c.cardLabel ?? (typeof c.header === "string" ? c.header : textOf(c.header).trim()), cellText(c.cell(r)).trim()])
      .filter(([, v]) => v !== "" && !dashOnly(v))} />);
  return (
    <>
    {((file && file.rows.length > 0 && !menuCsv) || (cardsNow && selectAll && allRows.length > 0) || sortBy) && (
      <div className="k-tbl-tools">{cardsNow && allBox(true)}{sortBy}{file && file.rows.length > 0 && !menuCsv && <CsvButton name={file.name} label={label} columns={allColumns} rows={file.rows} />}</div>)}
    <div ref={box} data-grid={grid || scrollEnd ? "" : undefined} className={`k-tbl-wrap${stack ? " stack" : ""}${stack && compact ? " compact" : ""}${stack && columns.some((c) => c.lead) ? " has-lead" : ""}${stack && columns.some((c) => c.up) ? " has-up" : ""}${columns.some((c) => c.narrow === false || c.tight === false) ? " has-narrow" : ""}${fit ? " k-fit" : ""}${pinHead ? " pinhead" : ""}`} role="region" aria-label={stack && phone ? `${label}, as cards` : `${label}, scrolls sideways`} tabIndex={0}
      onScroll={scrollEnd ? (e) => markScrolled(e.currentTarget) : undefined}>
      <table className="k-table" aria-label={label} role={stack ? "table" : undefined}>
        <thead>
          <tr role={stack ? "row" : undefined}>{columns.map((c, ci) => {
            const by = canSort(c) ? (sortState ?? { key: "", desc: false }) : null;
            const on = !!sortState && by?.key === c.key && (!!page || !!sortCol);
            return (
              <th key={c.key} scope="col" role={stack ? "columnheader" : undefined} className={cls(c)} aria-sort={by ? (on ? (by.desc ? "descending" : "ascending") : "none") : undefined}>
                {/* a number column's (i) goes before its words, so the words end where the figures do (RC2B-027: "Of shares issued") */}
                {c.numeric && c.info && info(c)}
                {ci === 0 && !cardsNow && allBox(false)}
                {by ? <button type="button" className="k-th-sort" data-sort-key={c.key} onClick={() => onSort(c)}>{c.header}<span aria-hidden="true">{on ? (by.desc ? " ↓" : " ↑") : ""}</span></button>
                  : c.header === "" || c.header == null ? <span className="sr-only">{c.action ? "Actions" : c.key}</span> : c.header}
                {!c.numeric && c.info && info(c)}
              </th>
            );
          })}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td className="k-empty-row" colSpan={columns.length}>{empty}</td></tr>}
          {shown.map(({ r, i: ri }) => {
            const note = rowNote?.(r);
            const k = rowKey(r, ri), isOpen = !!detail && openRows.has(k), did = `${uid}-d-${ri}`;
            const attrs = rowAttrs?.(r) ?? {};
            const more = detail && (
              <button type="button" className="k-detail-btn" aria-expanded={isOpen} aria-controls={isOpen ? did : undefined} onClick={() => toggle(k)}>
                {detail.label}<span aria-hidden="true">{isOpen ? " ▴" : " ▾"}</span></button>);
            return (
              <Fragment key={k}>
              <tr role={stack ? "row" : undefined} {...attrs} className={[attrs.className, isOpen && "k-open"].filter(Boolean).join(" ") || undefined}>
                {columns.map((c, i) => {
                  if (note !== undefined && i > 0) return i === 1 ? <td key={c.key} colSpan={columns.length - 1} className="k-row-note">{note}</td> : null;
                  const label = c.cardLabel ?? (typeof c.header === "string" ? c.header : textOf(c.header).trim() || undefined);
                  const v = minusNode(c.cell(r));
                  // TABLE-SWEEP: an empty cell is marked, so a phone card leaves it out instead of a label over nothing; a compact phone row
                  // leaves out a lone dash too, and so does any phone card's lead cell (e79, LIVE15A-014: Cement's 15 lone "–" quote lines)
                  const blank = v == null || v === "" || v === false || (cardsNow && (!!compact || !!c.lead) && !c.rowHeader && dashOnly(cellText(v)));
                  return c.rowHeader ? <th key={c.key} scope="row" role={stack ? "rowheader" : undefined} className={cls(c)}>{v}{more}{report(r, v)}</th>
                    : <td key={c.key} role={stack ? "cell" : undefined} data-label={label} data-blank={blank ? "" : undefined} className={cls(c)}>{v}</td>;
                })}
              </tr>
              {isOpen && (
                <tr id={did} className={["k-detail-row", attrs.className].filter(Boolean).join(" ")} role={stack ? "row" : undefined}>
                  <td colSpan={columns.length} role={stack ? "cell" : undefined}>{detail!.render(r)}</td>
                </tr>
              )}
              </Fragment>
            );
          })}
        </tbody>
        {foot && rows.length > 0 && (
          <tfoot>
            <tr role={stack ? "row" : undefined}>{columns.map((c, i) => (i === 0 ? <th key={c.key} scope="row" role={stack ? "rowheader" : undefined}>{foot[c.key]}</th>
              : <td key={c.key} role={stack ? "cell" : undefined} data-label={typeof c.header === "string" ? c.header : textOf(c.header).trim() || undefined}
                  data-blank={foot[c.key] == null || foot[c.key] === "" ? "" : undefined} className={c.numeric ? "k-num" : undefined}>{foot[c.key]}</td>))}</tr>
          </tfoot>
        )}
      </table>
    </div>
    {more && allRows.length > 0 && (
      <p className="k-note k-loaded" aria-live="polite" data-testid="k-loaded">
        Loaded {allRows.length.toLocaleString("en-IN")} of {Math.max(more.total, allRows.length).toLocaleString("en-IN")}{more.noun ? ` ${more.noun}` : ""}{more.busy ? "; loading more…" : allRows.length < more.total ? "; more load as you scroll" : ""}
      </p>
    )}
    </>
  );
}
