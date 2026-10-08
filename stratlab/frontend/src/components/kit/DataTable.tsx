import { useEffect, useState, type ReactNode } from "react";
import { Info } from "../ui";
import { minusNode } from "../../lib/format";

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
};

const cls = (c: { numeric?: boolean; wrap?: boolean; action?: boolean }) => [c.numeric && "k-num", c.wrap && "k-wrap", c.action && "k-act"].filter(Boolean).join(" ") || undefined;

/** The one table: a header row, right-aligned numbers, a hover row, and its own horizontal scroll box so a wide table
 * never makes the page scroll sideways. `label` names the table for screen readers. `rowNote` turns a row into its
 * first cell plus one line of words across the rest (a stock with no data). An empty list shows `empty` in one row. */
/** Whether the page is at phone width (where a `stack` table is a list of cards). */
function usePhone(): boolean {
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

export function DataTable<R>({ label, columns, rows: allRows, rowKey, empty = "Nothing to show yet.", rowAttrs, rowNote, foot, sticky: _sticky, stack, pinHead, sort, phonePage }: {
  label: string; columns: Column<R>[]; rows: R[]; rowKey: (row: R) => string; empty?: ReactNode;
  /** No longer used: a long table scrolls with the page, never in a box of its own. Kept so callers need not change. */
  sticky?: boolean;
  /** On a phone, each row becomes a card (the first column as its title, every other cell under its own column name),
   * so nothing is cut off at the edge and the figures that matter are all in view. Desktop is unchanged. */
  stack?: boolean;
  /** A table that fits its card (a few narrow columns) keeps its header row in view while the page scrolls past it. */
  pinHead?: boolean;
  /** Which column the rows are sorted by now, and what a click on a sortable header does. */
  sort?: { key: string; desc: boolean; onSort: (key: string) => void };
  /** A totals row under the rows: a cell for each column key (the first column's names the row). */
  foot?: Record<string, ReactNode>;
  rowAttrs?: (row: R) => Record<string, string>; rowNote?: (row: R) => ReactNode | undefined;
  /** With `stack`: on a phone, this many cards at a time, then "Show more" (R6O-018: 352 ETF cards made one 13,000 px page). */
  phonePage?: number;
}) {
  const phone = usePhone();
  const [pages, setPages] = useState(1);
  useEffect(() => { setPages(1); }, [allRows.length]);
  const cap = stack && phonePage && phone ? phonePage * pages : Infinity;
  const rows = allRows.length > cap ? allRows.slice(0, cap) : allRows;
  const left = allRows.length - rows.length;
  return (
    <>
    <div className={`k-tbl-wrap${stack ? " stack" : ""}${pinHead ? " pinhead" : ""}`} role="region" aria-label={`${label}, scrolls sideways`} tabIndex={0}>
      <table className="k-table" aria-label={label} role={stack ? "table" : undefined}>
        <thead>
          <tr role={stack ? "row" : undefined}>{columns.map((c) => {
            const by = sort && c.sortable ? sort : null;
            const on = by?.key === c.key;
            return (
              <th key={c.key} scope="col" role={stack ? "columnheader" : undefined} className={cls(c)} aria-sort={by ? (on ? (by.desc ? "descending" : "ascending") : "none") : undefined}>
                {by ? <button type="button" className="k-th-sort" onClick={() => by.onSort(c.key)}>{c.header}<span aria-hidden="true">{on ? (by.desc ? " ↓" : " ↑") : ""}</span></button>
                  : c.header === "" || c.header == null ? <span className="sr-only">{c.action ? "Actions" : c.key}</span> : c.header}
                {c.info && <Info label={`About ${typeof c.header === "string" ? c.header.toLowerCase() : "this column"}`}>{c.info}</Info>}
              </th>
            );
          })}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td className="k-empty-row" colSpan={columns.length}>{empty}</td></tr>}
          {rows.map((r) => {
            const note = rowNote?.(r);
            return (
              <tr key={rowKey(r)} role={stack ? "row" : undefined} {...rowAttrs?.(r)}>
                {columns.map((c, i) => {
                  if (note !== undefined && i > 0) return i === 1 ? <td key={c.key} colSpan={columns.length - 1} className="k-row-note">{note}</td> : null;
                  const label = typeof c.header === "string" ? c.header : undefined;
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
              : <td key={c.key} role={stack ? "cell" : undefined} data-label={typeof c.header === "string" ? c.header : undefined} className={c.numeric ? "k-num" : undefined}>{foot[c.key]}</td>))}</tr>
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
