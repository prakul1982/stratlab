import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { money, num, pct, TF_NAME, tzOf } from "../lib/format";
import { refName, opSay } from "../lib/rules";
import type { Cond, Experiment, Strategy } from "../lib/types";
import { XYChart } from "../components/Charts";
import { pctTick } from "../lib/chartFormat";
import { VerdictBadge } from "../components/ui";
import { Card, CardHead, DataTable, EmptyState, Field, FormGrid, PageHeader, Select, Skeleton, type Column } from "../components/kit";
import { NotebookProblem, useNotebook } from "./NotebookPage";
import "./trade/trade.css";

const condText = (c: Cond) => `${refName(c.l)} ${opSay(c.op)} ${refName(c.r)}`;

/** Plain-English list of what differs between two experiments' setups. */
function changes(a: Experiment, b: Experiment): string[] {
  const out: string[] = [];
  const sa: Strategy = a.strategy, sb: Strategy = b.strategy;
  if (a.instrument?.symbol !== b.instrument?.symbol) out.push(`Instrument: ${a.instrument?.symbol} → ${b.instrument?.symbol}`);
  if ((sa.side ?? "long") !== (sb.side ?? "long")) out.push(`Direction: ${sa.side === "short" ? "short" : "long"} → ${sb.side === "short" ? "short" : "long"}`);
  if (sa.tf !== sb.tf) out.push(`Candles: ${TF_NAME[sa.tf]} → ${TF_NAME[sb.tf]}`);
  if (a.days !== b.days) out.push(`Test period: ${a.days} → ${b.days} days`);
  const rules = (s: Strategy, k: "entry" | "exit") => (s[k] ?? []).map(condText).join(" · ") || "none";
  if (rules(sa, "entry") !== rules(sb, "entry") || sa.entryJoin !== sb.entryJoin) out.push(`Entry: ${rules(sa, "entry")} → ${rules(sb, "entry")}`);
  if (rules(sa, "exit") !== rules(sb, "exit")) out.push(`Exit: ${rules(sa, "exit")} → ${rules(sb, "exit")}`);
  const risk: [keyof Strategy["risk"], string, string][] = [["sl", "Stop loss", "%"], ["tgt", "Target", "%"], ["trail", "Trailing stop", "%"],
    ["maxBars", "Time limit", " candles"], ["riskPct", "Risk per trade", "%"], ["capital", "Capital", ""], ["brokerage", "Brokerage", ""], ["slippage", "Slippage", "%"]];
  for (const [k, label, unit] of risk) {
    const x = sa.risk[k] ?? 0, y = sb.risk[k] ?? 0;
    if (x !== y) out.push(`${label}: ${x || "off"}${x ? unit : ""} → ${y || "off"}${y ? unit : ""}`);
  }
  const say = (v: unknown) => (v === "" || v == null || v === 0 ? "off" : String(v));
  if ((sa.risk.stopType ?? "pct") !== (sb.risk.stopType ?? "pct")) out.push(`Stop measured in: ${sa.risk.stopType ?? "pct"} → ${sb.risk.stopType ?? "pct"}`);
  if ((sa.risk.tgtType ?? "pct") !== (sb.risk.tgtType ?? "pct")) out.push(`Target measured in: ${sa.risk.tgtType ?? "pct"} → ${sb.risk.tgtType ?? "pct"}`);
  if ((sa.risk.sizing ?? "risk") !== (sb.risk.sizing ?? "risk") || (sa.risk.perTrade ?? 0) !== (sb.risk.perTrade ?? 0) || (sa.risk.leverage ?? 1) !== (sb.risk.leverage ?? 1))
    out.push(`Position size: ${sa.risk.sizing ?? "risk"} → ${sb.risk.sizing ?? "risk"}`);
  if (rules(sa, "shortEntry" as "entry") !== rules(sb, "shortEntry" as "entry")) out.push(`Short entry: ${(sa.shortEntry ?? []).map(condText).join(" · ") || "none"} → ${(sb.shortEntry ?? []).map(condText).join(" · ") || "none"}`);
  if (sa.entryJoin !== sb.entryJoin || (sa.minScore ?? 0) !== (sb.minScore ?? 0)) out.push(`Rules combine: ${sa.entryJoin}${sa.entryJoin === "score" ? ` ≥ ${sa.minScore}` : ""} → ${sb.entryJoin}${sb.entryJoin === "score" ? ` ≥ ${sb.minScore}` : ""}`);
  const labels: [keyof NonNullable<Strategy["session"]>, string][] = [["start", "First entry"], ["end", "Last entry"], ["squareoff", "Square-off"],
    ["maxTradesDay", "Trades a day"], ["cooldown", "Cooldown (candles)"], ["dailyLossPct", "Daily loss cap %"]];
  for (const [k, label] of labels) {
    const x = sa.session?.[k] ?? "", y = sb.session?.[k] ?? "";
    if (say(x) !== say(y)) out.push(`${label}: ${say(x)} → ${say(y)}`);
  }
  return out;
}

type Line = { label: string; a: string; b: string; winA: boolean; winB: boolean };

