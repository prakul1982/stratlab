import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money, moneyShort, pct, periodName, price, priceAxis, qty, signClass, TF_NAME, tzOf, when } from "../lib/format";
import type { Basket, Check, Experiment, Notebook } from "../lib/types";
import { DrawdownBand, Heatmap, Legend, LineChart, SplitBars, type Marker } from "../components/Charts";
import { Info, Loading, STATUS_NAME } from "../components/ui";
import { HELP } from "../lib/help";
import { useNotebook } from "./NotebookPage";
import { downloadShareImage } from "../components/shareImage";
import { Book, Globe, Pencil, Pulse, Share } from "../components/Icons";

const PEERS: Record<string, string> = { CRYPTO: "coins", FX: "currency pairs" };

/** Same rules, same period, ~10 similar instruments: does the edge travel, or is it one lucky chart? */
function BasketCheck({ nb, e }: { nb: Notebook; e: Experiment }) {
  const { fail, refreshMe } = useApp();
  const [b, setB] = useState<Basket | undefined>(e.basket);
  const [busy, setBusy] = useState(false);
  const peers = PEERS[e.instrument.market || ""] || "stocks";
  if (!e.instrument.market || e.instrument.market === "CSV") return null;
  const run = async () => {
    setBusy(true);
    try { setB((await api<{ basket: Basket }>(`/notebooks/${nb.id}/experiments/${e.v}/basket`, { method: "POST" })).basket); refreshMe(); }
    catch (err) { fail(err); }
    finally { setBusy(false); }
  };
  return (
    <section className="card stack" style={{ gap: 12 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 12 }}>
        <h2 className="h2 row" style={{ gap: 0 }}>Does it work on similar {peers}?<Info>{HELP.basket}</Info></h2>
        <button className="btn quiet sm" disabled={busy} onClick={run}>{busy ? `Testing ${peers}…` : b ? "Run again" : `Test on 10 similar ${peers}`}</button>
      </div>
      {!b && <p className="small muted">An edge that only works on one chart is often luck. This runs the same rules over the same period on about 10 well-known {peers} and counts how many make money. Counts as one experiment.</p>}
      {b && <>
        <div className="row wrap" style={{ gap: 12 }}>
          <span className={`badge ${b.status}`}>{STATUS_NAME[b.status]}</span>
          <span className="serif" style={{ fontSize: 20 }}>{b.headline}</span>
        </div>
        {b.tested > 0 && <p className="small muted">Median return {pct(b.median_ret ?? 0)} · beat buy and hold on {b.beat_buy_hold} of {b.tested}.</p>}
        <div className="table-wrap">
          <table>
            <thead><tr><th>Instrument</th><th>Return</th><th>Buy and hold</th><th>Trades</th><th>Win rate</th><th>Worst fall</th></tr></thead>
            <tbody>{b.rows.map((r) => r.error
              ? <tr key={r.id}><td>{r.symbol}</td><td colSpan={5} className="muted">{r.error}</td></tr>
              : <tr key={r.id}><td title={r.name || undefined}>{r.symbol}</td>
                  <td className={`num ${signClass(r.n ? r.ret! : null)}`}>{r.n ? pct(r.ret!) : "No trades"}</td>
                  <td className="num">{pct(r.buy_hold!)}</td><td className="num">{r.n}</td>
                  <td className="num">{r.n ? `${r.win!.toFixed(0)}%` : "–"}</td><td className="num">{r.n ? pct(-Math.abs(r.mdd!)) : "–"}</td></tr>)}
            </tbody>
          </table>
        </div>
      </>}
    </section>
  );
}

const yearSpan = (a: string, b: string) => (a === b ? a : `${a}–${b}`);
const tradeCount = (n: number) => `${n} trade${n === 1 ? "" : "s"}`;

