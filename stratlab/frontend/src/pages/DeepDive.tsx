import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { pct, signClass } from "../lib/format";
import { Panel, ResearchNav, TrendBars } from "../components/Research";
import { Loading } from "../components/ui";

type Year = { year: string; sales: number | null; profit: number | null; opm: number | null; capex: number | null;
  capex_pct_sales: number | null; cfo: number | null; cfi: number | null; fcf: number | null; debt: number | null };
type Quarter = { quarter: string; sales: number | null; profit: number | null; opm: number | null; sales_yoy: number | null };
type Doc = { kind: string; at: string; title: string; url: string };
type Source = { title: string; at: string; url: string; kind: string } | null;
type Target = { metric: string; low: number | null; high: number | null; period: string | null; what: string; quote: string; said_at: string;
  source: { title: string; at: string; url: string }; actual: number | null; unit: string; result: "met" | "missed" | "pending" | "unchecked";
  revised?: { low: number | null; high: number | null; at: string; quote: string } | null };
export type CheckState = "pass" | "watch" | "fail" | "na";
type Checklist = { checks: { group: string; label: string; state: CheckState; value: string; rule: string }[];
  counts: Record<CheckState, number>; scored: number; industry?: { group: string; label: string; path: string[]; note: string } };
type Measure = { name: string; value: string; period: string | null; change: string | null; quote: string; source: Source };
type Card = { rows: Target[]; met: number; missed: number; pending: number; unchecked: number; score: number | null;
  read: { kind: string; at: string; title: string }[]; problems: string[]; at: string };
export interface DeepView {
  symbol: string; region?: "IN" | "US"; ai?: boolean; source_url?: string | null; name: string; about: string; documents: Doc[]; doc_note: string | null; reads_stale: boolean;
  calls: number; card: Card | null; card_stale: boolean; checklist: Checklist;
  industry_measures?: { key: string; label: string | null; measures: string[] };
  valuation?: { name: string; short: string; value: number | null; pe: number | null; why: string };
  numbers: { years: Year[]; quarters: Quarter[]; unit: string; capex_3y_total: number | null; bank?: boolean; notes?: string[]; capex_reported?: boolean;
    growth: { sales_cagr_3y: number | null; sales_cagr_5y: number | null; profit_cagr_3y: number | null; profit_cagr_5y: number | null;
      eps_cagr_3y?: number | null; eps_cagr_5y?: number | null } };
  reads: null | {
    at: string; problems: string[]; read: { kind: string; at: string; title: string }[];
    business: null | { summary: string; customers: string; drivers: string[]; strengths: string[]; risks: string[]; measures?: Measure[]; industry?: string | null;
      segments: { name: string; share_pct: number | null; what: string }[]; sources: Source[] };
    plans: null | { capex: { what: string; amount: string | null; size?: string | null; timeline: string | null; status: string; quote: string; source: Source }[];
      outlook: { statement: string; quote: string; source: Source }[]; sources: Source[] };
  };
}

const cr = (v: number | null | undefined) => (v == null ? "–" : v.toLocaleString("en-IN", { maximumFractionDigits: 2 }));
const usd = (v: number | null | undefined) => (v == null ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: 2 }));
const pc = (v: number | null | undefined) => (v == null ? "–" : `${v.toFixed(1)}%`);
const day = (s: string) => new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const KIND: Record<string, string> = { transcript: "Call transcript", presentation: "Investor presentation", annual_report: "Annual report",
  quarterly_report: "Quarterly report", earnings_release: "Earnings release" };

function Stat({ label, v, why }: { label: string; v: number | null; why?: string }) {
  return (
    <div className="stat"><span className="tiny muted">{label}</span><b className={`num ${signClass(v)}`}>{v == null ? "–" : pct(v)}</b>
      {v == null && why && <span className="tiny muted">{why}</span>}</div>
  );
}

/** Why a growth rate is blank: a loss (or zero) at the start of the period or along the way makes a yearly rate meaningless. */
function lossNote(values: (number | null | undefined)[], years: number): string | undefined {
  const span = values.slice(-(years + 1)).filter((x): x is number => x != null);
  if (span.length < years + 1) return "Not enough years reported";
  return span.some((x) => x <= 0) ? "A loss year in the period, so no yearly rate" : undefined;
}

