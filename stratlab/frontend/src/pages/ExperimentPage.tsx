import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money, moneyShort, pct, periodName, price, priceAxis, qty, signClass, TF_NAME, tzOf, when } from "../lib/format";
import type { Basket, Check, Experiment, Notebook, WalkForward } from "../lib/types";
import { DrawdownBand, Heatmap, Legend, LineChart, SplitBars, type Marker } from "../components/Charts";
import { Info, Loading, Modal, STATUS_NAME } from "../components/ui";
import { HELP } from "../lib/help";
import { useNotebook } from "./NotebookPage";
import { cardFromExperiment, renderCard, shareVerdict } from "../components/shareImage";
import { MoreMenu } from "../components/MoreMenu";
import { Book, Globe, Layers, Pencil, Pulse, Share, Trash } from "../components/Icons";

const shortDate = (d: string) => new Date(d).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });

/** Re-tune on the past, trade the next unseen block, slide forward, repeat. */
function WalkForwardCheck({ nb, e }: { nb: Notebook; e: Experiment }) {
  if (e.group) return null;
  return <WalkForwardInner nb={nb} e={e} />;
}

function WalkForwardInner({ nb, e }: { nb: Notebook; e: Experiment }) {
  const { fail, refreshMe } = useApp();
  const [w, setW] = useState<WalkForward | undefined>(e.walkforward);
  const [busy, setBusy] = useState(false);
  if (!e.instrument.market || e.instrument.market === "CSV") return null;
  const run = async () => {
    setBusy(true);
    try { setW((await api<{ walkforward: WalkForward }>(`/notebooks/${nb.id}/experiments/${e.v}/walkforward`, { method: "POST" })).walkforward); refreshMe(); }
    catch (err) { fail(err); }
    finally { setBusy(false); }
  };
  const s = w?.series;
  return (
    <section className="card stack" style={{ gap: 14 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 12 }}>
        <h2 className="h2 row" style={{ gap: 0 }}>Walk-forward test<Info>{HELP.walkforward}</Info></h2>
        <button className="btn quiet sm" disabled={busy} onClick={run}>{busy ? "Walking forward…" : w ? "Run again" : "Run a walk-forward test"}</button>
      </div>
      {!w && <p className="small muted">Would this idea still work if you kept re-tuning it? Walk-forward tunes the settings on the past, trades them on the next stretch it never saw, then slides forward and repeats. It's the strictest test of a tuned strategy. Counts as one experiment.</p>}
      {w && <>
        <div className="row wrap" style={{ gap: 12 }}>
          <span className={`badge ${w.status}`}>{STATUS_NAME[w.status]}</span>
          <span className="serif" style={{ fontSize: 22 }}>{w.headline}</span>
        </div>
        <p className="small" style={{ maxWidth: "80ch" }}>{w.detail}</p>
        {w.windows.length > 0 && <>
          <div className="stats-grid">
            {([["Walk-forward return", w.wf_ret!, "Tuned on the past each time, traded only on unseen blocks."],
              ["Your settings, same blocks", w.fixed_ret!, "Your exact settings, never re-tuned, over the same unseen blocks."],
              ["Buy and hold, same span", w.buy_hold_ret!, "Just buying and holding over the same unseen span."]] as [string, number, string][]).map(([k, v, h]) => (
              <div key={k} className="card stack" style={{ gap: 4, padding: "14px 16px" }}>
                <span className={`serif ${signClass(v)}`} style={{ fontSize: 24, lineHeight: 1.15 }}>{pct(v)}</span>
                <span className="small muted row" style={{ gap: 0 }}>{k}<Info>{h}</Info></span>
              </div>
            ))}
            <div className="card stack" style={{ gap: 4, padding: "14px 16px" }}>
              <span className="serif" style={{ fontSize: 24, lineHeight: 1.15 }}>{w.profitable} of {w.total}</span>
              <span className="small muted row" style={{ gap: 0 }}>Unseen blocks in profit<Info>{`Each block was traded with settings chosen only from the data before it. ${w.trades} trades in all.`}</Info></span>
            </div>
          </div>
          {s && s.t.length > 1 && <>
            <LineChart ariaLabel="Walk-forward return against your fixed settings" height={220}
              labels={s.t.map((t) => when(t, tzOf(e.instrument), false))} axisLabels={s.t.map((t) => shortDate(t))}
              lines={[{ values: s.fixed, color: "var(--dash)", width: 1.6, label: "Your settings" }, { values: s.wf, color: "var(--blue)", width: 2.4, label: "Walk-forward" }]}
              format={(v) => pct(v)} baseline={0} />
            <Legend items={[{ label: "Walk-forward (re-tuned each block)", color: "var(--blue)" }, { label: "Your settings, never re-tuned", color: "var(--dash)" }]} />
          </>}
          <p className="hint">
            Each step tried {w.grid_size} nearby settings around your {w.tuned?.join(" and ")} on the past and kept the best.
            {w.efficiency != null && ` Unseen blocks earned ${Math.round(w.efficiency * 100)}% of the yearly return the tuning showed`}
            {w.efficiency != null && (w.efficiency >= 0.5 ? " (50% or more is healthy)." : " (under 50% means the tuning flatters it).")}
            {w.settings_used! > 3 && " The best settings kept changing, which suggests they're fitting noise."}
          </p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Tuned on</th><th>Then traded</th><th>Settings picked</th><th>Tuned return</th><th>Unseen return</th><th>Yours, unseen</th></tr></thead>
              <tbody>{w.windows.map((x) => (
                <tr key={x.test_from}>
                  <td>{shortDate(x.train_from)} – {shortDate(x.train_to)}</td>
                  <td>{shortDate(x.test_from)} – {shortDate(x.test_to)}</td>
                  <td className="num">{x.chosen.map((c) => `${c.label} ${c.value}${c.value === c.yours ? "" : ` (yours ${c.yours})`}`).join(" · ")}</td>
                  <td className={`num ${signClass(x.train_ret)}`}>{pct(x.train_ret)}</td>
                  <td className={`num ${signClass(x.test_ret)}`} style={{ fontWeight: 700 }}>{pct(x.test_ret)}</td>
                  <td className={`num ${signClass(x.fixed_ret)}`}>{pct(x.fixed_ret)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>}
      </>}
    </section>
  );
}

const PEERS: Record<string, string> = { CRYPTO: "coins", FX: "currency pairs", MCX: "MCX commodities", CDS: "currency pairs", CMDTY: "global commodities" };

/** Same rules, same period, ~10 similar instruments: does the edge travel, or is it one lucky chart? */
function BasketCheck({ nb, e }: { nb: Notebook; e: Experiment }) {
  if (e.group) return null;
  return <BasketInner nb={nb} e={e} />;
}

function BasketInner({ nb, e }: { nb: Notebook; e: Experiment }) {
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

/** How each member of a group did, best first. */
function GroupMembers({ e, cur }: { e: Experiment; cur: string }) {
  const g = e.group!;
  return (
    <section className="card stack" style={{ gap: 12 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2 row" style={{ gap: 0 }}>{g.name}: one by one<Info>{HELP.group}</Info></h2>
        <span className="small muted">Up to {g.max_open} positions at once · most at once: {g.most_open}</span>
      </div>
      {g.skipped.length > 0 && <p className="hint">Left out ({g.skipped.length}): {g.skipped.slice(0, 6).join(" · ")}{g.skipped.length > 6 ? " …" : ""}</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Symbol</th><th>Trades</th><th>Win rate</th><th>P&amp;L after costs</th><th>Buy and hold</th></tr></thead>
          <tbody>{g.members.map((m) => (
            <tr key={m.id}>
              <td className="num" style={{ textAlign: "left" }}>{m.symbol}</td><td className="num">{m.trades}</td>
              <td className="num">{m.win == null ? "–" : `${m.win.toFixed(0)}%`}</td>
              <td className={`num ${signClass(m.pnl)}`}>{money(m.pnl, cur)}</td>
              <td className={`num ${signClass(m.buy_hold)}`}>{m.buy_hold == null ? "–" : pct(m.buy_hold)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
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

function ExperimentView({ nb, e }: { nb: Notebook; e: Experiment }) {
  const nav = useNavigate();
  const { fail, refreshNotebooks } = useApp();
  const remove = async () => {
    if (!confirm(`Delete experiment v${e.v} ("${e.label}")? The notebook and its other experiments stay. This can't be undone.`)) return;
    try {
      await api(`/notebooks/${nb.id}/experiments/${e.v}`, { method: "DELETE" });
      await refreshNotebooks();
      nav(`/n/${nb.id}`);
    } catch (err) { fail(err); }
  };
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
  const twoWay = e.strategy.side === "both" || e.strategy.side === "short" || e.trades.some((t) => t.side === "short");

  return (
    <div className="stack" style={{ gap: 28 }}>
      <div className="spread" style={{ flexWrap: "wrap" }}>
        <Link to={`/n/${nb.id}`} className="link" style={{ textDecoration: "none" }}>← {nb.name}</Link>
        <div className="row wrap" style={{ gap: 10 }}>
          <ShareMenu nb={nb} e={e} />
          <button className="btn" onClick={() => nav(`/n/${nb.id}`)}>Next experiment →</button>
        </div>
      </div>
      <div className="toolbar" role="toolbar" aria-label="What next">
        <span className="small muted" style={{ alignSelf: "center" }}>Next:</span>
        <button className="btn quiet sm" onClick={() => nav(`/n/${nb.id}`, { state: { action: "edit_rules" } })}><Pencil size={17} />Change the rules</button>
        <button className="btn quiet sm" onClick={() => nav(`/n/${nb.id}`, { state: { action: "paper_trade" } })}><Pulse size={17} />Paper trade it</button>
        {nb.experiments.some((x) => x.v < e.v) && (
          <button className="btn quiet sm" onClick={() => nav(`/n/${nb.id}/compare?a=${Math.max(...nb.experiments.filter((x) => x.v < e.v).map((x) => x.v))}&b=${e.v}`)}>Compare with the previous run</button>
        )}
        {/* the less common next steps wait behind More, so the verdict isn't buried under a row of buttons */}
        <MoreMenu items={[
          { label: "Try another market", icon: <Globe size={17} />, run: () => nav(`/n/${nb.id}/market`) },
          ...(!nb.group ? [{ label: "Test on a group", icon: <Layers size={17} />, run: () => nav(`/n/${nb.id}/market#group`) }] : []),
          ...((e.instrument.market ?? nb.instrument?.market) === "IN" && !nb.group
            ? [{ label: "Trade it with options", icon: <Layers size={17} />, run: () => nav(`/options?enter=rules&nb=${nb.id}`) }] : []),
          { label: "Write a lab note", icon: <Book size={17} />, run: () => nav(`/n/${nb.id}`, { state: { action: "note" } }) },
          { label: "Delete this experiment", icon: <Trash size={17} />, run: remove, danger: true },
        ]} />
      </div>
      {(st.skipped_size ?? 0) > 0 && (
        <div className="banner">
          <span>{st.skipped_size} entry signal{st.skipped_size === 1 ? " was" : "s were"} skipped because one {e.instrument.market === "MCX" || e.instrument.market === "CDS" || e.instrument.fno ? "lot" : "unit"} cost more than the capital allowed for a trade
            {(e.instrument.market === "MCX" || e.instrument.market === "CDS") && e.instrument.lot_units ? ` (a ${e.instrument.symbol} lot is ${e.instrument.lot_units} × the price)` : ""}.
            Raise the capital{e.instrument.market === "MCX" ? ", use leverage (futures margin) or pick a mini contract" : e.instrument.market === "CDS" ? " or use leverage (futures margin)" : ""} under Size in the rules.</span>
        </div>
      )}

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
        <div className="card stack" style={{ flex: "1 1 300px", gap: 12 }}>
          <div className="spread" style={{ flexWrap: "wrap", gap: "4px 12px" }}><h2 className="h2 row" style={{ gap: 0, whiteSpace: "nowrap" }}>What you'd keep<Info>{HELP.keep}</Info></h2><span className="small muted">{e.instrument.market === "IN" ? "India costs" : "Costs"}</span></div>
          <div className="costs-table">
            <div><span>Profit before costs</span><span>{money(e.costs.gross_pnl, cur)}</span></div>
            {e.costs.items.map((i) => <div key={i.label} className="sub"><span>{i.label}</span><span>−{money(i.amount, cur)}</span></div>)}
            {e.costs.tax.amount != null && <div className="sub"><span>Tax estimate</span><span>−{money(e.costs.tax.amount, cur)}</span></div>}
            <div className="total"><span>{e.costs.tax.amount != null ? "In your pocket" : "After costs"}</span><span className={signClass(e.costs.kept)}>{money(e.costs.kept, cur)}</span></div>
          </div>
          <p className="hint">{e.costs.tax.note}</p>
        </div>
      </section>

      {e.group && <GroupMembers e={e} cur={cur} />}
      {!e.group && <section className="card stack" style={{ gap: 12 }}>
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
      </section>}

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
          <span className="small muted">{e.trades.length} shown, after costs{e.trades_trimmed ? ` (the ${e.trades_trimmed} earlier ones were cleared to save space; run it again to see every trade)` : ""}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr>{e.group && <th>Symbol</th>}<th>Opened</th><th>Closed</th>{twoWay && <th>Side</th>}<th>Qty</th><th>In</th><th>Out</th><th>P&amp;L</th><th>Return</th><th>Why it closed</th></tr></thead>
            <tbody>
              {allTrades.length === 0 && <tr><td colSpan={10} className="muted" style={{ textAlign: "center", padding: 24 }}>No trades in this period.</td></tr>}
              {allTrades.map((t, k) => (
                <tr key={k}>
                  {e.group && <td className="num" style={{ textAlign: "left" }}>{t.symbol}</td>}
                  <td>{when(t.entry_t, tz, intraday)}</td><td>{t.exit_t ? when(t.exit_t, tz, intraday) : "Still open"}</td>
                  {twoWay && <td>{t.side === "short" ? "Short" : "Long"}</td>}
                  <td className="num">{qty(t.qty)}</td><td className="num">{price(t.entry, cur)}</td><td className="num">{price(t.exit, cur)}</td>
                  <td className={`num ${signClass(t.pnl)}`}>{money(t.pnl, cur)}</td><td className={`num ${signClass(t.ret)}`}>{pct(t.ret, 2)}</td><td>{t.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <WalkForwardCheck key={`wf${e.v}`} nb={nb} e={e} />

      <BasketCheck key={e.v} nb={nb} e={e} />

      <section className="card dashed row wrap" style={{ gap: 14 }}>
        <h2 className="serif" style={{ fontSize: 20, fontWeight: 600, fontStyle: "italic", marginRight: 8 }}>What to try next</h2>
        {v.suggestions.map((sg) => (
          <button key={sg.action} className="btn quiet" style={{ whiteSpace: "normal", textAlign: "left", height: "auto", minHeight: 40 }} onClick={() => nav(`/n/${nb.id}`, { state: { action: sg.action } })}>{sg.text}</button>
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


const siteUrl = () => (location.hostname === "localhost" ? location.origin : "https://stratlab.studio");

/** Share a verdict: an image for chats and posts, or a public link that previews as the same card. */
function ShareMenu({ nb, e }: { nb: Notebook; e: Experiment }) {
  const { notify, fail, theme } = useApp();
  const [token, setToken] = useState<string | null>(e.public ?? null);
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  const link = token ? `${siteUrl()}/v/${token}` : null;
  const image = async () => {
    try {
      const r = await shareVerdict(nb, e, dark ? "dark" : "light", link);
      if (r === "saved") notify("Share card saved (and copied, where your browser allows). Post it anywhere.");
    } catch (x) { fail(x); }
  };
  const makeLink = async () => {
    try {
      const blob = await renderCard(cardFromExperiment(nb, e), "light");
      const b64 = await new Promise<string>((ok) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.readAsDataURL(blob); });
      const out = await api<{ token: string }>(`/notebooks/${nb.id}/experiments/${e.v}/share`, { method: "POST", body: { image: b64 } });
      setToken(out.token);
      const url = `${siteUrl()}/v/${out.token}`;
      try { await navigator.clipboard.writeText(url); notify(`Public link copied: ${url}`); } catch { notify(`Public link: ${url}`); }
    } catch (x) { fail(x); }
  };
  const copy = async () => { if (!link) return; try { await navigator.clipboard.writeText(link); notify("Link copied."); } catch { notify(link); } };
  const off = async () => {
    if (!confirm("Turn off the public link? Anyone who has it will see that it's gone.")) return;
    try { await api(`/notebooks/${nb.id}/experiments/${e.v}/share`, { method: "DELETE" }); setToken(null); notify("Public link turned off."); } catch (x) { fail(x); }
  };
  const nav = useNavigate();
  const [lib, setLib] = useState<string | null>(e.library ?? null);
  const [publishing, setPublishing] = useState(false);
  const [desc, setDesc] = useState("");
  const [author, setAuthor] = useState(() => { try { return localStorage.getItem("stratlab.libAuthor") ?? ""; } catch { return ""; } });
  const upload = e.instrument?.market === "CSV";
  const publish = async () => {
    try {
      try { localStorage.setItem("stratlab.libAuthor", author.trim()); } catch { /* private mode */ }
      const out = await api<{ id: string }>(`/notebooks/${nb.id}/experiments/${e.v}/library`, { method: "POST", body: { description: desc, author } });
      setLib(out.id); setPublishing(false);
      notify(lib ? "Updated in the library." : "Published to the strategy library.", { label: "View the library", run: () => nav("/library") });
    } catch (x) { fail(x); }
  };
  const unpublish = async () => {
    if (!lib || !confirm("Take this strategy out of the library? Copies people already made stay theirs.")) return;
    try { await api(`/library/${lib}`, { method: "DELETE" }); setLib(null); notify("Taken out of the library."); } catch (x) { fail(x); }
  };
  return (
    <>
      <MoreMenu label="Share verdict" icon={<Share size={17} />} buttonClass="btn outline" align="right" items={[
        { label: "Share the card as an image", icon: <Share size={16} />, run: image },
        ...(token ? [
          { label: "Copy the public link", run: copy },
          { label: "Turn off the public link", run: off, danger: true },
        ] : [{ label: "Make a public link", run: makeLink }]),
        ...(upload ? [] : lib ? [
          { label: "Update it in the strategy library", run: () => setPublishing(true) },
          { label: "Take it out of the library", run: unpublish, danger: true },
        ] : [{ label: "Publish to the strategy library", run: () => setPublishing(true) }]),
      ]} />
      {publishing && (
        <Modal title={lib ? "Update in the strategy library" : "Publish to the strategy library"} onClose={() => setPublishing(false)}>
          <div className="stack" style={{ gap: 14 }}>
            <p className="muted">Other traders will see these rules, this verdict ({e.verdict.headline.replace(/\.$/, "")}) and its numbers, and can copy the rules to test themselves. Your email and notes are never shown.</p>
            <label className="field">What's the idea? (optional)<textarea className="input" rows={3} maxLength={600} value={desc} onChange={(x) => setDesc(x.target.value)} placeholder="A few words on why it might work, or what you learned." /></label>
            <label className="field">Show it as by (optional)<input className="input" maxLength={40} value={author} onChange={(x) => setAuthor(x.target.value)} placeholder="A StratLab user" /></label>
            <div className="row" style={{ gap: 10, justifyContent: "flex-end" }}>
              <button className="btn quiet" onClick={() => setPublishing(false)}>Cancel</button>
              <button className="btn blue" onClick={publish}>{lib ? "Update" : "Publish"}</button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