function CheckCard({ c, cur }: { c: Check; cur: string }) {
  const d = c.data;
  return (
    <div className="card stack" style={{ gap: 12, padding: 20 }}>
      <div className="spread" style={{ alignItems: "flex-start" }}><h3 className="h3 row" style={{ gap: 0 }}>{c.title}<Info>{HELP[c.id]}</Info></h3><span className={`badge ${c.status}`}>{STATUS_NAME[c.status]}</span></div>
      {c.id === "unseen" && d && (
        <SplitBars built={d.built_ret} unseen={d.unseen_ret}
          builtLabel={`Built on ${yearSpan(d.built_from, d.built_to)} · ${tradeCount(d.built_trades)}`} unseenLabel={`Tested on ${yearSpan(d.unseen_from, d.unseen_to)} · ${tradeCount(d.unseen_trades)}`} />
      )}
      {c.id === "nearby" && d && (
        <>
          <Heatmap grid={d.grid} yours={d.yours} label={`Returns for ${d.total} nearby settings; ${d.profitable} profitable`} />
          <div className="mono spread" style={{ fontSize: 11.5, color: "var(--muted)" }}>
            <span>{d.col_label} {d.cols[0]} → {d.cols[d.cols.length - 1]}</span>
            {d.row_label && <span>{d.row_label} {d.rows[0]} → {d.rows[d.rows.length - 1]}</span>}
          </div>
          <p className="small muted"><b style={{ color: "var(--ink)" }}>{d.profitable} of {d.total}</b> nearby settings made money. Yours is outlined.</p>
        </>
      )}
      {c.id === "shuffle" && d && <DrawdownBand yours={d.yours} p95={d.p95} worst={d.worst} />}
      {c.id === "sample" && d && <div className="serif" style={{ fontSize: 56, lineHeight: 1, letterSpacing: "-0.03em" }}>{d.trades}</div>}
      <p className="small muted" style={{ lineHeight: 1.5 }}>{c.detail}</p>
      {c.id === "sample" && <span className="hint">Under 15 trades, luck dominates. 30 or more is a fair sample.</span>}
      {c.id === "shuffle" && d && <span className="hint">From {d.runs.toLocaleString()} reshuffles of your trades{cur ? ", after costs" : ""}.</span>}
    </div>
  );
}

function markersFor(e: Experiment): Marker[] {
  const ts = e.series.t.map((t) => new Date(t).getTime());
  const idx = (iso: string | null) => {
    if (!iso) return -1;
    const v = new Date(iso).getTime();
    let lo = 0, hi = ts.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (ts[mid] <= v) lo = mid; else hi = mid - 1; }
    return lo;
  };
  const out: Marker[] = [];
  for (const t of e.trades) {
    out.push({ i: idx(t.entry_t), side: "buy" });
    if (t.exit_t) out.push({ i: idx(t.exit_t), side: "sell" });
  }
  return out.filter((m) => m.i >= 0);
}

