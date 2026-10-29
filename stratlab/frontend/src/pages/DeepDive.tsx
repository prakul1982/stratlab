import { unsettledNote, saidOn } from "../lib/reportCard";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { deepDiveLimitLine } from "../lib/account";
import { asOf, CRORE, inrCompact, marketTz, pct, safeHref, fmtDate } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { marginText, millionsOf, scaleFor, usdAmount } from "../lib/research";
import { Panel, TrendBars } from "../components/Research";
import { BizUpdatesPanel } from "../components/BizUpdates";
import { Badge, Card, DataTable, ErrorState, Meter, PageHeader, PlanNote, Select, Signed, Skeleton, Stat, StatRow } from "../components/kit";
import { AlertButton } from "../components/AlertForm";
import { ShareCompanyButton } from "../components/ShareCompany";
import { track } from "../lib/analytics";
import { CHECK_BADGE, checkCountsLine } from "../lib/checklistText";

type Year = { year: string; sales: number | null; profit: number | null; opm: number | null; capex: number | null;
  capex_pct_sales: number | null; cfo: number | null; cfi: number | null; fcf: number | null; debt: number | null };
type Quarter = { quarter: string; sales: number | null; profit: number | null; opm: number | null; sales_yoy: number | null };
type Doc = { kind: string; at: string; title: string; url: string };
type Source = { title: string; at: string; url: string; kind: string } | null;
type Target = { metric: string; low: number | null; high: number | null; period: string | null; what: string; quote: string; said_at: string;
  source: { title: string; at: string; url: string }; actual: number | null; unit: string; result: "met" | "missed" | "pending" | "unchecked";
  revised?: { low: number | null; high: number | null; at: string; quote: string } | null;
  settled_by?: { actual: number; met: boolean; quote: string; source: { title: string; at: string; url: string } };
  /** one short line on why the numbers can't settle it (UI-CO item 7), and whether it is a plan with no figure at all */ why?: string | null; qualitative?: boolean; segment?: string };
export type CheckState = "pass" | "watch" | "fail" | "na";
type Checklist = { checks: { group: string; label: string; state: CheckState; value: string; rule: string }[];
  counts: Record<CheckState, number>; scored: number; industry?: { group: string; label: string; path: string[]; note: string } };
type Measure = { name: string; value: string; period: string | null; change: string | null; quote: string; source: Source };
type Card = { rows: Target[]; met: number; missed: number; pending: number; unchecked: number; no_figure?: number; score: number | null;
  read: { kind: string; at: string; title: string }[]; problems: string[]; at: string; years?: number };
export interface DeepView {
  symbol: string; region?: "IN" | "US"; ai?: boolean; source_url?: string | null; name: string; about: string; documents: Doc[]; doc_note: string | null; reads_stale: boolean;
  calls: number; card: Card | null; card_stale: boolean; checklist: Checklist;
  as_of?: string | null; numbers_at?: string | null; price_at?: string | null;
  industry_measures?: { key: string; label: string | null; measures: string[] };
  snapshot?: { div_yield: number | null };
  valuation?: { name: string; short: string; value: number | null; pe: number | null; why: string };
  numbers: { years: Year[]; quarters: Quarter[]; unit: string; capex_3y_total: number | null; capex_years?: number; bank?: boolean; notes?: string[]; capex_reported?: boolean;
    growth: { sales_cagr_3y: number | null; sales_cagr_5y: number | null; profit_cagr_3y: number | null; profit_cagr_5y: number | null;
      eps_cagr_3y?: number | null; eps_cagr_5y?: number | null };
    /** growth rates off a tiny base: not meaningful (DD-018) */ growth_nm?: Record<string, { from: number; year: string }> };
  reads: null | {
    at: string; problems: string[]; read: { kind: string; at: string; title: string }[];
    business: null | { summary: string; customers: string; drivers: string[]; strengths: string[]; risks: string[]; measures?: Measure[]; industry?: string | null;
      segments: { name: string; share_pct: number | null; what: string }[]; sources: Source[] };
    plans: null | { capex: { what: string; amount: string | null; size?: string | null; timeline: string | null; status: string; quote: string; source: Source }[];
      outlook: { statement: string; quote: string; source: Source }[]; sources: Source[] };
  };
}

/** An amount in ₹ crore as people say it in Indian units: "₹945 cr", "₹1.25 lakh cr". */
const inrAmount = (v: number | null | undefined) => (v == null ? "–" : inrCompact(v * CRORE));
const pc = (v: number | null | undefined) => (v == null ? "–" : `${v.toFixed(1)}%`);
const day = (s: string) => fmtDate(s);
const KIND: Record<string, string> = { transcript: "Call transcript", presentation: "Investor presentation", annual_report: "Annual report",
  quarterly_report: "Quarterly report", earnings_release: "Earnings release" };