const METRIC: Record<string, string> = { revenue_growth: "Revenue growth", profit_growth: "Profit growth", margin: "Operating margin", capex: "Capex", other: "" };
const RESULT: Record<string, [string, string]> = { met: ["Met", "pass"], missed: ["Missed", "fail"], pending: ["Not due yet", "next"], unchecked: ["Can't check", "skip"] };
const target = (lo: number | null, hi: number | null, unit: string) =>
  lo == null ? "–" : unit === "crore" ? `₹${cr(lo)}${hi != null ? `–${cr(hi)}` : ""} cr`
    : unit === "million" ? `$${usd(lo)}${hi != null ? `–${usd(hi)}` : ""} m` : `${lo}${hi != null ? `–${hi}` : ""}%`;

function ReportCard({ c }: { c: Card }) {
  const checked = c.met + c.missed;
  return (
    <>
      <div className="stat-row">
        <div className="stat"><span className="tiny muted">Targets met</span><b className="num">{checked ? `${c.met} of ${checked}` : "–"}</b></div>
        <div className="stat"><span className="tiny muted">Missed</span><b className="num">{c.missed}</b></div>
        <div className="stat"><span className="tiny muted">Not due yet</span><b className="num">{c.pending}</b></div>
        <div className="stat"><span className="tiny muted">Can't check from the numbers</span><b className="num">{c.unchecked}</b></div>
      </div>
      <p className="small" style={{ margin: 0 }}>{checked
        ? <>Of the {checked} targets from past calls that the reported numbers can settle, <b>{c.met} {c.met === 1 ? "was" : "were"} met</b> and {c.missed} missed ({c.score}% met).</>
        : "None of the targets found can be settled by the reported numbers yet."}</p>
      {c.rows.length > 0 ? (
        <div className="promises">{c.rows.map((r, i) => {
          const [label, tone] = RESULT[r.result];
          return (
            <div key={i} className="promise">
              <div className="spread" style={{ gap: 10, alignItems: "flex-start" }}>
                <span className="small">{METRIC[r.metric] ? <b>{METRIC[r.metric]}: </b> : null}{r.what}</span>
                <span className={`badge ${tone}`}>{label}</span>
              </div>
              <div className="promise-facts tiny">
                {r.period && <span><span className="muted">For</span> {r.period}</span>}
                {r.low != null && <span><span className="muted">Target</span> <b className="mono">{target(r.low, r.high, r.unit)}</b></span>}
                {r.actual != null && <span><span className="muted">Actual</span> <b className="mono">{r.unit === "crore" ? `₹${cr(r.actual)} cr` : r.unit === "million" ? `$${usd(r.actual)} m` : `${r.actual.toFixed(1)}%`}</b></span>}
                <a className="link" href={r.source.url} target="_blank" rel="noopener noreferrer" title={r.source.title}>Said {day(r.source.at)} ↗</a>
              </div>
              {r.quote && <span className="tiny muted">"{r.quote}"</span>}
              {r.revised && <span className="tiny muted">Later changed to {target(r.revised.low, r.revised.high, r.unit)} ({day(r.revised.at)}).</span>}
            </div>);
        })}</div>
      ) : <p className="small muted" style={{ margin: 0 }}>No specific targets were found in these calls.</p>}
      <p className="tiny muted" style={{ margin: 0 }}>Checked against the reported annual and quarterly numbers: growth on the year before (within 1 point; profit within 2), operating margin (within 0.5 points; the company may quote EBITDA margin, which can differ slightly), and estimated capex (within 10%). A target repeated on later calls counts once, from the first time it was said.</p>
    </>
  );
}

export const CHECK: Record<CheckState, [string, string]> = { pass: ["Pass", "pass"], watch: ["Watch", "warn"], fail: ["Fail", "fail"], na: ["No data", "skip"] };

