import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { inr, safeHref } from "../lib/format";
import { Badge, DataTable, EmptyState, ErrorState, Seg, Skeleton } from "./kit";

export type DealKind = "insider" | "sast" | "bulk" | "block";
export interface Deal {
  id: string; kind: DealKind; label: string; symbol: string; date: string; filed: string; who: string;
  relation: "promoter" | "director" | "kmp" | "employee" | "other" | null;
  side: "bought" | "sold" | "pledged" | "released" | "invoked"; mode: "market" | "off_market" | "pledge" | "esop" | "other";
  mode_text: string | null; qty: number | null; price: number | null; value: number | null; pct_after: number | null; url: string;
}
export interface DealsReport {
  symbol: string; days: number; items: Deal[]; count: number; problems: string[]; flow_text: string | null; flow_days: number;
}

const SIDE: Record<Deal["side"], string> = { bought: "Bought", sold: "Sold", pledged: "Pledged", released: "Pledge released", invoked: "Pledge invoked" };
const RELATION: Record<string, string> = { promoter: "Promoter", director: "Director", kmp: "Key officer", employee: "Employee", other: "Other" };
const MODE: Record<string, string> = { market: "open market", off_market: "off market", pledge: "pledge", esop: "stock options", other: "other" };
const SHOW: [string, string, DealKind[]][] = [
  ["all", "All", ["insider", "sast", "bulk", "block"]], ["insider", "Promoters and insiders", ["insider", "sast"]],
  ["deals", "Bulk and block deals", ["bulk", "block"]],
];

function day(iso: string) {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** ₹2.4 cr, ₹35.0 lakh or ₹48,000: how amounts this size are usually written in India. */
function rupees(v: number | null) {
  if (v == null || !Number.isFinite(v)) return "–";
  if (v >= 1e7) return `₹${(v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} lakh`;
  return `₹${Math.round(v).toLocaleString("en-IN")}`;
}

/** An Indian company's deals and insider trades from exchange disclosures, as a dated table: who, which way, how
 * many, the value, when, and the disclosure. Facts as filed; nothing here is a call on the stock. */
export function DealsPanel({ symbol }: { symbol: string }) {
  const [rep, setRep] = useState<DealsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [show, setShow] = useState("all");
  const [more, setMore] = useState(false);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    setRep(null); setError(null);
    api<DealsReport>(`/research/deals/${encodeURIComponent(symbol)}`)
      .then((r) => live && setRep(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : "Couldn't load the disclosures."));
    return () => { live = false; };
  }, [symbol, tries]);

  if (error) return <ErrorState title="The disclosures couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>;
  if (!rep) return <Skeleton label="Reading the exchange disclosures" lines={3} />;
  const kinds = (SHOW.find((s) => s[0] === show) ?? SHOW[0])[2];
  const rows = rep.items.filter((d) => kinds.includes(d.kind));
  const list = more ? rows : rows.slice(0, 12);
  return (
    <div className="k-stack deals">
      <span className="k-small">{rep.flow_text
        ? <>Promoters and insiders on the open market, last {Math.round(rep.flow_days / 30)} months: <b>{rep.flow_text}</b>.</>
        : <span className="k-muted">No open-market trades by promoters or insiders disclosed in the last {Math.round(rep.flow_days / 30)} months.</span>}</span>
      <Seg label="Which disclosures" value={show} onChange={(v) => { setShow(v); setMore(false); }} options={SHOW.map(([id, label]) => ({ value: id, label }))} />
      {rows.length === 0 ? <EmptyState title="Nothing disclosed">None disclosed in the last year.</EmptyState> : (
        <div className="deals-table">
          <DataTable label={`${symbol} deals and insider trades`} rows={list} rowKey={(d) => d.id} sticky={list.length > 14}
            columns={[
              { key: "who", header: "Who", rowHeader: true, wrap: true, cell: (d) => <><span className="deal-who">{d.who}</span>{d.relation && <span className="k-sub-line">{RELATION[d.relation]}</span>}</> },
              { key: "side", header: "Bought or sold", cell: (d) => <Badge tone="plain" dot={false}>{SIDE[d.side] ?? d.side}</Badge> },
              { key: "qty", header: "Shares", numeric: true, cell: (d) => (d.qty == null ? "–" : Math.round(d.qty).toLocaleString("en-IN")) },
              { key: "val", header: "Value", numeric: true, cell: (d) => <>{rupees(d.value)}{d.kind !== "insider" && d.kind !== "sast" && d.price != null && <span className="k-sub-line">at {inr(d.price, d.price < 100 ? 2 : 0)}</span>}</> },
              { key: "date", header: "Date", cell: (d) => day(d.date) },
              { key: "what", header: "What", wrap: true, cell: (d) => <>{d.label}{d.kind === "insider" || d.kind === "sast" ? <span className="k-sub-line">{MODE[d.mode] ?? d.mode}{d.pct_after != null ? ` · ${d.pct_after.toFixed(2)}% after` : ""}</span>
                : d.pct_after != null ? <span className="k-sub-line">{d.pct_after.toFixed(2)}% after</span> : null}</> },
              { key: "src", header: "Source", cell: (d) => <a className="link" href={safeHref(d.url)} target="_blank" rel="noopener noreferrer">Disclosure ↗</a> },
            ]} />
        </div>
      )}
      {rows.length > list.length && <button className="btn quiet sm k-btn-end" onClick={() => setMore(true)}>Show all {rows.length}</button>}
      {rep.problems.length > 0 && <p className="k-note">Not available right now: {rep.problems.join(", ")}. Try again later.</p>}
      <p className="k-note">From exchange disclosures over the last year, as filed: insider trades and pledges by promoters, directors and key staff, substantial acquisitions, and bulk and block deals. Facts, not advice.</p>
    </div>
  );
}