/** One growth cell of the table: the rate (green or red), or n/m or a dash with its reason as a numbered note under the table (UI-CO: the figures as a table). */
type GrowthNote = { n: number; text: string };
function growthCell(label: string, v: number | null, why: string | undefined, nm: { from: number; year: string } | null | undefined, notes: GrowthNote[]) {
  // a rate off a tiny base is not meaningful, said with the base it starts from (DD-018)
  const text = nm ? `From a base of ${nm.from.toLocaleString("en-IN")} in ${nm.year}` : v == null ? why : undefined;
  const mark = text ? (notes.find((x) => x.text === `${label}: ${text}`) ?? (notes.push({ n: notes.length + 1, text: `${label}: ${text}` }), notes[notes.length - 1])) : null;
  return <>{nm ? "n/m" : v == null ? "–" : <Signed value={v}>{pct(v)}</Signed>}{mark && <sup className="cmp-foot-mark" aria-label={`see note ${mark.n}`}>{mark.n}</sup>}</>;
}

/** Why a growth rate is blank: a loss (or zero) at the start of the period or along the way makes a yearly rate meaningless. */
function lossNote(values: (number | null | undefined)[], years: number): string | undefined {
  const span = values.slice(-(years + 1)).filter((x): x is number => x != null);
  if (span.length < years + 1) return "Not enough years reported";
  return span.some((x) => x <= 0) ? "A loss year in the period, so no yearly rate" : undefined;
}

const METRIC: Record<string, string> = { revenue_growth: "Revenue growth", profit_growth: "Profit growth", ebitda_growth: "EBITDA growth", margin: "Operating margin", net_margin: "Net margin",
  gross_margin: "Gross margin", roe: "Return on equity", roce: "Return on capital employed", capex: "Capex", revenue: "Revenue", profit: "Profit", ebitda: "EBITDA", other: "" };
const RESULT: Record<string, [string, string]> = { met: ["Met", "pass"], missed: ["Missed", "fail"], pending: ["Not due yet", "next"], unchecked: ["Can't check", "skip"] };
/** A target in its own unit: rupees crore, millions, a percentage, or a plain number, never a crore amount with a "%"
 * (DD-050: "INR 40,000–50,000 crore" read "Target 40000–50000%"). */
const target = (lo: number | null, hi: number | null, unit: string, cur = "$") =>
  lo == null ? "–" : unit === "crore" ? (hi != null ? `${inrAmount(lo)} – ${inrAmount(hi)}` : inrAmount(lo))
    : unit === "million" ? (hi != null ? `${usdAmount(lo, cur)} – ${usdAmount(hi, cur)}` : usdAmount(lo, cur))
    : `${lo.toLocaleString("en-IN")}${hi != null ? `–${hi.toLocaleString("en-IN")}` : ""}${unit === "%" ? "%" : unit === "x" ? "×" : ""}`;
const actualText = (v: number, unit: string, cur = "$") =>
  unit === "crore" ? inrAmount(v) : unit === "million" ? usdAmount(v, cur) : unit === "%" ? `${v.toFixed(1)}%` : v.toLocaleString("en-IN");

/** `cur`: the currency a US filing's amounts are in ("$", or a foreign filer's own, like "CAD"). */
function ReportCard({ c, cur = "$" }: { c: Card; cur?: string }) {
  const checked = c.met + c.missed;
  return (
    <>
      {/* one reading in every cell: with nothing settled, none is met or missed yet (DD-050: "Targets met –" beside "Missed 0") */}
      <StatRow>
        <Stat label="Targets met" value={checked ? `${c.met} of ${checked}` : "None settled"} />
        <Stat label="Missed" value={checked ? String(c.missed) : "–"} />
        <Stat label="Not due yet" value={String(c.pending)} />
        <Stat label="Couldn't check" value={String(c.unchecked)} />
      </StatRow>
      <p className="k-small">{checked
        ? <>Of the {checked} targets from past calls that can be settled, by the reported numbers or by what the company itself said later, <b>{c.met} {c.met === 1 ? "was" : "were"} met</b> and {c.missed} missed ({c.score}% met).</>
        : unsettledNote(c)}{(c.no_figure ?? 0) > 0 && <> {c.no_figure} more {c.no_figure === 1 ? "is a plan" : "are plans"} with no figure to check.</>}</p>
      {c.rows.length > 0 ? (
        <DataTable label="Management targets and how they turned out" stack rows={c.rows} rowKey={(r, i) => `${r.metric}-${r.period}-${r.said_at}-${i}`}
          columns={[
            { key: "t", header: "Target", rowHeader: true, wrap: true, cell: (r) => (
              <span className="rc-target">
                <span className="k-small">{METRIC[r.metric] ? <b>{METRIC[r.metric]}: </b> : null}{r.what}</span>
                {r.quote && <span className="k-note rc-quote">"{r.quote}"</span>}
                {r.settled_by && <span className="k-note rc-quote"><span className="k-muted">Result from the company's own words:</span> "{r.settled_by.quote}" <a className="link" href={safeHref(r.settled_by.source.url)} target="_blank" rel="noopener noreferrer">{r.settled_by.source.title}, {day(r.settled_by.source.at)} ↗</a></span>}
                {r.revised && <span className="k-note">Later changed to {target(r.revised.low, r.revised.high, r.unit, cur)} ({day(r.revised.at)}).</span>}
              </span>) },
            { key: "p", header: "For", cell: (r) => r.period ?? "–" },
            { key: "s", header: "Said", numeric: true, cell: (r) => (
              <span className="rc-said">
                <b className="mono">{r.low != null ? target(r.low, r.high, r.unit, cur) : "No figure"}</b>
                <a className="link k-note" href={safeHref(r.source.url)} target="_blank" rel="noopener noreferrer" title={r.source.title}>{day(r.source.at)} ↗</a>
              </span>) },
            { key: "r", header: "Result", lead: true, cell: (r) => {
              const [label, tone] = r.result === "unchecked" && r.qualitative ? ["No figure", "skip"] : RESULT[r.result];
              return (
                <span className="rc-result">
                  <span className={`badge ${tone}`}>{label}</span>
                  {r.actual != null && <span className="k-note">Actual <b className="mono">{actualText(r.actual, r.unit, cur)}</b></span>}
                  {r.result === "unchecked" && r.why && <span className="k-note" data-testid="rc-why">{r.why}</span>}
                </span>);
            } },
          ]} />
      ) : <p className="k-small k-muted">No specific targets were found in these {c.read.length > 0 && c.read.every((d) => d.kind === "earnings_release") ? "earnings releases" : "calls"}.</p>}
      <p className="k-note">Checked against the reported annual and quarterly numbers: growth on the year before (within 1 point; profit within 2), operating margin (within 0.5 points; the company may quote EBITDA margin, which can differ slightly), a revenue or profit amount (at least the target, less 2%) and estimated capex (within 10%). A target the numbers can't settle (a bank's loan-to-deposit ratio, a retail mix) is settled from what the company said after the period ended, quoted word for word and checked against the document. A target repeated on later calls counts once, from the first time it was said.</p>
    </>
  );
}

