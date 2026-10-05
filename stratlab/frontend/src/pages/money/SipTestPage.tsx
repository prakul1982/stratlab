import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { dateOnly, money } from "../../lib/format";
import type { Instrument, Market } from "../../lib/types";
import { InstrumentSearch } from "../../components/InstrumentSearch";
import { LineChart } from "../../components/Charts";
import { Info } from "../../components/ui";
import { sipParams } from "../../lib/sip";

/* Test a stock or ETF SIP before setting one up: a fixed amount (or number of shares) every day, week or month into one
 * Indian stock or ETF or a split across up to 10, with a yearly step-up and an optional dip rule, on past closes with
 * real charges. The same money as a lump sum beside it, and (Basic) the same SIP from every start month. History of
 * the user's own rule: never a "best" setting. */

type Leg = { symbol: string; weight: number; units: number; buys: number; spent: number; avg_price: number | null; last: number | null; value: number; cash_waiting: number };
type Run = {
  start: string; end: string; instalments: number; invested: number; value: number; gain: number; gain_pct: number; xirr: number | null;
  deepest_fall_pct: number; underwater_days: number; underwater_from: string | null; underwater_to: string | null; charges: number; stamp: number;
  cash_waiting: number; legs?: Leg[]; series?: { d: string; invested: number; value: number }[];
};
type Lump = { invested: number; value: number; gain: number; xirr: number | null; deepest_fall_pct: number; charges: number; series: { d: string; value: number }[] };
type SpreadRun = { start: string; xirr: number; deepest_fall_pct: number; plain_xirr?: number | null };
type Spread = { years: number; count: number; every_months: number; worst: SpreadRun; best: SpreadRun; median: number; below_zero: number; runs: SpreadRun[];
  dip?: { compared: number; beat: number; median_diff_pp: number | null; worst_diff_pp: number | null; best_diff_pp: number | null } };
type Reply = {
  result: Run; lump_sum: Lump | null; plain: Run | null; full: boolean; plan: string; legs: { symbol: string; name: string; inst_id: string; weight: number }[];
  history: { from: string; to: string }; window: { from: string; to: string; years: number }; words: string; spread: Spread | null;
  assumptions: string[]; disclaimer: string;
};
type Pick = { id: string; symbol: string; name: string; weight: number };
type Rule = "plain" | "only_dips" | "extra_on_dips";

const INDIA = { id: "IN", name: "India" } as Market;
const inr = (v: number | null | undefined) => money(v, "INR", 0);
const rate = (v: number | null | undefined) => (v == null ? "–" : `${(v * 100).toFixed(1)}%`);
const signedPct = (v: number | null | undefined) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)} pts`);
const month = (m: string) => new Date(`${m.slice(0, 7)}-01T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
const span = (days: number) => (days >= 365 ? `${(days / 365).toFixed(1)} years` : days >= 60 ? `${Math.round(days / 30)} months` : `${days} days`);

