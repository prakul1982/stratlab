import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { price, safeHref, fmtDate } from "../lib/format";
import type { Region } from "../lib/research";
import { Badge, DataTable, ErrorState, Skeleton } from "./kit";

/* Corporate actions: dividends, bonus issues, splits, buybacks, rights issues and demergers, by ex-date. */

export type ActionKind = "dividend" | "bonus" | "split" | "buyback" | "rights" | "demerger";
export interface CorpAction {
  id: string; region: Region; symbol: string; name: string | null; kind: ActionKind; label: string; text: string;
  amount: number | null; ratio: number[] | null; factor: number | null; premium?: number | null; currency: string;
  ex_date: string; record_date: string | null; purpose: string; src: string; url?: string | null; mine?: boolean;
  /** a dividend declared before a later bonus or split: its amount in today's shares, and why (DD-013) */ now_amount?: number | null; now_note?: string | null;
  /** a trust's distribution, part by part (interest, dividend, capital repayment): DE-029 */
  parts?: { label: string; amount: number | null }[]; pay_date?: string | null;
}
export const KIND_NAME: Record<ActionKind, string> = {
  dividend: "Dividends and distributions", bonus: "Bonus issues", split: "Splits", buyback: "Buybacks", rights: "Rights issues", demerger: "Demergers and spin-offs",
};

/** "Thu 15 Oct", from an ISO date, without the browser's time zone moving it a day. */
export function exDay(iso: string, year = false) {
  return fmtDate(iso.slice(0, 10), { weekday: !year, year });
}

/** The figure of an action for its own column: a dividend's amount, a bonus's or rights issue's ratio, a split's factor, a buyback's price. */
export function ActionFigure({ a, cur }: { a: CorpAction; cur: string }) {
  if (a.kind === "dividend") return a.amount ? <>{price(a.amount, cur, a.amount < 1 ? 4 : 2)}<span className="k-note k-muted"> a {/unit/i.test(a.text) ? "unit" : "share"}</span></> : <span className="k-muted">Not stated</span>;
  if ((a.kind === "bonus" || a.kind === "rights") && a.ratio) return <>{a.ratio[0]}:{a.ratio[1]}</>;
  if (a.kind === "split" && a.factor) return a.factor >= 1 ? <>{+a.factor.toFixed(2)} for 1</> : <>1 for {+(1 / a.factor).toFixed(2)}</>;
  if (a.kind === "buyback" && a.amount) return <>{price(a.amount, cur)}<span className="k-note k-muted"> a share</span></>;
  return <span className="k-muted">Not stated</span>;
}

