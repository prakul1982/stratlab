import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { ago, marketTz, num, pct, price, safeHref, signCls } from "../lib/format";
import {
  bandPosition, metricText, monthsOld, newsAge, ordinal, researchApi, staleQuarter, trendValue, useWatchlist,
  type Company, type CompanyAI, type FactRow, type Idea, type MetricGroup, type NewsItem, type Quote, type Region, type SeriesPoint,
} from "../lib/research";
import { companyLoader, PriceChart as PriceChartView } from "../charts/price/lazy";
import { Star } from "./Icons";
import { BarList, Card, CardHead, DataTable, Delta, Disclosure, Notice, Seg, Signed, Skeleton } from "./kit";
import { SurvBadges } from "./Surveillance";
import { FoBadges } from "./FoBadges";
import { track } from "../lib/analytics";

export { CompanySearch } from "./CompanySearch";

/* ---------- navigation ---------- */
/** The India / United States switch at the top of a research page. The pages of Invest no longer have a row of tabs: the
 * breadcrumb at the top of every page and the sidebar are the menu. A page that has only one market passes no `setRegion`
 * and shows nothing here. */
export function RegionSwitch({ region, setRegion }: { region: Region; setRegion?: (r: Region) => void }) {
  if (!setRegion) return null;
  return <Seg label="Market" value={region} onChange={(v) => setRegion(v as Region)} options={[{ value: "IN", label: "₹ India" }, { value: "US", label: "$ United States" }]} />;
}

/* ---------- small pieces ---------- */
export function StarButton({ region, symbol, name }: { region: Region; symbol: string; name?: string | null }) {
  const { has, toggle } = useWatchlist();
  const { notify, fail } = useApp();
  const on = has(region, symbol);
  return (
    <button className={`btn quiet sm star-btn${on ? " on" : ""}`} aria-pressed={on}
      onClick={async () => {
        try {
          await toggle({ region, symbol, name: name ?? null });
          if (!on) track("watchlist add", { region });
          notify(on ? `${symbol} removed from your watchlist.` : `${symbol} added to your watchlist.`);
        } catch (e) { fail(e); }
      }}>
      <Star size={17} />{on ? "Watching" : "Watch"}
    </button>
  );
}

/** A card with a title: the kit's Card and CardHead, for pages that still pass a title, an (i) and something on the right. */
export function Panel({ title, info, children, right, id }: { title: ReactNode; info?: ReactNode; children: ReactNode; right?: ReactNode; id?: string }) {
  return (
    <Card id={id}>
      <CardHead title={title} info={info} actions={right} />
      {children}
    </Card>
  );
}

/** The day's price and its change as one block: the price in the page's sans font and a pill for the change, green or red
 * with the sign (and ▲/▼) printed. The price and its move. `closed`: the market is shut, so the price stands at the last close and says so, and the move
 * is that session's ("on the day"), never "today" for a day that hasn't traded. */
export function Change({ q, currency, closed = false }: { q: Quote | null; currency: string; closed?: boolean }) {
  if (!q || q.price == null) return null;
  return (
    <div className="k-stat inv-quote" data-testid="company-price">
      {closed && <span className="k-stat-k">Last close</span>}
      <span className="k-stat-v">{price(q.price, currency)}</span>
      {q.change_pct != null && (
        <span className="k-stat-d">
          <Delta value={q.change_pct}>{q.change != null ? `${q.change >= 0 ? "+" : "−"}${Math.abs(q.change).toFixed(2)} (${pct(q.change_pct, 2)})` : pct(q.change_pct, 2)}</Delta> {closed ? "on the day" : "today"}
        </span>
      )}
    </div>
  );
}

/* ---------- price chart ---------- */
/** The company's candles in the shared price chart (its code loads only on pages that show one). */
export function PriceChart({ region, symbol, currency, price: shown, asOf: shownAt }: { region: Region; symbol: string; currency: string; price?: number | null; asOf?: string | null }) {
  // the header's price and the title's are this page's one reading; the newest candle is it too (see settleLast)
  const load = useMemo(() => companyLoader(region, symbol, { price: shown, asOf: shownAt, tz: marketTz(region) }), [region, symbol, shown, shownAt]);
  const compare = useCallback((other: string) => companyLoader(region, other)("1d", { range: "max" }).then((r) => r.candles), [region]);
  return (
    <PriceChartView symbol={symbol} storageKey={`${region}:${symbol}`} currency={currency} load={load}
      timeframes={["5m", "15m", "1h", "1d", "1w", "1mo"]} compareLoad={compare} compareHint={region === "IN" ? "e.g. TCS" : "e.g. MSFT"}
      note="Prices as traded, not adjusted for dividends. Intraday candles cover recent weeks." />
  );
}

