import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { money, pct, TF_NAME, tzOf } from "../lib/format";
import { refName, opSay } from "../lib/rules";
import type { Cond, Experiment, Strategy } from "../lib/types";
import { LineChart, Legend } from "../components/Charts";
import { Info, Loading, VerdictBadge } from "../components/ui";
import { useNotebook } from "./NotebookPage";

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

export function CompareExperiments() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { nb } = useNotebook(id);
  if (!nb) return <Loading label="Opening the notebook" />;
  const exps = nb.experiments;
  const va = Number(params.get("a")), vb = Number(params.get("b"));
  const a = exps.find((e) => e.v === va) ?? exps[exps.length - 2], b = exps.find((e) => e.v === vb) ?? exps[exps.length - 1];
  if (!a || !b || a.v === b.v) return (
    <div className="stack" style={{ gap: 16 }}>
      <Link to={`/n/${nb.id}`} className="link">← {nb.name}</Link>
      <p className="muted">Run at least two experiments in this notebook to compare them.</p>
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
  const rows: [string, (e: Experiment) => string, (e: Experiment) => number | null, boolean][] = [
    ["Return after costs", (e) => pct(e.stats.ret), (e) => e.stats.ret, true],
    ["Yearly return", (e) => pct(e.stats.cagr), (e) => e.stats.cagr, true],
    ["Worst drop", (e) => pct(-Math.abs(e.stats.mdd)), (e) => -Math.abs(e.stats.mdd), true],
    ["Trades", (e) => String(e.stats.n), () => null, false],
    ["Win rate", (e) => `${e.stats.win.toFixed(0)}%`, (e) => e.stats.win, true],
    ["Sharpe", (e) => e.stats.sharpe.toFixed(2), (e) => e.stats.sharpe, true],
    ["Costs paid", (e) => money(e.costs.total, cur), (e) => -e.costs.total, true],
    ["Checks passed", (e) => `${e.verdict.passed} of ${e.verdict.total}`, (e) => e.verdict.passed, true],
    ["Buy and hold", (e) => pct(e.stats.buy_hold_ret), () => null, false],
  ];
  return (
    <div className="stack" style={{ gap: 24 }}>
      <Link to={`/n/${nb.id}`} className="link" style={{ textDecoration: "none" }}>← {nb.name}</Link>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Compare experiments</span>
        <h1 className="serif" style={{ fontSize: "clamp(30px, 4vw, 44px)", fontWeight: 400, letterSpacing: "-0.02em" }}>v{a.v} against v{b.v}</h1>
        <div className="row wrap" style={{ gap: 12 }}>
          {(["a", "b"] as const).map((k) => (
            <label key={k} className="field" style={{ minWidth: 220 }}>{k === "a" ? "Before" : "After"}
              <select value={(k === "a" ? a : b).v} onChange={(e) => pick(k, Number(e.target.value))}>
                {exps.map((e) => <option key={e.v} value={e.v}>v{e.v} · {e.label}</option>)}
              </select>
            </label>
          ))}
        </div>
      </div>
      <div className="grid2">
        {[a, b].map((e) => (
          <Link key={e.v} to={`/n/${nb.id}/e/${e.v}`} className="card stack" style={{ gap: 8, textDecoration: "none", color: "inherit" }}>
            <span className="eyebrow">v{e.v} · {e.label}</span>
            <div><VerdictBadge v={e.verdict.verdict} /></div>
            <span className="serif" style={{ fontSize: 22, lineHeight: 1.25 }}>{e.verdict.headline}</span>
            <span className="small muted">{e.verdict.summary}</span>
          </Link>
        ))}
      </div>
      <section className="card stack" style={{ gap: 10 }}>
        <h2 className="h3 row" style={{ gap: 0 }}>What changed<Info>Every difference in the setup between the two experiments. If more than one thing changed, you can't tell which one made the difference: change one thing at a time.</Info></h2>
        {diff.length === 0 ? <p className="small muted">Same setup. The results differ only if the prices did (a later run includes newer candles).</p>
          : <ul className="bullets small">{diff.map((d) => <li key={d}>{d}</li>)}</ul>}
        {diff.length > 2 && <p className="hint">Several things changed at once, so it's hard to say which one mattered.</p>}
      </section>
      <section className="card stack" style={{ gap: 12 }}>
        <h2 className="h3">Return over the test</h2>
        <LineChart ariaLabel="Both experiments' return over time" height={260} labels={lbl} axisLabels={lbl}
          lines={[{ values: dates.map((d) => ra.get(d) ?? null), color: "var(--dash)", width: 2, label: `v${a.v}` },
            { values: dates.map((d) => rb.get(d) ?? null), color: "var(--blue)", width: 2.4, label: `v${b.v}` }]}
          format={(v) => pct(v)} baseline={0} />
        <Legend items={[{ label: `v${a.v} · ${a.label}`, color: "var(--dash)" }, { label: `v${b.v} · ${b.label}`, color: "var(--blue)" }]} />
      </section>
      <section className="card" style={{ padding: 0 }}>
        <div className="table-wrap" style={{ margin: 0 }}>
          <table className="cmp-table">
            <thead><tr><th>Measure</th><th>v{a.v}</th><th>v{b.v}</th></tr></thead>
            <tbody>{rows.map(([label, show, score, better]) => {
              const x = score(a), y = score(b);
              const winB = better && x != null && y != null && y > x, winA = better && x != null && y != null && x > y;
              return <tr key={label}><td>{label}</td>
                <td className="num" style={{ fontWeight: winA ? 700 : 400 }}>{show(a)}</td>
                <td className="num" style={{ fontWeight: winB ? 700 : 400 }}>{show(b)}</td></tr>;
            })}</tbody>
          </table>
        </div>
      </section>
      <p className="hint">Bold marks the better of the two on each line. A better backtest isn't proof: trust the verdict's honesty checks, not the return alone.</p>
    </div>
  );
}