/** What the figure alone does not say: a bonus's shares, a split's face values, a rights issue's premium, a distribution's parts. */
export function actionAside(a: CorpAction, cur: string): string | null {
  if (a.kind === "split" || a.kind === "demerger") { const rest = a.text.toLowerCase().startsWith(a.label.toLowerCase()) ? a.text.slice(a.label.length).replace(/^[\s:·-]+/, "") : a.text; return rest && rest.toLowerCase() !== a.label.toLowerCase() ? rest : null; }
  if (a.kind === "bonus") { const rest = a.text.replace(/^Bonus[^(]*/, "").trim(); return rest.startsWith("(") ? rest.slice(1, -1) : null; }     // "1 new share for every 1 held"
  if (a.kind === "rights" && a.premium) return `at a premium of ${price(a.premium, cur)}`;
  if (a.parts?.length) return a.parts.map((p) => `${p.label} ${p.amount == null ? "" : price(p.amount, cur, 2)}`.trim()).join(", ");
  return null;
}

/** The action itself: its kind, what the figure does not say, a dividend in today's shares and the exchange's notice. */
export function ActionCell({ a, cur }: { a: CorpAction; cur: string }) {
  const more = actionAside(a, cur);
  return (
    <span className="k-stack">
      <span><Badge tone="plain" dot={false}>{a.label}</Badge></span>
      {more && <span className="k-note k-muted">{more}</span>}
      {a.now_note && <span className="k-note k-muted" data-testid="div-now">{a.now_note}</span>}
      {a.url && <span className="k-note"><a className="link" href={safeHref(a.url)} target="_blank" rel="noopener noreferrer">Notice ↗</a></span>}
    </span>);
}

/** The record date for its column: the day, "Same day" when it is the ex-date (as in India), "Not given" when the company gave none. */
export function recordCell(a: Pick<CorpAction, "ex_date" | "record_date">, year = false) {
  return a.record_date ? (a.record_date === a.ex_date ? <span className="k-muted">Same day</span> : exDay(a.record_date, year)) : <span className="k-muted">Not given</span>;
}

interface CompanyActions {
  ahead: CorpAction[]; past: CorpAction[]; dividends_12m: { amount: number; count: number; currency: string; adjusted?: boolean } | null; ahead_known: boolean; note: string;
}

/** What a row of the table says in its "Amount a share" cell, as the page's own words have it ("₹10" of "Dividend ₹10 a share"): the amount for a
 * dividend or a buyback, else what the action's words add to its type (a ratio, a face value), else a dash; `more` is what follows
 * ("a unit: ₹3 interest, ₹2 capital repayment"). */
export function actionAmount(a: Pick<CorpAction, "amount" | "label" | "text" | "currency" | "kind">, ccy: string): { amount: string; more: string } {
  const rest = a.text.toLowerCase().startsWith(a.label.toLowerCase()) ? a.text.slice(a.label.length).replace(/^[\s:·-]+/, "") : a.text === a.label ? "" : a.text;
  const m = rest.match(/^(.+?) a (?:share|unit)\b[\s:·-]*(.*)$/);
  if (m) return { amount: m[1], more: m[2] };
  if (a.amount != null && (a.kind === "dividend" || a.kind === "buyback")) return { amount: price(a.amount, a.currency && a.currency.length === 3 ? a.currency : ccy), more: "" };
  if (a.kind === "bonus") return { amount: "–", more: "" };            // its ratio is in the type ("Bonus 1:1"); the words only say it again
  return { amount: rest || "–", more: "" };
}

/** One row of a company's corporate-actions table: an action, or a line saying there is none to list (the "Coming up" line, an empty past). */
type ActionRow = { id: string; a: CorpAction; ahead: boolean } | { id: string; gap: string; head: string };

/** The company page's panel: the last 12 months' dividends in a line, then one table: what is ahead first (or a line saying nothing is), then the
 * last three years, newest first: Ex-date | Type | Amount a share | Record date (UI-CO item 1: two columns of chips read as loose lines). */
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
  const none = data.ahead_known ? (region === "US" ? "No dividend declared with an ex-date in the next four weeks." : "Nothing announced with an ex-date ahead.")
    : "Dividends declared for the next four weeks couldn't be read yet, so none is listed. A split ahead isn't listed until its ex-date; past ones are below.";
  const rows: ActionRow[] = [
    ...(data.ahead.length ? data.ahead.map((a) => ({ id: a.id, a, ahead: true })) : [{ id: "ahead-none", gap: none, head: "Coming up" }]),
    ...(past.length ? past.map((a) => ({ id: a.id, a, ahead: false })) : [{ id: "past-none", gap: "None on record in the past three years.", head: "Past three years" }]),
  ];
  // a dividend declared before a later bonus or split: its amount in today's shares is a numbered note under the table, not a sentence in the cell (DD-013)
  const notes = rows.flatMap((r) => ("a" in r && r.a.now_note ? [{ id: r.id, text: r.a.now_note, when: exDay(r.a.ex_date, true), label: r.a.label }] : []))
    .map((x, i) => ({ ...x, n: i + 1 }));
  return (
    <div className="k-stack">
      {data.dividends_12m && (
        <span className="k-small">Dividends with an ex-date in the last 12 months: <b>{price(data.dividends_12m.amount, ccy)}</b> a share{data.dividends_12m.adjusted ? " in today's shares" : ""} ({data.dividends_12m.count} payment{data.dividends_12m.count === 1 ? "" : "s"})</span>
      )}
      <div className="ca-table"><DataTable label="Corporate actions: ahead, and the past three years, newest first" rows={rows} rowKey={(r) => r.id} stack={false}
        rowNote={(r) => ("gap" in r ? <span className="k-small k-muted">{r.gap}</span> : undefined)}
        columns={[
          { key: "ex", header: "Ex-date", rowHeader: true, cell: (r) => ("gap" in r ? <b className="k-small">{r.head}</b> : (
            <span className="ca-ex">{exDay(r.a.ex_date, true)}{r.ahead && <b className="k-note ca-soon">Coming up</b>}</span>)) },
          { key: "ty", header: "Type", cell: (r) => ("gap" in r ? null : <span className="ca-type">{r.a.label}</span>) },
          { key: "am", header: "Amount a share", numeric: true, cell: (r) => ("gap" in r ? null : (
            <span className="ca-amt"><span>{actionAmount(r.a, ccy).amount}{notes.find((n) => n.id === r.id) && <sup className="cmp-foot-mark" aria-label={`see note ${notes.find((n) => n.id === r.id)!.n}`}>{notes.find((n) => n.id === r.id)!.n}</sup>}</span>
              {actionAmount(r.a, ccy).more && <span className="k-note">{actionAmount(r.a, ccy).more}</span>}</span>)) },
          { key: "rec", header: "Record date", numeric: true, cell: (r) => ("gap" in r ? null : (
            <span className="ca-amt">{r.a.record_date ? exDay(r.a.record_date, true) : "–"}
              {r.a.pay_date && <span className="k-note">paid {exDay(r.a.pay_date, true)}</span>}
              {r.a.url && <a className="link k-note" href={safeHref(r.a.url)} target="_blank" rel="noopener noreferrer">Notice ↗</a>}</span>)) },
        ]} /></div>
      {notes.length > 0 && <ul className="k-note cmp-foots" data-testid="div-now">{notes.map((x) => <li key={x.id}><sup>{x.n}</sup> {x.label} of {x.when}: {x.text}</li>)}</ul>}
      {data.past.length > 5 && <button className="btn quiet sm k-btn-end" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${data.past.length}`}</button>}
      <Link className="link k-small" to={`/research/corporate-actions?region=${region}`}>Every company's corporate actions →</Link>
    </div>
  );
}
