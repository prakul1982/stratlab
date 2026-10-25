import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fmtDate, money, monthYear, num, pct } from "../lib/format";
import { changes, onDates } from "../lib/compare";
import type { Experiment } from "../lib/types";
import { XYChart } from "../components/Charts";
import { pctTick } from "../lib/chartFormat";
import { VerdictBadge } from "../components/ui";
import { badgeLabel, checksCell } from "../lib/tradeUi";
import { compareGap, legacyNote, splitLegacy } from "../lib/legacyRun";
import { Card, CardHead, DataTable, EmptyState, Field, FormGrid, Notice, PageHeader, Select, Signed, Skeleton, type Column } from "../components/kit";
import { NotebookProblem, useNotebook } from "./NotebookPage";
import "./trade/trade.css";

type Line = { label: string; a: string; b: string; winA: boolean; winB: boolean; va: number | null; vb: number | null };

/* /n/:id/compare: two experiments side by side: what changed, the return curves and the numbers. Built from the kit. */
export function CompareExperiments() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { nb, problem, reload } = useNotebook(id, "Compare runs");
  if (!nb && problem) return <NotebookProblem problem={problem} retry={reload} />;
  if (!nb) return <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Compare experiments" /><Card><Skeleton label="Opening the notebook" /></Card></div>;
  // a run whose figures contradict each other is never charted or compared: it is listed with the reason (R38-001)
  const { shown: exps, legacy } = splitLegacy(nb.experiments);
  const notShown = legacy.length > 0 && (
    <Card label="Runs not compared">
      <CardHead level={3} title="Runs not compared" />
      <ul className="k-list">{legacy.map((e) => <li key={e.v}><Link to={`/n/${nb.id}/e/${e.v}`} className="link">v{e.v} · {e.label}</Link>: {legacyNote(e)}</li>)}</ul>
    </Card>
  );
  const va = Number(params.get("a")), vb = Number(params.get("b"));
  const a = exps.find((e) => e.v === va) ?? exps[exps.length - 2], b = exps.find((e) => e.v === vb) ?? exps[exps.length - 1];
  if (!a || !b) return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Compare experiments" lede={<Link to={`/n/${nb.id}`} className="link">← {nb.name}</Link>} />
      <EmptyState title="Nothing to compare yet" action={{ label: exps.length ? "Change the rules and run again" : "Run the first test", to: `/n/${nb.id}` }}>
        {compareGap(exps.length, legacy.length)}
      </EmptyState>
      {notShown}
    </div>
  );
  const pick = (k: "a" | "b", v: number) => { const p = new URLSearchParams(params); p.set(k, String(v)); nav(`?${p}`, { replace: true }); };
  const opts = exps.map((e) => ({ value: e.v, label: `v${e.v} · ${e.label}` }));
  const pickers = (
    <Card label="Pick two runs">
      <FormGrid label="Pick two runs">
        <Field label="Before">{(fid) => <Select id={fid} value={a.v} onChange={(v) => pick("a", Number(v))} options={opts} />}</Field>
        <Field label="After">{(fid) => <Select id={fid} value={b.v} onChange={(v) => pick("b", Number(v))} options={opts} />}</Field>
      </FormGrid>
    </Card>
  );
  // the same run on both sides: the pickers stay, so either side can be changed
  if (a.v === b.v) return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Compare experiments" lede={<Link to={`/n/${nb.id}`} className="link">← {nb.name}</Link>} />
      {pickers}
      <Notice tone="warn" role="status">Pick two different runs: v{a.v} is on both sides.</Notice>
      {notShown}
    </div>
  );

  // both equity curves as % return, on one date axis
  const ret = (e: Experiment) => {
    const m = new Map<string, number>();
    const start = e.strategy.risk.capital;
    e.series.t.forEach((t, i) => { const v = e.series.equity[i]; if (v != null) m.set(t.slice(0, 10), (v / start - 1) * 100); });
    return m;
  };
  const ra = ret(a), rb = ret(b);
  const dates = Array.from(new Set([...ra.keys(), ...rb.keys()])).sort();
  const lbl = dates.map((d) => monthYear(d));
  // on a time axis by date (each day its own distance, not each point: 2025→2026 was three times as wide as 2022→2023),
  // each run's line drawn across its own window (DA-031)
  const xs = dates.map((d) => Date.parse(`${d}T00:00:00Z`));
  const lineA = onDates(ra, dates), lineB = onDates(rb, dates);
  const span = (m: Map<string, number>) => { const k = [...m.keys()].sort(); return k.length ? `${fmtDate(k[0])} to ${fmtDate(k[k.length - 1])}` : ""; };
  const spanA = span(ra), spanB = span(rb);
  // said when the windows differ by month, not for runs a day or two apart
  const months = (m: Map<string, number>) => { const k = [...m.keys()].sort(); return k.length ? `${monthYear(k[0])}|${monthYear(k[k.length - 1])}` : ""; };
  const apart = months(ra) !== months(rb);
  const diff = changes(a, b);
  // the last flag is true for a gain or loss, which is green or red like everywhere else
  const defs: [string, (e: Experiment) => string, (e: Experiment) => number | null, boolean, boolean?][] = [
    ["Return after costs", (e) => pct(e.stats.ret), (e) => e.stats.ret, true, true],
    ["Yearly return", (e) => pct(e.stats.cagr), (e) => e.stats.cagr, true, true],
    // the verdict's own name for it (DA-031: "Worst drop" here, "Worst fall" there)
    ["Worst fall", (e) => pct(-Math.abs(e.stats.mdd)), (e) => -Math.abs(e.stats.mdd), true, true],
    ["Trades", (e) => String(e.stats.n), () => null, false],
    ["Win rate", (e) => e.stats.n ? `${e.stats.win.toFixed(0)}%` : "–", (e) => e.stats.win, true],
    ["Sharpe", (e) => num(e.stats.sharpe, 2), (e) => e.stats.sharpe, true],
    // each run's costs in its own currency (v1 on NIFTY in rupees beside v2 on AAPL in dollars)
    // ...and never marked the smaller of two currencies
    ["Costs paid", (e) => money(e.costs.total, e.instrument?.currency), (e) => -e.costs.total, (a.instrument?.currency || "") === (b.instrument?.currency || "")],
    // a count in a cell, "2 of 4", not the verdict's sentence "4 of 4 checks run · 2 passed" (DA-031)
    ["Checks passed", (e) => checksCell(e.verdict.passed, e.verdict.total), (e) => e.verdict.passed, true],
    ["Buy and hold", (e) => pct(e.stats.buy_hold_ret), () => null, false],
  ];
  const lines: Line[] = defs.map(([label, show, score, better, gain]) => {
    const x = score(a), y = score(b);
    const buyHold = label === "Buy and hold";
    return { label, a: show(a), b: show(b), va: gain ? x : buyHold ? a.stats.buy_hold_ret : null, vb: gain ? y : buyHold ? b.stats.buy_hold_ret : null, winA: better && x != null && y != null && x > y, winB: better && x != null && y != null && y > x };
  });
  const cols: Column<Line>[] = [
    { key: "m", header: "Measure", rowHeader: true, cell: (l) => l.label },
    { key: "a", header: `v${a.v}`, numeric: true, cell: (l) => { const t = <Signed value={l.va}>{l.a}</Signed>; return l.winA ? <b>{t}</b> : t; } },
    { key: "b", header: `v${b.v}`, numeric: true, cell: (l) => { const t = <Signed value={l.vb}>{l.b}</Signed>; return l.winB ? <b>{t}</b> : t; } },
  ];
  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title={`v${a.v} against v${b.v}`} lede={<Link to={`/n/${nb.id}`} className="link">← {nb.name}</Link>} />
      {pickers}
      <div className="k-two">
        {[a, b].map((e) => (
          <Card key={e.v} label={`v${e.v}`}>
            <span className="k-eyebrow">v{e.v} · {e.label}</span>
            <div><VerdictBadge v={e.verdict.verdict} label={badgeLabel(e.verdict)} /></div>
            <CardHead level={3} title={<Link to={`/n/${nb.id}/e/${e.v}`} className="k-title-link">{e.verdict.headline}</Link>} />
            <span className="k-small k-muted">{e.verdict.summary}</span>
          </Card>
        ))}
      </div>
      <Card label="What changed">
        <CardHead level={3} title="What changed" info="Every difference in the setup between the two experiments. If more than one thing changed, you can't tell which one made the difference: change one thing at a time." infoLabel="About what changed" />
        {diff.length === 0 ? <p className="k-small k-muted">Same setup. The results differ only if the prices did (a later run includes newer candles).</p>
          : <ul className="k-list">{diff.map((d) => <li key={d}>{d}</li>)}</ul>}
        {diff.length > 2 && <p className="k-note">Several things changed at once, so it's hard to say which one mattered.</p>}
      </Card>
      <Card label="Return over the test">
        <CardHead level={3} title="Return over the test" />
        <XYChart ariaLabel="Both experiments' return over time" height={260} times={dates} x={xs} labels={lbl}
          series={[{ id: "a", values: lineA, color: "var(--muted)", width: 1.5, dash: "5 4", label: `v${a.v} · ${a.label}` },
            { id: "b", values: lineB, color: "var(--series-1)", label: `v${b.v} · ${b.label}` }]}
          format={(v) => pct(v)} signedTip axisFormat={(v) => pctTick(v, true, 0)} refs={[{ v: 0, strong: true }]} />
        {apart && <p className="k-note" data-testid="compare-windows">The two runs cover different dates: v{a.v} {spanA}, v{b.v} {spanB}. Each line is drawn over its own run's dates.</p>}
      </Card>
      <Card label="The numbers">
        <CardHead level={3} title="The numbers" info="Bold marks the larger of the two on each line. A higher backtest figure is not proof: the verdict's honesty checks are what test for luck." infoLabel="About the numbers" />
        <DataTable label="Compared numbers" columns={cols} rows={lines} rowKey={(l) => l.label} />
      </Card>
      {notShown}
    </div>
  );
}
