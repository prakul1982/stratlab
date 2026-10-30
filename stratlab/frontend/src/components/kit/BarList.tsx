import type { ReactNode } from "react";
import { DataTable, usePhone, type Column } from "./DataTable";

/** A thin bar filled to `pct` percent (decoration; the figure beside it says the same in words). */
export function Meter({ pct }: { pct: number | null | undefined }) {
  return <div className="k-meter" aria-hidden="true"><i style={{ width: `${Math.max(1, Math.min(100, pct ?? 0))}%` }} /></div>;
}

export type ShareRow = { key: string; name: ReactNode; count?: ReactNode; detail?: ReactNode; value?: ReactNode; pct: number | null; title?: string };

/** A share of a whole as a table (TABLE-SWEEP, owner 29 Oct: "wherever you can, just make a table"): what it is, how many (when
 * the rows count something), what is in it, its amount, and its share with a thin bar under the figure. "By sector", "by asset
 * class". A column no row fills is left out, so no column stands half empty; `total` adds a row under them. It was a list of
 * bars, the share said only beside each bar. `pct` is 0 to 100. */
export function ShareTable({ label, rows, head = "Item", countHead = "Count", detailHead = "In it", valueHead = "Value", shareHead = "Share", total, footnote }: {
  label: string; rows: ShareRow[]; head?: string; countHead?: string; detailHead?: string; valueHead?: string; shareHead?: string;
  total?: { name: ReactNode; count?: ReactNode; value?: ReactNode; pct?: number | null }; footnote?: ReactNode;
}) {
  const phone = usePhone();
  const has = (k: "count" | "detail" | "value") => rows.some((r) => r[k] != null && r[k] !== "");
  const share = (pct: number | null | undefined) => <span className="dd-share"><span>{pct == null ? "–" : `${pct.toFixed(1)}%`}</span><Meter pct={pct} /></span>;
  // on a phone the count and what is in it go under the name, so the table stays three columns across (name, amount, share) and
  // each row one line of the table, not a card of its own (eleven cards made a 1,300px "By asset class" on a 360px phone)
  const under = (r: ShareRow) => phone && (has("count") || has("detail"))
    ? <span className="k-sub-line">{[has("count") && r.count != null && r.count !== "" ? <>{countHead}: {r.count}</> : null, has("detail") ? r.detail : null].filter(Boolean).map((x, i) => <span key={i}>{i > 0 && " · "}{x}</span>)}</span> : null;
  const cols: Column<ShareRow>[] = [
    { key: "n", header: head, rowHeader: true, wrap: true, cell: (r) => <><span title={r.title}>{r.name}</span>{under(r)}</> },
    ...(has("count") && !phone ? [{ key: "c", header: countHead, numeric: true, cell: (r: ShareRow) => r.count ?? "" } as Column<ShareRow>] : []),
    ...(has("detail") && !phone ? [{ key: "d", header: detailHead, wrap: true, cell: (r: ShareRow) => (r.detail ? <span className="k-note k-muted">{r.detail}</span> : "") } as Column<ShareRow>] : []),
    ...(has("value") ? [{ key: "v", header: valueHead, numeric: true, cell: (r: ShareRow) => r.value ?? "–" } as Column<ShareRow>] : []),
    { key: "s", header: shareHead, numeric: true, cell: (r) => share(r.pct) },
  ];
  const foot = total ? { n: total.name, c: total.count ?? "", d: "", v: total.value ?? "", s: total.pct === undefined ? "" : total.pct == null ? "–" : `${total.pct.toFixed(1)}%` } : undefined;
  return (
    <>
      <div className="k-share"><DataTable label={label} rows={rows} rowKey={(r) => r.key} columns={cols} foot={foot} stack={false} /></div>
      {footnote && <p className="k-note">{footnote}</p>}
    </>
  );
}