function ChecklistPanel({ c }: { c: Checklist }) {
  const groups = [...new Set(c.checks.map((x) => x.group))];
  return (
    <Panel title="Investor checklist" span="full" info="Fixed rules on the reported numbers, the price trend, the filings and the management report card. Each rule is written under its check. A screen to help you look closer, not a recommendation.">
      <p className="small" style={{ margin: 0 }}><b>{c.counts.pass} pass</b> · {c.counts.watch} watch · {c.counts.fail} fail{c.counts.na ? ` · ${c.counts.na} without data` : ""}</p>
      {c.industry && c.industry.group !== "general" && (
        <p className="tiny muted" style={{ margin: 0 }}><b>Rules for: {c.industry.label}{c.industry.path.length ? ` (${c.industry.path.join(" › ")})` : ""}.</b> {c.industry.note}</p>)}
      <div className="checklist">{groups.map((g) => (
        <div key={g} className="check-group">
          <span className="eyebrow">{g}</span>
          {c.checks.filter((x) => x.group === g).map((x) => (
            <div key={x.label} className="check-row">
              <div className="stack" style={{ gap: 2, minWidth: 0 }}><span className="small">{x.label}</span><span className="tiny muted">{x.rule}</span></div>
              <span className="small num" style={{ textAlign: "right" }}>{x.value}</span>
              <span className={`badge ${CHECK[x.state][1]}`}>{CHECK[x.state][0]}</span>
            </div>))}
        </div>))}</div>
    </Panel>
  );
}

function SourceLink({ s }: { s: Source }) {
  return s ? <a className="link tiny" href={s.url} target="_blank" rel="noopener noreferrer" title={s.title}>{KIND[s.kind] ?? "Filing"}, {day(s.at)} ↗</a> : null;
}

