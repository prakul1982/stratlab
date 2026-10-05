import { money, price, signClass, when } from "../lib/format";

/* Paper orders, the same way on every session page: the orders sent at one moment for one reason (an entry, a
 * re-centre, a stop) under one line with their P&L added up, each order a row: side, contract, quantity × price. */

export type PaperOrder = { t: string; side: "buy" | "sell"; qty: number; px: number; why: string; sym: string; pnl?: number | null;
  slices?: number; strike?: number; opt?: "CE" | "PE"; pick?: string };

export function OrderList({ events, cur, tz, newest = false }: { events: PaperOrder[]; cur: string; tz: string; newest?: boolean }) {
  const groups = orderGroups(events);
  if (newest) groups.reverse();
  return (
    <div className="order-list">{groups.map((g) => (
      <div key={g.key} className="order-group">
        <div className="order-head small"><span><b>{g.why}</b> <span className="muted">· {when(g.t, tz, true)}</span></span>
          {g.pnl != null && <span className={`order-num ${signClass(g.pnl)}`}>{money(g.pnl, cur)}</span>}</div>
        <ul className="orders order-rows">{g.rows.map((e, i) => (
          <li key={i} title={e.slices && e.slices > 1 ? `Sent in ${e.slices} slices (the exchange's freeze limit)` : undefined}>
            <span className={`side-chip ${e.side}`} aria-label={e.side === "buy" ? "Buy" : "Sell"} role="img">{e.side === "buy" ? "B" : "S"}</span>
            <span className="order-sym">{contract(e)}</span>
            <span className="order-num small muted">{e.qty.toLocaleString("en-IN", { maximumFractionDigits: 4 })} × {price(e.px, cur)}</span>
            {e.pick && <span className="order-pick tiny muted" data-testid="order-pick">{e.pick}</span>}
          </li>
        ))}</ul>
      </div>
    ))}</div>
  );
}

/** Orders sent together (same moment, same reason) as one group, oldest first, with their P&L added up. */
export function orderGroups(events: PaperOrder[]) {
  const out: { key: string; t: string; why: string; pnl: number | null; rows: PaperOrder[] }[] = [];
  for (const e of events) {
    const last = out[out.length - 1];
    if (last && last.t === e.t && last.why === e.why) {
      last.rows.push(e);
      if (e.pnl != null) last.pnl = (last.pnl ?? 0) + e.pnl;
    } else out.push({ key: `${e.t}|${e.why}|${out.length}`, t: e.t, why: e.why, pnl: e.pnl ?? null, rows: [e] });
  }
  return out;
}

/** "NIFTY 22450 PE" from an option order, or read from the exchange's symbol for orders saved before strikes were
 * kept; a stock's symbol as it is. */
export function contract(e: { sym: string; strike?: number; opt?: "CE" | "PE" }): string {
  const name = e.sym.match(/^[A-Z&-]+/)?.[0] ?? e.sym;
  if (e.strike != null && e.opt) return `${name} ${e.strike} ${e.opt}`;
  const m = e.sym.match(/^[A-Z&-]+(?:\d{2}[A-Z]{3}|\d{2}[0-9OND]\d{2})(\d+(?:\.\d+)?)(CE|PE)$/);
  return m ? `${name} ${m[1]} ${m[2]}` : e.sym;
}

const ms = (iso: string) => new Date(iso).getTime();
/** The orders sent between two moments, both included: one trade's orders. */
export const ordersBetween = <T extends { t: string }>(events: T[], from: string, to: string) => events.filter((e) => ms(e.t) >= ms(from) && ms(e.t) <= ms(to));
/** The orders sent from a moment on: the open trade's orders. */
export const ordersSince = <T extends { t: string }>(events: T[], from: string) => events.filter((e) => ms(e.t) >= ms(from));