export const CHECK = CHECK_BADGE;

function ChecklistPanel({ c }: { c: Checklist }) {
  const groups = [...new Set(c.checks.map((x) => x.group))];
  return (
    <Panel title="Investor checklist" info="Fixed rules on the reported numbers, the price trend, the filings and the management report card. Each threshold is written under its check, and each line says where the figure sits against it: a fact, not a verdict on the company.">
      <p className="k-small" data-testid="check-counts">{checkCountsLine(c.counts)}</p>
      {c.industry && c.industry.group !== "general" && (
        <p className="k-note"><b>Rules for: {c.industry.label}{c.industry.path.length ? ` (${c.industry.path.join(" › ")})` : ""}.</b> {c.industry.note}</p>)}
      {/* UI-CO item 5: a table for each group (Check with its rule under it | Value | Result), one under the other at one width: no two-column
          masonry of uneven heights */}
      <div className="checklist">{groups.map((g) => (
        <div key={g} className="check-group">
          <DataTable label={`Investor checklist: ${g}`} rows={c.checks.filter((x) => x.group === g)} rowKey={(x) => x.label} stack
            columns={[
              { key: "c", header: g, rowHeader: true, cell: (x) => <span className="k-stack"><span className="k-small">{x.label}</span><span className="k-note">{x.rule}</span></span> },
              { key: "v", header: "Value", numeric: true, cell: (x) => (x.state === "na" && /^[-–—]?$/.test(x.value.trim()) ? "" : <span className={x.value.length > 32 ? "ck-long" : undefined}>{x.value}</span>) },
              { key: "r", header: "Result", cell: (x) => <span className={`badge ${CHECK[x.state][1]}`}>{CHECK[x.state][0]}</span> },
            ]} />
        </div>))}</div>
    </Panel>
  );
}

/** Documents as a table: Document (its title under its kind) | Date | link (UI-CO item 6: the list of documents read was one long run-on line). */
function DocTable({ docs, label, empty }: { docs: { kind: string; at: string; title: string; url: string }[]; label: string; empty?: string }) {
  return (
    <div className="dd-fit"><DataTable label={label} rows={docs} rowKey={(d, i) => `${d.url}-${d.at}-${i}`} stack={false} empty={empty}
      columns={[{ key: "d", header: "Document", rowHeader: true, cell: (d) => <span className="k-stack"><span className="k-small">{KIND[d.kind] ?? d.kind}</span>{d.title && d.title.trim().toLowerCase() !== (KIND[d.kind] ?? "").toLowerCase() && <span className="k-note">{d.title}</span>}</span> },
        { key: "t", header: "Date", numeric: true, cell: (d) => day(d.at) },
        { key: "l", header: "Link", numeric: true, cell: (d) => (d.url ? <a className="link" href={safeHref(d.url)} target="_blank" rel="noopener noreferrer" title={d.title}>Open ↗</a> : "") }]} /></div>
  );
}

function SourceLink({ s }: { s: Source }) {
  return s ? <a className="link tiny" href={safeHref(s.url)} target="_blank" rel="noopener noreferrer" title={s.title}>{KIND[s.kind] ?? "Filing"}, {day(s.at)} ↗</a> : null;
}

