import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useApp } from "../lib/app";
import { ago, pct, price, priceAxis, safeHref, signClass } from "../lib/format";
import {
  bandPosition, metricText, ordinal, researchApi, trendValue, useWatchlist,
  type Company, type CompanyAI, type Idea, type MetricGroup, type NewsItem, type Quote, type Region, type SeriesPoint,
} from "../lib/research";
import { LineChart } from "./Charts";
import { Star } from "./Icons";
import { Info } from "./ui";

export { CompanySearch } from "./CompanySearch";

/* ---------- navigation ---------- */
export function ResearchNav({ region, setRegion }: { region: Region; setRegion?: (r: Region) => void }) {
  const tabs: [string, string][] = [["/research", "Companies"], ["/research/themes", "Themes"], ["/research/pulse", "Market pulse"],
    ["/research/compare", "Compare"], ["/research/watchlist", "Watchlist"], ["/research/investor", "At a glance"], ["/research/scan", "Scan"], ["/research/rotation", "Rotation"], ["/research/filings", "Red flags"]];
  // on a phone the tabs scroll sideways in one row: bring the open one into view
  const bar = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = bar.current, on = el?.querySelector<HTMLElement>(".seg-link.on");
    if (el && on && el.scrollWidth > el.clientWidth) el.scrollLeft = on.offsetLeft - (el.clientWidth - on.offsetWidth) / 2;
  }, []);
  return (
    <div className="spread research-nav" style={{ flexWrap: "wrap", gap: 12 }}>
      <nav className="seg" aria-label="Research sections" ref={bar}>
        {tabs.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === "/research"} className={({ isActive }) => `seg-link${isActive ? " on" : ""}`}>{label}</NavLink>
        ))}
      </nav>
      {setRegion && (
        <div className="seg" role="radiogroup" aria-label="Market">
          {(["IN", "US"] as Region[]).map((r) => (
            <button key={r} role="radio" aria-checked={region === r} aria-pressed={region === r} onClick={() => setRegion(r)}>
              {r === "IN" ? "₹ India" : "$ United States"}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- small pieces ---------- */
export function StarButton({ region, symbol, name }: { region: Region; symbol: string; name?: string | null }) {
  const { has, toggle } = useWatchlist();
  const { notify, fail } = useApp();
  const on = has(region, symbol);
  return (
    <button className={`btn quiet sm star-btn${on ? " on" : ""}`} aria-pressed={on}
      onClick={async () => {
        try { await toggle({ region, symbol, name: name ?? null }); notify(on ? `${symbol} removed from your watchlist.` : `${symbol} added to your watchlist.`); }
        catch (e) { fail(e); }
      }}>
      <Star size={17} />{on ? "Watching" : "Watch"}
    </button>
  );
}

export function Panel({ title, info, children, right, span, id }: { title: ReactNode; info?: string; children: ReactNode; right?: ReactNode; span?: "full" | "half"; id?: string }) {
  return (
    <section className={`card stack rs-panel${span === "full" ? " full" : ""}`} style={{ gap: 14 }} id={id}>
      <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
        <h2 className="h3 row" style={{ gap: 0 }}>{title}{info && <Info>{info}</Info>}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Change({ q, currency }: { q: Quote | null; currency: string }) {
  if (!q || q.price == null) return null;
  const up = (q.change_pct ?? 0) >= 0;
  return (
    <div className="stack quote-big" style={{ gap: 4 }}>
      <span className="serif" style={{ fontSize: "clamp(30px, 4vw, 42px)", lineHeight: 1 }}>{price(q.price, currency)}</span>
      {q.change_pct != null && (
        <span className={`badge ${up ? "next" : "fail"}`}>{up ? "▲" : "▼"} {q.change != null ? `${up ? "+" : "−"}${Math.abs(q.change).toFixed(2)} ` : ""}({pct(q.change_pct, 2)}) today</span>
      )}
    </div>
  );
}

/* ---------- price chart ---------- */
const RANGES: [string, string][] = [["1m", "1M"], ["6m", "6M"], ["1y", "1Y"], ["3y", "3Y"], ["5y", "5Y"]];

export function PriceChart({ region, symbol, currency }: { region: Region; symbol: string; currency: string }) {
  const [range, setRange] = useState("1y");
  const [data, setData] = useState<{ t: string; c: number }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [src, setSrc] = useState("");
  useEffect(() => {
    let live = true;
    setData(null); setError(null);
    researchApi.chart(region, symbol, range).then((r) => { if (live) { setData(r.candles); setSrc(r.source); } })
      .catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [region, symbol, range]);
  const change = data && data.length > 1 ? (data[data.length - 1].c / data[0].c - 1) * 100 : null;
  const fmtDate = (t: string) => new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });
  const short = (t: string) => new Date(t).toLocaleDateString("en-GB", range === "1m" ? { day: "numeric", month: "short" } : { month: "short", year: "2-digit" });
  const ticks = data ? data.map((d) => short(d.t)) : [];
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <div className="seg" role="radiogroup" aria-label="Chart range">
          {RANGES.map(([k, l]) => <button key={k} role="radio" aria-checked={range === k} aria-pressed={range === k} onClick={() => setRange(k)}>{l}</button>)}
        </div>
        {change != null && <span className={`small ${signClass(change)}`} style={{ fontWeight: 600 }}>{pct(change)} over {RANGES.find((r) => r[0] === range)?.[1]}</span>}
      </div>
      {error ? <p className="small muted" style={{ padding: "40px 0", textAlign: "center" }}>Couldn't load the chart: {error}</p>
        : !data ? <div className="chart-skel" style={{ height: 260 }} />
          : data.length < 2 ? <p className="small muted">No price history for this range.</p>
            : <LineChart ariaLabel={`${symbol} price, ${range}`} height={260}
                lines={[{ values: data.map((d) => d.c), color: "var(--ink)", width: 2, label: "Close" }]}
                labels={data.map((d) => fmtDate(d.t))} axisLabels={ticks}
                format={(v) => price(v, currency)} axisFormat={(v) => priceAxis(v, currency)} />}
      {src && <span className="hint">{src === "Live prices" ? "Live exchange prices" : "Delayed prices"}. Daily closes.</span>}
    </div>
  );
}

/* ---------- 52-week rail ---------- */
export function Rail52({ q, low, high, currency }: { q: Quote | null; low: number | null; high: number | null; currency: string }) {
  const px = q?.price;
  if (px == null || low == null || high == null || high <= low) return null;
  const at = (v: number) => Math.max(0, Math.min(100, ((v - low) / (high - low)) * 100));
  const p = at(px);
  const band = q?.low != null && q?.high != null && q.high > q.low ? [at(q.low), at(q.high)] : null;
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="rail-track" aria-hidden="true">
        {band && <div className="rail-band" style={{ left: `${band[0]}%`, width: `${Math.max(band[1] - band[0], 0.8)}%` }} />}
        <div className="rail-mark" style={{ left: `${p}%` }} />
      </div>
      <div className="spread small"><span className="muted">Low <b className="num" style={{ color: "var(--ink)" }}>{price(low, currency)}</b></span>
        <span className="muted">High <b className="num" style={{ color: "var(--ink)" }}>{price(high, currency)}</b></span></div>
      <p className="small">Trading in the <b>{ordinal(Math.round(p))} percentile</b> of its 52-week range{band ? ". The shaded band is today's range." : "."}</p>
    </div>
  );
}

/* ---------- where a unit of revenue goes ---------- */
export function MarginCascade({ gross, operating, net }: { gross: number | null; operating: number | null; net: number | null }) {
  if (gross == null || operating == null || net == null || gross <= 0) return null;
  const steps = [{ k: "Revenue", v: 100, lost: "" }, { k: "Gross profit", v: gross, lost: "cost of goods" },
    { k: "Operating profit", v: operating, lost: "running costs, R&D" }, { k: "Net profit", v: net, lost: "tax, interest, other" }];
  return (
    <div className="stack" style={{ gap: 10 }}>
      {steps.map((s, i) => {
        const w = Math.max(0, Math.min(100, s.v)), prev = i ? steps[i - 1].v : null, lost = prev != null ? prev - s.v : 0;
        return (
          <div key={s.k} className="casc-row">
            <span className="small">{s.k}</span>
            <div className="casc-bar">
              <div className="casc-fill" style={{ width: `${w}%`, background: i === 3 ? "var(--blue)" : i === 0 ? "var(--dash)" : "var(--ink-2)" }} />
              {lost > 0 && <div className="casc-lost" style={{ left: `${w}%`, width: `${Math.min(lost, 100 - w)}%` }} title={`−${lost.toFixed(1)} to ${s.lost}`} />}
            </div>
            <span className="num small" style={{ textAlign: "right" }}>{s.v.toFixed(1)}%</span>
          </div>
        );
      })}
      <p className="hint">Of every 100 in sales. The hatched part is what costs take at each step.</p>
    </div>
  );
}

/* ---------- metrics with context rails ---------- */
/** The short names in Key numbers, in plain words, for anyone who doesn't read balance sheets for a living. */
const TERMS: Record<string, string> = {
  "P/E": "Price to earnings: the share price divided by a year's profit per share.",
  "P/B": "Price to book: the share price divided by the company's net assets per share.",
  "Div yield": "The last year's dividends as a share of today's price.",
  "Book value": "The company's net assets (what it owns minus what it owes) per share.",
  "Face value": "The nominal value printed on each share; it doesn't change with the price.",
  "ROCE": "Return on capital employed: operating profit as a share of all the money in the business, borrowed or not.",
  "ROE": "Return on equity: profit as a share of the shareholders' money in the business.",
  "OPM": "Operating profit margin: the share of sales left after running costs, before interest and tax.",
  "Net margin": "Profit after everything, as a share of sales.",
  "Debt / equity": "Borrowings divided by the shareholders' money in the business.",
  "Latest YoY": "The latest year against the year before.",
  "3Y CAGR": "Compound annual growth rate: the steady yearly growth that gets from the start to the end of the period.",
};

export function MetricsGrid({ groups, currency, industry }: { groups: MetricGroup[]; currency: string; industry?: string | null }) {
  const used = Object.entries(TERMS).filter(([k]) => groups.some((g) => g.items.some((m) => m.label === k)));
  return (
    <>
    <div className="metric-groups">
      {groups.map((g) => (
        <div key={g.title} className="stack" style={{ gap: 2 }}>
          <span className="eyebrow" style={{ marginBottom: 6 }}>{g.title}</span>
          {g.items.map((m) => {
            const b = bandPosition(m.label, m.value, industry);
            const signed = m.unit === "%±";
            return (
              <div key={m.label} className="metric-row">
                <span className="small muted">{m.label}</span>
                <span className={`num ${signed ? signClass(m.value) : ""}`} style={{ fontWeight: 600, textAlign: "right" }}>{metricText(m, currency)}</span>
                {b ? (
                  <span className="krail" aria-hidden="true">
                    <s style={{ left: `${b.weak}%` }} /><s style={{ left: `${b.strong}%` }} />
                    <i className={b.tone} style={{ left: `${b.pos}%` }} />
                  </span>
                ) : <span />}
              </div>
            );
          })}
        </div>
      ))}
    </div>
    {used.length > 0 && (
      <details className="ref-more">
        <summary>What these terms mean</summary>
        <dl className="terms">{used.map(([k, v]) => <div key={k}><dt>{k === "3Y CAGR" ? "CAGR" : k}</dt><dd>{v}</dd></div>)}</dl>
      </details>
    )}
    </>
  );
}

/* ---------- bars ---------- */
export function TrendBars({ points, label, unit, tone = "ink" }: { points: SeriesPoint[]; label: string; unit: string; tone?: "ink" | "blue" }) {
  if (points.length < 2) return null;
  // bars grow up from a zero line for gains and hang down from it for losses, so a loss year reads as a loss
  const up = Math.max(0, ...points.map((p) => p.v));
  const down = Math.max(0, ...points.map((p) => -p.v));
  const span = up + down || 1;
  const PLOT = 112;                                    // px for bars; the labels sit outside the bars
  const zero = (up / span) * PLOT;                     // px from the top
  const first = points[0].v, last = points[points.length - 1].v;
  const lossYears = points.some((p) => p.v <= 0);
  const growth = !lossYears && first > 0 ? (Math.pow(last / first, 1 / (points.length - 1)) - 1) * 100 : null;
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="spread"><b className="small">{label} <span className="muted" style={{ fontWeight: 400 }}>({unit})</span></b>
        {growth != null ? <span className={`small ${signClass(growth)}`}>{pct(growth)} a year</span>
          : lossYears ? <span className="small muted">loss years in between, so no yearly rate</span> : null}</div>
      <div className="tbars">
        {points.map((p, i) => {
          const h = Math.max(2, (Math.abs(p.v) / span) * PLOT);
          const neg = p.v < 0;
          const color = neg ? "var(--orange)" : i === points.length - 1 ? (tone === "blue" ? "var(--blue)" : "var(--ink)") : "var(--dash)";
          return (
            <div key={p.y} className="tbar" title={`${p.y}: ${p.v.toLocaleString(/cr/i.test(unit) ? "en-IN" : "en-US", { maximumFractionDigits: 2 })} ${unit}`}>
              <div className="tbar-plot" style={{ height: PLOT + 36 }}>
                {down > 0 && <div className="tbar-zero" style={{ top: 18 + zero }} />}
                <div className="tbar-bar" data-v={p.v} style={{ background: color, height: h, top: neg ? 18 + zero : 18 + zero - h,
                  borderRadius: neg ? "0 0 4px 4px" : "4px 4px 0 0" }} />
                <span className={`num tiny tbar-num ${neg ? "neg" : ""}`} style={neg ? { top: 18 + zero + h + 2 } : { top: 18 + zero - h - 16 }}>
                  {trendValue(p.v, unit)}</span>
              </div>
              <span className="tiny muted">{p.y}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function EarningsBars({ rows }: { rows: Company["earnings"] }) {
  if (rows.length < 2) return null;
  const max = Math.max(4, ...rows.map((r) => Math.abs(r.surprise_pct)));
  const beats = rows.filter((r) => r.surprise_pct >= 0).length;
  // the zero line sits at the bottom when every quarter beat, at the top when every one missed, else in the middle
  const zero = beats === rows.length ? 0 : beats === 0 ? 100 : 50;   // % from the bottom
  const plotH = zero === 50 ? 150 : 100;
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="eq">
        {rows.map((r) => {
          const up = r.surprise_pct >= 0, h = (Math.abs(r.surprise_pct) / max) * (up ? 100 - zero : zero) * 0.78;
          return (
            <div key={r.period} className="eq-col">
              <div className="eq-plot" style={{ height: plotH }}>
                <div className="eq-zero" style={{ top: "auto", bottom: `${zero}%` }} />
                <div className="eq-bar" style={{ background: up ? "var(--blue)" : "var(--orange)", ...(up ? { bottom: `${zero}%`, height: `${h}%` } : { top: `${100 - zero}%`, height: `${h}%` }) }} />
                <span className={`eq-num ${up ? "pos" : "neg"}`} style={up ? { bottom: `calc(${zero}% + ${h}% + 4px)` } : { top: `calc(${100 - zero}% + ${h}% + 4px)` }}>{pct(r.surprise_pct)}</span>
              </div>
              <span className="tiny muted">{r.period.slice(0, 7)}</span>
              <span className="tiny num" style={{ textAlign: "center", lineHeight: 1.35 }}>{r.actual.toFixed(2)}<br /><span className="muted">vs {r.estimate.toFixed(2)}</span></span>
            </div>
          );
        })}
      </div>
      <p className="hint">{beats} of {rows.length} quarters beat analysts' earnings-per-share estimate.</p>
    </div>
  );
}

const DONUT = ["var(--ink)", "var(--blue)", "var(--orange)", "var(--dash)", "var(--blue-ink)", "var(--orange-ink)", "var(--muted)", "var(--line-2)"];
function Donut({ segments }: { segments: { label: string; share: number }[] }) {
  const tot = segments.reduce((a, s) => a + s.share, 0) || 1;
  const R = 42, C = 2 * Math.PI * R;
  let acc = 0;
  return (
    <div className="row wrap" style={{ gap: 20, alignItems: "center" }}>
      <svg viewBox="0 0 120 120" width="120" height="120" aria-hidden="true">
        <circle cx="60" cy="60" r={R} fill="none" stroke="var(--chip)" strokeWidth="15" />
        {segments.map((s, i) => {
          const f = s.share / tot;
          const el = <circle key={s.label} cx="60" cy="60" r={R} fill="none" stroke={DONUT[i % DONUT.length]} strokeWidth="15"
            strokeDasharray={`${f * C} ${C}`} strokeDashoffset={-acc * C} transform="rotate(-90 60 60)" />;
          acc += f;
          return el;
        })}
      </svg>
      <div className="stack" style={{ gap: 6 }}>
        {segments.map((s, i) => (
          <span key={s.label} className="row small" style={{ gap: 8 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: DONUT[i % DONUT.length], flex: "none" }} />
            {s.label}<span className="muted num">{Math.round((s.share / tot) * 100)}%</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ScoreBar({ label, v }: { label: string; v: number | null }) {
  if (v == null) return null;
  return (
    <div className="score-row">
      <span className="small">{label}</span>
      <div className="score-track"><div style={{ width: `${v}%`, background: v >= 66 ? "var(--blue)" : v >= 40 ? "var(--ink-2)" : "var(--orange)" }} /></div>
      <span className="num small" style={{ textAlign: "right" }}>{v}</span>
    </div>
  );
}



/* ---------- lists ---------- */
export function NewsList({ items, limit = 8 }: { items: NewsItem[]; limit?: number }) {
  if (!items.length) return <p className="small muted">No recent headlines.</p>;
  return (
    <div className="stack" style={{ gap: 0 }}>
      {items.slice(0, limit).map((n, i) => (
        <a key={i} className="news-row" href={safeHref(n.url)} target="_blank" rel="noopener noreferrer">
          <span>{n.headline}</span>
          <span className="tiny muted">{n.source}{n.at ? ` · ${ago(n.at)}` : ""} ↗</span>
        </a>
      ))}
    </div>
  );
}

export function QuoteGrid({ region, symbols, names, empty }: { region: Region; symbols: string[]; names?: Record<string, string | null>; empty?: ReactNode }) {
  const [q, setQ] = useState<Record<string, Quote | null> | null>(null);
  const key = symbols.join(",");
  useEffect(() => {
    let live = true;
    setQ(null);
    if (!symbols.length) return;
    researchApi.quotes(region, symbols).then((r) => live && setQ(r)).catch(() => live && setQ({}));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region, key]);
  if (!symbols.length) return <>{empty}</>;
  return (
    <div className="quote-grid">
      {symbols.map((s) => {
        const x = q?.[s];
        return (
          <Link key={s} to={`/research/${region}/${encodeURIComponent(s)}`} className="quote-card">
            <b>{s}</b>
            {names?.[s] && <span className="tiny muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{names[s]}</span>}
            <span className="num">{q == null ? <span className="skel" /> : x?.price != null ? price(x.price, region === "IN" ? "INR" : "USD") : "–"}</span>
            <span className={`tiny num ${signClass(x?.change_pct)}`}>{x?.change_pct != null ? pct(x.change_pct, 2) : ""}</span>
          </Link>
        );
      })}
    </div>
  );
}


export function Shareholding({ s }: { s: NonNullable<Company["shareholding"]> }) {
  return (
    <div className="stack" style={{ gap: 10 }}>
      {s.rows.map((r) => (
        <div key={r.label} className="score-row">
          <span className="small">{r.label}</span>
          <div className="score-track"><div style={{ width: `${Math.min(100, r.value)}%`, background: r.label === "Promoters" ? "var(--ink)" : "var(--dash)" }} /></div>
          <span className="num small" style={{ textAlign: "right" }}>{r.value.toFixed(1)}%
            {r.change != null && Math.abs(r.change) >= 0.05 && <span className={`tiny ${signClass(r.change)}`}> {r.change > 0 ? "+" : "−"}{Math.abs(r.change).toFixed(1)}</span>}</span>
        </div>
      ))}
      <p className="hint">As of {s.as_of}. The small number is the change over the last year.</p>
    </div>
  );
}

export function QuarterTable({ q }: { q: NonNullable<Company["quarters"]> }) {
  const f = (v: number | null) => (v == null ? "–" : Math.round(v).toLocaleString("en-IN"));
  return (
    <div className="table-wrap">
      <table className="nums">
        <thead><tr><th>₹ Cr</th>{q.cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          <tr><td>Sales</td>{q.sales.map((v, i) => <td key={i} className="num">{f(v)}</td>)}</tr>
          <tr><td>Net profit</td>{q.profit.map((v, i) => <td key={i} className="num">{f(v)}</td>)}</tr>
          <tr><td>Operating margin</td>{q.opm.map((v, i) => <td key={i} className="num">{v == null ? "–" : `${v}%`}</td>)}</tr>
        </tbody>
      </table>
    </div>
  );
}

/* ---------- AI read ---------- */
export function AIRead({ region, symbol, onTest }: { region: Region; symbol: string; onTest: (idea: Idea) => void }) {
  const [r, setR] = useState<CompanyAI | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = async (refresh = false) => {
    setBusy(true); setError(null);
    try { setR(await researchApi.companyAI(region, symbol, refresh)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  useEffect(() => { setR(null); load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [region, symbol]);
  const age = r ? ago(new Date(r.generated_at * 1000).toISOString()) : "";
  return (
    <section className="card stack ai-read" style={{ gap: 18 }} aria-labelledby="ai-h">
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 id="ai-h" className="h2 row" style={{ gap: 0 }}>AI read<Info>{"An AI analyst's scored take, written from the live numbers on this page. Treat it as a starting point for ideas, not advice: the scores are opinions, and segment shares are estimates."}</Info></h2>
        <span className="row small muted" style={{ gap: 10 }}>{r && `Written ${age}`}
          <button className="btn quiet sm" disabled={busy} onClick={() => load(true)}>{busy ? "Thinking…" : "Refresh"}</button></span>
      </div>
      {error ? <p className="small" style={{ color: "var(--orange-ink)" }}>{error}</p>
        : !r ? <div className="row muted" style={{ gap: 10 }}><span className="spinner" />Reading the numbers…</div> : (
          <>
            {r.summary && <p className="serif" style={{ fontSize: 19, lineHeight: 1.45 }}>{r.summary}</p>}
            {(Object.values(r.scores).some((x) => x != null) || r.valuation_note) && <div className="ai-top">
              <div className="stack" style={{ gap: 6, flex: "1 1 240px" }}>
                <ScoreBar label="Moat" v={r.scores.moat} /><ScoreBar label="Growth" v={r.scores.growth} />
                <ScoreBar label="Momentum" v={r.scores.momentum} />
                <ScoreBar label="Health" v={r.scores.health} />
              </div>
              {r.valuation_note && <div className="stack" style={{ gap: 8, flex: "1 1 200px" }}>
                <span className="eyebrow">Valuation</span>
                <p className="small muted">{r.valuation_note}</p>
              </div>}
            </div>}
            {(r.bull.length > 0 || r.bear.length > 0) && <div className="grid2" style={{ gap: 20 }}>
              {r.bull.length > 0 && <div className="stack" style={{ gap: 8 }}><b className="pos">Strengths</b><ul className="bullets">{r.bull.map((b) => <li key={b}>{b}</li>)}</ul></div>}
              {r.bear.length > 0 && <div className="stack" style={{ gap: 8 }}><b className="neg">Risks</b><ul className="bullets">{r.bear.map((b) => <li key={b}>{b}</li>)}</ul></div>}
            </div>}
            {(r.position || r.watch.length > 0) && (
              <div className="grid2" style={{ gap: 20 }}>
                {r.position && <div className="stack" style={{ gap: 6 }}><b>Where it sits</b><p className="small">{r.position}</p></div>}
                {r.watch.length > 0 && <div className="stack" style={{ gap: 6 }}><b>What to watch</b><ul className="bullets small">{r.watch.map((w) => <li key={w}>{w}</li>)}</ul></div>}
              </div>
            )}
            {r.segments.length > 1 && <div className="stack" style={{ gap: 10 }}><b>Revenue by segment <span className="muted" style={{ fontWeight: 400 }}>(estimate)</span></b><Donut segments={r.segments} /></div>}
            {r.ideas.length > 0 && (
              <div className="stack ideas-box" style={{ gap: 12 }}>
                <div className="stack" style={{ gap: 2 }}>
                  <b style={{ fontSize: 17 }}>Ideas to test on {symbol}</b>
                  <span className="small muted">Opinions are cheap. Pick one and StratLab will test it on years of real prices, after costs.</span>
                </div>
                <div className="idea-grid">
                  {r.ideas.map((i) => (
                    <div key={i.text} className="idea-card">
                      <b>{i.title}</b>
                      <span className="small">"{i.text}"</span>
                      {i.why && <span className="tiny muted">{i.why}</span>}
                      <button className="btn blue sm" style={{ alignSelf: "flex-start", marginTop: "auto" }} onClick={() => onTest(i)}>Test this idea →</button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
    </section>
  );
}

export function SourcesNote({ sources }: { sources: Company["sources"] }) {
  const bad = sources.filter((s) => !s.ok);
  if (!bad.length) return null;
  return <div className="banner small" role="status">Some data is missing: {bad.map((s) => `${s.source} (${s.error})`).join(" · ")}</div>;
}

