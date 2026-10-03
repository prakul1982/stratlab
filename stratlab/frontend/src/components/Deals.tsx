import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { safeHref } from "../lib/format";
import { Loading } from "./ui";

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
export function rupees(v: number | null) {
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

  useEffect(() => {
    let live = true;
    setRep(null); setError(null);
    api<DealsReport>(`/research/deals/${encodeURIComponent(symbol)}`)
      .then((r) => live && setRep(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : "Couldn't load the disclosures."));
    return () => { live = false; };
  }, [symbol]);

  if (error) return <p className="small muted">{error}</p>;
  if (!rep) return <Loading label="Reading the exchange disclosures" />;
  const kinds = (SHOW.find((s) => s[0] === show) ?? SHOW[0])[2];
  const rows = rep.items.filter((d) => kinds.includes(d.kind));
  const list = more ? rows : rows.slice(0, 12);
  return (
    <div className="stack deals" style={{ gap: 12 }}>
      <span className="small">{rep.flow_text
        ? <>Promoters and insiders on the open market, last {Math.round(rep.flow_days / 30)} months: <b>{rep.flow_text}</b>.</>
        : <span className="muted">No open-market trades by promoters or insiders disclosed in the last {Math.round(rep.flow_days / 30)} months.</span>}</span>
      <div className="seg" role="radiogroup" aria-label="Which disclosures">
        {SHOW.map(([id, label]) => (
          <button key={id} role="radio" aria-checked={show === id} aria-pressed={show === id} onClick={() => { setShow(id); setMore(false); }}>{label}</button>
        ))}
      </div>
      {rows.length === 0 ? <p className="small muted">None disclosed in the last year.</p> : (
        <div className="table-wrap deals-table">
          <table>
            <thead><tr><th>Who</th><th>Bought or sold</th><th className="num">Shares</th><th className="num">Value</th><th>Date</th><th>What</th><th>Source</th></tr></thead>
            <tbody>{list.map((d) => (
              <tr key={d.id}>
                <td><span className="deal-who">{d.who}</span>{d.relation && <span className="tiny muted"> {RELATION[d.relation]}</span>}</td>
                <td><span className={`badge ${d.side === "bought" ? "next" : "skip"}`}>{SIDE[d.side] ?? d.side}</span></td>
                <td className="num">{d.qty == null ? "–" : Math.round(d.qty).toLocaleString("en-IN")}</td>
                <td className="num">{rupees(d.value)}{d.kind !== "insider" && d.kind !== "sast" && d.price != null && <span className="tiny muted"> at ₹{d.price.toLocaleString("en-IN")}</span>}</td>
                <td className="mono small">{day(d.date)}</td>
                <td className="small">{d.label}{d.kind === "insider" || d.kind === "sast" ? <span className="tiny muted"> · {MODE[d.mode] ?? d.mode}</span> : null}
                  {d.pct_after != null && <span className="tiny muted"> · {d.pct_after.toFixed(2)}% after</span>}</td>
                <td><a className="link small" href={safeHref(d.url)} target="_blank" rel="noopener noreferrer">Disclosure ↗</a></td>
              </tr>))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > list.length && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setMore(true)}>Show all {rows.length}</button>}
      {rep.problems.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>Not available right now: {rep.problems.join(", ")}. Try again later.</p>}
      <p className="tiny muted" style={{ margin: 0 }}>From exchange disclosures over the last year, as filed: insider trades and pledges by promoters, directors and key staff, substantial acquisitions, and bulk and block deals. Facts, not advice.</p>
    </div>
  );
}
