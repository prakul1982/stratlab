import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, dataUrl } from "../lib/api";
import { useApp } from "../lib/app";
import { charge, fall, money, num, pct, periodName, price, priceDp, qty, TF_NAME, tzOf, when } from "../lib/format";
import { CHECKS, checkTone, checksLine, upDown } from "../lib/tradeUi";
import type { Basket, BasketRow, Check, Experiment, Notebook, Trade, WalkForward, WFWindow } from "../lib/types";
import { DrawdownBand, Heatmap, SplitBars, XYChart } from "../components/Charts";
import { pctTick, moneyCompact } from "../lib/chartFormat";
import { instrumentLoader, PriceChart, strategyStudies, type Tf } from "../charts/price/lazy";
import { Info, Modal, STATUS_NAME } from "../components/ui";
import { Badge, Card, CardHead, ChartFrame, ConfirmDialog, DataTable, EmptyState, Field, FormActions, FormGrid, Notice, PageHeader, Skeleton, Stat, StatRow, type Column } from "../components/kit";
import { HELP } from "../lib/help";
import { NotebookProblem, useNotebook } from "./NotebookPage";
import { cardFromExperiment, renderCard, shareVerdict } from "../components/shareImage";
import { MoreMenu } from "../components/MoreMenu";
import { track } from "../lib/analytics";
import { siteUrl } from "../lib/share";
import { Book, Globe, Layers, Pencil, Pulse, Share, Trash } from "../components/Icons";
import "./trade/trade.css";

