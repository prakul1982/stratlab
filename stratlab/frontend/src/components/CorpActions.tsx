import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { price, safeHref } from "../lib/format";
import type { Region } from "../lib/research";

/* Corporate actions: dividends, bonus issues, splits, buybacks, rights issues and demergers, by ex-date. */

export type ActionKind = "dividend" | "bonus" | "split" | "buyback" | "rights" | "demerger";
export interface CorpAction {
  id: string; region: Region; symbol: string; name: string | null; kind: ActionKind; label: string; text: string;
  amount: number | null; ratio: number[] | null; factor: number | null; currency: string;
  ex_date: string; record_date: string | null; purpose: string; src: string; url?: string | null; mine?: boolean;
}
export const KIND_NAME: Record<ActionKind, string> = {
  dividend: "Dividends", bonus: "Bonus issues", split: "Splits", buyback: "Buybacks", rights: "Rights issues", demerger: "Demergers",
};

/** "Thu 15 Oct", from an ISO date, without the browser's time zone moving it a day. */
export function exDay(iso: string, year = false) {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: year ? undefined : "short", day: "numeric", month: "short", year: year ? "numeric" : undefined });
}

/** One action: what it is, its ex-date and record date. */
export function ActionLine({ a, showSymbol = true, year = false }: { a: CorpAction; showSymbol?: boolean; year?: boolean }) {
  return (
    <div className="result-row">
      {showSymbol && (
        <span className="row wrap" style={{ gap: 8 }}>
          <Link className="btn quiet sm" to={`/research/${a.region}/${encodeURIComponent(a.symbol)}`}><b>{a.symbol}</b></Link>
          {a.name && <span className="small muted">{a.name}</span>}
          {a.mine && <span className="badge">Yours</span>}
        </span>
      )}
      <span className="small"><span className={`badge ca-${a.kind}`}>{a.label}</span> {a.text}</span>
      <span className="tiny muted">
        Ex-date {exDay(a.ex_date, year)}{a.record_date && a.record_date !== a.ex_date ? ` · record date ${exDay(a.record_date, year)}` : a.record_date ? " (also the record date)" : ""}
        {a.url && <> · <a className="link" href={safeHref(a.url)} target="_blank" rel="noopener noreferrer">Notice ↗</a></>}
      </span>
    </div>
  );
}

interface CompanyActions {
  ahead: CorpAction[]; past: CorpAction[]; dividends_12m: { amount: number; count: number; currency: string } | null; ahead_known: boolean; note: string;
}

/** The company page's panel: actions ahead and the last three years'. */
export function CompanyActions({ region, symbol }: { region: Region; symbol: string }) {
  const [data, setData] = useState<CompanyActions | null>(null);
  const [failed, setFailed] = useState(false);
  const [all, setAll] = useState(false);
  useEffect(() => {
    let live = true;
    setData(null); setFailed(false);
    api<CompanyActions>(`/research/corp-actions/${region}/${encodeURIComponent(symbol)}`).then((x) => live && setData(x)).catch(() => live && setFailed(true));
    return () => { live = false; };
  }, [region, symbol]);
  if (failed) return <p className="small muted">Corporate actions are unavailable right now.</p>;
  if (!data) return <div className="row muted small" style={{ gap: 8 }}><span className="spinner" />Reading the corporate actions…</div>;
  const past = all ? data.past : data.past.slice(0, 5);
  const ccy = region === "IN" ? "INR" : "USD";
  return (
    <div className="stack" style={{ gap: 12 }}>
      {data.dividends_12m && (
        <span className="small">Dividends with an ex-date in the last 12 months: <b className="num">{price(data.dividends_12m.amount, ccy)}</b> a share ({data.dividends_12m.count} payment{data.dividends_12m.count === 1 ? "" : "s"})</span>
      )}
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Coming up</span>
        {data.ahead.length ? data.ahead.map((a) => <ActionLine key={a.id} a={a} showSymbol={false} />)
          : <span className="small muted">{data.ahead_known ? "Nothing announced with an ex-date ahead." : "Dates ahead aren't available for US companies yet; past ones are below."}</span>}
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Past three years</span>
        {past.length ? past.map((a) => <ActionLine key={a.id} a={a} showSymbol={false} year />) : <span className="small muted">None on record.</span>}
        {data.past.length > 5 && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${data.past.length}`}</button>}
      </div>
      <Link className="link small" to={`/research/corporate-actions?region=${region}`}>Every company's corporate actions →</Link>
    </div>
  );
}
