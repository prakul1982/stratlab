import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { money, pct, signClass, TF_NAME } from "../lib/format";
import type { CheckStatus, Stats, VerdictKind } from "../lib/types";
import { LineChart } from "../components/Charts";
import { Logo } from "../components/Logo";
import { Loading, STATUS_NAME } from "../components/ui";

interface Snapshot {
  name: string; question: string; instrument: { symbol: string; name?: string; market?: string; currency?: string; type?: string };
  tf: string; range: { from: string; to: string } | null; side: string; created_at: string;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number;
    checks: { id: string; title: string; status: CheckStatus; detail: string }[] };
  stats: Stats; series: { t: string[]; equity: (number | null)[]; buy_hold: (number | null)[]; split: number | null };
  group: { name: string; max_open: number; members: { symbol: string; trades: number; pnl: number; win: number | null; buy_hold: number | null }[] } | null;
}

const d = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric" });

/** A verdict someone shared: readable without an account, with no rules and no owner details. */
export function PublicVerdict() {
  const { token = "" } = useParams();
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  useEffect(() => {
    api<Snapshot>(`/public/v/${encodeURIComponent(token)}`).then(setSnap).catch((e: ApiError) => setGone(e.message));
  }, [token]);

  const v = snap?.verdict;
  const tone = v?.verdict === "edge" ? "var(--blue)" : v?.verdict === "luck" || v?.verdict === "no_edge" ? "var(--orange)" : "var(--ink)";
  const cur = snap?.instrument.currency || (snap?.instrument.market === "IN" ? "INR" : "");
  useEffect(() => { if (snap) document.title = `${snap.verdict.headline} ${snap.name} · StratLab`; }, [snap]);

  return (
    <div className="pub">
      <header className="pub-nav">
        <a href="/" aria-label="StratLab home"><Logo size={40} /></a>
        <a className="btn sm" href="/">Test your own idea free</a>
      </header>
      <main className="pub-main stack" style={{ gap: 24 }}>
        {!snap && !gone && <Loading label="Opening the verdict" />}
        {gone && (
          <div className="card stack" style={{ gap: 10 }}>
            <h1 className="h2">This verdict isn't available</h1>
            <p className="muted">{gone} The person who shared it may have turned the link off.</p>
            <a className="btn" href="/" style={{ alignSelf: "flex-start" }}>See what StratLab does</a>
          </div>
        )}
        {snap && v && (
          <>
            <div className="stack" style={{ gap: 8 }}>
              <span className="eyebrow">
                {snap.name} · {snap.group ? `${snap.group.name} (${snap.group.members.length})` : snap.instrument.symbol} · {TF_NAME[snap.tf] ?? snap.tf} candles
                {snap.range ? ` · ${d(snap.range.from)} – ${d(snap.range.to)}` : ""}
              </span>
              <h1 className="serif" style={{ fontSize: "clamp(40px, 7vw, 76px)", fontWeight: 400, letterSpacing: "-0.03em", lineHeight: 1, color: tone }}>{v.headline}</h1>
              <p className="serif" style={{ fontSize: 20, maxWidth: "60ch" }}>{v.summary}</p>
              {snap.question && <p className="muted">The question: {snap.question}</p>}
            </div>

            <section className="card stack" style={{ gap: 10 }}>
              <div className="spread"><h2 className="h3">Return after costs</h2><span className="small muted">{v.checks.length} honesty checks · {v.passed} passed</span></div>
              {snap.series.t.length > 1 && (
                <LineChart ariaLabel="Strategy against buy and hold" height={240} split={snap.series.split}
                  splitNotes={["tuned on these years", "never seen"]}
                  labels={snap.series.t.map((t) => new Date(t).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" }))}
                  format={(x) => money(x, cur)} axisFormat={(x) => money(x, cur)}
                  lines={[{ label: "Strategy", values: snap.series.equity, color: "var(--ink)", width: 1.8 },
                    { label: "Buy and hold", values: snap.series.buy_hold, color: "var(--muted)", width: 1.2, dash: "4 4" }]} />
              )}
              <div className="stats-grid opt-stats">
                {[["Return after costs", pct(snap.stats.ret), snap.stats.ret], ["Buy and hold", pct(snap.stats.buy_hold_ret), snap.stats.buy_hold_ret],
                  ["Worst fall", pct(snap.stats.mdd), snap.stats.mdd], ["Trades", String(snap.stats.n), null]].map(([k, val, n]) => (
                  <div key={k as string}><span className="eyebrow">{k}</span><b className={`mono ${signClass(n as number | null)}`} style={{ fontSize: 22 }}>{val}</b></div>
                ))}
              </div>
            </section>

            <section className="pub-checks">
              {v.checks.map((c) => (
                <div key={c.id} className="card stack" style={{ gap: 6 }}>
                  <div className="spread"><b>{c.title}</b><span className={`badge ${c.status}`}>{STATUS_NAME[c.status]}</span></div>
                  <p className="small muted">{c.detail}</p>
                </div>
              ))}
            </section>

            {snap.group && (
              <section className="card stack" style={{ gap: 10 }}>
                <h2 className="h3">{snap.group.name}: member by member</h2>
                <div className="table-wrap"><table>
                  <thead><tr><th>Symbol</th><th>Trades</th><th>P&amp;L</th><th>Win rate</th><th>Buy and hold</th></tr></thead>
                  <tbody>{snap.group.members.map((m) => (
                    <tr key={m.symbol}><td className="mono">{m.symbol}</td><td className="mono">{m.trades}</td>
                      <td className={`mono ${signClass(m.pnl)}`}>{money(m.pnl, cur)}</td><td className="mono">{m.win == null ? "–" : `${m.win}%`}</td>
                      <td className={`mono ${signClass(m.buy_hold)}`}>{m.buy_hold == null ? "–" : pct(m.buy_hold)}</td></tr>
                  ))}</tbody>
                </table></div>
              </section>
            )}

            <section className="card stack pub-cta" style={{ gap: 10 }}>
              <h2 className="serif" style={{ fontSize: 28, fontWeight: 400 }}>Is your idea real, or just lucky?</h2>
              <p className="muted">Describe a strategy in plain words. StratLab tests it on years of real prices, after real costs, and runs the same four honesty checks.</p>
              <a className="btn" href="/" style={{ alignSelf: "flex-start" }}>Test your own idea free</a>
            </section>
            <p className="small muted">Shared from StratLab. Research and paper trading only: past results don't predict future returns, and this isn't investment advice. The strategy's rules are private to the person who shared it.</p>
          </>
        )}
      </main>
    </div>
  );
}
