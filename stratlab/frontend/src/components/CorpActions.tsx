import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { price, safeHref, fmtDate } from "../lib/format";
import type { Region } from "../lib/research";
import { Badge, ErrorState, Skeleton } from "./kit";

/* Corporate actions: dividends, bonus issues, splits, buybacks, rights issues and demergers, by ex-date. */

export type ActionKind = "dividend" | "bonus" | "split" | "buyback" | "rights" | "demerger";
export interface CorpAction {
  id: string; region: Region; symbol: string; name: string | null; kind: ActionKind; label: string; text: string;
  amount: number | null; ratio: number[] | null; factor: number | null; currency: string;
  ex_date: string; record_date: string | null; purpose: string; src: string; url?: string | null; mine?: boolean;
  /** a dividend declared before a later bonus or split: its amount in today's shares, and why (DD-013) */ now_amount?: number | null; now_note?: string | null;
  /** a trust's distribution, part by part (interest, dividend, capital repayment): DE-029 */
  parts?: { label: string; amount: number | null }[]; pay_date?: string | null;
}
export const KIND_NAME: Record<ActionKind, string> = {
  dividend: "Dividends and distributions", bonus: "Bonus issues", split: "Splits", buyback: "Buybacks", rights: "Rights issues", demerger: "Demergers and spin-offs",
};

/** The dates under an action. Under a day's "Ex-date …" heading the ex-date isn't said again (DE-031), only the record
 * date (and the pay date, where the company gave one). */
export function actionDates(a: Pick<CorpAction, "ex_date" | "record_date" | "pay_date">, year = false, showEx = true): string {
  const rec = a.record_date && a.record_date !== a.ex_date ? `record date ${exDay(a.record_date, year)}` : a.record_date ? (showEx ? "" : "record date the same day") : "";
  const pay = a.pay_date ? `paid ${exDay(a.pay_date, year)}` : "";
  if (showEx) return [`Ex-date ${exDay(a.ex_date, year)}${a.record_date && a.record_date === a.ex_date ? " (also the record date)" : ""}`, rec, pay].filter(Boolean).join(" · ");
  const rest = [rec, pay].filter(Boolean).join(" · ");
  return rest ? rest[0].toUpperCase() + rest.slice(1) : "";
}

/** "Thu 15 Oct", from an ISO date, without the browser's time zone moving it a day. */
export function exDay(iso: string, year = false) {
  return fmtDate(iso.slice(0, 10), { weekday: !year, year });
}

/** One action: what it is, its ex-date and record date. */
export function ActionLine({ a, showSymbol = true, year = false, showEx = true }: { a: CorpAction; showSymbol?: boolean; year?: boolean; showEx?: boolean }) {
  const dates = actionDates(a, year, showEx);
  return (
    <div className="inv-row">
      {showSymbol && (
        <span className="k-row">
          <Link className="btn quiet sm" to={`/research/${a.region}/${encodeURIComponent(a.symbol)}`}><b>{a.symbol}</b></Link>
          {a.name && <span className="k-small k-muted">{a.name}</span>}
          {a.mine && <Badge tone="plain" dot={false}>Yours</Badge>}
        </span>
      )}
      <span className="k-small"><Badge tone="plain" dot={false}>{a.label}</Badge> {a.text.toLowerCase().startsWith(a.label.toLowerCase()) ? a.text.slice(a.label.length).replace(/^[\s:·-]+/, "") : a.text}
        {a.now_note && <span className="k-sub-line" data-testid="div-now">{a.now_note}</span>}</span>
      {(dates || a.url) && (
        <span className="k-note">
          {dates}
          {a.url && <>{dates ? " · " : ""}<a className="link" href={safeHref(a.url)} target="_blank" rel="noopener noreferrer">Notice ↗</a></>}
        </span>
      )}
    </div>
  );
}

interface CompanyActions {
  ahead: CorpAction[]; past: CorpAction[]; dividends_12m: { amount: number; count: number; currency: string; adjusted?: boolean } | null; ahead_known: boolean; note: string;
}

/** The company page's panel: actions ahead and the last three years'. */
export function CompanyActions({ region, symbol }: { region: Region; symbol: string }) {
  const [data, setData] = useState<CompanyActions | null>(null);
  const [failed, setFailed] = useState(false);
  const [all, setAll] = useState(false);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let live = true;
    setData(null); setFailed(false);
    api<CompanyActions>(`/research/corp-actions/${region}/${encodeURIComponent(symbol)}`).then((x) => live && setData(x)).catch(() => live && setFailed(true));
    return () => { live = false; };
  }, [region, symbol, tries]);
  if (failed) return <ErrorState title="Corporate actions are unavailable right now" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }} />;
  if (!data) return <Skeleton label="Reading the corporate actions" lines={3} />;
  const past = all ? data.past : data.past.slice(0, 5);
  const ccy = region === "IN" ? "INR" : "USD";
  return (
    <div className="k-stack">
      {data.dividends_12m && (
        <span className="k-small">Dividends with an ex-date in the last 12 months: <b>{price(data.dividends_12m.amount, ccy)}</b> a share{data.dividends_12m.adjusted ? " in today's shares" : ""} ({data.dividends_12m.count} payment{data.dividends_12m.count === 1 ? "" : "s"})</span>
      )}
      {/* what is ahead and what has been, side by side where there is room: one under the other left a wide card half empty (UI-FIX-1, R2) */}
      <div className="inv-pair">
      <div className="k-stack">
        <span className="k-eyebrow">Coming up: dividends and splits</span>
        {data.ahead.length ? <div className="inv-rows">{data.ahead.map((a) => <ActionLine key={a.id} a={a} showSymbol={false} />)}</div>
          : <span className="k-small k-muted">{data.ahead_known ? (region === "US" ? "No dividend declared with an ex-date in the next four weeks." : "Nothing announced with an ex-date ahead.") : "Dividends declared for the next four weeks couldn't be read yet, so none is listed. A split ahead isn't listed until its ex-date; past ones are below."}</span>}
      </div>
      <div className="k-stack">
        <span className="k-eyebrow">Past three years</span>
        {past.length ? <div className="inv-rows">{past.map((a) => <ActionLine key={a.id} a={a} showSymbol={false} year />)}</div> : <span className="k-small k-muted">None on record.</span>}
        {data.past.length > 5 && <button className="btn quiet sm k-btn-end" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${data.past.length}`}</button>}
      </div>
      </div>
      <Link className="link k-small" to={`/research/corporate-actions?region=${region}`}>Every company's corporate actions →</Link>
    </div>
  );
}