export function DeepDivePage() {
  const { symbol = "" } = useParams();
  const region: "IN" | "US" = useLocation().pathname.startsWith("/research/US/") ? "US" : "IN";
  const sym = symbol.toUpperCase();
  const us = region === "US";
  const q = (extra = "") => (us ? `?region=US${extra ? `&${extra}` : ""}` : extra ? `?${extra}` : "");
  const num = us ? usd : cr;                                   // amounts in the company's own unit: $ million or ₹ crore
  const unitWord = us ? "$ million" : "₹ crore";
  const { me, fail, notify } = useApp();
  const pro = !!me?.plan_info?.features?.deepdive;
  const [v, setV] = useState<DeepView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [carding, setCarding] = useState(false);
  const [decking, setDecking] = useState(false);

  const downloadDeck = async () => {
    setDecking(true);
    try {
      const r = await api<Response>(`/research/deep/${encodeURIComponent(sym)}/deck${q()}`, { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = `${sym}-deep-dive.pptx`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } catch (e) { fail(e); } finally { setDecking(false); }
  };

  useEffect(() => {
    if (!pro) return;
    let live = true;
    setV(null); setError(null);
    api<DeepView>(`/research/deep/${encodeURIComponent(sym)}${q()}`).then((x) => live && setV(x)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [sym, pro, region]); // eslint-disable-line react-hooks/exhaustive-deps

  const readDocs = async (refresh = false) => {
    setReading(true);
    try {
      const x = await api<DeepView>(`/research/deep/${encodeURIComponent(sym)}/read${q(refresh ? "refresh=true" : "")}`, { method: "POST" });
      setV(x);
      if (x.reads?.problems?.length) notify(`Read with ${x.reads.problems.length} document${x.reads.problems.length === 1 ? "" : "s"} skipped.`);
    } catch (e) { fail(e); } finally { setReading(false); }
  };

  const checkCalls = async (refresh = false) => {
    setCarding(true);
    try {
      const x = await api<DeepView>(`/research/deep/${encodeURIComponent(sym)}/card${q(refresh ? "refresh=true" : "")}`, { method: "POST" });
      setV(x);
      if (x.card?.problems?.length) notify(`Checked with ${x.card.problems.length} call${x.card.problems.length === 1 ? "" : "s"} skipped.`);
    } catch (e) { fail(e); } finally { setCarding(false); }
  };

  const n = v?.numbers;
  const years = (n?.years ?? []).filter((y) => y.sales != null);
  const b = v?.reads?.business, p = v?.reads?.plans;
  return (
    <div className="stack" style={{ gap: 22 }}>
      <ResearchNav region={region} />
      <div className="stack" style={{ gap: 8 }}>
        <Link className="link small" to={`/research/${region}/${encodeURIComponent(sym)}`}>← {v?.name ?? sym}</Link>
        <span className="eyebrow">Deep dive · {us ? "United States" : "India"} · {sym}</span>
        <h1 className="serif" style={{ fontSize: "clamp(30px, 4vw, 44px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>{v?.name ?? sym}: business, capex and growth</h1>
        <p className="muted" style={{ fontSize: 16, maxWidth: 760 }}>{us
          ? <>The numbers the company reports to the SEC in its annual and quarterly filings (10-K and 10-Q), in $ million{v?.source_url ? <> (<a className="link" href={v.source_url} target="_blank" rel="noopener noreferrer">its filings ↗</a>)</> : null}. Facts, not advice.</>
          : "The reported numbers, and what the company itself says in its latest investor presentation and earnings calls. Facts and the company's own words, not advice."}</p>
        {v && <div className="row wrap" style={{ gap: 10 }}>
          <button className="btn quiet sm" disabled={decking} onClick={downloadDeck} title="Numbers, business, plans, report card and checklist as slides, with sources">{decking ? "Making the deck…" : "Download as slides (PowerPoint)"}</button>
          <Link className="btn quiet sm" to="/research/investor">Investor home →</Link>
        </div>}
      </div>
      {!pro && <div className="banner"><span>The deep dive is on the Pro plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>}
      {pro && error && <div className="card"><p className="muted">{error}</p></div>}
      {pro && !v && !error && <Loading label="Reading the reported numbers" />}
      {v && n && (
        <>
          <Panel title="Growth and margins" span="full" info="Compound annual growth from the reported annual sales and net profit. OPM is operating profit as a share of sales.">
            <div className="stat-row">
              <Stat label="Sales growth a year, last 3 years" v={n.growth.sales_cagr_3y} /><Stat label="Sales growth a year, last 5 years" v={n.growth.sales_cagr_5y} />
              <Stat label="Profit growth a year, last 3 years" v={n.growth.profit_cagr_3y} why={lossNote(years.map((y) => y.profit), 3)} />
              <Stat label="Profit growth a year, last 5 years" v={n.growth.profit_cagr_5y} why={lossNote(years.map((y) => y.profit), 5)} />
              {n.growth.eps_cagr_5y != null && <Stat label="Earnings per share growth a year, last 5 years" v={n.growth.eps_cagr_5y} />}
            </div>
            {(n.notes ?? []).map((t) => <p key={t} className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>{t}</p>)}
            <div className="rs-grid">
              <TrendBars points={years.map((y) => ({ y: y.year.replace("Mar ", "FY"), v: y.sales as number }))} label={us ? "Revenue" : "Sales"} unit={n.unit} />
              <TrendBars points={years.filter((y) => y.profit != null).map((y) => ({ y: y.year.replace("Mar ", "FY"), v: y.profit as number }))} label="Net profit" unit={n.unit} tone="blue" />
            </div>
            {n.quarters.length > 0 && (
              <div className="table-wrap"><table>
                <thead><tr><th>Quarter</th><th className="num">Sales</th><th className="num">vs a year ago</th><th className="num">{n.bank ? "Financing margin" : "Operating margin"}</th><th className="num">Net profit</th></tr></thead>
                <tbody>{n.quarters.slice(-8).map((q) => (
                  <tr key={q.quarter}><td>{q.quarter}</td><td className="num">{num(q.sales)}</td><td className={`num ${signClass(q.sales_yoy)}`}>{q.sales_yoy == null ? "–" : pct(q.sales_yoy)}</td>
                    <td className="num">{pc(q.opm)}</td><td className="num">{num(q.profit)}</td></tr>))}</tbody>
              </table></div>
            )}
          </Panel>

          {v.valuation && (
            <Panel title="How it's valued" span="full" info={v.valuation.why}>
              <div className="stat-row">
                <div className="stat"><span className="tiny muted">{v.valuation.name}</span><b className="num">{v.valuation.value == null ? "–" : `${v.valuation.value.toFixed(1)}×`}</b></div>
                {v.valuation.short !== "P/E" && <div className="stat"><span className="tiny muted">Price to earnings</span><b className="num">{v.valuation.pe == null ? "–" : `${v.valuation.pe.toFixed(1)}×`}</b></div>}
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>{v.valuation.why} A number to compare with similar companies, not a verdict on the price.</p>
            </Panel>
          )}

          {v.checklist && <ChecklistPanel c={v.checklist} />}

          {n.bank ? (
            <Panel title="Capex and cash" span="full">
              <p className="small muted" style={{ margin: 0 }}>This is a bank or lender: its revenue is mostly interest, and lending runs through its cash flow, so capex, free cash flow, operating margin and debt to equity don't describe it. The checklist uses return on equity instead.</p>
            </Panel>
          ) : (
          <Panel title="Capex and cash" span="full" info={n.capex_reported
            ? `Capex as the company reports it in its cash flow statement (purchases of property, plant and equipment). Free cash flow is cash from operations minus capex. Figures in ${unitWord}.`
            : `Capex is estimated from the balance sheet: the rise in fixed assets and work in progress, plus the year's depreciation. Free cash flow is cash from operations minus that capex. Figures in ${unitWord}.`}>
            {n.capex_3y_total != null && <p className="small" style={{ margin: 0 }}>{n.capex_reported ? "" : "About "}<b>{us ? `$${usd(n.capex_3y_total)} million` : `₹${cr(n.capex_3y_total)} crore`}</b> spent on capex over the last three years. Figures in {unitWord}.</p>}
            <div className="table-wrap"><table>
              <thead><tr><th>Year</th><th className="num">Sales</th><th className="num">Capex</th><th className="num">Capex / sales</th><th className="num">Cash from operations</th><th className="num">Free cash flow</th><th className="num">Debt</th></tr></thead>
              <tbody>{[...years].reverse().slice(0, 8).map((y) => (
                <tr key={y.year}><td>{y.year}</td><td className="num">{num(y.sales)}</td><td className="num">{num(y.capex)}</td><td className="num">{pc(y.capex_pct_sales)}</td>
                  <td className="num">{num(y.cfo)}</td><td className={`num ${signClass(y.fcf)}`}>{num(y.fcf)}</td><td className="num">{num(y.debt)}</td></tr>))}</tbody>
            </table></div>
          </Panel>
          )}

          <section className="card stack" style={{ gap: 12 }}>
            <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
              <div className="stack" style={{ gap: 2 }}>
                <h2 className="h3">From the company's own documents</h2>
                <span className="small muted">{v.reads ? `Read ${day(v.reads.at)}: ${v.reads.read.map((d) => `${KIND[d.kind] ?? "Filing"}, ${day(d.at)}`).join(" · ") || "the company profile"}` : us ? `${v.documents.filter((d) => d.kind === "annual_report").length} annual report${v.documents.filter((d) => d.kind === "annual_report").length === 1 ? "" : "s"} and ${v.documents.filter((d) => d.kind === "earnings_release").length} earnings releases filed in the last two years.`
                  : `${v.documents.length} presentations and call transcripts found in the last two years.`}</span>
              </div>
              <button className="btn sm" disabled={reading || (!v.documents.length && !v.about)} onClick={() => readDocs(!!v.reads)}>
                {reading ? "Reading… about a minute" : v.reads ? (v.reads_stale ? "Read the newest documents" : "Read again") : us ? "Read the annual report and releases" : "Read the latest presentation and calls"}</button>
            </div>
            {v.doc_note && <p className="tiny muted" style={{ margin: 0 }}>Filings: {v.doc_note}</p>}
            {reading && <Loading label={us ? "Reading the annual report (10-K) and earnings releases" : "Reading the latest investor presentation and earnings calls"} />}
            {!v.reads && !reading && <p className="small muted" style={{ margin: 0 }}>The business model, {v.industry_measures?.label ? `the ${v.industry_measures.label.toLowerCase()} measures (${v.industry_measures.measures.slice(0, 3).join(", ")}…), ` : ""}capex plans and management's outlook come from these documents. Reading them takes about a minute and counts as one of your daily AI reads; a read is kept for a week and shared, so someone may already have done it.</p>}
            {v.reads?.problems?.length ? <p className="tiny muted" style={{ margin: 0 }}>Couldn't read: {v.reads.problems.join(" · ")}</p> : null}
          </section>

          {b && (
            <Panel title="Business model" span="full">
              <p style={{ margin: 0 }}>{b.summary}</p>
              {b.segments.length > 0 && (
                <div className="stack" style={{ gap: 8 }}>
                  {b.segments.map((s) => (
                    <div key={s.name} className="seg-row">
                      <div className="spread small"><b>{s.name}</b><span className="muted">{s.share_pct != null ? `${s.share_pct.toFixed(0)}% of revenue` : ""}</span></div>
                      {s.share_pct != null && <div className="seg-bar"><i style={{ width: `${Math.min(100, s.share_pct)}%` }} /></div>}
                      {s.what && <span className="tiny muted">{s.what}</span>}
                    </div>))}
                </div>
              )}
              <div className="rs-grid">
                {b.customers && <div className="stack" style={{ gap: 4 }}><b className="small">Customers</b><span className="small">{b.customers}</span></div>}
                {b.drivers.length > 0 && <div className="stack" style={{ gap: 4 }}><b className="small">What drives revenue</b><ul className="bullets small">{b.drivers.map((x) => <li key={x}>{x}</li>)}</ul></div>}
                {b.strengths.length > 0 && <div className="stack" style={{ gap: 4 }}><b className="small">Strengths it points to</b><ul className="bullets small">{b.strengths.map((x) => <li key={x} className="pos-dot">{x}</li>)}</ul></div>}
                {b.risks.length > 0 && <div className="stack" style={{ gap: 4 }}><b className="small">Risks it names</b><ul className="bullets small">{b.risks.map((x) => <li key={x} className="neg-dot">{x}</li>)}</ul></div>}
              </div>
              <div className="row wrap" style={{ gap: 10 }}>{b.sources.map((s, i) => <SourceLink key={i} s={s} />)}</div>
            </Panel>
          )}

          {b && (b.measures?.length || v.industry_measures?.label) ? (
            <Panel title={`${b.industry ?? v.industry_measures?.label ?? "Operating"} measures, from the company`} span="full"
              info="The numbers this industry is judged on (for a hospital, revenue per occupied bed and occupancy), as the company states them in its presentation. They aren't in the financial tables.">
              {b.measures?.length ? (
                <div className="promises">{b.measures.map((m, i) => (
                  <div key={i} className="promise">
                    <div className="spread" style={{ gap: 10, alignItems: "baseline" }}><span className="small"><b>{m.name}</b></span><b className="num">{m.value}</b></div>
                    <div className="promise-facts tiny">
                      {m.period && <span><span className="muted">Period</span> {m.period}</span>}
                      {m.change && <span><span className="muted">Change</span> {m.change}</span>}
                      <SourceLink s={m.source} />
                    </div>
                    {m.quote && <span className="tiny muted">"{m.quote}"</span>}
                  </div>))}</div>
              ) : <p className="small muted" style={{ margin: 0 }}>The presentation read didn't state these: {v.industry_measures?.measures.join(", ")}.</p>}
            </Panel>
          ) : null}

          {p && (p.capex.length > 0 || p.outlook.length > 0) && (
            <Panel title="Capex and growth plans, in management's words" span="full">
              {p.capex.length > 0 && (
                <div className="promises">{p.capex.map((c, i) => (
                  <div key={i} className="promise">
                    <div className="spread" style={{ gap: 10, alignItems: "flex-start" }}>
                      <span className="small"><b>{c.what}</b></span>
                      <span className={`badge ${c.status === "done" ? "pass" : c.status === "under way" ? "next" : "skip"}`}>{c.status}</span>
                    </div>
                    <div className="promise-facts tiny">
                      {c.amount && <span><span className="muted">Amount</span> <b>{c.amount}</b></span>}
                      {c.size && <span><span className="muted">Size</span> <b>{c.size}</b></span>}
                      {c.timeline && <span><span className="muted">When</span> {c.timeline}</span>}
                      <SourceLink s={c.source} />
                    </div>
                    {c.quote && <span className="tiny muted">"{c.quote}"</span>}
                  </div>))}</div>
              )}
              {p.outlook.length > 0 && (
                <div className="stack" style={{ gap: 8 }}>
                  <b className="small">Outlook</b>
                  {p.outlook.map((o, i) => (
                    <div key={i} className="quote-row"><span className="small">{o.statement}</span>{o.quote && <span className="tiny muted">"{o.quote}"</span>}<SourceLink s={o.source} /></div>))}
                </div>
              )}
            </Panel>
          )}

          <section className="card stack" style={{ gap: 12 }}>
            <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
              <div className="stack" style={{ gap: 2 }}>
                <h2 className="h3">Management report card</h2>
                <span className="small muted">{us
                  ? (v.card ? `What they said in ${v.card.read.length} earnings release${v.card.read.length === 1 ? "" : "s"}, and what the numbers showed. Checked ${day(v.card.at)}.`
                    : `What management forecast in its earnings releases, against what happened. ${v.calls} release${v.calls === 1 ? "" : "s"} found.`)
                  : v.card ? `What they said on ${v.card.read.length} earnings call${v.card.read.length === 1 ? "" : "s"}, and what the numbers showed. Checked ${day(v.card.at)}.`
                  : `What management promised on past earnings calls, against what happened. ${v.calls} call transcript${v.calls === 1 ? "" : "s"} found.`}</span>
              </div>
              <button className="btn sm" disabled={carding || !v.calls} onClick={() => checkCalls(!!v.card)}>
                {carding ? (us ? "Reading the releases… about a minute" : "Reading the calls… about a minute") : v.card ? (v.card_stale ? (us ? "Check the newest releases" : "Check the newest calls") : "Check again") : us ? "Check past releases" : "Check past calls"}</button>
            </div>
            {carding && <Loading label={us ? "Reading past earnings releases" : "Reading past earnings calls"} />}
            {!v.card && !carding && <p className="small muted" style={{ margin: 0 }}>{v.calls ? `Reads up to six ${us ? "earnings releases" : "calls"} over the last two years for the targets management gave (growth, margins, capex), then checks each against the reported results. Counts as one of your daily AI reads; kept for a week and shared.`
              : us ? "No earnings releases were found in the company's filings for the last two years." : "No earnings-call transcripts were found in the company's filings for the last two years."}</p>}
            {v.card && <ReportCard c={v.card} />}
            {v.card?.problems?.length ? <p className="tiny muted" style={{ margin: 0 }}>Couldn't read: {v.card.problems.join(" · ")}</p> : null}
          </section>

          {v.documents.length > 0 && (
            <Panel title="Documents" span="full">
              <div className="filings">{v.documents.map((d) => (
                <div key={d.url} className="filing"><span className="tiny muted mono">{day(d.at)}</span>
                  <div className="stack" style={{ gap: 2, minWidth: 0 }}><span className="small">{d.title}</span><span className="tiny muted">{KIND[d.kind] ?? d.kind}</span></div>
                  <a className="link tiny" href={d.url} target="_blank" rel="noopener noreferrer">Open ↗</a></div>))}</div>
            </Panel>
          )}
          <p className="small muted" style={{ maxWidth: "80ch" }}>Numbers are the company's reported figures{n.capex_reported ? "" : "; capex and free cash flow are estimated from them"}.{us ? " Ratios that need a price (market value, P/E, dividend yield) use the latest share price and the share count on the company's latest report." : ""}
            {" "}The document read quotes the company and links each point to its source; it can miss or misread things, so open the source before relying on it. Nothing here is investment advice.</p>
        </>
      )}
    </div>
  );
}