export function SipTestPage() {
  const { me, fail } = useApp();
  const [params] = useSearchParams();
  const [picks, setPicks] = useState<Pick[]>([]);
  const [mode, setMode] = useState<"amount" | "qty">("amount");
  const [amount, setAmount] = useState(() => sipParams(params).amount ?? "10000");
  const [qty, setQty] = useState("1");
  const [freq, setFreq] = useState<"daily" | "weekly" | "monthly">(() => sipParams(params).freq ?? "monthly");
  const [dom, setDom] = useState("1");
  const [weekday, setWeekday] = useState("0");
  const [stepUp, setStepUp] = useState("0");
  const [years, setYears] = useState(() => sipParams(params).years ?? "5");
  const [brokerage, setBrokerage] = useState("0");
  const [rule, setRule] = useState<Rule>("plain");
  const [dip, setDip] = useState("10");
  const [lookback, setLookback] = useState("252");
  const [extra, setExtra] = useState("50");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [res, setRes] = useState<Reply | null>(null);
  const [copied, setCopied] = useState(false);
  const canDip = me?.plan_info?.features?.sip_luck ?? true;

  // opened from a company or ETF page: that one, ready to test
  const wanted = (params.get("symbol") ?? "").toUpperCase();
  useEffect(() => {
    if (!wanted) return;
    api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(wanted)}&market=IN`).then((r) => {
      const hit = r.find((i) => i.symbol === wanted && (i.type === "EQ" || i.type === "ETF")) ?? null;
      if (hit) setPicks((p) => (p.length ? p : [{ id: hit.id, symbol: hit.symbol, name: hit.name ?? "", weight: 100 }]));
    }).catch(() => undefined);
  }, [wanted]);

  const add = (i: Instrument) => {
    if (i.type !== "EQ" && i.type !== "ETF") { setProblem(`${i.symbol} isn't a stock or ETF. A SIP test takes shares and ETFs only.`); return; }
    setProblem(null);
    setPicks((p) => {
      if (p.some((x) => x.id === i.id) || p.length >= 10) return p;
      const next = [...p, { id: i.id, symbol: i.symbol, name: i.name ?? "", weight: 0 }];
      const even = Math.floor(100 / next.length);
      return next.map((x, k) => ({ ...x, weight: k === 0 ? 100 - even * (next.length - 1) : even }));
    });
  };
  const total = picks.reduce((s, p) => s + (Number(p.weight) || 0), 0);

  const run = async () => {
    setBusy(true); setProblem(null); setCopied(false);
    try {
      const body = {
        legs: picks.map((p) => ({ inst_id: p.id, weight: picks.length > 1 ? Number(p.weight) : 100 })), mode, amount: Number(amount), qty: Number(qty), freq,
        dom: Number(dom), weekday: Number(weekday), step_up: Number(stepUp) || 0, years: Number(years), brokerage: Number(brokerage) || 0,
        rule, dip: Number(dip), lookback: Number(lookback), extra: Number(extra),
      };
      setRes(await api<Reply>("/invest/sip-test", { method: "POST", body }));
    } catch (e) {
      const msg = (e as { message?: string })?.message;
      if (msg) setProblem(msg); else fail(e);
    } finally { setBusy(false); }
  };

  const r = res?.result;
  const chart = useMemo(() => {
    if (!r?.series) return null;
    return { labels: r.series.map((p) => dateOnly(p.d)), times: r.series.map((p) => p.d), invested: r.series.map((p) => p.invested), value: r.series.map((p) => p.value) };
  }, [r]);
  const ready = picks.length > 0 && (picks.length === 1 || Math.abs(total - 100) < 0.5) && (mode === "amount" ? Number(amount) > 0 : Number(qty) >= 1);

  return (
    <div className="stack sip-test" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Money · before you start a SIP</span>
        <h1 className="page-title">Test a SIP</h1>
        <p className="page-sub">What a stock or ETF SIP of your own would have done on past prices, with the charges on every purchase, beside the same
          money put in on day one. History of the rule you set, not a forecast or a suggestion.</p>
      </div>

      <section className="card stack" style={{ gap: 14 }} aria-label="Your SIP">
        <h2 className="h2">Your SIP</h2>
        <div className="stack" style={{ gap: 8 }}>
          <span className="small">Stocks or ETFs, up to 10</span>
          <InstrumentSearch market={INDIA} compact onPick={add} />
          {picks.length > 0 && (
            <ul className="stack" style={{ gap: 6, margin: 0, padding: 0, listStyle: "none" }} aria-label="In this SIP">
              {picks.map((p) => (
                <li key={p.id} className="row wrap" style={{ gap: 10, alignItems: "center" }}>
                  <span style={{ minWidth: 120 }}><b>{p.symbol}</b> <span className="tiny muted">{p.name !== p.symbol ? p.name : ""}</span></span>
                  {picks.length > 1 && (
                    <label className="field" style={{ width: 110 }}>Share (%)
                      <input className="input" type="number" min={1} max={100} value={p.weight} aria-label={`Share for ${p.symbol} (%)`}
                        onChange={(e) => setPicks((all) => all.map((x) => (x.id === p.id ? { ...x, weight: Number(e.target.value) } : x)))} />
                    </label>
                  )}
                  <button type="button" className="btn quiet sm" onClick={() => setPicks((all) => all.filter((x) => x.id !== p.id))} aria-label={`Remove ${p.symbol}`}>Remove</button>
                </li>
              ))}
            </ul>
          )}
          {picks.length > 1 && Math.abs(total - 100) >= 0.5 && <p className="tiny" role="status" style={{ margin: 0 }}>The shares add up to {total}%; make them 100%.</p>}
        </div>

        <div className="sip-grid">
          <div className="seg" role="group" aria-label="Each time">
            <button type="button" aria-pressed={mode === "amount"} onClick={() => setMode("amount")}>An amount</button>
            <button type="button" aria-pressed={mode === "qty"} onClick={() => { setMode("qty"); setRule("plain"); }}>Shares</button>
          </div>
          {mode === "amount"
            ? <label className="field">Amount each time (₹)<input className="input" type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
            : <label className="field">Shares each time<input className="input" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} /></label>}
          <label className="field">How often
            <select value={freq} onChange={(e) => setFreq(e.target.value as typeof freq)}>
              <option value="monthly">Every month</option><option value="weekly">Every week</option><option value="daily">Every trading day</option>
            </select>
          </label>
          {freq === "monthly" && <label className="field">Day of the month<input className="input" type="number" min={1} max={28} value={dom} onChange={(e) => setDom(e.target.value)} /></label>}
          {freq === "weekly" && (
            <label className="field">Day of the week
              <select value={weekday} onChange={(e) => setWeekday(e.target.value)}>{WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select>
            </label>
          )}
          <label className="field">Step-up a year (%)<input className="input" type="number" min={0} max={50} value={stepUp} onChange={(e) => setStepUp(e.target.value)} /></label>
          <label className="field">Years
            <select value={years} onChange={(e) => setYears(e.target.value)}>{Array.from({ length: 10 }, (_, i) => i + 1).map((y) => <option key={y} value={y}>{y}</option>)}</select>
          </label>
          <label className="field">Brokerage an order (₹)<input className="input" type="number" min={0} value={brokerage} onChange={(e) => setBrokerage(e.target.value)} /></label>
          <label className="field">Dip rule
            <select value={rule} onChange={(e) => setRule(e.target.value as Rule)} disabled={mode === "qty"}>
              <option value="plain">None: invest on schedule</option>
              <option value="only_dips" disabled={!canDip}>Only on dips{canDip ? "" : " (Basic)"}</option>
              <option value="extra_on_dips" disabled={!canDip}>Extra on dips{canDip ? "" : " (Basic)"}</option>
            </select>
          </label>
          {rule !== "plain" && <>
            <label className="field">Fall from the recent high (%)<input className="input" type="number" min={1} max={60} value={dip} onChange={(e) => setDip(e.target.value)} /></label>
            <label className="field">Recent high over
              <select value={lookback} onChange={(e) => setLookback(e.target.value)}>
                <option value="20">20 trading days</option><option value="60">60 trading days</option><option value="125">125 trading days</option><option value="252">252 trading days</option>
              </select>
            </label>
            {rule === "extra_on_dips" && <label className="field">Extra on a dip (%)<input className="input" type="number" min={1} max={500} value={extra} onChange={(e) => setExtra(e.target.value)} /></label>}
          </>}
        </div>
        {!canDip && <div className="banner"><span>Dip rules, and the same SIP run from every start month, are on the Basic plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>}
        <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
          <button type="button" className="btn" disabled={!ready || busy} onClick={run}>{busy ? "Running…" : "Run the test"}</button>
          {problem && <span className="small" role="alert">{problem}</span>}
        </div>
      </section>

      {res && r && (
        <section className="card stack" style={{ gap: 14 }} aria-label="What the SIP did">
          <div className="stack" style={{ gap: 4 }}>
            <h2 className="h2">What this SIP did</h2>
            <p className="small muted" style={{ margin: 0 }}>{dateOnly(r.start)} to {dateOnly(r.end)}: {r.instalments} instalment{r.instalments === 1 ? "" : "s"}{res.legs.length > 1 ? ` into ${res.legs.map((l) => `${l.weight}% ${l.symbol}`).join(", ")}` : ` into ${res.legs[0].symbol}`}.</p>
          </div>
          <div className="stat-row">
            <div className="stat"><span className="tiny muted">Put in</span><b className="num">{inr(r.invested)}</b></div>
            <div className="stat"><span className="tiny muted">Value at the end</span><b className="num">{inr(r.value)}</b><span className="tiny muted">{r.gain_pct > 0 ? "+" : ""}{r.gain_pct.toFixed(1)}% on the money put in</span></div>
            <div className="stat"><span className="tiny muted">XIRR</span><b className="num">{rate(r.xirr)}</b></div>
            <div className="stat"><span className="tiny muted">Deepest fall <Info label="What the deepest fall is">The largest drop of the pot from a high, leaving out the instalments themselves.</Info></span><b className="num">{r.deepest_fall_pct.toFixed(1)}%</b></div>
            <div className="stat"><span className="tiny muted">Longest below the money put in</span><b className="num">{r.underwater_days ? span(r.underwater_days) : "Never"}</b>{r.underwater_from && <span className="tiny muted">{dateOnly(r.underwater_from)} to {dateOnly(r.underwater_to)}</span>}</div>
            <div className="stat"><span className="tiny muted">Charges</span><b className="num">{inr(r.charges)}</b><span className="tiny muted">{inr(r.stamp)} of it stamp duty</span></div>
          </div>
          {r.cash_waiting > 1 && <p className="small" style={{ margin: 0 }}>{inr(r.cash_waiting)} was still waiting as cash at the end{res.plain ? ", for a dip that hadn't come" : ", short of a whole share"}; it is counted in the value.</p>}
          {chart && (
            <LineChart lines={[{ values: chart.value, color: "var(--series-1)", width: 2, label: "Value" }, { values: chart.invested, color: "var(--series-2)", width: 2, dash: "4 3", label: "Put in" }]}
              labels={chart.labels} times={chart.times} format={inr} height={220} legend ariaLabel="The SIP's value and the money put in, over time" />
          )}

          <div className="table-wrap">
            <table aria-label="Side by side">
              <thead><tr><th style={{ textAlign: "left" }}></th><th>Put in</th><th>Value</th><th>XIRR</th><th>Deepest fall</th><th>Charges</th></tr></thead>
              <tbody>
                <tr><td style={{ textAlign: "left" }}>This SIP</td><td className="num">{inr(r.invested)}</td><td className="num">{inr(r.value)}</td><td className="num">{rate(r.xirr)}</td><td className="num">{r.deepest_fall_pct.toFixed(1)}%</td><td className="num">{inr(r.charges)}</td></tr>
                {res.plain && <tr><td style={{ textAlign: "left" }}>The same SIP, no dip rule</td><td className="num">{inr(res.plain.invested)}</td><td className="num">{inr(res.plain.value)}</td><td className="num">{rate(res.plain.xirr)}</td><td className="num">{res.plain.deepest_fall_pct.toFixed(1)}%</td><td className="num">{inr(res.plain.charges)}</td></tr>}
                {res.lump_sum && <tr><td style={{ textAlign: "left" }}>All of it on {dateOnly(r.start)}</td><td className="num">{inr(res.lump_sum.invested)}</td><td className="num">{inr(res.lump_sum.value)}</td><td className="num">{rate(res.lump_sum.xirr)}</td><td className="num">{res.lump_sum.deepest_fall_pct.toFixed(1)}%</td><td className="num">{inr(res.lump_sum.charges)}</td></tr>}
              </tbody>
            </table>
          </div>

          {r.legs && r.legs.length > 0 && (
            <div className="table-wrap">
              <table aria-label="Each stock or ETF">
                <thead><tr><th style={{ textAlign: "left" }}>Stock or ETF</th><th>Shares</th><th>Purchases</th><th>Average cost</th><th>Last close</th><th>Value</th></tr></thead>
                <tbody>{r.legs.map((l) => (
                  <tr key={l.symbol}><td style={{ textAlign: "left" }}><b>{l.symbol}</b>{r.legs!.length > 1 && <div className="tiny muted">{l.weight}% of each instalment</div>}</td>
                    <td className="num">{l.units.toLocaleString("en-IN")}</td><td className="num">{l.buys}</td><td className="num">{money(l.avg_price, "INR", 2)}</td>
                    <td className="num">{money(l.last, "INR", 2)}</td><td className="num">{inr(l.value)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}

          {res.spread && (
            <div className="stack" style={{ gap: 8 }} aria-label="Every start month" role="region">
              <h3 className="h3" style={{ margin: 0 }}>The same SIP from every start month</h3>
              <p className="small muted" style={{ margin: 0 }}>{res.spread.count} runs of {res.spread.years} year{res.spread.years === 1 ? "" : "s"} each, starting {res.spread.every_months > 1 ? `every ${res.spread.every_months} months` : "every month"} from {month(res.spread.runs[0].start)}. How much the answer depends on when you began.</p>
              <div className="stat-row">
                <div className="stat"><span className="tiny muted">Lowest XIRR</span><b className="num">{rate(res.spread.worst.xirr)}</b><span className="tiny muted">from {month(res.spread.worst.start)}</span></div>
                <div className="stat"><span className="tiny muted">Middle XIRR</span><b className="num">{rate(res.spread.median)}</b></div>
                <div className="stat"><span className="tiny muted">Highest XIRR</span><b className="num">{rate(res.spread.best.xirr)}</b><span className="tiny muted">from {month(res.spread.best.start)}</span></div>
                <div className="stat"><span className="tiny muted">Runs below zero</span><b className="num">{res.spread.below_zero} of {res.spread.count}</b></div>
              </div>
              <LineChart lines={[{ values: res.spread.runs.map((x) => x.xirr * 100), color: "var(--series-1)", width: 2, label: "XIRR" },
                ...(res.spread.dip ? [{ values: res.spread.runs.map((x) => (x.plain_xirr == null ? null : x.plain_xirr * 100)), color: "var(--series-2)", width: 2, dash: "4 3", label: "No dip rule" }] : [])]}
                labels={res.spread.runs.map((x) => `Started ${month(x.start)}`)} times={res.spread.runs.map((x) => `${x.start}-01`)} format={(v) => `${v.toFixed(1)}%`} baseline={0}
                height={200} legend={!!res.spread.dip} ariaLabel="XIRR by start month" />
              {res.spread.dip && (
                <p className="small" style={{ margin: 0 }}>The dip rule's XIRR was above the plain SIP's in {res.spread.dip.beat} of {res.spread.dip.compared} start months;
                  the middle difference was {signedPct(res.spread.dip.median_diff_pp)} (from {signedPct(res.spread.dip.worst_diff_pp)} to {signedPct(res.spread.dip.best_diff_pp)}).</p>
              )}
            </div>
          )}
          {!res.full && <div className="banner"><span>The same SIP from every start month, and dip rules with their luck check, are on the {res.plan} plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>}

          <div className="stack" style={{ gap: 6 }}>
            <h3 className="h3" style={{ margin: 0 }}>Your rule in plain words</h3>
            <p className="small" style={{ margin: 0 }} data-testid="sip-words">{res.words}</p>
            <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
              <button type="button" className="btn quiet sm" onClick={() => { navigator.clipboard?.writeText(res.words).then(() => setCopied(true)).catch(() => setCopied(false)); }}>Copy the rule</button>
              {copied && <span className="tiny muted" role="status">Copied.</span>}
            </div>
          </div>
          <p className="tiny muted" style={{ margin: 0 }}>Prices from {dateOnly(res.history.from)} to {dateOnly(res.history.to)}. {res.disclaimer}</p>
          <details className="small">
            <summary className="tiny" style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>How this is worked out</summary>
            <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{res.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
          </details>
        </section>
      )}
    </div>
  );
}