/* ---------- 52-week rail ---------- */
export function Rail52({ q, low, high, currency, compact }: { q: Quote | null; low: number | null; high: number | null; currency: string; compact?: boolean }) {
  const px = q?.price;
  if (px == null || low == null || high == null || high <= low) return null;
  const at = (v: number) => Math.max(0, Math.min(100, ((v - low) / (high - low)) * 100));
  const p = at(px);
  const band = q?.low != null && q?.high != null && q.high > q.low ? [at(q.low), at(q.high)] : null;
  // in a company's header: the rail and its two ends, under the price (the percentile is in the rail's label)
  if (compact) return (
    <div className="inv-rail52" title={`${ordinal(Math.round(p))} percentile of its 52-week range${band ? "; the shaded band is today's range" : ""}`}>
      <svg className="inv-rail" viewBox="0 0 100 10" preserveAspectRatio="none" role="img" aria-label={`52-week range ${price(low, currency)} to ${price(high, currency)}; today's price sits at the ${ordinal(Math.round(p))} percentile`}>
        <rect className="track" x="0" y="3" width="100" height="4" rx="2" />
        {band && <rect className="band" x={band[0]} y="1" width={Math.max(band[1] - band[0], 0.8)} height="8" />}
        <rect className="mark" x={Math.min(98.8, Math.max(0, p - 0.6))} y="0" width="1.2" height="10" />
      </svg>
      <div className="k-spread k-note"><span>52-wk low {price(low, currency)}</span><span>high {price(high, currency)}</span></div>
    </div>
  );
  return (
    <div className="k-stack">
      <svg className="inv-rail" viewBox="0 0 100 10" preserveAspectRatio="none" role="img" aria-label={`Today's price sits at ${ordinal(Math.round(p))} percentile of its 52-week range`}>
        <rect className="track" x="0" y="3" width="100" height="4" rx="2" />
        {band && <rect className="band" x={band[0]} y="1" width={Math.max(band[1] - band[0], 0.8)} height="8" />}
        <rect className="mark" x={Math.min(98.8, Math.max(0, p - 0.6))} y="0" width="1.2" height="10" />
      </svg>
      <div className="k-spread k-small">
        <span className="k-muted">Low <b className="inv-ink">{price(low, currency)}</b></span>
        <span className="k-muted">High <b className="inv-ink">{price(high, currency)}</b></span>
      </div>
      <p className="k-small">Trading in the <b>{ordinal(Math.round(p))} percentile</b> of its 52-week range{band ? ". The shaded band is today's range." : "."}</p>
    </div>
  );
}