/* /n/:id/compare: two experiments side by side: what changed, the return curves and the numbers. Built from the kit. */
export function CompareExperiments() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { nb, problem, reload } = useNotebook(id);
  if (!nb && problem) return <NotebookProblem problem={problem} retry={reload} />;
  if (!nb) return <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Compare experiments" /><Card><Skeleton label="Opening the notebook" /></Card></div>;
  const exps = nb.experiments;
  const va = Number(params.get("a")), vb = Number(params.get("b"));
  const a = exps.find((e) => e.v === va) ?? exps[exps.length - 2], b = exps.find((e) => e.v === vb) ?? exps[exps.length - 1];
  if (!a || !b || a.v === b.v) return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Compare experiments" lede={<Link to={`/n/${nb.id}`} className="link">← {nb.name}</Link>} />
      <EmptyState title="Nothing to compare yet" action={{ label: exps.length ? "Change the rules and run again" : "Run the first test", to: `/n/${nb.id}` }}>
        Comparing needs two runs of this notebook. {exps.length ? "It has one so far: change one thing and run it again." : "It has none yet."}
      </EmptyState>
    </div>
  );
  const pick = (k: "a" | "b", v: number) => { const p = new URLSearchParams(params); p.set(k, String(v)); nav(`?${p}`, { replace: true }); };

  // both equity curves as % return, on one date axis
  const tz = tzOf(b.instrument);
  const ret = (e: Experiment) => {
    const m = new Map<string, number>();
    const start = e.strategy.risk.capital;
    e.series.t.forEach((t, i) => { const v = e.series.equity[i]; if (v != null) m.set(t.slice(0, 10), (v / start - 1) * 100); });
    return m;
  };
  const ra = ret(a), rb = ret(b);
  const dates = Array.from(new Set([...ra.keys(), ...rb.keys()])).sort();
  const lbl = dates.map((d) => new Date(d).toLocaleDateString("en-GB", { timeZone: tz, month: "short", year: "2-digit" }));
  const diff = changes(a, b);
  const cur = b.instrument?.currency;
  const defs: [string, (e: Experiment) => string, (e: Experiment) => number | null, boolean][] = [
    ["Return after costs", (e) => pct(e.stats.ret), (e) => e.stats.ret, true],
    ["Yearly return", (e) => pct(e.stats.cagr), (e) => e.stats.cagr, true],
    ["Worst drop", (e) => pct(-Math.abs(e.stats.mdd)), (e) => -Math.abs(e.stats.mdd), true],
    ["Trades", (e) => String(e.stats.n), () => null, false],
    ["Win rate", (e) => `${e.stats.win.toFixed(0)}%`, (e) => e.stats.win, true],
    ["Sharpe", (e) => num(e.stats.sharpe, 2), (e) => e.stats.sharpe, true],
    ["Costs paid", (e) => money(e.costs.total, cur), (e) => -e.costs.total, true],
    ["Checks passed", (e) => `${e.verdict.passed} of ${e.verdict.total}`, (e) => e.verdict.passed, true],
    ["Buy and hold", (e) => pct(e.stats.buy_hold_ret), () => null, false],
  ];
  const lines: Line[] = defs.map(([label, show, score, better]) => {
    const x = score(a), y = score(b);
    return { label, a: show(a), b: show(b), winA: better && x != null && y != null && x > y, winB: better && x != null && y != null && y > x };
  });
  const cols: Column<Line>[] = [
    { key: "m", header: "Measure", rowHeader: true, cell: (l) => l.label },
    { key: "a", header: `v${a.v}`, numeric: true, cell: (l) => (l.winA ? <b>{l.a}</b> : l.a) },
    { key: "b", header: `v${b.v}`, numeric: true, cell: (l) => (l.winB ? <b>{l.b}</b> : l.b) },
  ];
  const opts = exps.map((e) => ({ value: e.v, label: `v${e.v} · ${e.label}` }));
  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title={`v${a.v} against v${b.v}`} lede={<Link to={`/n/${nb.id}`} className="link">← {nb.name}</Link>} />
      <Card label="Pick two runs">
        <FormGrid label="Pick two runs">
          <Field label="Before">{(fid) => <Select id={fid} value={a.v} onChange={(v) => pick("a", Number(v))} options={opts} />}</Field>
          <Field label="After">{(fid) => <Select id={fid} value={b.v} onChange={(v) => pick("b", Number(v))} options={opts} />}</Field>
        </FormGrid>
      </Card>
      <div className="k-two">
        {[a, b].map((e) => (
          <Card key={e.v} label={`v${e.v}`}>
            <span className="k-eyebrow">v{e.v} · {e.label}</span>
            <div><VerdictBadge v={e.verdict.verdict} /></div>
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
        <XYChart ariaLabel="Both experiments' return over time" height={260} times={dates} labels={lbl}
          series={[{ id: "a", values: dates.map((d) => ra.get(d) ?? null), color: "var(--muted)", width: 1.5, dash: "5 4", label: `v${a.v} · ${a.label}` },
            { id: "b", values: dates.map((d) => rb.get(d) ?? null), color: "var(--series-1)", label: `v${b.v} · ${b.label}` }]}
          format={(v) => pct(v)} axisFormat={(v) => pctTick(v, true, 0)} refs={[{ v: 0, strong: true }]} />
      </Card>
      <Card label="The numbers">
        <CardHead level={3} title="The numbers" info="Bold marks the larger of the two on each line. A higher backtest figure is not proof: the verdict's honesty checks are what test for luck." infoLabel="About the numbers" />
        <DataTable label="Compared numbers" columns={cols} rows={lines} rowKey={(l) => l.label} />
      </Card>
    </div>
  );
}
