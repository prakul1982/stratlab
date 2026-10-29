import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { inr, price, qty as qtyText } from "../lib/format";
import { exDay } from "./CorpActions";
import { fyLink } from "../lib/fy";
import { Card, CardHead, DataTable, FactTable, Notice, type Column } from "./kit";

/* My Holdings: bonuses and splits since the holdings were saved (offered, never made silently), and dividend income. */
interface IncomeLine { symbol: string; label: string; ex_date: string; record_date: string | null; amount: number; qty: number; total: number }
interface Notice1 {
  symbol: string; id: string; kind: string; label: string; text: string; text_action: string; ex_date: string;
  from_qty: number; to_qty: number; from_avg: number | null; to_avg: number | null; more: number;
}
export interface HoldingsActions {
  ahead: IncomeLine[]; ahead_total: number; received: IncomeLine[]; received_total: number; by_fy?: { fy: number; label: string; total: number; count: number }[]; notices: Notice1[];
  undo: { symbol: string; id: string; label: string; qty: number; avg: number | null }[]; checking: number; today: string;
}

/** A dividend a share as announced: ₹11.00, ₹0.50, ₹0.125 (never padded to four places). */
const perShare = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;

const incomeCols: Column<IncomeLine>[] = [
  // the dividend's name under the stock, so the ex-date fits a phone without a sideways swipe (R1-080)
  { key: "stock", header: "Stock", rowHeader: true, wrap: true, cell: (d) => <><Link className="link" to={`/research/IN/${encodeURIComponent(d.symbol)}`}><b>{d.symbol}</b></Link><span className="k-sub-line">{d.label}</span></> },
  { key: "ex", header: "Ex-date", numeric: true, cell: (d) => exDay(d.ex_date, true) },
  { key: "ps", header: "A share", numeric: true, cell: (d) => perShare(d.amount) },
  { key: "qty", header: "Shares", numeric: true, cell: (d) => qtyText(Math.round(d.qty * 10000) / 10000) },
  { key: "amt", header: "Amount", numeric: true, cell: (d) => inr(d.total) },
];

/** The button that was pressed is gone once the notice is answered, which drops focus to the top of the page. Put it on the next
 * notice's first button; else on the Undo beside the adjusted stocks; else on the dividends card; else the page heading. */
export function focusAfterAnswer(doc: Document = document) {
  const el = doc.querySelector<HTMLElement>(".ha-notice button:not(:disabled)") ?? doc.querySelector<HTMLElement>(".ha-undo button:not(:disabled)")
    ?? doc.getElementById("holdings-dividends") ?? doc.querySelector<HTMLElement>("h1");
  if (!el) return;
  if (!el.matches("button, a[href], input, select, textarea, [tabindex]")) el.tabIndex = -1;
  el.focus();
}