/* /n/:id/e/:v: one experiment's verdict, its four checks, the money, every trade and the extra tests. Built from the
 * kit (components/kit); the big verdict headline and the checks grid keep their own layout. */

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
  const cols: Column<WFWindow>[] = [
    { key: "tuned", header: "Tuned on", cell: (x) => `${shortDate(x.train_from)} – ${shortDate(x.train_to)}` },
    { key: "traded", header: "Then traded", cell: (x) => `${shortDate(x.test_from)} – ${shortDate(x.test_to)}` },
    { key: "set", header: "Settings picked", wrap: true, cell: (x) => x.chosen.map((c) => `${c.label} ${c.value}${c.value === c.yours ? "" : ` (yours ${c.yours})`}`).join(" · ") },
    { key: "train", header: "Tuned return", numeric: true, cell: (x) => <span className={upDown(x.train_ret)}>{pct(x.train_ret)}</span> },
    { key: "test", header: "Unseen return", numeric: true, cell: (x) => <b className={upDown(x.test_ret)}>{pct(x.test_ret)}</b> },
    { key: "fixed", header: "Yours, unseen", numeric: true, cell: (x) => <span className={upDown(x.fixed_ret)}>{pct(x.fixed_ret)}</span> },
  ];
  return (
    <Card label="Walk-forward test">
      <CardHead title="Walk-forward test" info={HELP.walkforward} infoLabel="About the walk-forward test"
        actions={<button type="button" className="btn quiet sm" disabled={busy} onClick={run}>{busy ? "Walking forward…" : w ? "Run again" : "Run a walk-forward test"}</button>} />
      {!w && <p className="k-small k-muted">Would this idea still work if you kept re-tuning it? Walk-forward tunes the settings on the past, trades them on the next stretch it never saw, then slides forward and repeats. It's the strictest test of a tuned strategy. Counts as one experiment.</p>}
      {w && <>
        <div className="k-row"><Badge tone={checkTone(w.status)}>{STATUS_NAME[w.status]}</Badge><span className="k-sub">{w.headline}</span></div>
        <p className="k-small">{w.detail}</p>
        {w.windows.length > 0 && <>
          <StatRow label="Walk-forward results">
            {([["Walk-forward return", w.wf_ret!, "Tuned on the past each time, traded only on unseen blocks."],
              ["Your settings, same blocks", w.fixed_ret!, "Your exact settings, never re-tuned, over the same unseen blocks."],
              ["Buy and hold, same span", w.buy_hold_ret!, "Just buying and holding over the same unseen span."]] as [string, number, string][]).map(([k, v, h]) => (
              <Stat key={k} item label={<>{k}<Info>{h}</Info></>} value={pct(v)} tone={v > 0 ? "up" : v < 0 ? "down" : undefined} />
            ))}
            <Stat item label={<>Unseen blocks in profit<Info>{`Each block was traded with settings chosen only from the data before it. ${w.trades} trades in all.`}</Info></>} value={`${w.profitable} of ${w.total}`} />
          </StatRow>
          {s && s.t.length > 1 && (
            <XYChart ariaLabel="Walk-forward return against your fixed settings" height={220} times={s.t} tz={tzOf(e.instrument)}
              series={[{ id: "wf", values: s.wf, color: "var(--series-1)", label: "Walk-forward (re-tuned each block)" },
                { id: "fixed", values: s.fixed, color: "var(--muted)", width: 1.5, dash: "5 4", label: "Your settings, never re-tuned" }]}
              format={(v) => pct(v)} axisFormat={(v) => pctTick(v, true, 0)} refs={[{ v: 0, strong: true }]} />
          )}
          <p className="k-note">
            Each step tried {w.grid_size} nearby settings around your {w.tuned?.join(" and ")} on the past and kept the best.
            {w.efficiency != null && ` Unseen blocks earned ${Math.round(w.efficiency * 100)}% of the yearly return the tuning showed`}
            {w.efficiency != null && (w.efficiency >= 0.5 ? " (50% or more means most of it carried over)." : " (under 50% means the tuning flattered it).")}
            {w.settings_used! > 3 && " The best settings kept changing, which suggests they're fitting noise."}
          </p>
          <DataTable label="Walk-forward windows" columns={cols} rows={w.windows} rowKey={(x) => x.test_from} />
        </>}
      </>}
    </Card>
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
  const cols: Column<BasketRow>[] = [
    { key: "sym", header: "Instrument", rowHeader: true, cell: (r) => <b title={r.name || undefined}>{r.symbol}</b> },
    { key: "ret", header: "Return", numeric: true, cell: (r) => (r.error ? "" : r.n ? <span className={upDown(r.ret)}>{pct(r.ret!)}</span> : "No trades") },
    { key: "bh", header: "Buy and hold", numeric: true, cell: (r) => (r.error ? "" : pct(r.buy_hold!)) },
    { key: "n", header: "Trades", numeric: true, cell: (r) => (r.error ? "" : r.n) },
    { key: "win", header: "Win rate", numeric: true, cell: (r) => (r.error ? "" : r.n ? `${r.win!.toFixed(0)}%` : "–") },
    { key: "mdd", header: "Worst fall", numeric: true, cell: (r) => (r.error ? "" : r.n ? pct(-Math.abs(r.mdd!)) : "–") },
  ];
  return (
    <Card label="Similar instruments">
      <CardHead title={`Does it work on similar ${peers}?`} info={HELP.basket} infoLabel={`About the test on similar ${peers}`}
        actions={<button type="button" className="btn quiet sm" disabled={busy} onClick={run}>{busy ? `Testing ${peers}…` : b ? "Run again" : `Test on 10 similar ${peers}`}</button>} />
      {!b && <p className="k-small k-muted">An edge that only works on one chart is often luck. This runs the same rules over the same period on about 10 well-known {peers} and counts how many make money. Counts as one experiment.</p>}
      {b && <>
        <div className="k-row"><Badge tone={checkTone(b.status)}>{STATUS_NAME[b.status]}</Badge><span className="k-sub">{b.headline}</span></div>
        {b.tested > 0 && <p className="k-small k-muted">Median return {pct(b.median_ret ?? 0)} · beat buy and hold on {b.beat_buy_hold} of {b.tested}.</p>}
        <DataTable label="Similar instruments" columns={cols} rows={b.rows} rowKey={(r) => r.id} rowNote={(r) => r.error || undefined} />
      </>}
    </Card>
  );
}

const yearSpan = (a: string, b: string) => (a === b ? a : `${a}–${b}`);
const tradeCount = (n: number) => `${n} trade${n === 1 ? "" : "s"}`;
/** "5 trades", or "5 trades + 1 still open": the open trade is counted the same way everywhere on the page. */
const withOpen = (n: number, open: number) => `${tradeCount(n)}${open ? ` + ${open} still open` : ""}`;

/** A trade's return after costs: its P&L as a share of what it put in (so P&L and Return always agree in sign). */
const tradeRet = (t: Trade) => (t.qty && t.entry ? (t.pnl / (t.qty * t.entry)) * 100 : t.ret);

function CheckCard({ c, cur }: { c: Check; cur: string }) {
  const d = c.data;
  return (
    <Card label={c.title}>
      <CardHead level={3} title={c.title} info={HELP[c.id]} infoLabel={`About ${c.title.toLowerCase()}`} />
      <div className="k-row"><Badge tone={checkTone(c.status)}>{STATUS_NAME[c.status]}</Badge></div>
      {c.id === "unseen" && d && (
        <SplitBars built={d.built_ret} unseen={d.unseen_ret}
          builtLabel={`Built on ${yearSpan(d.built_from, d.built_to)} · ${withOpen(d.built_trades, d.open_built ?? 0)}`}
          unseenLabel={`Tested on ${yearSpan(d.unseen_from, d.unseen_to)} · ${withOpen(d.unseen_trades, d.open_unseen ?? 0)}`} />
      )}
      {c.id === "unseen" && d?.spanning > 0 && (
        <span className="k-note">{d.spanning === 1 ? "1 trade was opened before the split and closed after it; it counts" : `${d.spanning} trades were opened before the split and closed after it; they count`} with the built part (marked in Every trade).</span>
      )}
      {c.id === "nearby" && d && (
        <>
          <Heatmap grid={d.grid} yours={d.yours} label={`Returns for ${d.total} nearby settings; ${d.profitable} profitable`} />
          <div className="k-spread k-note">
            <span>{d.col_label} {d.cols[0]} → {d.cols[d.cols.length - 1]}</span>
            {d.row_label && <span>{d.row_label} {d.rows[0]} → {d.rows[d.rows.length - 1]}</span>}
          </div>
          <p className="k-small k-muted"><b className="k-ink">{d.profitable} of {d.total}</b> nearby settings made money. Yours is outlined.</p>
        </>
      )}
      {c.id === "shuffle" && d && <DrawdownBand yours={d.yours} p95={d.p95} worst={d.worst} />}
      {c.id === "sample" && d && <div className="k-big">{d.trades}</div>}
      <p className="k-small k-muted">{c.detail}</p>
      {c.id === "sample" && <span className="k-note">Under 15 trades, luck dominates. 30 or more is a fair sample.</span>}
      {c.id === "shuffle" && d && <span className="k-note">From {d.runs.toLocaleString("en-IN")} reshuffles of your trades{cur ? ", after costs" : ""}{d.daily ? ", falls measured day by day as in Worst fall" : ""}.</span>}
    </Card>
  );
}

/** How each member of a group did, best first. */
function GroupMembers({ e, cur }: { e: Experiment; cur: string }) {
  const g = e.group!;
  const cols: Column<(typeof g.members)[number]>[] = [
    { key: "sym", header: "Symbol", rowHeader: true, cell: (m) => <b>{m.symbol}</b> },
    { key: "n", header: "Trades", numeric: true, cell: (m) => m.trades },
    { key: "win", header: "Win rate", numeric: true, cell: (m) => (m.win == null ? "–" : `${m.win.toFixed(0)}%`) },
    { key: "pnl", header: "P&L after costs", numeric: true, cell: (m) => <span className={upDown(m.pnl)}>{money(m.pnl, cur)}</span> },
    { key: "bh", header: "Buy and hold", numeric: true, cell: (m) => (m.buy_hold == null ? "–" : <span className={upDown(m.buy_hold)}>{pct(m.buy_hold)}</span>) },
  ];
  return (
    <Card label="Group members">
      <CardHead title={`${g.name}: one by one`} info={HELP.group} infoLabel="About the group"
        actions={<span className="k-note">Up to {g.max_open} positions at once · most at once: {g.most_open}</span>} />
      {g.skipped.length > 0 && <p className="k-note">Left out ({g.skipped.length}): {g.skipped.slice(0, 6).join(" · ")}{g.skipped.length > 6 ? " …" : ""}</p>}
      <DataTable label="Group members" columns={cols} rows={g.members} rowKey={(m) => m.id} />
    </Card>
  );
}

/** Each trade's entry and exit on the chart: a buy below the candle, a sell above it (a short enters with a sell). */
function tradeMarks(e: Experiment): { t: string; side: "buy" | "sell" }[] {
  const out: { t: string; side: "buy" | "sell" }[] = [];
  for (const t of e.trades) {
    const short = t.side === "short";
    out.push({ t: t.entry_t, side: short ? "sell" : "buy" });
    if (t.exit_t) out.push({ t: t.exit_t, side: short ? "buy" : "sell" });
  }
  return out;
}

/** The instrument's candles with the test's trades and the indicators its rules use. Uploaded data is drawn from
 *  the closes the experiment kept. */
function TradesChart({ e, cur }: { e: Experiment; cur: string }) {
  const csv = !e.instrument.market || e.instrument.market === "CSV" || !e.instrument.id;
  const load = useMemo(() => (csv ? undefined : instrumentLoader(e.instrument.id)), [csv, e.instrument.id]);
  const bars = useMemo(() => (csv ? e.series.t.map((t, i) => ({ t, c: e.series.close[i] })) : undefined), [csv, e]);
  const marks = useMemo(() => tradeMarks(e), [e]);
  const studies = useMemo(() => strategyStudies([...e.strategy.entry, ...e.strategy.exit, ...(e.strategy.shortEntry ?? []), ...(e.strategy.shortExit ?? [])]), [e]);
  const tfs: Tf[] = e.tf === "1d" ? ["1d", "1w", "1mo"] : [e.tf as Tf, "1d"];
  return (
    <PriceChart symbol={e.instrument.symbol} storageKey={(e.instrument.id || e.instrument.symbol).slice(0, 40)} currency={cur}
      load={load} bars={bars} tf={e.tf as Tf} timeframes={csv ? [e.tf as Tf] : tfs} range={null} markers={marks} pageStudies={studies} height={380} closesOnly={csv}
      decimals={priceDp(e.instrument)} noVolume={e.instrument.market === "FX"} rangesKeepTf
      history={e.days <= 366 ? "1y" : e.days <= 1100 ? "3y" : e.days <= 1830 ? "5y" : "max"}
      note={csv ? "Your uploaded data: the closes this experiment kept." : "Markers: entries and exits of this test. Lines from your rules are listed in the legend."} />
  );
}

/** The one place for what to do next: the step the verdict points to as the main button, the other steps beside it,
 *  and the rarer ones behind More. */
function NextSteps({ nb, e, onDelete }: { nb: Notebook; e: Experiment; onDelete: () => void }) {
  const nav = useNavigate();
  const go = (action: string) => nav(`/n/${nb.id}`, { state: { action } });
  const steps = e.verdict.suggestions.filter((s) => s.action !== "note");
  const [main, ...rest] = steps.length ? steps : [{ action: "edit_rules", text: "Change the rules" }];
  const prev = nb.experiments.filter((x) => x.v < e.v).map((x) => x.v);
  return (
    <Card label="Next step" compact>
      <CardHead title="Next step" level={3} info={HELP.nextSteps} infoLabel="About next steps" />
      <div className="k-toolbar" role="toolbar" aria-label="Next step">
        <button type="button" className="btn" onClick={() => go(main.action)}>{main.action === "paper_trade" ? <Pulse size={17} /> : null}{main.text}</button>
        {rest.map((s) => <button type="button" key={s.action} className="btn quiet sm" onClick={() => go(s.action)}>{s.action === "paper_trade" ? <Pulse size={17} /> : null}{s.text}</button>)}
        {main.action !== "edit_rules" && <button type="button" className="btn quiet sm" onClick={() => go("edit_rules")}><Pencil size={17} />Change the rules</button>}
        {prev.length > 0 && (
          <button type="button" className="btn quiet sm" onClick={() => nav(`/n/${nb.id}/compare?a=${Math.max(...prev)}&b=${e.v}`)}>Compare with v{Math.max(...prev)}</button>
        )}
        <MoreMenu items={[
          ...(steps.some((s) => s.action === "paper_trade") ? [] : [{ label: "Paper trade it", icon: <Pulse size={17} />, run: () => go("paper_trade") }]),
          { label: "Try another market", icon: <Globe size={17} />, run: () => nav(`/n/${nb.id}/market`) },
          ...(!nb.group ? [{ label: "Test on a group", icon: <Layers size={17} />, run: () => nav(`/n/${nb.id}/market#group`) }] : []),
          ...((e.instrument.market ?? nb.instrument?.market) === "IN" && !nb.group
            ? [{ label: "Trade it with options", icon: <Layers size={17} />, run: () => nav(`/options?enter=rules&nb=${nb.id}`) }] : []),
          { label: "Write a lab note", icon: <Book size={17} />, run: () => go("note") },
          { label: "Delete this experiment", icon: <Trash size={17} />, run: onDelete, danger: true },
        ]} />
      </div>
    </Card>
  );
}

function ExperimentView({ nb, e }: { nb: Notebook; e: Experiment }) {
  const nav = useNavigate();
  const { fail, refreshNotebooks } = useApp();
  const [removing, setRemoving] = useState(false);
  const remove = async () => {
    setRemoving(false);
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
  const unseen = v.checks.find((c) => c.id === "unseen")?.data;
  const cap = e.strategy.risk.capital;
  const st = e.stats;
  const allTrades = [...e.trades].reverse();
  const open = e.trades.filter((t) => !t.exit_t).length;
  const closed = e.trades.length - open;
  const twoWay = e.strategy.side === "both" || e.strategy.side === "short" || e.trades.some((t) => t.side === "short");
  const dp = priceDp(e.instrument);
  const step = e.instrument.step;

  const tradeCols: Column<Trade>[] = [
    ...(e.group ? [{ key: "sym", header: "Symbol", rowHeader: true, cell: (t: Trade) => <b>{t.symbol}</b> }] : []),
    { key: "open", header: "Opened", cell: (t) => <>{when(t.entry_t, tz, intraday)}{t.spans_split ? <span className="k-sub-line">Spans the split: counts as built</span> : t.part === "unseen" ? <span className="k-sub-line">Unseen part</span> : null}</> },
    { key: "close", header: "Closed", cell: (t) => (t.exit_t ? when(t.exit_t, tz, intraday) : "Still open") },
    ...(twoWay ? [{ key: "side", header: "Side", cell: (t: Trade) => (t.side === "short" ? "Short" : "Long") }] : []),
    { key: "qty", header: "Qty", numeric: true, cell: (t) => qty(t.qty, step) },
    { key: "in", header: "In", numeric: true, cell: (t) => price(t.entry, cur, dp) },
    { key: "out", header: "Out", numeric: true, cell: (t) => price(t.exit, cur, dp) },
    { key: "pnl", header: "P&L", numeric: true, cell: (t) => <span className={upDown(t.pnl)}>{money(t.pnl, cur)}</span> },
    { key: "ret", header: "Return", numeric: true, cell: (t) => { const r = tradeRet(t); return <span className={upDown(r)}>{pct(r, 2)}</span>; } },
    { key: "why", header: "Why it closed", wrap: true, cell: (t) => (t.exit_t ? t.why : "Valued at the last close") },
  ];
  const stats: [string, string, number | null, string][] = [
    ["Total return", pct(st.ret), st.ret, HELP.totalReturn],
    ["Buy and hold", pct(st.buy_hold_ret), st.buy_hold_ret, HELP.buyHold],
    ["Worst fall", fall(st.mdd), st.mdd, HELP.worstFall],
    ["Win rate", st.n ? `${st.win.toFixed(0)}%` : "–", null, HELP.winRate],
    ["Profit factor", st.pf == null ? "∞" : !st.n ? "–" : st.pf > 100 ? "> 100" : st.pf.toFixed(2), null, HELP.profitFactor],
    ["Sharpe ratio", num(st.sharpe, 2), null, HELP.sharpe],
    ["Average trade", money(st.avg, cur), st.avg, HELP.avgTrade],
    ["Period", `${periodName(e.days)}, ${e.candles.toLocaleString("en-IN")} candles`, null, HELP.period],
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title={nb.name}
        lede={<><Link to={`/n/${nb.id}`} className="link">← Back to the notebook</Link> · {/^Experiment v\d+$/.test(e.label) ? e.label : `v${e.v}: ${e.label}`} · {e.instrument.symbol} · {TF_NAME[e.tf]} · {yearSpan(e.range.from.slice(0, 4), e.range.to.slice(0, 4))} · {withOpen(st.n, open)}</>}
        actions={<ShareMenu nb={nb} e={e} />} />
      {(st.skipped_size ?? 0) > 0 && (
        <Notice tone="warn">
          {st.skipped_size} entry signal{st.skipped_size === 1 ? " was" : "s were"} skipped because one {e.instrument.market === "MCX" || e.instrument.market === "CDS" || e.instrument.fno ? "lot" : "unit"} cost more than the capital allowed for a trade
          {(e.instrument.market === "MCX" || e.instrument.market === "CDS") && e.instrument.lot_units ? ` (a ${e.instrument.symbol} lot is ${e.instrument.lot_units} × the price)` : ""}.
          Raise the capital{e.instrument.market === "MCX" ? ", use leverage (futures margin) or pick a mini contract" : e.instrument.market === "CDS" ? " or use leverage (futures margin)" : ""} under Size in the rules.
        </Notice>
      )}

      <section className="k-verdict-hero" aria-label="The verdict">
        <div className="k-stack">
          <div className="k-card-titlerow"><h2 className={`verdict-head ${v.verdict}`}>{v.headline}</h2><Info label="About the verdict: how it is decided">{HELP.verdict}</Info></div>
          <p className="k-lede">{v.summary}</p>
        </div>
        <Card label="Strength of evidence">
          <CardHead level={3} title="Strength of evidence" info={HELP.strength} infoLabel="About the strength of evidence" />
          <div className="dots" role="img" aria-label={checksLine(v.passed, v.total)}>
            {Array.from({ length: CHECKS }, (_, k) => <span key={k} className={k < v.passed ? "on" : k >= v.total ? "skip" : ""} />)}
          </div>
          <span className="k-small">{checksLine(v.passed, v.total)}</span>
        </Card>
      </section>

      <NextSteps nb={nb} e={e} onDelete={() => setRemoving(true)} />

      <section className="k-checks" aria-label="The four checks">{v.checks.map((c) => <CheckCard key={c.id} c={c} cur={cur} />)}</section>

      <section className="k-money">
        <ChartFrame title="Where the money came from, and went" info={HELP.equity} label="Account value" actions={<span className="k-note">{money(cap, cur)} start</span>}>
          <XYChart ariaLabel="Account value over the test, with the unseen part shaded" times={e.series.t} tz={tz} height={260} compare
            format={(x) => money(x, cur)} axisFormat={(x) => moneyCompact(x, cur ?? "INR")} refs={[{ v: cap }]} split={e.series.split}
            splitNotes={unseen ? [`tuned on these years: ${pct(unseen.built_ret)}`, `never seen: ${pct(unseen.unseen_ret)}`] : undefined}
            series={[
              { id: "strategy", label: "Strategy", values: e.series.equity, color: "var(--ink)", width: 2 },
              { id: "hold", label: "Buy and hold", values: e.series.buy_hold, color: "var(--muted)", width: 1.5, dash: "5 4" },
            ]} />
        </ChartFrame>
        <Card label="What you'd keep">
          <CardHead title="What you'd keep" info={HELP.keep} infoLabel="About costs" actions={<span className="k-note">{e.instrument.market === "IN" ? "India costs" : "Costs"}</span>} />
          <div className="k-rows" role="list" aria-label="Profit and costs">
            <div role="listitem"><span>Profit before costs</span><b>{money(e.costs.gross_pnl, cur)}</b></div>
            {e.costs.items.map((i) => <div role="listitem" key={i.label}><span>{i.label}</span><b>{charge(i.amount, cur)}</b></div>)}
            {e.costs.tax.amount != null && <div role="listitem"><span>Tax estimate</span><b>{charge(e.costs.tax.amount, cur)}</b></div>}
            <div role="listitem" className="hl"><span>{e.costs.tax.amount != null ? "In your pocket" : "After costs"}</span><b className={upDown(e.costs.kept)}>{money(e.costs.kept, cur)}</b></div>
          </div>
          <p className="k-note">{e.costs.tax.note}</p>
        </Card>
      </section>

      {e.group && <GroupMembers e={e} cur={cur} />}
      {!e.group && (
        <Card label="Price and trades">
          <CardHead title="Price and trades" info={HELP.priceChart} actions={<span className="k-note">▲ buy &nbsp; ▼ sell</span>} />
          <TradesChart e={e} cur={cur} />
        </Card>
      )}

      <Card label="The numbers">
        <CardHead title="The numbers" />
        <StatRow label="Experiment results">
          {stats.map(([k, val, sign, help]) => (
            <Stat key={k} item label={<>{k}<Info label={`What is ${k}?`}>{help}</Info></>} value={val} tone={sign == null || sign === 0 ? undefined : sign > 0 ? "up" : "down"} />
          ))}
        </StatRow>
      </Card>

      <Card label="Every trade">
        <CardHead title="Every trade" info={HELP.trades} infoLabel="About the trades"
          actions={<span className="k-note">{closed} closed{open ? ` + ${open} still open` : ""} · P&L and Return after costs{e.trades_trimmed ? ` (the ${e.trades_trimmed} earlier ones were cleared to save space; run it again to see every trade)` : ""}</span>} />
        <DataTable label="Every trade" columns={tradeCols} rows={allTrades} rowKey={(t) => `${t.symbol ?? ""}${t.entry_t}${t.exit_t ?? ""}${t.qty}`} empty="No trades in this period." />
      </Card>

      <WalkForwardCheck key={`wf${e.v}`} nb={nb} e={e} />

      <BasketCheck key={e.v} nb={nb} e={e} />

      <p className="k-note">Paper trading and research only. Past results don't predict future returns, and nothing here is investment advice.</p>
      {removing && (
        <ConfirmDialog title={`Delete experiment v${e.v}?`} confirmLabel="Delete experiment" onConfirm={remove} onClose={() => setRemoving(false)}>
          "{e.label}" is removed. The notebook and its other experiments stay. This can't be undone.
        </ConfirmDialog>
      )}
    </div>
  );
}

export function ExperimentPage() {
  const { id, v } = useParams();
  const { nb, problem, reload } = useNotebook(id);
  if (!nb && problem) return <NotebookProblem problem={problem} retry={reload} />;
  if (!nb) return <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Experiment" /><Card><Skeleton label="Opening experiment" /></Card></div>;
  const e = nb.experiments.find((x) => String(x.v) === v);
  if (!e) return <div className="k-page"><EmptyState title="That experiment wasn't found." action={{ label: "Back to the notebook", to: `/n/${nb.id}` }} /></div>;
  return <ExperimentView nb={nb} e={e} />;
}


/** Share a verdict: an image for chats and posts, or a public link that previews as the same card. */
function ShareMenu({ nb, e }: { nb: Notebook; e: Experiment }) {
  const { notify, fail, theme } = useApp();
  const [token, setToken] = useState<string | null>(e.public ?? null);
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  const link = token ? `${siteUrl()}/v/${token}` : null;
  const [ask, setAsk] = useState<"link" | "library" | null>(null);
  const image = async () => {
    try {
      const r = await shareVerdict(nb, e, dark ? "dark" : "light", link);
      if (r !== "cancelled") track("card shared", { kind: "verdict", channel: r });
      if (r === "saved") notify("Share card saved (and copied, where your browser allows). Post it anywhere.");
    } catch (x) { fail(x); }
  };
  const makeLink = async () => {
    try {
      const blob = await renderCard(cardFromExperiment(nb, e), "light");
      const b64 = await dataUrl(blob);
      const out = await api<{ token: string }>(`/notebooks/${nb.id}/experiments/${e.v}/share`, { method: "POST", body: { image: b64 } });
      setToken(out.token);
      track("card shared", { kind: "verdict", channel: "link" });
      const url = `${siteUrl()}/v/${out.token}`;
      try { await navigator.clipboard.writeText(url); notify(`Public link copied: ${url}`); } catch { notify(`Public link: ${url}`); }
    } catch (x) { fail(x); }
  };
  const copy = async () => { if (!link) return; try { await navigator.clipboard.writeText(link); notify("Link copied."); } catch { notify(link); } };
  const off = async () => {
    setAsk(null);
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
    setAsk(null);
    if (!lib) return;
    try { await api(`/library/${lib}`, { method: "DELETE" }); setLib(null); notify("Taken out of the library."); } catch (x) { fail(x); }
  };
  return (
    <>
      <MoreMenu label="Share verdict" icon={<Share size={17} />} buttonClass="btn outline" align="right" items={[
        { label: "Share the card as an image", icon: <Share size={16} />, run: image },
        ...(token ? [
          { label: "Copy the public link", run: copy },
          { label: "Turn off the public link", run: () => setAsk("link"), danger: true },
        ] : [{ label: "Make a public link", run: makeLink }]),
        ...(upload ? [] : lib ? [
          { label: "Update it in the strategy library", run: () => setPublishing(true) },
          { label: "Take it out of the library", run: () => setAsk("library"), danger: true },
        ] : [{ label: "Publish to the strategy library", run: () => setPublishing(true) }]),
      ]} />
      {publishing && (
        <Modal title={lib ? "Update in the strategy library" : "Publish to the strategy library"} onClose={() => setPublishing(false)}>
          <div className="k-stack">
            <p className="k-small k-muted">Other traders will see these rules, this verdict ({e.verdict.headline.replace(/\.$/, "")}) and its numbers, and can copy the rules to test themselves. Your email and notes are never shown.</p>
            <FormGrid label="Publish">
              <Field label="What's the idea?" optional wide>{(id) => (
                <textarea id={id} className="k-textarea" rows={3} maxLength={600} value={desc} onChange={(x) => setDesc(x.target.value)} placeholder="A few words on why it might work, or what you learned." />
              )}</Field>
              <Field label="Show it as by" optional wide maxLength={40} value={author} onChange={(x) => setAuthor(x.target.value)} placeholder="A StratLab user" />
              <FormActions>
                <button type="button" className="btn" onClick={publish}>{lib ? "Update" : "Publish"}</button>
                <button type="button" className="btn quiet" onClick={() => setPublishing(false)}>Cancel</button>
              </FormActions>
            </FormGrid>
          </div>
        </Modal>
      )}
      {ask === "link" && <ConfirmDialog title="Turn off the public link?" confirmLabel="Turn it off" onConfirm={off} onClose={() => setAsk(null)}>Anyone who has it will see that it's gone.</ConfirmDialog>}
      {ask === "library" && <ConfirmDialog title="Take this strategy out of the library?" confirmLabel="Take it out" onConfirm={unpublish} onClose={() => setAsk(null)}>Copies people already made stay theirs.</ConfirmDialog>}
    </>
  );
}
