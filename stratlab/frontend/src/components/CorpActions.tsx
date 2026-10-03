import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money, price, qty as qtyText, safeHref } from "../lib/format";
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

/* ---------- My Holdings ---------- */
interface IncomeLine { symbol: string; label: string; ex_date: string; record_date: string | null; amount: number; qty: number; total: number }
interface Notice {
  symbol: string; id: string; kind: string; label: string; text: string; text_action: string; ex_date: string;
  from_qty: number; to_qty: number; from_avg: number | null; to_avg: number | null; more: number;
}
export interface HoldingsActions {
  ahead: IncomeLine[]; ahead_total: number; received: IncomeLine[]; received_total: number; notices: Notice[];
  undo: { symbol: string; id: string; label: string; qty: number; avg: number | null }[]; checking: number; today: string;
}

const inr = (v: number) => money(v, "INR", 0);

/** Bonuses and splits since the holdings were saved (offered, never made silently), and dividend income. */
export function HoldingsActionsPanel<V>({ onHoldings, version }: { onHoldings: (v: V) => void; version: number }) {
  const { fail, notify } = useApp();
  const [data, setData] = useState<HoldingsActions | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    let live = true;
    api<HoldingsActions>("/holdings/corp-actions").then((x) => live && setData(x)).catch(() => live && setData(null));
    return () => { live = false; };
  }, [version]);

  const act = async (symbol: string, id: string, action: "apply" | "dismiss" | "undo", done: string) => {
    setBusy(`${symbol}:${action}`);
    try {
      const r = await api<{ holdings: V; actions: HoldingsActions }>("/holdings/corp-actions", { method: "POST", body: { symbol, id, action } });
      setData(r.actions);
      onHoldings(r.holdings);
      notify(done);
    } catch (e) { fail(e); } finally { setBusy(null); }
  };

  if (!data) return null;
  const received = showAll ? data.received : data.received.slice(0, 6);
  return (
    <>
      {data.notices.map((n) => (
        <div key={n.id} className="banner ca-notice" role="status">
          <div className="stack" style={{ gap: 4, minWidth: 0 }}>
            <b>{n.text}</b>
            <span className="small muted">{n.text_action}. Your saved quantity ({qtyText(n.from_qty)}{n.from_avg != null ? ` at ${price(n.from_avg, "INR")}` : ""}) is from before it. Apply it, or keep it as it is if your broker's file already showed the new quantity.{n.more > 0 ? ` ${n.more} more for ${n.symbol} after this one.` : ""}</span>
          </div>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <button className="btn sm" disabled={!!busy} onClick={() => act(n.symbol, n.id, "apply", `${n.symbol}: quantity ${qtyText(n.to_qty)}${n.to_avg != null ? `, average price ${price(n.to_avg, "INR")}` : ""}.`)}>Apply</button>
            <button className="btn quiet sm" disabled={!!busy} onClick={() => act(n.symbol, n.id, "dismiss", `${n.symbol} kept as it is.`)}>Already in my file</button>
          </div>
        </div>
      ))}
      {data.undo.length > 0 && (
        <p className="tiny muted" style={{ margin: 0 }}>
          Adjusted for corporate actions: {data.undo.map((u, i) => (
            <span key={u.symbol}>{i > 0 && " · "}{u.symbol} ({u.label}) <button className="btn quiet sm" disabled={!!busy} onClick={() => act(u.symbol, u.id, "undo", `${u.symbol} is back to ${qtyText(u.qty)} shares.`)}>Undo</button></span>
          ))}
        </p>
      )}
      {(data.ahead.length > 0 || data.received.length > 0) && (
        <section className="card stack" style={{ gap: 12 }}>
          <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
            <h2 className="h2">Dividends</h2>
            <Link className="link small" to="/research/corporate-actions?region=IN">Corporate actions calendar →</Link>
          </div>
          <div className="stat-row">
            <div className="stat"><span className="tiny muted">Announced, ex-date ahead</span><b className="num">{inr(data.ahead_total)}</b></div>
            <div className="stat"><span className="tiny muted">Last 12 months (estimated)</span><b className="num">{inr(data.received_total)}</b></div>
          </div>
          {data.ahead.length > 0 && (
            <div className="table-wrap">
              <table aria-label="Dividends ahead">
                <thead><tr><th>Stock</th><th style={{ textAlign: "left" }}>Dividend</th><th>Ex-date</th><th>A share</th><th>Shares</th><th>Amount</th></tr></thead>
                <tbody>{data.ahead.map((d) => <IncomeRow key={`${d.symbol}-${d.ex_date}-${d.label}`} d={d} />)}</tbody>
              </table>
            </div>
          )}
          {received.length > 0 && (
            <div className="table-wrap">
              <table aria-label="Dividends in the last 12 months">
                <thead><tr><th>Stock</th><th style={{ textAlign: "left" }}>Dividend</th><th>Ex-date</th><th>A share</th><th>Shares</th><th>Amount</th></tr></thead>
                <tbody>{received.map((d) => <IncomeRow key={`${d.symbol}-${d.ex_date}-${d.label}`} d={d} />)}</tbody>
              </table>
            </div>
          )}
          {data.received.length > 6 && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${data.received.length}`}</button>}
          <p className="tiny muted" style={{ margin: 0 }}>Amount a share as the company announced it, times the shares you'd hold on the ex-date. The last 12 months assume you held today's quantity throughout (worked back through any bonus or split), so they're an estimate; amounts are before tax.{data.checking > 0 ? ` Still reading the history of ${data.checking} stock${data.checking === 1 ? "" : "s"}; reload in a minute.` : ""}</p>
        </section>
      )}
    </>
  );
}

function IncomeRow({ d }: { d: IncomeLine }) {
  return (
    <tr>
      <td><Link className="link" to={`/research/IN/${encodeURIComponent(d.symbol)}`}><b>{d.symbol}</b></Link></td>
      <td style={{ textAlign: "left" }} className="small">{d.label}</td>
      <td className="small">{exDay(d.ex_date, true)}</td>
      <td className="num">{price(d.amount, "INR")}</td>
      <td className="num">{qtyText(Math.round(d.qty * 10000) / 10000)}</td>
      <td className="num">{inr(d.total)}</td>
    </tr>
  );
}