export function HoldingsActionsPanel<V>({ onHoldings, version, onLoaded }: { onHoldings: (v: V) => void; version: number; onLoaded?: () => void }) {
  const { fail, notify } = useApp();
  const [data, setData] = useState<HoldingsActions | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [again, setAgain] = useState(0);              // how many times the page has asked again while some stocks were still being read
  useEffect(() => {
    let live = true;
    // onLoaded: the page keeps the cards below this one waiting until it knows its size, so nothing jumps when it arrives
    api<HoldingsActions>("/holdings/corp-actions").then((x) => live && setData(x)).catch(() => live && setData(null)).finally(() => live && onLoaded?.());
    return () => { live = false; };
  }, [version, again]);
  // stocks whose dividends are still being read: the page asks again by itself every half minute (six times at most), so nobody has to reload (LIVE2-033)
  useEffect(() => {
    if (!data || data.checking <= 0 || again >= 6) return;
    const t = setTimeout(() => setAgain((n) => n + 1), 30_000);
    return () => clearTimeout(t);
  }, [data, again]);

  const act = async (symbol: string, id: string, action: "apply" | "dismiss" | "undo", done: string) => {
    setBusy(`${symbol}:${action}`);
    try {
      const r = await api<{ holdings: V; actions: HoldingsActions }>("/holdings/corp-actions", { method: "POST", body: { symbol, id, action } });
      setData(r.actions);
      onHoldings(r.holdings);
      notify(done);
      requestAnimationFrame(() => focusAfterAnswer());
    } catch (e) { fail(e); } finally { setBusy(null); }
  };

  if (!data) return null;
  const received = showAll ? data.received : data.received.slice(0, 6);
  const key = (d: IncomeLine) => `${d.symbol}-${d.ex_date}-${d.label}`;
  return (
    <>
      {data.notices.map((n) => (
        <Notice key={n.id} role="status" className="ha-notice" actions={<>
          <button type="button" className="btn sm" disabled={!!busy} onClick={() => act(n.symbol, n.id, "apply", `${n.symbol}: quantity ${qtyText(n.to_qty)}${n.to_avg != null ? `, average price ${price(n.to_avg, "INR")}` : ""}.`)}>Apply</button>
          <button type="button" className="btn quiet sm" disabled={!!busy} onClick={() => act(n.symbol, n.id, "dismiss", `${n.symbol} kept as it is.`)}>Already in my file</button>
        </>}>
          <b>{n.text}</b>
          <span className="k-sub-line">{n.text_action}. Your saved quantity ({qtyText(n.from_qty)}{n.from_avg != null ? ` at ${price(n.from_avg, "INR")}` : ""}) is from before it. Apply it, or keep it as it is if your broker's file already showed the new quantity.{n.more > 0 ? ` ${n.more} more for ${n.symbol} after this one.` : ""}</span>
        </Notice>
      ))}
      {data.undo.length > 0 && (
        <p className="k-note ha-undo">
          Adjusted for corporate actions: {data.undo.map((u, i) => (
            <span key={u.symbol}>{i > 0 && " · "}{u.symbol} ({u.label}) <button type="button" className="btn quiet sm" disabled={!!busy} onClick={() => act(u.symbol, u.id, "undo", `${u.symbol} is back to ${qtyText(u.qty)} shares.`)}>Undo</button></span>
          ))}
        </p>
      )}
      {(data.ahead.length > 0 || data.received.length > 0) && (
        <Card id="holdings-dividends">
          <CardHead title="Dividends" info="Amount a share as the company announced it, times the shares you'd hold on the ex-date. The last 12 months assume you held today's quantity throughout (worked back through any bonus or split), so they're an estimate; amounts are before tax. Tax tools and the ITR export add the same dividends up by financial year (April to March), each in the year of its record date, so their figures are the financial-year ones below, not the rolling twelve months."
            actions={<Link className="link k-small" to="/research/corporate-actions?region=IN">Corporate actions calendar →</Link>} />
          {/* a financial year with the same total as the last twelve months is that figure said twice (LIVE1C-058: ₹49,724 twice): one row, which says it is both */}
          {(() => {
            const years = (data.by_fy ?? []).filter((y) => y.count > 0);
            const same = years.find((y) => Math.round(y.total) === Math.round(data.received_total));
            return (
              <FactTable label="Dividends in total" itemHead="Period" figureHead="Amount" noteHead="Payments" rows={[
                { id: "ahead", k: "Announced, ex-date ahead", v: inr(data.ahead_total) },
                ...(!same ? [{ id: "12m", k: "Last 12 months (estimated)", v: inr(data.received_total) }] : []),
                ...years.map((y) => ({ id: `fy${y.fy}`, k: `${y.label} (estimated)`, v: inr(y.total),
                  n: <>{y.count} payment{y.count === 1 ? "" : "s"}{y === same ? ", the same as the last 12 months" : ""} · <Link className="link" to={fyLink("/money/tax-tools", y.fy)}>as in tax tools</Link></> })),
              ]} />
            );
          })()}
          {data.ahead.length > 0 && <><h3 className="k-sub">Ex-date ahead</h3><DataTable label="Dividends ahead" columns={incomeCols} rows={data.ahead} rowKey={key} stack phonePage={8} /></>}
          {received.length > 0 && <><h3 className="k-sub">Paid in the last 12 months, by company</h3><DataTable label="Dividends in the last 12 months" columns={incomeCols} rows={received} rowKey={key} stack phonePage={8} /></>}
          {data.received.length > 6 && <button type="button" className="btn quiet sm k-btn-end" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${data.received.length}`}</button>}
          {data.checking > 0 && <p className="k-note" data-testid="ha-checking">The dividends of {data.checking} of your stocks are still being collected, so the totals above may leave some payments out for now. This list asks again by itself.</p>}
        </Card>
      )}
    </>
  );
}
