import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Info } from "../ui";
import { textOf } from "./Card";
import { minusNode } from "../../lib/format";
import { scrollToEnd } from "../../lib/phoneFit";

export type Column<R> = {
  key: string;
  header: ReactNode;
  info?: ReactNode;                          // an (i) in the header
  numeric?: boolean;                         // right-aligned, in the header too
  rowHeader?: boolean;                       // the cell that names the row (a stock): read as the row's header
  wrap?: boolean;                            // lets long text in this column wrap (a name with notes under it)
  action?: boolean;                          // the last column's buttons (Edit, Remove): as narrow as they are, right-aligned
  sortable?: boolean;                        // the header is a button that sorts by this column (needs the table's `sort`)
  cell: (row: R) => ReactNode;
  cardLabel?: string;                        // the figure's name on a phone card when the header isn't plain text (R88-003)
  up?: boolean;                              // on a phone card, this figure comes right under the row's name with its label, ahead of the other columns: the gain, not the ninth figure (VR1-147)
  lead?: boolean;                            // on a phone card (`stack`), this cell comes right under the row's name, across the card: the answer first (DE-004, DE-035)
};

const info = (c: { header?: ReactNode; info?: ReactNode }) => <Info label={`About ${typeof c.header === "string" ? c.header.toLowerCase() : "this column"}`}>{c.info}</Info>;
const cls = (c: { numeric?: boolean; wrap?: boolean; action?: boolean; lead?: boolean; up?: boolean }) =>
  [c.numeric && "k-num", c.wrap && "k-wrap", c.action && "k-act", c.lead && "k-lead", c.up && "k-first"].filter(Boolean).join(" ") || undefined;

/** The one table: a header row, right-aligned numbers, a hover row, and its own horizontal scroll box so a wide table
 * never makes the page scroll sideways. `label` names the table for screen readers. `rowNote` turns a row into its
 * first cell plus one line of words across the rest (a stock with no data). An empty list shows `empty` in one row. */
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

export function DataTable<R>({ label, columns, rows: allRows, rowKey, empty = "Nothing to show yet.", rowAttrs, rowNote, foot, sticky: _sticky, stack: stackProp, grid, pinHead, sort, phonePage, scrollEnd }: {
  label: string; columns: Column<R>[]; rows: R[]; rowKey: (row: R, index: number) => string; empty?: ReactNode;
  /** No longer used: a long table scrolls with the page, never in a box of its own. Kept so callers need not change. */
  sticky?: boolean;
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
  /** Which column the rows are sorted by now, and what a click on a sortable header does. */
  sort?: { key: string; desc: boolean; onSort: (key: string) => void };
  /** A totals row under the rows: a cell for each column key (the first column's names the row). */
  foot?: Record<string, ReactNode>;
  rowAttrs?: (row: R) => Record<string, string>; rowNote?: (row: R) => ReactNode | undefined;
  /** With `stack`: on a phone, this many cards at a time, then "Show more" (R6O-018: 352 ETF cards made one 13,000 px page). */
  phonePage?: number;
}) {
  const phone = usePhone();
  // a table that does not fit the phone is read as cards, however few its columns (a watchlist's Actions column sat off the edge); `spill` is set after
  // a first look at the drawn table
  const [spill, setSpill] = useState(false);
  const stack = stackProp ?? (!grid && !scrollEnd && (columns.length >= 5 || spill));
  const [pages, setPages] = useState(1);
  useEffect(() => { setPages(1); }, [allRows.length]);
  const box = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!phone) { setSpill(false); return; }
    const b = box.current;
    if (stackProp === undefined && !grid && !scrollEnd && !pinHead && !spill && b && b.scrollWidth > b.clientWidth + 2) setSpill(true);
  }, [phone, spill, stackProp, grid, scrollEnd, pinHead, allRows.length, columns.length]);
  useLayoutEffect(() => { if (scrollEnd) scrollToEnd(box.current); }, [scrollEnd, columns.length, allRows.length]);
  const cap = stack && phonePage && phone ? phonePage * pages : Infinity;
  const rows = allRows.length > cap ? allRows.slice(0, cap) : allRows;
  const left = allRows.length - rows.length;
  return (
    <>
    <div ref={box} data-grid={grid || scrollEnd ? "" : undefined} className={`k-tbl-wrap${stack ? " stack" : ""}${stack && columns.some((c) => c.lead) ? " has-lead" : ""}${stack && columns.some((c) => c.up) ? " has-up" : ""}${pinHead ? " pinhead" : ""}`} role="region" aria-label={stack && phone ? `${label}, as cards` : `${label}, scrolls sideways`} tabIndex={0}>
      <table className="k-table" aria-label={label} role={stack ? "table" : undefined}>
        <thead>
          <tr role={stack ? "row" : undefined}>{columns.map((c) => {
            const by = sort && c.sortable ? sort : null;
            const on = by?.key === c.key;
            return (
              <th key={c.key} scope="col" role={stack ? "columnheader" : undefined} className={cls(c)} aria-sort={by ? (on ? (by.desc ? "descending" : "ascending") : "none") : undefined}>
                {/* a number column's (i) goes before its words, so the words end where the figures do (RC2B-027: "Of shares issued") */}
                {c.numeric && c.info && info(c)}
                {by ? <button type="button" className="k-th-sort" onClick={() => by.onSort(c.key)}>{c.header}<span aria-hidden="true">{on ? (by.desc ? " ↓" : " ↑") : ""}</span></button>
                  : c.header === "" || c.header == null ? <span className="sr-only">{c.action ? "Actions" : c.key}</span> : c.header}
                {!c.numeric && c.info && info(c)}
              </th>
            );
          })}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td className="k-empty-row" colSpan={columns.length}>{empty}</td></tr>}
          {rows.map((r, ri) => {
            const note = rowNote?.(r);
            return (
              <tr key={rowKey(r, ri)} role={stack ? "row" : undefined} {...rowAttrs?.(r)}>
                {columns.map((c, i) => {
                  if (note !== undefined && i > 0) return i === 1 ? <td key={c.key} colSpan={columns.length - 1} className="k-row-note">{note}</td> : null;
                  const label = c.cardLabel ?? (typeof c.header === "string" ? c.header : textOf(c.header).trim() || undefined);
                  return c.rowHeader ? <th key={c.key} scope="row" role={stack ? "rowheader" : undefined} className={cls(c)}>{minusNode(c.cell(r))}</th>
                    : <td key={c.key} role={stack ? "cell" : undefined} data-label={label} className={cls(c)}>{minusNode(c.cell(r))}</td>;
                })}
              </tr>
            );
          })}
        </tbody>
        {foot && rows.length > 0 && (
          <tfoot>
            <tr role={stack ? "row" : undefined}>{columns.map((c, i) => (i === 0 ? <th key={c.key} scope="row" role={stack ? "rowheader" : undefined}>{foot[c.key]}</th>
              : <td key={c.key} role={stack ? "cell" : undefined} data-label={typeof c.header === "string" ? c.header : textOf(c.header).trim() || undefined} className={c.numeric ? "k-num" : undefined}>{foot[c.key]}</td>))}</tr>
          </tfoot>
        )}
      </table>
    </div>
    {left > 0 && (
      <div className="k-row">
        <span className="k-note">Showing {rows.length} of {allRows.length}.</span>
        <button type="button" className="btn quiet sm" onClick={() => setPages((n) => n + 1)}>Show {Math.min(left, phonePage ?? left)} more</button>
      </div>
    )}
    </>
  );
}
