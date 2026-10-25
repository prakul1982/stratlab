import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { money, fmtDate, num } from "../lib/format";
import { upDown } from "../lib/tradeUi";
import { XYChart } from "./Charts";
import { moneyCompact } from "../lib/chartFormat";
import { Card, CardHead, DataTable, Stat, StatRow, type Column } from "./kit";
import "../pages/trade/trade.css";

interface Cur {
  currency: string; sessions: number; capital: number; equity: number; pnl: number; today: number; open_value: number;
  worst_day: { date: string; pnl: number } | null; best_day: { date: string; pnl: number } | null; max_drawdown_pct: number;
  deepest_fall?: { pnl: number; pct: number; date: string; intraday?: boolean; at?: string; day_close?: number | null; held?: boolean } | null;
  curve: { t: string; pnl: number }[];
  /** the market's latest trading day, and that session's result when today is not a trading day (a weekend, a holiday) */
  session?: string; session_pnl?: number | null;
}
interface Row { id: string; name: string; kind: string; currency: string; open_value: number; today: number; pnl: number; capital: number; session_pnl?: number | null }
const KIND: Record<string, string> = { single: "Rules", group: "Group", options: "Options", signal: "Signals" };
const day = (d: string) => fmtDate(d, { year: false });
/** What the day figure is called: "Today" on a trading day, "Last session (Fri 16 Oct)" when today has no session, so a
 * weekend's zero is not read as an empty day (R41A). */
const dayLabel = (c: Pick<Cur, "session" | "session_pnl">) => (c.session && c.session_pnl != null ? `Last session (${fmtDate(c.session, { weekday: true, year: false })})` : "Today");
const tone = (n: number | null) => (n == null || n === 0 ? undefined : n > 0 ? ("up" as const) : ("down" as const));

/** Every running paper session together: what's at stake now, today, overall, the worst day and the deepest fall. */
export function RiskOverview({ onOpen }: { onOpen: (id: string, kind: string) => void }) {
  const [data, setData] = useState<{ currencies: Cur[]; sessions: Row[] } | null>(null);
  useEffect(() => {
    let live = true;
    const load = () => api<{ currencies: Cur[]; sessions: Row[] }>("/live/overview").then((d) => live && setData(d)).catch(() => undefined);
    load();
    const t = window.setInterval(load, 30000);
    return () => { live = false; window.clearInterval(t); };
  }, []);
  if (!data || !data.currencies.length) return null;
  return (
    <section className="k-stack" aria-label="All running sessions">
      {data.currencies.map((c, ci) => {
        const rows = data.sessions.filter((s) => s.currency === c.currency);
        const cols: Column<Row>[] = [
          { key: "name", header: "Session", rowHeader: true, cell: (r) => <button type="button" className="link" onClick={() => onOpen(r.id, r.kind)}>{r.name}</button> },
          { key: "kind", header: "Kind", cell: (r) => KIND[r.kind] ?? r.kind },
          { key: "open", header: "Open value", numeric: true, cell: (r) => money(r.open_value, r.currency) },
          { key: "share", header: "Share", numeric: true, cell: (r) => (c.open_value ? `${Math.round((r.open_value / c.open_value) * 100)}%` : "–") },
          { key: "today", header: dayLabel(c), numeric: true, cell: (r) => { const v = c.session_pnl != null ? r.session_pnl ?? 0 : r.today; return <span className={upDown(v)}>{money(v, r.currency)}</span>; } },
          { key: "pnl", header: "Since the start", numeric: true, cell: (r) => <span className={upDown(r.pnl)}>{money(r.pnl, r.currency)}</span> },
        ];
        return (
          <Card key={c.currency} label={`All running sessions in ${c.currency}`}>
            <CardHead title={ci === 0 ? "All running sessions" : `All running sessions (${c.currency})`}
              info="Every running paper session added up, per currency (rupees and dollars are never mixed). Open value is what the open positions are worth now at the latest prices. The worst day and the deepest fall are for all of them together, which is what you'd feel if this were one account." infoLabel="About all running sessions" />
            <StatRow label={`Totals in ${c.currency}`}>
              {/* a figure in the figure's style, the words beside it (DB-023: "No open positions" in the big type) */}
              <Stat item label="Open value" value={money(c.open_value, c.currency)} note={c.open_value && c.capital ? `${Math.round((c.open_value / c.capital) * 100)}% of ${money(c.capital, c.currency)}` : "No open positions"} />
              <Stat item label={dayLabel(c)} value={money(c.session_pnl ?? c.today, c.currency)} tone={tone(c.session_pnl ?? c.today)} />
              <Stat item label="Since the start" value={money(c.pnl, c.currency)} tone={tone(c.pnl)} note={`${c.sessions} session${c.sessions === 1 ? "" : "s"}`} />
              <Stat item label="Worst day" value={c.worst_day ? money(c.worst_day.pnl, c.currency) : "None yet"} tone={tone(c.worst_day?.pnl ?? null)} note={c.worst_day ? day(c.worst_day.date) : undefined} />
              <Stat item label="Deepest fall" value={`${num(c.max_drawdown_pct, 1)}%`}
                note={c.deepest_fall ? (c.deepest_fall.intraday && (c.deepest_fall.held ?? c.deepest_fall.day_close === c.deepest_fall.pnl)
                  // the low held to the close: one figure, not "-3,94,147 ... the day closed at -3,94,147" (R77-007)
                  ? `${money(c.deepest_fall.pnl, c.currency)} on ${day(c.deepest_fall.date)}${c.deepest_fall.at ? `, reached at ${c.deepest_fall.at} IST` : ""} and held to the close`
                  : c.deepest_fall.intraday
                  ? `${money(c.deepest_fall.pnl, c.currency)} at the lowest point on ${day(c.deepest_fall.date)}${c.deepest_fall.at ? ` (${c.deepest_fall.at} IST)` : ""}, during the day${c.deepest_fall.day_close != null ? `; the day closed at ${money(c.deepest_fall.day_close, c.currency)}` : ""}`
                  : `${money(c.deepest_fall.pnl, c.currency)} from the high point to the low on ${day(c.deepest_fall.date)}`) : "from the high point"} />
            </StatRow>
            {c.curve.length > 1 && (
              <XYChart ariaLabel={`Combined paper P&L in ${c.currency}`} height={150} times={c.curve.map((p) => p.t)} refs={[{ v: 0, strong: true }]}
                format={(v) => money(v, c.currency)} axisFormat={(v) => moneyCompact(v, c.currency)}
                series={[{ label: "All sessions", values: c.curve.map((p) => p.pnl), color: "var(--series-1)", area: { base: 0, pos: "var(--series-1)", neg: "var(--series-2)" } }]} />
            )}
            <DataTable stack label={`Running sessions in ${c.currency}`} columns={cols} rows={rows} rowKey={(r) => r.id} />
          </Card>
        );
      })}
    </section>
  );
}