/* ---------- where a unit of revenue goes ---------- */
export function MarginCascade({ gross, operating, net }: { gross: number | null; operating: number | null; net: number | null }) {
  if (gross == null || operating == null || net == null || gross <= 0) return null;
  const steps = [{ k: "Revenue", v: 100, lost: "" }, { k: "Gross profit", v: gross, lost: "cost of goods" },
    { k: "Operating profit", v: operating, lost: "running costs, R&D" }, { k: "Net profit", v: net, lost: "tax, interest, other" }];
  return (
    <BarList label="Where a sale goes" footnote="Of every 100 in sales, what is left at each step."
      rows={steps.map((s, i) => {
        const lost = i ? steps[i - 1].v - s.v : 0;
        return { key: s.k, name: s.k, note: lost > 0 ? `−${lost.toFixed(1)} to ${s.lost}` : undefined, value: `${s.v.toFixed(1)}%`, pct: Math.max(0, Math.min(100, s.v)) };
      })} />
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
  "EBITDA margin": "Operating profit before depreciation, interest and tax (EBITDA) as a share of sales: what is left after running costs.",
  "Net margin": "Profit after everything, as a share of sales.",
  "Debt / equity": "Borrowings divided by the shareholders' money in the business.",
  "Latest YoY": "The latest year against the year before.",
  "3Y CAGR": "Compound annual growth rate: the steady yearly growth that gets from the start to the end of the period.",
};

export function MetricsGrid({ groups, currency, industry }: { groups: MetricGroup[]; currency: string; industry?: string | null }) {
  const used = Object.entries(TERMS).filter(([k]) => groups.some((g) => g.items.some((m) => m.label === k)));
  return (
    <>
      <div className="inv-metrics">
        {groups.map((g) => (
          <div key={g.title} className="k-stack">
            <span className="k-eyebrow">{g.title}</span>
            <div className="inv-metric-rows">
              {g.items.map((m) => {
                const b = bandPosition(m.label, m.value, industry);
                return (
                  <div key={m.label} className="inv-metric">
                    {/* a note says what a figure counts (a dividend yield with a special dividend in it) */}
                    <span className="k-small k-muted">{m.label}{m.note && <span className="k-sub-line">{m.note}</span>}</span>
                    <span className={`inv-metric-v ${m.unit === "%±" ? signCls(m.value) : ""}`}>{metricText(m, currency)}</span>
                    {b ? (
                      <svg className="inv-krail" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
                        <rect className="track" x="0" y="3" width="100" height="4" rx="2" />
                        <rect className="tick" x={b.weak} y="1" width="0.8" height="8" />
                        <rect className="tick" x={b.strong} y="1" width="0.8" height="8" />
                        <rect className="mark" x={Math.max(0, b.pos - 1.2)} y="0" width="2.4" height="10" />
                      </svg>
                    ) : <span />}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {used.length > 0 && (
        <Disclosure summary="What these terms mean">
          <dl className="inv-terms">{used.map(([k, v]) => <div key={k}><dt>{k === "3Y CAGR" ? "CAGR" : k}</dt><dd>{v}</dd></div>)}</dl>
        </Disclosure>
      )}
    </>
  );
}

/* ---------- bars ---------- */
/** Yearly figures as bars that grow up from a zero line for gains and hang down from it for losses, so a loss year reads as
 * a loss. Each year's figure is written above its bar, the year under it. */
export function TrendBars({ points, label, unit, tone = "ink" }: { points: SeriesPoint[]; label: string; unit: string; tone?: "ink" | "blue" }) {
  if (points.length < 2) return null;
  const up = Math.max(0, ...points.map((p) => p.v));
  const down = Math.max(0, ...points.map((p) => -p.v));
  const span = up + down || 1;
  const PLOT = 112;                                    // the plot's height in its own units
  const zero = (up / span) * PLOT;                     // from the top
  const first = points[0].v, last = points[points.length - 1].v;
  const lossYears = points.some((p) => p.v <= 0);
  const growth = !lossYears && first > 0 ? (Math.pow(last / first, 1 / (points.length - 1)) - 1) * 100 : null;
  return (
    <div className="k-stack">
      <div className="k-spread">
        <b className="k-small">{label} <span className="k-muted inv-plain">({unit})</span></b>
        {growth != null ? <span className="k-small k-muted"><Signed value={growth}>{pct(growth)}</Signed> a year</span>
          : lossYears ? <span className="k-small k-muted">loss years in between, so no yearly rate</span> : null}
      </div>
      <div className="tbars">
        {points.map((p, i) => {
          const h = Math.max(2, (Math.abs(p.v) / span) * PLOT);
          const neg = p.v < 0;
          const cls = `tbar-bar${neg ? " neg" : i === points.length - 1 ? ` last ${tone}` : ""}`;
          return (
            <div key={p.y} className="tbar" title={`${p.y}: ${p.v.toLocaleString(/cr/i.test(unit) ? "en-IN" : "en-US", { maximumFractionDigits: 2 })} ${unit}`}>
              <span className={`tbar-num${neg ? " neg" : ""}`}>{trendValue(p.v, unit)}</span>
              <svg className="tbar-plot" viewBox={`0 0 10 ${PLOT}`} preserveAspectRatio="none" aria-hidden="true">
                {down > 0 && <line className="tbar-zero" x1="0" x2="10" y1={zero} y2={zero} vectorEffect="non-scaling-stroke" />}
                <rect className={cls} data-v={p.v} x="1.5" width="7" y={neg ? zero : zero - h} height={h} />
              </svg>
              <span className="tbar-year">{p.y}</span>
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
  const PLOT = 100;
  // the zero line sits at the bottom when every quarter beat, at the top when every one missed, else in the middle
  const zero = beats === rows.length ? PLOT : beats === 0 ? 0 : PLOT / 2;
  return (
    <div className="k-stack">
      <div className="tbars eq">
        {rows.map((r) => {
          const up = r.surprise_pct >= 0;
          const h = Math.max(2, (Math.abs(r.surprise_pct) / max) * (up ? zero : PLOT - zero) * 0.95);
          return (
            <div key={r.period} className="tbar">
              <span className={`tbar-num${up ? " up" : " neg"}`}>{pct(r.surprise_pct)}</span>
              <svg className="tbar-plot" viewBox={`0 0 10 ${PLOT}`} preserveAspectRatio="none" aria-hidden="true">
                <line className="tbar-zero" x1="0" x2="10" y1={zero} y2={zero} vectorEffect="non-scaling-stroke" />
                <rect className={`tbar-bar ${up ? "beat" : "neg"}`} data-v={r.surprise_pct} x="1.5" width="7" y={up ? zero - h : zero} height={h} />
              </svg>
              <span className="tbar-year">{r.period.slice(0, 7)}</span>
              <span className="k-note tbar-sub">{num(r.actual, 2)}<br />vs {num(r.estimate, 2)}</span>
            </div>
          );
        })}
      </div>
      <p className="k-note">{beats} of {rows.length} quarters beat analysts' earnings-per-share estimate.</p>
    </div>
  );
}

/** Plain-number lines (growth, price trend, debt and cash, margins and returns), each a label and its facts. No
 *  bars, grades or colours: the numbers are the whole story. */
function FactRows({ rows }: { rows: FactRow[] }) {
  return (
    <dl className="fact-rows">
      {rows.map((r) => (
        <div key={r.id} className="fact-row">
          <dt className="k-small"><b>{r.label}</b></dt>
          <dd className="k-small">{r.items.map((i) => <span key={i.label} className="fact-item"><span className="k-muted">{i.label}</span> <span>{i.text}</span></span>)}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- lists ---------- */
export function NewsList({ items, limit = 8 }: { items: NewsItem[]; limit?: number }) {
  if (!items.length) return <p className="k-small k-muted">No recent headlines.</p>;
  // newest first; an item over a week old says how old it is beside its date, so it never reads as today's news
  const when = (n: NewsItem) => (n.at ? new Date(n.at).getTime() : -Infinity);
  const sorted = [...items].sort((a, b) => when(b) - when(a));
  return (
    <div className="inv-news">
      {sorted.slice(0, limit).map((n, i) => {
        const old = newsAge(n.at);
        return (
          <a key={i} className="inv-news-row" href={safeHref(n.url)} target="_blank" rel="noopener noreferrer">
            <span>{n.headline}</span>
            <span className="k-note">{[n.source, n.at ? ago(n.at) : null, old].filter(Boolean).join(" · ")} ↗</span>
          </a>
        );
      })}
    </div>
  );
}

/** Companies as small tiles that open them: the symbol, its name, the price and the day's change (a neutral pill). */
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
    <div className="inv-tiles">
      {symbols.map((s) => {
        const x = q?.[s];
        return (
          <Link key={s} to={`/research/${region}/${encodeURIComponent(s)}`} className="inv-tile">
            <span className="inv-tile-top"><b>{s}</b><span className="inv-tile-px">{q == null ? <span className="skel" /> : x?.price != null ? price(x.price, region === "IN" ? "INR" : "USD") : "–"}</span></span>
            {names?.[s] && <span className="k-note inv-clip">{names[s]}</span>}
            <span className="inv-tile-chg">
              {x?.change_pct != null && <Delta value={x.change_pct}>{pct(x.change_pct, 2)}</Delta>}
              <SurvBadges region={region} symbol={s} />
              <FoBadges region={region} symbol={s} plain />
            </span>
          </Link>
        );
      })}
    </div>
  );
}

/** " (16 months old)" when a newer quarter's shareholding should have been filed by now (within 21 days of its end). */
function holdersAge(asOf: string): string {
  const n = staleQuarter(asOf, 21);
  return n != null ? ` (${monthsOld(n)})` : "";
}

export function Shareholding({ s }: { s: NonNullable<Company["shareholding"]> }) {
  return (
    <BarList label="Who owns it" footnote={`As of ${s.as_of}${holdersAge(s.as_of)}. The change is over the last year.${s.note ? ` ${s.note}` : ""}`}
      rows={s.rows.map((r) => ({
        key: r.label, name: r.label, pct: Math.min(100, r.value),
        value: <>{r.value.toFixed(1)}%{r.change != null && Math.abs(r.change) >= 0.05 && <span className="k-note"> <Signed value={r.change}>{r.change > 0 ? "+" : "−"}{Math.abs(r.change).toFixed(1)}</Signed></span>}</>,
      }))} />
  );
}

export function QuarterTable({ q, bank = false }: { q: NonNullable<Company["quarters"]>; bank?: boolean }) {
  const f = (v: number | null) => (v == null ? "–" : num(Math.round(v), 0));
  const rows = [
    { name: "Sales", cells: q.sales.map(f) }, { name: "Net profit", cells: q.profit.map(f) },
    // a bank reports a financing margin there, not an EBITDA margin (R7O-001)
    { name: bank ? "Financing margin" : "EBITDA margin", cells: q.opm.map((v) => (v == null ? "–" : `${v}%`)) },
  ];
  return (
    <DataTable label="The last quarters, in ₹ cr" rows={rows} rowKey={(r) => r.name}
      columns={[{ key: "m", header: "₹ cr", rowHeader: true, cell: (r) => r.name },
        ...q.cols.map((c, i) => ({ key: c, header: c, numeric: true, cell: (r: (typeof rows)[number]) => r.cells[i] }))]} />
  );
}

/* ---------- AI read ---------- */
/** Why an AI read is missing, as the words that follow "No AI read right now": a few plain words, never the message
 * itself, which can be long or name an internal step. When the cause isn't one worth naming, nothing is said of it. */
export function aiReason(message: string | null): string {
  if (message && /busy|overloaded|try again in/i.test(message)) return ": the AI service is busy. Ask again in a minute.";
  if (message && /used \d+|limit|allowance|tomorrow/i.test(message)) return ": today's fresh AI reads are used up.";
  if (message && /plan|upgrade/i.test(message)) return ": it isn't on your plan.";
  return ". Ask again in a moment.";
}

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
    <div className="ai-read">
      <Card label="AI read">
        <CardHead title="AI read" info={"A written read from the live numbers on this page, with no scores or ratings. \"The numbers\" are worked out from the reported results and daily prices, not by the AI. Segment shares are estimates. A starting point for ideas, not advice."}
          actions={error ? undefined : <>{r && <span className="k-note">Written {age}</span>}<button className="btn quiet sm" disabled={busy} onClick={() => load(true)}>{busy ? "Thinking…" : "Refresh"}</button></>} />
        {/* a missing AI read is not a fault with the company's numbers: one calm line and one way to ask again */}
        {error ? (
          <div className="k-row ai-read-off" role="status">
            <span className="k-small k-muted">No AI read right now{aiReason(error)} The numbers on this page don't depend on it.</span>
            <button type="button" className="btn quiet sm" disabled={busy} onClick={() => load(true)}>{busy ? "Asking…" : "Ask again"}</button>
          </div>
        )
          : !r ? <Skeleton label="Reading the numbers" lines={3} /> : (
            <>
              {r.summary && <p className="inv-summary">{r.summary}</p>}
              {((r.facts ?? []).length > 0 || r.valuation_note) && <div className="inv-two">
                {(r.facts ?? []).length > 0 && <div className="k-stack">
                  <span className="k-eyebrow">The numbers</span>
                  <FactRows rows={r.facts} />
                </div>}
                {r.valuation_note && <div className="k-stack">
                  <span className="k-eyebrow">Valuation</span>
                  <p className="k-small k-muted">{r.valuation_note}</p>
                </div>}
              </div>}
              {(r.bull.length > 0 || r.bear.length > 0) && <div className="inv-two">
                {r.bull.length > 0 && <div className="k-stack"><b className="k-sub">Strengths</b><ul className="k-list">{r.bull.map((b) => <li key={b}>{b}</li>)}</ul></div>}
                {r.bear.length > 0 && <div className="k-stack"><b className="k-sub">Risks</b><ul className="k-list">{r.bear.map((b) => <li key={b}>{b}</li>)}</ul></div>}
              </div>}
              {(r.position || r.watch.length > 0) && (
                <div className="inv-two">
                  {r.position && <div className="k-stack"><b className="k-sub">Where it sits</b><p className="k-small">{r.position}</p></div>}
                  {r.watch.length > 0 && <div className="k-stack"><b className="k-sub">What to watch</b><ul className="k-list">{r.watch.map((w) => <li key={w}>{w}</li>)}</ul></div>}
                </div>
              )}
              {r.ideas.length > 0 && (
                <div className="k-inset">
                  <div className="k-stack">
                    <b className="k-sub">Rule templates to test on {symbol}</b>
                    <span className="k-small k-muted">Each is a test setup, not a suggestion. Pick one and StratLab shows how it would have done on years of real prices, after costs.</span>
                  </div>
                  <div className="inv-ideas">
                    {r.ideas.map((i) => (
                      <div key={i.text} className="inv-idea">
                        <b>{i.title}</b>
                        <span className="k-small">"{i.text}"</span>
                        {i.why && <span className="k-note">{i.why}</span>}
                        <button className="btn sm" onClick={() => onTest(i)}>Test this idea →</button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
      </Card>
    </div>
  );
}

export function SourcesNote({ sources }: { sources: Company["sources"] }) {
  const bad = sources.filter((s) => !s.ok);
  if (!bad.length) return null;
  return <Notice tone="warn" role="status">Some data is missing: {bad.map((s) => `${s.source} (${s.error})`).join(" · ")}</Notice>;
}
