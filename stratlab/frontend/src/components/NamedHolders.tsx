import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { safeHref, fmtDate } from "../lib/format";
import { DataTable, ErrorState, Signed, Skeleton } from "./kit";

/* Named holders above 1% from the quarterly shareholding pattern (shareholders.py): the promoter group's members and
 * every public holder above 1%, by stake size, with the change since the quarter before. Names and numbers as filed. */

export type HolderChange = "new" | "up" | "down" | "same" | "dropped" | null;
export interface NamedHolder {
  name: string; kind: string; group: "promoter" | "public"; shares: number; pct: number;
  prev_pct: number | null; prev_shares: number | null; change: HolderChange; pct_change: number | null;
}
export interface CompanyHolders {
  symbol: string; name: string; quarter: string; prev_quarter: string | null; filed: string | null; url: string | null;
  holders: NamedHolder[]; dropped: { name: string; kind: string; group: string; prev_pct: number; prev_shares: number }[];
  note: string; search: boolean;
  /** false when nothing is filed (not on NSE, or no filing yet): the section is left out */
  available?: boolean;
}

/** Whether a pattern's date is a quarter's last day; one filed for an allotment or a listing is dated that day. */
export function isQuarterEnd(iso: string | null | undefined) {
  return !!iso && ["03-31", "06-30", "09-30", "12-31"].includes(iso.slice(5, 10));
}

export function quarterEnd(iso: string | null | undefined) {
  if (!iso) return "–";
  const s = fmtDate(iso);
  return s === "–" ? iso : s;
}

export function shares(n: number | null | undefined) {
  return n == null ? "–" : Math.round(n).toLocaleString("en-IN");
}

/** "New", "+0.81 pts", "−0.21 pts", "No change": the change since the quarter before, in plain words. */
export function changeText(c: HolderChange, d: number | null) {
  if (c === "new") return "New above 1%";
  if (c === "dropped") return "Below 1% or out";
  if (c === "same") return "No change";
  if ((c === "up" || c === "down") && d != null) return `${d > 0 ? "+" : d < 0 ? "−" : ""}${Math.abs(d).toFixed(2)} pts`;
  if (c === "up") return "More shares";
  if (c === "down") return "Fewer shares";
  return "–";
}

/** The same change, in the kit's colours: a bigger stake green, a smaller one red, the words unchanged. */
export function ChangeText({ c, d }: { c: HolderChange; d: number | null }) {
  const dir = c === "up" ? 1 : c === "down" ? -1 : 0;
  return <Signed value={d != null && d !== 0 ? d : dir}>{changeText(c, d)}</Signed>;
}

export function NamedHoldersPanel({ symbol, wrap }: { symbol: string; wrap: (body: React.ReactNode, right?: React.ReactNode) => React.ReactNode }) {
  const [v, setV] = useState<CompanyHolders | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [none, setNone] = useState(false);
  const [all, setAll] = useState(false);

  useEffect(() => {
    let live = true;
    setV(null); setError(null); setNone(false);
    api<CompanyHolders>(`/research/holders/${encodeURIComponent(symbol)}`)
      .then((x) => { if (!live) return; if (x.available === false) setNone(true); else setV(x); })       // not listed on NSE, or nothing filed
      .catch((e) => live && setError(e instanceof Error ? e.message : "Couldn't read the shareholding filing."));
    return () => { live = false; };
  }, [symbol]);

  if (none) return null;
  if (error) return wrap(<ErrorState title="The shareholding filing couldn't be read">{error}</ErrorState>);
  if (!v) return wrap(<Skeleton label="Reading the shareholding filing" lines={3} />);
  const list = all ? v.holders : v.holders.slice(0, 12);
  const right = v.search ? <Link className="btn quiet sm" to="/invest/holders">Search a holder</Link> : null;
  return wrap(
    <div className="k-stack named-holders">
      <span className="k-small">{isQuarterEnd(v.quarter) ? "Quarter to" : "As of"} <b>{quarterEnd(v.quarter)}</b>{v.prev_quarter ? <> · changes since {quarterEnd(v.prev_quarter)}</> : null}
        {v.url && <> · <a className="link" href={safeHref(v.url)} target="_blank" rel="noopener noreferrer">Filing ↗</a></>}</span>
      {v.holders.length === 0 ? <p className="k-small k-muted">The filing names no holder above 1%.</p> : (
        <DataTable label={`${v.symbol} named holders`} rows={list} rowKey={(h) => `${h.group}-${h.name}`} sticky={list.length > 14} rowAttrs={(h) => ({ "data-holder": h.name })}
          columns={[
            { key: "n", header: "Holder", rowHeader: true, wrap: true, cell: (h) => <>{h.name}<span className="k-sub-line">{h.group === "promoter" ? "Promoter group · " : ""}{h.kind}</span></> },
            { key: "s", header: "Shares", numeric: true, cell: (h) => shares(h.shares) },
            { key: "p", header: "Stake", numeric: true, cell: (h) => `${h.pct.toFixed(2)}%` },
            { key: "c", header: "Since last quarter", numeric: true, cell: (h) => <><ChangeText c={h.change} d={h.pct_change} />{h.prev_pct != null && h.change !== "same" && <span className="k-sub-line">was {h.prev_pct.toFixed(2)}%</span>}</> },
          ]} />
      )}
      {v.holders.length > list.length && <button className="btn quiet sm k-btn-end" onClick={() => setAll(true)}>Show all {v.holders.length}</button>}
      {v.dropped.length > 0 && <p className="k-small"><span className="k-muted">Listed last quarter, not this one (below 1%, or sold):</span>{" "}
        {v.dropped.map((d) => `${d.name} (${d.prev_pct.toFixed(2)}%)`).join("; ")}</p>}
      <p className="k-note">{v.note}{!v.search && <> Searching a holder across companies and following one is on the <Link className="link" to="/plans">Basic plan</Link>.</>}</p>
    </div>, right);
}

