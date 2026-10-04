import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { money, signClass } from "../lib/format";
import { XYChart } from "./Charts";
import { moneyCompact } from "../lib/chartFormat";
import { Info } from "./ui";

interface Cur {
  currency: string; sessions: number; capital: number; equity: number; pnl: number; today: number; open_value: number;
  worst_day: { date: string; pnl: number } | null; best_day: { date: string; pnl: number } | null; max_drawdown_pct: number;
  curve: { t: string; pnl: number }[];
}
interface Row { id: string; name: string; kind: string; currency: string; open_value: number; today: number; pnl: number; capital: number }
const KIND: Record<string, string> = { single: "Rules", group: "Group", options: "Options" };
const day = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

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
    <section className="stack" style={{ gap: 14 }} aria-labelledby="risk-h">
      <h2 id="risk-h" className="h2 row" style={{ gap: 0 }}>All running sessions<Info>{"Every running paper session added up, per currency (rupees and dollars are never mixed). Open value is what the open positions are worth now at the latest prices. The worst day and the deepest fall are for all of them together, which is what you'd feel if this were one account."}</Info></h2>
      {data.currencies.map((c) => {
        const rows = data.sessions.filter((s) => s.currency === c.currency);
        const stats: [string, string, number | null, string?][] = [
          ["Open value", money(c.open_value, c.currency), null, c.capital ? `${Math.round((c.open_value / c.capital) * 100)}% of ${money(c.capital, c.currency)}` : undefined],
          ["Today", money(c.today, c.currency), c.today],
          ["Since the start", money(c.pnl, c.currency), c.pnl, `${c.sessions} session${c.sessions === 1 ? "" : "s"}`],
          ["Worst day", c.worst_day ? money(c.worst_day.pnl, c.currency) : "None yet", c.worst_day?.pnl ?? null, c.worst_day ? day(c.worst_day.date) : undefined],
          ["Deepest fall", `${c.max_drawdown_pct.toFixed(1)}%`, c.max_drawdown_pct || null, "from the high point"],
        ];
        return (
          <div key={c.currency} className="card stack" style={{ gap: 14 }}>
            <div className="risk-stats">
              {stats.map(([k, v, n, sub]) => (
                <div key={k}><span className="eyebrow">{k}</span><b className={`mono ${signClass(n)}`} style={{ fontSize: 20 }}>{v}</b>{sub && <span className="small muted">{sub}</span>}</div>
              ))}
            </div>
            {c.curve.length > 1 && (
              <XYChart ariaLabel={`Combined paper P&L in ${c.currency}`} height={150} times={c.curve.map((p) => p.t)} refs={[{ v: 0, strong: true }]}
                format={(v) => money(v, c.currency)} axisFormat={(v) => moneyCompact(v, c.currency)}
                series={[{ label: "All sessions", values: c.curve.map((p) => p.pnl), color: "var(--series-1)", area: { base: 0, pos: "var(--series-1)", neg: "var(--series-2)" } }]} />
            )}
            <div className="table-wrap"><table>
              <thead><tr><th>Session</th><th>Kind</th><th>Open value</th><th>Share</th><th>Today</th><th>Since the start</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => onOpen(r.id, r.kind)}>
                  <td>{r.name}</td><td>{KIND[r.kind] ?? r.kind}</td><td className="mono">{money(r.open_value, r.currency)}</td>
                  <td className="mono">{c.open_value ? `${Math.round((r.open_value / c.open_value) * 100)}%` : "–"}</td>
                  <td className={`mono ${signClass(r.today)}`}>{money(r.today, r.currency)}</td>
                  <td className={`mono ${signClass(r.pnl)}`}>{money(r.pnl, r.currency)}</td>
                </tr>
              ))}</tbody>
            </table></div>
          </div>
        );
      })}
    </section>
  );
}