export function DeepDivePage() {
  const { symbol = "" } = useParams();
  const region: "IN" | "US" = useLocation().pathname.startsWith("/research/US/") ? "US" : "IN";
  const sym = symbol.toUpperCase();
  const us = region === "US";
  const q = (extra = "") => (us ? `?region=US${extra ? `&${extra}` : ""}` : extra ? `?${extra}` : "");
  const { me, fail, notify, refreshMe } = useApp();
  const [v, setV] = useState<DeepView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [limited, setLimited] = useState(false);         // the plan's monthly deep dives are used up
  const [tries, setTries] = useState(0);                   // one more with each "Try again" (RC5-001)
  const u = me?.usage;
  const [reading, setReading] = useState(false);
  const [carding, setCarding] = useState(false);
  const [decking, setDecking] = useState<"pptx" | "pdf" | null>(null);
  const [span, setSpan] = useState(2);            // years of documents a read looks back over
  const here = useRef("");                         // the company on the page now: a read or a check that finishes for another is ignored
  here.current = `${region}:${sym}`;

  const downloadDeck = async (format: "pptx" | "pdf") => {
    setDecking(format);
    try {
      const r = await api<Response>(`/research/deep/${encodeURIComponent(sym)}/deck${q(`format=${format}`)}`, { raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = `${sym}-deep-dive.${format}`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      void refreshMe();                               // the deck count in Account
    } catch (e) { fail(e); } finally { setDecking(null); }
  };

  useEffect(() => { track("deep dive opened", { region }); }, [sym, region]);

  useEffect(() => {
    let live = true;
    setV(null); setError(null); setLimited(false); setReading(false); setCarding(false);
    api<DeepView>(`/research/deep/${encodeURIComponent(sym)}${q()}`)
      .then((x) => { if (live) { setV(x); void refreshMe(); } })
      .catch((e) => { if (live) { setError((e as Error).message); setLimited(e instanceof ApiError && e.status === 402); } });
    return () => { live = false; };
  }, [sym, region, tries]); // eslint-disable-line react-hooks/exhaustive-deps

  const readDocs = async (refresh = false) => {
    const mine = here.current;
    setReading(true);
    try {
      const x = await api<DeepView>(`/research/deep/${encodeURIComponent(sym)}/read${q(`years=${span}${refresh ? "&refresh=true" : ""}`)}`, { method: "POST" });
      if (mine !== here.current) return;
      setV(x);
      if (x.reads?.problems?.length) notify(`Read with ${x.reads.problems.length} document${x.reads.problems.length === 1 ? "" : "s"} skipped.`);
    } catch (e) { if (mine === here.current) fail(e); } finally { if (mine === here.current) setReading(false); }
  };

  const checkCalls = async (refresh = false) => {
    const mine = here.current;
    setCarding(true);
    try {
      const x = await api<DeepView>(`/research/deep/${encodeURIComponent(sym)}/card${q(`years=${span}${refresh ? "&refresh=true" : ""}`)}`, { method: "POST" });
      if (mine !== here.current) return;
      setV(x);
      if (x.card?.problems?.length) notify(`Checked with ${x.card.problems.length} call${x.card.problems.length === 1 ? "" : "s"} skipped.`);
    } catch (e) { if (mine === here.current) fail(e); } finally { if (mine === here.current) setCarding(false); }
  };

  const n = v?.numbers;
  const years = (n?.years ?? []).filter((y) => y.sales != null);
  // each chart and table picks its own unit (see scaleFor): large and exact enough → $ billion / ₹ lakh crore
  const cur = millionsOf(n?.unit);       // a US-listed company reporting in another currency: its figures in that currency
  // sales and profit, side by side, share one unit (a profit chart in crore never sits beside sales in lakh crore)
  const salesS = scaleFor(years.flatMap((y) => [y.sales, y.profit]), us, n?.unit), profitS = salesS;
  const qS = scaleFor((n?.quarters ?? []).slice(-8).flatMap((q) => [q.sales, q.profit]), us, n?.unit);
  const capS = scaleFor([...years].reverse().slice(0, 8).flatMap((y) => [y.sales, y.capex, y.cfo, y.fcf, y.debt]), us, n?.unit);
  const b = v?.reads?.business, p = v?.reads?.plans;
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research")} title={`${v?.name ?? sym}: business, capex and growth`}
        asOf={v?.numbers_at} asOfLabel="Reported numbers as of" asOfTz={marketTz(region)}
        lede={us
          ? <>The numbers the company reports to the SEC in its annual and quarterly filings (10-K and 10-Q), in {cur === "$" ? "dollars" : `the currency it reports in (${cur})`}, each table and chart labelled with its unit{v?.source_url ? <> (<a className="link" href={safeHref(v.source_url)} target="_blank" rel="noopener noreferrer">its filings ↗</a>)</> : null}. Facts, not advice.</>
          : "The reported numbers, and what the company itself says in its latest investor presentation and earnings calls. Facts and the company's own words, not advice."}
        actions={<>
          {v?.price_at && <Badge>Last close as of {asOf(v.price_at, { tz: marketTz(region) })}</Badge>}
          <Link className="btn quiet sm" to={`/research/${region}/${encodeURIComponent(sym)}`}>← {v?.name ?? sym}</Link>
        </>} />
      <div className="k-row">
        {v && <>
          <button className="btn quiet sm" disabled={!!decking} onClick={() => downloadDeck("pptx")} title="Numbers, business, plans, report card and checklist as slides, with sources">{decking === "pptx" ? "Making the deck…" : "Slides (PowerPoint)"}</button>
          <button className="btn quiet sm" disabled={!!decking} onClick={() => downloadDeck("pdf")} title="The same slides as a PDF, to read or share anywhere">{decking === "pdf" ? "Making the PDF…" : "Slides (PDF)"}</button>
        </>}
        <AlertButton region={region} symbol={sym} />
        <ShareCompanyButton region={region} symbol={sym} />
        {v && <Link className="btn quiet sm" to="/research/investor">Watchlist at a glance →</Link>}
      </div>
      {limited && <PlanNote>{error}</PlanNote>}
      {!limited && error && <ErrorState title="The deep dive couldn't be opened" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>}
      {!v && !error && <Card><Skeleton label="Reading the reported numbers" lines={5} /></Card>}
      {v && u?.deepdive_limit != null && (
        <p className="k-note">{deepDiveLimitLine(u.deepdive_used ?? 0, u.deepdive_limit, u.deck_used ?? 0, u.deck_limit)} <Link className="link" to="/plans">Plans</Link></p>
      )}
      {v && n && (
        <>
          <Panel title="Growth and margins" info="Compound annual growth from the reported annual sales and net profit. EBITDA margin is operating profit before depreciation, interest and tax, as a share of sales.">
            {(() => {
              // a table: Sales, Net profit and earnings per share by the 3 and 5 years' rate a year; a reason a rate is blank is a numbered note under it
              const notes: GrowthNote[] = [];
              const rows = [
                { k: "sales", name: us ? "Revenue" : "Sales", y3: growthCell("Sales, last 3 years", n.growth.sales_cagr_3y, undefined, n.growth_nm?.sales_cagr_3y, notes), y5: growthCell("Sales, last 5 years", n.growth.sales_cagr_5y, undefined, n.growth_nm?.sales_cagr_5y, notes) },
                { k: "profit", name: "Net profit", y3: growthCell("Net profit, last 3 years", n.growth.profit_cagr_3y, lossNote(years.map((y) => y.profit), 3), n.growth_nm?.profit_cagr_3y, notes), y5: growthCell("Net profit, last 5 years", n.growth.profit_cagr_5y, lossNote(years.map((y) => y.profit), 5), n.growth_nm?.profit_cagr_5y, notes) },
                ...(n.growth.eps_cagr_5y != null ? [{ k: "eps", name: "Earnings per share", y3: growthCell("Earnings per share, last 3 years", n.growth.eps_cagr_3y ?? null, undefined, null, notes), y5: growthCell("Earnings per share, last 5 years", n.growth.eps_cagr_5y ?? null, undefined, null, notes) }] : []),
              ];
              return (
                <>
                  <div className="dd-fit"><DataTable label="Growth a year" rows={rows} rowKey={(r) => r.k} stack={false}
                    columns={[{ key: "n", header: "Growth a year", rowHeader: true, cell: (r) => r.name },
                      { key: "3", header: "Last 3 years", numeric: true, cell: (r) => r.y3 }, { key: "5", header: "Last 5 years", numeric: true, cell: (r) => r.y5 }]} /></div>
                  {notes.length > 0 && <ul className="k-note cmp-foots" data-testid="growth-notes">{notes.map((x) => <li key={x.n}><sup>{x.n}</sup> {x.text}</li>)}</ul>}
                </>
              );
            })()}
            {(n.notes ?? []).map((t) => <p key={t} className="k-small k-muted inv-text">{t}</p>)}
            <div className="k-cols">
              <TrendBars points={years.map((y) => ({ y: y.year.replace("Mar ", "FY"), v: (y.sales as number) / salesS.k }))} label={us ? "Revenue" : "Sales"} unit={salesS.unit} />
              <TrendBars points={years.filter((y) => y.profit != null).map((y) => ({ y: y.year.replace("Mar ", "FY"), v: (y.profit as number) / profitS.k }))} label="Net profit" unit={profitS.unit}
                baseSales={(() => { const f = years.find((y) => y.profit != null); return f?.sales != null ? f.sales / profitS.k : null; })()} />
            </div>
            {n.quarters.length > 0 && (
              <DataTable label="The last eight quarters" stack rows={n.quarters.slice(-8)} rowKey={(q) => q.quarter}
                columns={[{ key: "q", header: <>Quarter <span className="k-note">({qS.unit})</span></>, rowHeader: true, cell: (q) => q.quarter },
                  { key: "s", header: "Sales", numeric: true, cell: (q) => qS.fmt(q.sales) },
                  { key: "y", header: "vs a year ago", numeric: true, cell: (q) => (q.sales_yoy == null ? "–" : <Signed value={q.sales_yoy}>{pct(q.sales_yoy)}</Signed>) },
                  ...(n.bank && n.quarters.slice(-8).every((q) => q.opm == null) ? [] : [{ key: "o", header: n.bank ? "Financing margin" : "EBITDA margin", numeric: true, cell: (q: (typeof n.quarters)[number]) => marginText(q.opm) }]),
                  { key: "p", header: "Net profit", numeric: true, cell: (q) => qS.fmt(q.profit) }]} />
            )}
          </Panel>

          {v.valuation && (
            <Panel title="How it's valued" info={v.valuation.why}>
              <div className="dd-fit"><DataTable label="How it's valued" rows={[
                { k: "v", name: v.valuation.name, v: v.valuation.value == null ? "–" : `${v.valuation.value.toFixed(1)}×` },
                ...(v.valuation.short !== "P/E" ? [{ k: "pe", name: "Price to earnings", v: v.valuation.pe == null ? "–" : `${v.valuation.pe.toFixed(1)}×` }] : []),
                ...(v.snapshot?.div_yield != null ? [{ k: "dy", name: "Dividend yield", v: `${v.snapshot.div_yield.toFixed(2)}%` }] : []),
              ]} rowKey={(r) => r.k} stack={false}
                columns={[{ key: "n", header: "Measure", rowHeader: true, cell: (r) => r.name }, { key: "v", header: "Value", numeric: true, cell: (r) => <b>{r.v}</b> }]} /></div>
              <p className="k-note">{v.valuation.why} A number to compare with similar companies, not a verdict on the price.</p>
            </Panel>
          )}

          {v.checklist && <ChecklistPanel c={v.checklist} />}

          {!us && <BizUpdatesPanel symbol={v.symbol} wrap={(body, right) => <Panel title="Business updates" right={right}
            info="Monthly or quarterly numbers the company files between results, copied from its own filing with the line and page each comes from.">{body}</Panel>} />}

          {/* the named holders and the deals tables are the company page's: linked from here, not shown twice (DD-054) */}
          {!us && <Panel title="Holders and deals">
            <p className="k-small" data-testid="deep-holders-deals">The named holders above 1% and the deals and insider trades are on the company page:{" "}
              <Link className="link" to={`/research/IN/${encodeURIComponent(v.symbol)}#named-holders`}>named holders</Link>,{" "}
              <Link className="link" to={`/research/IN/${encodeURIComponent(v.symbol)}#deals`}>deals and insider trades</Link>.</p>
          </Panel>}

          {n.bank ? (
            <Panel title="Capex and cash">
              <p className="k-small k-muted">This is a bank or lender: its revenue is mostly interest, and lending runs through its cash flow, so capex, free cash flow, operating margin and debt to equity don't describe it. The checklist uses return on equity instead.</p>
            </Panel>
          ) : (
          <Panel title="Capex and cash" info={n.capex_reported
            ? `Capex as the company reports it in its cash flow statement (purchases of property, plant and equipment). Free cash flow is cash from operations minus capex. Figures in ${capS.unit}.`
            : `Capex is estimated from the balance sheet: the rise in fixed assets and work in progress, plus the year's depreciation. Free cash flow is cash from operations minus that capex. Figures in ${capS.unit}.`}>
            {n.capex_3y_total != null && <p className="k-small">{n.capex_reported ? "" : "About "}<b>{us ? usdAmount(n.capex_3y_total, cur) : inrAmount(n.capex_3y_total)}</b> spent on capex over {(n.capex_years ?? 3) >= 3 ? "the last three years" : `${n.capex_years} of the last three years (no figure for the rest)`}. Figures in {capS.unit}.</p>}
            <DataTable label="Capex and cash by year" stack rows={[...years].reverse().slice(0, 8)} rowKey={(y) => y.year}
              columns={[{ key: "y", header: <>Year <span className="k-note">({capS.unit})</span></>, rowHeader: true, cell: (y) => y.year },
                { key: "s", header: "Sales", numeric: true, cell: (y) => capS.fmt(y.sales) }, { key: "c", header: "Capex", numeric: true, cell: (y) => capS.fmt(y.capex) },
                { key: "cs", header: "Capex / sales", numeric: true, cell: (y) => pc(y.capex_pct_sales) }, { key: "cfo", header: "Cash from operations", numeric: true, cell: (y) => capS.fmt(y.cfo) },
                { key: "f", header: "Free cash flow", numeric: true, cell: (y) => capS.fmt(y.fcf) }, { key: "d", header: "Debt", numeric: true, cell: (y) => capS.fmt(y.debt) }]} />
          </Panel>
          )}

          <Card>
            <div className="k-spread">
              <div className="k-stack">
                <h2 className="k-card-title">From the company's own documents</h2>
                <span className="k-small k-muted">{v.reads ? `Read ${day(v.reads.at)}, from the documents below.` : us ? `${v.documents.filter((d) => d.kind === "annual_report").length} annual report${v.documents.filter((d) => d.kind === "annual_report").length === 1 ? "" : "s"} and ${v.documents.filter((d) => d.kind === "earnings_release").length} earnings releases filed in the last two years.`
                  : `${v.documents.length} presentations and call transcripts found in the last two years.`}</span>
              </div>
              <div className="k-row dd-ask">
                <Select small label="Years to look back" value={span} onChange={(x) => setSpan(Number(x))} options={[1, 2, 3, 4, 5].map((y) => ({ value: y, label: y === 1 ? "Last year" : `Last ${y} years` }))} />
              <button className="btn sm" disabled={reading || (!v.documents.length && !v.about)} onClick={() => readDocs(!!v.reads || span !== 2)}>
                {reading ? "Reading… about a minute" : v.reads ? (v.reads_stale ? "Read the newest documents" : "Read again") : us ? "Read the annual report and releases" : "Read the latest presentation and calls"}</button>
              </div>
            </div>
            {v.reads && <DocTable label="The documents the read used" docs={v.reads.read.map((d) => ({ kind: d.kind, at: d.at, title: d.title, url: v.documents.find((x) => x.at === d.at && x.kind === d.kind)?.url ?? "" }))}
              empty="Only the company profile was read: no document was found." />}
            {v.doc_note && <p className="k-note">Filings: {v.doc_note}</p>}
            {reading && <Skeleton label={us ? "Reading the annual report (10-K) and earnings releases" : "Reading the latest investor presentation and earnings calls"} lines={3} />}
            {!v.reads && !reading && <p className="k-small k-muted">The business model, {v.industry_measures?.label ? `the ${v.industry_measures.label.toLowerCase()} measures (${v.industry_measures.measures.slice(0, 3).join(", ")}…), ` : ""}capex plans and management's outlook come from these documents. Reading them takes about a minute and counts as one of your daily AI reads; a read is kept for a week and shared, so someone may already have done it.</p>}
            {v.reads?.problems?.length ? <p className="k-note">Couldn't read: {v.reads.problems.join(" · ")}</p> : null}
          </Card>

          {b && (
            <Panel title="Business model">
              <p>{b.summary}</p>
              {b.segments.length > 0 && (
                <div className="dd-fit"><DataTable label="What the business earns from" rows={b.segments} rowKey={(x) => x.name} stack={false}
                  columns={[{ key: "n", header: "Business", rowHeader: true, cell: (x) => <b className="k-small">{x.name}</b> },
                    { key: "s", header: "Share of revenue", numeric: true, cell: (x) => (x.share_pct != null ? <span className="dd-share"><span>{x.share_pct.toFixed(0)}%</span><Meter pct={x.share_pct} /></span> : "") },
                    { key: "w", header: "What it is", cell: (x) => <span className="k-small">{x.what}</span> }]} /></div>
              )}
              {/* the rest of the read as one table too: the area on the left, its points on the right (the same grid as the company page's AI read) */}
              {(() => {
                const rows = [
                  ...(b.customers ? [{ k: "c", area: "Customers", body: <span className="k-small">{b.customers}</span> }] : []),
                  ...(b.drivers.length ? [{ k: "d", area: "What drives revenue", body: <ul className="bullets small">{b.drivers.map((x) => <li key={x}>{x}</li>)}</ul> }] : []),
                  ...(b.strengths.length ? [{ k: "s", area: "Strengths it points to", body: <ul className="bullets small">{b.strengths.map((x) => <li key={x} className="pos-dot">{x}</li>)}</ul> }] : []),
                  ...(b.risks.length ? [{ k: "r", area: "Risks it names", body: <ul className="bullets small">{b.risks.map((x) => <li key={x} className="neg-dot">{x}</li>)}</ul> }] : []),
                ];
                return rows.length ? (
                  <div className="ai-table">
                    <DataTable label="The business, in the company's words" rows={rows} rowKey={(r) => r.k} stack={false}
                      columns={[{ key: "a", header: "The business", rowHeader: true, cell: (r) => <b className="k-small">{r.area}</b> }, { key: "b", header: "What the documents say", cell: (r) => r.body }]} />
                  </div>
                ) : null;
              })()}
              <div className="k-row">{b.sources.map((s, i) => <SourceLink key={i} s={s} />)}</div>
            </Panel>
          )}

          {b && (b.measures?.length || v.industry_measures?.label) ? (
            <Panel title={`${b.industry ?? v.industry_measures?.label ?? "Operating"} measures, from the company`}
              info="The numbers this industry is judged on (for a hospital, revenue per occupied bed and occupancy), as the company states them in its presentation. They aren't in the financial tables.">
              {b.measures?.length ? (
                <DataTable label="Operating measures, from the company" rows={b.measures} rowKey={(m, i) => `${m.name}-${i}`} stack
                  columns={[{ key: "n", header: "Measure", rowHeader: true, wrap: true, cell: (m) => <span className="rc-target"><b className="k-small">{m.name}</b>{m.quote && <span className="k-note rc-quote">"{m.quote}"</span>}</span> },
                    { key: "v", header: "Value", numeric: true, cell: (m) => <b className="num">{m.value}</b> },
                    { key: "p", header: "Period", cell: (m) => m.period ?? "–" },
                    { key: "c", header: "Change", cell: (m) => m.change ?? "–" },
                    { key: "s", header: "Source", cell: (m) => <SourceLink s={m.source} /> }]} />
              ) : <p className="k-small k-muted">The presentation read didn't state these: {v.industry_measures?.measures.join(", ")}.</p>}
            </Panel>
          ) : null}

          {p && (p.capex.length > 0 || p.outlook.length > 0) && (
            <Panel title="Capex and growth plans, in management's words">
              {p.capex.length > 0 && (
                <DataTable label="Capex plans, in management's words" rows={p.capex} rowKey={(c, i) => `${c.what}-${i}`} stack
                  columns={[{ key: "w", header: "Plan", rowHeader: true, wrap: true, cell: (c) => <span className="rc-target"><b className="k-small">{c.what}</b>{c.quote && <span className="k-note rc-quote">"{c.quote}"</span>}</span> },
                    { key: "a", header: "Amount", numeric: true, cell: (c) => <span className="rc-said">{c.amount ? <b>{c.amount}</b> : "–"}{c.size && <span className="k-note">{c.size}</span>}</span> },
                    { key: "t", header: "When", cell: (c) => c.timeline ?? "–" },
                    { key: "s", header: "Status", cell: (c) => <span className={`badge ${c.status === "done" ? "pass" : c.status === "under way" ? "next" : "skip"}`}>{c.status}</span> },
                    { key: "r", header: "Source", cell: (c) => <SourceLink s={c.source} /> }]} />
              )}
              {p.outlook.length > 0 && (
                <DataTable label="Outlook, in management's words" rows={p.outlook} rowKey={(o, i) => `${o.statement}-${i}`} stack
                  columns={[{ key: "o", header: "Outlook", rowHeader: true, wrap: true, cell: (o) => <span className="rc-target"><span className="k-small">{o.statement}</span>{o.quote && <span className="k-note rc-quote">"{o.quote}"</span>}</span> },
                    { key: "d", header: "When", cell: (o) => saidOn(o.source?.at, day) },
                    { key: "s", header: "Source", cell: (o) => <SourceLink s={o.source} /> }]} />
              )}
            </Panel>
          )}

          <Card>
            <div className="k-spread">
              <div className="k-stack">
                <h2 className="k-card-title">Management report card</h2>
                <span className="k-small k-muted">{us
                  ? (v.card ? `What they said in ${v.card.read.length} earnings release${v.card.read.length === 1 ? "" : "s"}, and what the numbers showed. Checked ${day(v.card.at)}.`
                    : `What management forecast in its earnings releases, against what happened. ${v.calls} release${v.calls === 1 ? "" : "s"} found.`)
                  : v.card ? `What they said on ${v.card.read.length} earnings call${v.card.read.length === 1 ? "" : "s"} over ${v.card.years ?? 2} year${(v.card.years ?? 2) === 1 ? "" : "s"}, and what happened. Checked ${day(v.card.at)}.`
                  : `What management promised on past earnings calls, against what happened. ${v.calls} call transcript${v.calls === 1 ? "" : "s"} found.`}</span>
              </div>
              <div className="k-row dd-ask">
                <Select small label="Years to look back" value={span} onChange={(x) => setSpan(Number(x))} options={[1, 2, 3, 4, 5].map((y) => ({ value: y, label: y === 1 ? "Last year" : `Last ${y} years` }))} />
              <button className="btn sm" disabled={carding || !v.calls} onClick={() => checkCalls(!!v.card || span !== 2)}>
                {carding ? (us ? "Reading the releases… about a minute" : "Reading the calls… about a minute") : v.card ? (v.card_stale ? (us ? "Check the newest releases" : "Check the newest calls") : "Check again") : us ? "Check past releases" : "Check past calls"}</button>
              </div>
            </div>
            {carding && <Skeleton label={us ? "Reading past earnings releases" : "Reading past earnings calls"} lines={3} />}
            {!v.card && !carding && <p className="k-small k-muted">{v.calls ? `Reads up to ${({ 1: 4, 2: 6, 3: 9 } as Record<number, number>)[span] ?? 12} ${us ? "earnings releases" : "calls"} over the last ${span === 1 ? "year" : `${span} years`} (pick how far back) for the targets management gave (growth, margins, capex), then checks each against the reported results. Counts as one of your daily AI reads; kept for a week and shared.`
              : us ? "No earnings releases were found in the company's filings for the last two years." : "No earnings-call transcripts were found in the company's filings for the last two years."}</p>}
            {v.card && <ReportCard c={v.card} cur={cur} />}
            {v.card?.problems?.length ? <p className="k-note">Couldn't read: {v.card.problems.join(" · ")}</p> : null}
          </Card>

          {v.documents.length > 0 && (
            <Panel title="Documents">
              <DocTable label="Documents" docs={v.documents} />
            </Panel>
          )}
          <p className="k-note inv-text">Numbers are the company's reported figures{n.capex_reported ? "" : "; capex and free cash flow are estimated from them"}.{us ? " Ratios that need a price (market value, P/E, dividend yield) use the latest share price and the share count on the company's latest report." : ""}
            {" "}The document read quotes the company and links each point to its source; it can miss or misread things, so open the source before relying on it. Nothing here is investment advice.</p>
        </>
      )}
    </div>
  );
}