export function ExperimentView({ nb, e }: { nb: Notebook; e: Experiment }) {
  const nav = useNavigate();
  const { notify } = useApp();
  const cur = e.instrument.currency || "";
  const tz = tzOf(e.instrument);
  const intraday = e.tf !== "1d";
  const v = e.verdict;
  const labels = e.series.t.map((t) => when(t, tz, intraday));
  const years = e.series.t.map((t) => new Date(t).toLocaleDateString("en-GB", { timeZone: tz, month: "short", year: "2-digit" }));
  const unseen = v.checks.find((c) => c.id === "unseen")?.data;
  const cap = e.strategy.risk.capital;
  const st = e.stats;
  const allTrades = [...e.trades].reverse();

  return (
    <div className="stack" style={{ gap: 28 }}>
      <div className="spread" style={{ flexWrap: "wrap" }}>
        <Link to={`/n/${nb.id}`} className="link" style={{ textDecoration: "none" }}>← {nb.name}</Link>
        <div className="row wrap" style={{ gap: 10 }}>
          <button className="btn outline" onClick={async () => { await downloadShareImage(nb, e); notify("Share image saved. Post it anywhere."); }}><Share size={17} />Share verdict</button>
          <button className="btn" onClick={() => nav(`/n/${nb.id}`)}>Next experiment →</button>
        </div>
      </div>
      <div className="toolbar" role="toolbar" aria-label="What next">
        <span className="small muted" style={{ alignSelf: "center" }}>Next:</span>
        <button className="btn quiet sm" onClick={() => nav(`/n/${nb.id}`, { state: { action: "edit_rules" } })}><Pencil size={17} />Change the rules</button>
        <button className="btn quiet sm" onClick={() => nav(`/n/${nb.id}/market`)}><Globe size={17} />Try another market</button>
        <button className="btn quiet sm" onClick={() => nav(`/n/${nb.id}`, { state: { action: "paper_trade" } })}><Pulse size={17} />Paper trade it</button>
        <button className="btn quiet sm" onClick={() => nav(`/n/${nb.id}`, { state: { action: "note" } })}><Book size={17} />Write a lab note</button>
        {nb.experiments.some((x) => x.v < e.v) && (
          <button className="btn quiet sm" onClick={() => nav(`/n/${nb.id}/compare?a=${Math.max(...nb.experiments.filter((x) => x.v < e.v).map((x) => x.v))}&b=${e.v}`)}>Compare with the previous run</button>
        )}
      </div>

      <section className="row" style={{ gap: 40, alignItems: "flex-end", paddingBottom: 26, borderBottom: "1px solid var(--line-2)", flexWrap: "wrap" }}>
        <div className="stack" style={{ gap: 12, flex: "1 1 520px", minWidth: 0 }}>
          <span className="eyebrow">
            {e.label} · {e.instrument.symbol} · {TF_NAME[e.tf]} · {yearSpan(String(new Date(e.range.from).getFullYear()), String(new Date(e.range.to).getFullYear()))} · {tradeCount(st.n)}
          </span>
          <h1 className={`verdict-head ${v.verdict}`}>{v.headline}<Info label="How is the verdict decided?">{HELP.verdict}</Info></h1>
          <p className="serif" style={{ fontSize: 22, lineHeight: 1.4, color: "var(--ink-2)", maxWidth: 820 }}>{v.summary}</p>
        </div>
        <div className="card stack" style={{ gap: 10, width: 250, flex: "none", padding: 20 }}>
          <span className="small muted row" style={{ fontWeight: 600, gap: 0 }}>Strength of evidence<Info>{HELP.strength}</Info></span>
          <div className="dots" aria-label={`${v.passed} of ${v.total} checks passed`}>
            {Array.from({ length: v.total }, (_, k) => <span key={k} className={k < v.passed ? "on" : ""} />)}
          </div>
          <span className="mono">{v.passed} of {v.total} checks passed</span>
        </div>
      </section>

      <section className="grid4">{v.checks.map((c) => <CheckCard key={c.id} c={c} cur={cur} />)}</section>

      <section className="row" style={{ gap: 16, alignItems: "stretch", flexWrap: "wrap" }}>
        <div className="card stack" style={{ flex: "1 1 520px", minWidth: 0, gap: 12 }}>
          <div className="spread" style={{ flexWrap: "wrap" }}>
            <h2 className="h2 row" style={{ gap: 0 }}>Where the money came from, and went<Info>{HELP.equity}</Info></h2>
            <span className="mono small muted">{money(cap, cur)} start</span>
          </div>
          <LineChart ariaLabel="Account value over the test, with the unseen part shaded" labels={labels} axisLabels={years} height={260}
            format={(x) => moneyShort(x, cur)} baseline={cap} split={e.series.split}
            splitNotes={unseen ? [`tuned on these years: ${pct(unseen.built_ret, 0)}`, `never seen: ${pct(unseen.unseen_ret, 0)}`] : undefined}
            lines={[
              { label: "Strategy", values: e.series.equity, color: "var(--ink)", width: 2.2 },
              { label: "Buy and hold", values: e.series.buy_hold, color: "var(--dash)", width: 1.4, dash: "5 4" },
            ]} />
          <Legend items={[{ label: "Strategy", color: "var(--ink)" }, { label: "Buy and hold", color: "var(--dash)", dash: true }]} />
        </div>
        <div className="card stack" style={{ flex: "0 1 400px", gap: 12 }}>
          <div className="spread"><h2 className="h2 row" style={{ gap: 0 }}>What you'd keep<Info>{HELP.keep}</Info></h2><span className="small muted">{e.instrument.market === "IN" ? "India costs" : "Costs"}</span></div>
          <div className="costs-table">
            <div><span>Profit before costs</span><span>{money(e.costs.gross_pnl, cur)}</span></div>
            {e.costs.items.map((i) => <div key={i.label} className="sub"><span>{i.label}</span><span>−{money(i.amount, cur)}</span></div>)}
            {e.costs.tax.amount != null && <div className="sub"><span>Tax estimate</span><span>−{money(e.costs.tax.amount, cur)}</span></div>}
            <div className="total"><span>{e.costs.tax.amount != null ? "In your pocket" : "After costs"}</span><span className={signClass(e.costs.kept)}>{money(e.costs.kept, cur)}</span></div>
          </div>
          <p className="hint">{e.costs.tax.note}</p>
        </div>
      </section>

      <section className="card stack" style={{ gap: 12 }}>
        <div className="spread" style={{ flexWrap: "wrap" }}>
          <h2 className="h2 row" style={{ gap: 0 }}>Price and trades<Info>{HELP.priceChart}</Info></h2>
          <span className="small muted">▲ buy &nbsp; ▼ sell</span>
        </div>
        <LineChart ariaLabel={`${e.instrument.symbol} price with buy and sell points`} labels={labels} axisLabels={years} height={300}
          format={(x) => price(x, cur)} axisFormat={(x) => priceAxis(x, cur)} markers={markersFor(e)}
          lines={[
            { label: "Close", values: e.series.close, color: "var(--ink)", width: 1.6 },
            ...Object.entries(e.series.overlays).map(([k, vals], i) => ({ label: k, values: vals, color: ["var(--blue)", "var(--orange)", "var(--muted)", "var(--dash)"][i % 4], width: 1.3 })),
          ]} />
        <Legend items={[{ label: "Close", color: "var(--ink)" }, ...Object.keys(e.series.overlays).map((k, i) => ({ label: k, color: ["var(--blue)", "var(--orange)", "var(--muted)", "var(--dash)"][i % 4] }))]} />
      </section>

      <section className="stats-grid">
        {[
          ["Total return", pct(st.ret), st.ret, HELP.totalReturn],
          ["Buy and hold", pct(st.buy_hold_ret), st.buy_hold_ret, HELP.buyHold],
          ["Worst fall", pct(st.mdd), st.mdd, HELP.worstFall],
          ["Win rate", st.n ? `${st.win.toFixed(0)}%` : "–", null, HELP.winRate],
          ["Profit factor", st.pf == null ? "∞" : st.n ? st.pf.toFixed(2) : "–", null, HELP.profitFactor],
          ["Sharpe ratio", st.sharpe.toFixed(2), null, HELP.sharpe],
          ["Average trade", money(st.avg, cur), st.avg, HELP.avgTrade],
          ["Period", `${periodName(e.days)}, ${e.candles.toLocaleString()} candles`, null, HELP.period],
        ].map(([k, val, sign, help]) => (
          <div key={k as string} className="card stack" style={{ gap: 4, padding: "16px 18px" }}>
            <span className={`serif ${signClass(sign as number | null)}`} style={{ fontSize: 26, lineHeight: 1.15 }}>{val as string}</span>
            <span className="small muted row" style={{ gap: 0 }}>{k as string}<Info label={`What is ${k}?`}>{help as string}</Info></span>
          </div>
        ))}
      </section>

      <section className="card">
        <div className="spread" style={{ marginBottom: 12 }}>
          <h2 className="h2 row" style={{ gap: 0 }}>Every trade<Info>{HELP.trades}</Info></h2>
          <span className="small muted">{e.trades.length} shown, after costs</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Bought</th><th>Sold</th><th>Qty</th><th>Buy</th><th>Sell</th><th>P&amp;L</th><th>Return</th><th>Why it sold</th></tr></thead>
            <tbody>
              {allTrades.length === 0 && <tr><td colSpan={8} className="muted" style={{ textAlign: "center", padding: 24 }}>No trades in this period.</td></tr>}
              {allTrades.map((t, k) => (
                <tr key={k}>
                  <td>{when(t.entry_t, tz, intraday)}</td><td>{t.exit_t ? when(t.exit_t, tz, intraday) : "Still open"}</td>
                  <td className="num">{qty(t.qty)}</td><td className="num">{price(t.entry, cur)}</td><td className="num">{price(t.exit, cur)}</td>
                  <td className={`num ${signClass(t.pnl)}`}>{money(t.pnl, cur)}</td><td className={`num ${signClass(t.ret)}`}>{pct(t.ret, 2)}</td><td>{t.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <BasketCheck key={e.v} nb={nb} e={e} />

      <section className="card dashed row wrap" style={{ gap: 14 }}>
        <h2 className="serif" style={{ fontSize: 20, fontWeight: 600, fontStyle: "italic", marginRight: 8 }}>What to try next</h2>
        {v.suggestions.map((sg) => (
          <button key={sg.action} className="btn quiet" onClick={() => nav(`/n/${nb.id}`, { state: { action: sg.action } })}>{sg.text}</button>
        ))}
      </section>
      <p className="small muted">Paper trading and research only. Past results don't predict future returns, and nothing here is investment advice.</p>
    </div>
  );
}

export function ExperimentPage() {
  const { id, v } = useParams();
  const { nb } = useNotebook(id);
  if (!nb) return <Loading label="Opening experiment" />;
  const e = nb.experiments.find((x) => String(x.v) === v);
  if (!e) return <div className="stack"><p>That experiment wasn't found.</p><Link to={`/n/${nb.id}`}>Back to the notebook</Link></div>;
  return <ExperimentView nb={nb} e={e} />;
}
