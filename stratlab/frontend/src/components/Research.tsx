import { DENSE_BARS, compactValue, labelledBar, shortYear } from "../lib/phoneFit";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { marketState } from "../lib/marketHours";
import { liveQuote, useLiveRefresh } from "../lib/liveRefresh";
import { aiLimited, aiReason } from "../lib/aiReason";
import { stageMeaning } from "../lib/stageNote";
import { fmtDate, marketTz, monthLong, num, pct, price, safeHref, signCls, signedMove } from "../lib/format";
import {
  SETTLING, bandPosition, metricText, holderRowName, missingLine, monthsOld, newsWhen, ordinal, plausibleRange, priceLabel, researchApi, staleQuarter, trendShort, trendValue, useWatchlist, watchNote,
  type Company, type CompanyAI, type Idea, type MetricGroup, type MetricItem, type NewsItem, type Quote, type Region, type SeriesPoint,
} from "../lib/research";
import { companyLoader, PriceChart as PriceChartView } from "../charts/price/lazy";
import { surpriseShown } from "../lib/surprise";
import { tinyBase } from "../lib/researchFormat";
import { Star } from "./Icons";
import { Info } from "./ui";
import { Card, CardHead, DataTable, Delta, Disclosure, Meter, Notice, Seg, Signed, Skeleton, type Column } from "./kit";
import { SurvBadges } from "./Surveillance";
import { AiAd } from "./AiAd";
import { StoredNote, StoredStamp, useStoredRefresh } from "./StoredStamp";
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
          const want = !on;                // what the button said: Watch adds, Watching removes, whatever the list holds
          const changed = await toggle({ region, symbol, name: name ?? null }, want);
          if (want && changed) track("watchlist add", { region });
          notify(watchNote(symbol, want, changed));
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
export function Change({ q, currency, closed: shut = false, preOpen = false, settling = false, quoteDay, today }: {
  q: Quote | null; currency: string; closed?: boolean; preOpen?: boolean; settling?: boolean;
  /** the price's trading day (null: its time is unknown) and the market's today: "today" is said only of today's price */
  quoteDay?: string | null; today?: string;
}) {
  if (!q || q.price == null) return null;
  // before India's 09:15 open the price is the pre-open auction's: indicative, never a close (R7T-004); between the US
  // close and its settle point it is the day's last prints, not yet the close (R13-005)
  const closed = shut && !preOpen && !settling;
  const { label, since } = priceLabel({ market_open: !shut, phase: preOpen ? "pre_open" : settling ? "settling" : null, quote_day: quoteDay },
    today, (d) => fmtDate(d, { year: false }));
  return (
    <div className="k-stat inv-quote" data-testid="company-price" data-phase={preOpen ? "pre_open" : settling ? "settling" : undefined}>
      {preOpen && <span className="k-stat-k">Pre-open (indicative)</span>}
      {settling && <span className="k-stat-k">{SETTLING}</span>}
      {closed && <span className="k-stat-k">Last close</span>}
      {/* while the market trades: an earlier session's price says so, and one with no time says that (review 5c) */}
      {!closed && !preOpen && !settling && label && <span className="k-stat-k" data-testid="price-when">{label}</span>}
      <span className="k-stat-v">{price(q.price, currency)}</span>
      {q.change_pct != null && (
        <span className="k-stat-d">
          <Delta value={q.change_pct}>{q.change != null ? `${signedMove(q.change, 2)} (${pct(q.change_pct, 2)})` : pct(q.change_pct, 2)}</Delta> <span className="nowrap">{closed && (q.change_day || quoteDay) ? `on ${fmtDate((q.change_day || quoteDay)!, { year: false })}` : since}</span>{/* "on 16 Oct" never splits (R53-008); a US quote has no change_day, so its own session's day (R90-008: AAPL "on the day" beside RELIANCE "on 23 Oct") */}
        </span>
      )}
      {/* the close the move is from, while it trades and after its close too (R71-006: "$216.31 ▲ +2.18 (+1.02%) today"
          with no previous close; R89-005: none after the close either, so the base couldn't be checked) */}
      {/* a new listing's first session is against its issue price, said so (DD-010) */}
      {!preOpen && q.change != null && <span className="k-note" data-testid="price-prev">{q.ref === "issue" ? "Issue price" : "Previous close"} {price(q.price - q.change, currency)}{q.ref === "issue" ? " (first day of trading)" : ""}</span>}
    </div>
  );
}

/* ---------- price chart ---------- */
/** The company's candles in the shared price chart (its code loads only on pages that show one). */
export function PriceChart({ region, symbol, currency, price: shown, asOf: shownAt, compareWith }: { region: Region; symbol: string; currency: string; price?: number | null; asOf?: string | null;
  /** Drawn against this company on a % scale from the start (the Compare page, DD-060). */ compareWith?: string }) {
  // the header's price and the title's are this page's one reading; the newest candle is it too (see settleLast)
  const load = useMemo(() => companyLoader(region, symbol, { price: shown, asOf: shownAt, tz: marketTz(region) }), [region, symbol, shown, shownAt]);
  const compare = useCallback((other: string) => companyLoader(region, other)("1d", { range: "max" }).then((r) => r.candles), [region]);
  // LIVE3-011: the chart is told whether its market trades now (from the market's hours, checked each minute), so it never says "Live"
  // after the close
  const { markets } = useApp();
  const [tick, setTick] = useState(0);
  useEffect(() => { const t = setInterval(() => setTick((n) => n + 1), 60_000); return () => clearInterval(t); }, []);
  const market = markets.find((m) => m.id === region);
  const open = useMemo(() => (market ? marketState(market).open : null), [market, tick]);
  return (
    <PriceChartView symbol={symbol} storageKey={`${region}:${symbol}`} currency={currency} load={load} marketOpen={open} market={region}
      timeframes={["5m", "15m", "1h", "1d", "1w", "1mo"]} compareLoad={compare} compareHint={region === "IN" ? "e.g. TCS" : "e.g. MSFT"} compareWith={compareWith}
      note="Prices adjusted for splits and bonus issues, not for regular dividends. Intraday candles cover recent weeks." />
  );
}

/* ---------- 52-week rail ---------- */
export function Rail52({ q, low, high, currency, compact, since, tradedFrom }: { q: Quote | null; low: number | null; high: number | null; currency: string; compact?: boolean;
  /** a share listed within the year: its first day of trading, and the range is since then, not 52 weeks (DD-011) */ since?: string | null;
  /** an older share whose prices on record begin within the year (relisted, or long without trades): the range is since then (SECMEM 6) */
  tradedFrom?: string | null }) {
  const px = q?.price;
  const from = since ?? tradedFrom ?? null;
  const span = since ? "range since listing" : tradedFrom ? "range since its first price on record" : "52-week range";
  // a range that can't be this share's (another class's, another listing's) is never drawn under its price (R7T-001)
  if (px == null || low == null || high == null || high <= low || !plausibleRange(px, low, high)) return null;
  const at = (v: number) => Math.max(0, Math.min(100, ((v - low) / (high - low)) * 100));
  const p = at(px);
  const band = q?.low != null && q?.high != null && q.high > q.low ? [at(q.low), at(q.high)] : null;
  // in a company's header: the rail and its two ends, under the price (the percentile is in the rail's label)
  if (compact) return (
    <div className="inv-rail52" title={`${ordinal(Math.round(p))} percentile of its ${span}${band ? "; the shaded band is today's range" : ""}`}>
      <svg className="inv-rail" viewBox="0 0 100 10" preserveAspectRatio="none" role="img" aria-label={`${since ? "Range since listing" : tradedFrom ? "Range since its first price on record" : "52-week range"} ${price(low, currency)} to ${price(high, currency)}; today's price sits at the ${ordinal(Math.round(p))} percentile`}>
        <rect className="track" x="0" y="3" width="100" height="4" rx="2" />
        {band && <rect className="band" x={band[0]} y="1" width={Math.max(band[1] - band[0], 0.8)} height="8" />}
        <rect className="mark" x={Math.min(98.8, Math.max(0, p - 0.6))} y="0" width="1.2" height="10" />
      </svg>
      <div className="k-spread k-note"><span>{since ? `Since listing (${fmtDate(since, { year: false })}): low` : from ? `Prices on record from ${fmtDate(from, { year: false })}: low` : "52-wk low"} {price(low, currency)}</span><span>high {price(high, currency)}</span></div>
    </div>
  );
  return (
    <div className="k-stack">
      <svg className="inv-rail" viewBox="0 0 100 10" preserveAspectRatio="none" role="img" aria-label={`Today's price sits at ${ordinal(Math.round(p))} percentile of its ${span}`}>
        <rect className="track" x="0" y="3" width="100" height="4" rx="2" />
        {band && <rect className="band" x={band[0]} y="1" width={Math.max(band[1] - band[0], 0.8)} height="8" />}
        <rect className="mark" x={Math.min(98.8, Math.max(0, p - 0.6))} y="0" width="1.2" height="10" />
      </svg>
      <div className="k-spread k-small">
        <span className="k-muted">Low <b className="inv-ink">{price(low, currency)}</b></span>
        <span className="k-muted">High <b className="inv-ink">{price(high, currency)}</b></span>
      </div>
      <p className="k-small">Trading in the <b>{ordinal(Math.round(p))} percentile</b> of its {span}{band ? ". The shaded band is today's range." : "."}</p>
    </div>
  );
}

/* ---------- where a unit of revenue goes ---------- */
export function MarginCascade({ gross, operating, net }: { gross: number | null; operating: number | null; net: number | null }) {
  if (gross == null || operating == null || net == null || gross <= 0) return null;
  const steps = [{ k: "Revenue", v: 100, lost: "" }, { k: "Gross profit", v: gross, lost: "cost of goods" },
    { k: "Operating profit", v: operating, lost: "running costs, R&D" }, { k: "Net profit", v: net, lost: "tax, interest, other" }];
  const rows = steps.map((s, i) => ({ ...s, drop: i ? steps[i - 1].v - s.v : 0 }));
  // a table (UI-CO: tables wherever there are figures): the step, what is left of every 100 in sales (with its bar), and what was lost to get there
  return (
    <div className="k-stack">
      <div className="dd-fit"><DataTable label="Where a sale goes" rows={rows} rowKey={(r) => r.k} stack={false}
        columns={[{ key: "s", header: "Step", rowHeader: true, cell: (r) => r.k },
          { key: "v", header: "Left of 100 in sales", numeric: true, cell: (r) => <span className="dd-share"><span>{r.v.toFixed(1)}%</span><Meter pct={Math.max(0, Math.min(100, r.v))} /></span> },
          { key: "l", header: "Lost on the way", numeric: true, cell: (r) => (r.drop > 0 ? `−${r.drop.toFixed(1)} to ${r.lost}` : "–") }]} /></div>
      <p className="k-note">Of every 100 in sales, what is left at each step.</p>
    </div>
  );
}

/* ---------- metrics with context rails ---------- */
/** The short names in Key numbers, in plain words, for anyone who doesn't read balance sheets for a living. */
const TERMS: Record<string, string> = {
  "P/E": "Price to earnings: the share price divided by earnings per share over the last four reported quarters. A loss has no P/E.",
  "P/B": "Price to book: the share price divided by the company's net assets per share.",
  "Div yield": "Every dividend with an ex-date in the last 12 months, special dividends included, as a share of the price.",
  "Book value": "The company's net assets (what it owns minus what it owes) per share.",
  "Face value": "The nominal value printed on each share; it doesn't change with the price.",
  "ROCE": "Return on capital employed: operating profit as a share of all the money in the business, borrowed or not.",
  "ROE": "Return on equity: profit as a share of the shareholders' money in the business.",
  "EBITDA margin": "Operating profit before depreciation, interest and tax (EBITDA) as a share of sales: what is left after running costs.",
  "Net margin": "Profit after everything, as a share of sales.",
  "Debt / equity": "Borrowings divided by the shareholders' money in the business.",
  "Total debt / equity": "All borrowings, short and long term, divided by the shareholders' money in the business.",
  "Long-term debt / equity": "Borrowings due after more than a year, divided by the shareholders' money in the business, from the latest quarter's balance sheet. A yearly debt to equity from the annual report can differ: it is of another date, and can count debt and equity differently.",
  "Latest YoY": "The latest reported quarter against the same quarter a year before; without quarterly results, the latest year against the year before. The note under it names the two periods.",
  "3Y CAGR": "Compound annual growth rate: the steady yearly growth that gets from the start to the end of the period.",
};

/** A note longer than this under a figure is a footnote under the grid ("Jun 2025 had other income of Rs 15,119 crore against a median of Rs 4,464 crore...": five
 * lines beside a -24.6%, so its row was four times as tall as its neighbours, LIVE1A-062). A short one stays under its label. */
const LONG_NOTE = 90;

/** A figure of a range in the measure's own unit, short: "12", "0.5", "25%" (no ".0"). */
function rangeFig(v: number, unit: string | null | undefined): string {
  const n = Math.abs(v) >= 10 ? Math.round(v).toString() : (Math.round(v * 10) / 10).toString();
  return `${n.replace("-", "−")}${unit === "%" || unit === "%±" ? "%" : ""}`;
}

/** The range bar beside a figure (owner, 5 Nov: "the ranges we have, where is the context of it? it's just a bar"): a scale for the measure
 *  with the usual span for large listed companies shaded on it (StratLab's rule of thumb, adjusted for the company's industry where that
 *  differs) and this company's figure as the dark mark; the usual span's two figures under it, and all of it said in the tooltip. */
function RangeBar({ b, m, currency, industry }: { b: NonNullable<ReturnType<typeof bandPosition>>; m: MetricItem; currency: string; industry?: string | null }) {
  const usual = `${rangeFig(b.from, m.unit)}–${rangeFig(b.to, m.unit)}`;
  const says = `${m.label} ${metricText(m, currency)}. Usual for large listed companies${b.scaled && industry ? ` in ${industry.toLowerCase()}` : ""}: ${rangeFig(b.from, m.unit)} to ${rangeFig(b.to, m.unit)} (the shaded part). The bar runs from ${rangeFig(b.min, m.unit)} to ${rangeFig(b.max, m.unit)}; the dark mark is this company.`;
  return (
    <span className="inv-krange" title={says}>
      <svg className="inv-krail" viewBox="0 0 100 10" preserveAspectRatio="none" role="img" aria-label={says}>
        <rect className="track" x="0" y="3" width="100" height="4" rx="2" />
        <rect className="band" x={Math.min(99, b.weak)} y="3" width={Math.max(1, Math.min(100 - Math.min(99, b.weak), b.strong - b.weak))} height="4" />
        <rect className="mark" x={Math.min(97.6, Math.max(0, b.pos - 1.2))} y="0" width="2.4" height="10" />
      </svg>
      <span className="inv-krange-txt" aria-hidden="true">{usual}</span>
    </span>
  );
}

/** "banks" for a bank's page: the industry as the note names it. */
const industryWord = (industry?: string | null): string => (/\bbank/i.test(industry ?? "") ? "banks" : (industry ?? "this industry").toLowerCase());

/** Key numbers: each group is a small table (the group's name | Value | Basis | Range bar), the tables in two columns of one width (CSS columns balance them, in reading order on a phone). A long note is a numbered note under the tables, its mark beside the value (UI-CO item 2). */
export function MetricsGrid({ groups, currency, industry }: { groups: MetricGroup[]; currency: string; industry?: string | null }) {
  const used = Object.entries(TERMS).filter(([k]) => groups.some((g) => g.items.some((m) => m.label === k)));
  const foot: { n: number; label: string; text: string }[] = [];
  for (const g of groups) for (const m of g.items) if (m.note && m.note.length > LONG_NOTE) foot.push({ n: foot.length + 1, label: m.label, text: m.note });
  const mark = (m: { label: string; note?: string | null }) => foot.find((f) => f.label === m.label && f.text === m.note);
  const anyBar = groups.some((g) => g.items.some((m) => bandPosition(m.label, m.value, industry)));
  // LIVE4-013: the note says which spans are this industry's, or that they are the same for all (a bank and a defence maker had identical
  // bands under "adjusted for the company's industry")
  const scaledAny = groups.flatMap((g) => g.items.filter((m) => bandPosition(m.label, m.value, industry)?.scaled).map((m) => m.label)).join(", ");
  return (
    <>
      <div className="inv-metrics">
        {groups.map((g) => (
              <div key={g.title} className="inv-mt">
                <DataTable label={`Key numbers: ${g.title}`} rows={g.items} rowKey={(m) => m.label} stack={false}
                  columns={[
                    { key: "m", header: g.title, rowHeader: true, cell: (m) => <span className="k-small">{m.label}</span> },
                    { key: "v", header: "Value", numeric: true, cell: (m) => <b className={`inv-metric-v ${m.unit === "%±" ? signCls(m.value) : ""}`}>{metricText(m, currency)}{mark(m) && <sup className="cmp-foot-mark" aria-label={`see note ${mark(m)!.n}`}>{mark(m)!.n}</sup>}</b> },
                    { key: "b", header: "Basis", cell: (m) => <span className="k-note">{m.note && !mark(m) ? m.note : ""}</span> },
                    { key: "r", header: anyBar ? "Usual range" : "", cardLabel: "Usual range", cell: (m) => { const b = bandPosition(m.label, m.value, industry); return b ? <RangeBar b={b} m={m} currency={currency} industry={industry} /> : null; } },
                  ]} />
              </div>
        ))}
      </div>
      {anyBar && <p className="k-note inv-krail-key" data-testid="krail-legend"><span className="inv-krail-demo" aria-hidden="true"><span /><b /></span>Usual range: the shaded part of each bar is the usual span of that measure for large listed companies (StratLab's rule of thumb, not this company's own history){scaledAny ? `; for ${industryWord(industry)} a few measures use that industry's span instead (${scaledAny}), the others the general one` : "; it is the same span for every industry"}. The dark mark is this company. The figures under a bar are the shaded part's ends; hover a bar for its whole scale.</p>}
      {foot.length > 0 && <ul className="k-note cmp-foots" data-testid="metric-notes">{foot.map((f) => <li key={f.n}><sup>{f.n}</sup> {f.label}: {f.text}</li>)}</ul>}
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
export function TrendBars({ points, label, unit, tone = "ink", baseSales }: { points: SeriesPoint[]; label: string; unit: string; tone?: "ink" | "blue";
  /** profit bars: the sales of their first year, in the same unit, for the tiny-base rule (DD-018) */ baseSales?: number | null }) {
  if (points.length < 2) return null;
  const up = Math.max(0, ...points.map((p) => p.v));
  const down = Math.max(0, ...points.map((p) => -p.v));
  const span = up + down || 1;
  const PLOT = 112;                                    // the plot's height in its own units
  const zero = (up / span) * PLOT;                     // from the top
  const first = points[0].v, last = points[points.length - 1].v;
  const lossYears = points.some((p) => p.v <= 0);
  const small = !lossYears && tinyBase(first, last, points.length - 1, baseSales);          // a rate off a tiny base is n/m (DD-018)
  const growth = !lossYears && first > 0 && !small ? (Math.pow(last / first, 1 / (points.length - 1)) - 1) * 100 : null;
  // a figure too long for its bar ("10,55,780" over ten bars at half the page) is written in short for every bar of the
  // chart ("10.56L"), never cut with an ellipsis ("10,55,7…"); the whole figure is in the bar's tooltip and the table
  // (DD-020, DD-054)
  const tight = points.some((p) => trendValue(p.v, unit).length > (points.length >= DENSE_BARS ? 6 : 7));
  const shown = (v: number) => (tight ? compactValue(v, unit) ?? trendShort(v, unit) : null) ?? trendValue(v, unit);
  return (
    <div className="k-stack">
      <div className="k-spread">
        <b className="k-small">{label} <span className="k-muted inv-plain">({unit})</span></b>
        {growth != null ? <span className="k-small k-muted"><Signed value={growth}>{pct(growth)}</Signed> a year</span>
          : lossYears ? <span className="k-small k-muted">loss years in between, so no yearly rate</span>
          : small ? <span className="k-small k-muted" data-testid="tiny-base">n/m: from a small base</span> : null}
      </div>
      <div className={`tbars${points.length >= DENSE_BARS ? " dense" : ""}`}>
        {points.map((p, i) => {
          const compact = points.length >= DENSE_BARS ? compactValue(p.v, unit) : null;
          const h = Math.max(2, (Math.abs(p.v) / span) * PLOT);
          const neg = p.v < 0;
          const cls = `tbar-bar${neg ? " neg" : i === points.length - 1 ? ` last ${tone}` : ""}`;
          return (
            <div key={p.y} className={`tbar${labelledBar(i, points.length) ? "" : " alt"}`} title={`${p.y}: ${p.v.toLocaleString(/cr/i.test(unit) ? "en-IN" : "en-US", { maximumFractionDigits: 2 })} ${unit}`}>
              <span className={`tbar-num${neg ? " neg" : ""}`}><span className="tbar-full">{shown(p.v)}</span>{(compact ?? trendShort(p.v, unit)) && <span className="tbar-short">{compact ?? trendShort(p.v, unit)}</span>}</span>
              <svg className="tbar-plot" viewBox={`0 0 10 ${PLOT}`} preserveAspectRatio="none" aria-hidden="true">
                {down > 0 && <line className="tbar-zero" x1="0" x2="10" y1={zero} y2={zero} vectorEffect="non-scaling-stroke" />}
                <rect className={cls} data-v={p.v} x="1.5" width="7" y={neg ? zero : zero - h} height={h} />
              </svg>
              <span className={`tbar-year${p.y.length > 4 && points.length >= 6 ? " long" : ""}`}><span className="tbar-full">{p.y}</span><span className="tbar-short">{shortYear(p.y)}</span></span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function EarningsBars({ rows: raw, basis }: { rows: Company["earnings"]; basis?: Company["earnings_basis"] }) {
  if (raw.length < 2) return null;
  // the percentage comes from the figures as printed, so they agree with it (R31-014)
  const rows = raw.map((r) => ({ ...r, surprise_pct: r.surprise_pct == null ? null : surpriseShown(r.actual, r.estimate) }));
  // against an estimate of 0 there is no surprise percentage: no bar, and a beat is the actual at or above it
  const max = Math.max(4, ...rows.map((r) => Math.abs(r.surprise_pct ?? 0)));
  const beat = (r: Company["earnings"][number]) => (r.surprise_pct != null ? r.surprise_pct >= 0 : r.actual >= r.estimate);
  const beats = rows.filter(beat).length;
  const gaap = basis === "adjusted" && rows.some((r) => r.gaap != null);
  type Row = (typeof rows)[number];
  // owner, 5 Nov ("what is this UI"): a compact table, a row a quarter, with a small bar in the surprise cell (green right of the zero line for
  // a beat, red left of it for a miss), where a tall bar chart left a hole under it beside the insider trades
  const columns: Column<Row>[] = [
    { key: "q", header: "Quarter", rowHeader: true, cell: (r) => <>{monthLong(r.period)}{r.fiscal && <span className="k-sub-line" data-testid="fiscal-quarter">{r.fiscal}</span>}</> },
    { key: "a", header: "EPS", numeric: true, cell: (r) => num(r.actual, 2) },
    { key: "e", header: "Estimate", numeric: true, cell: (r) => num(r.estimate, 2) },
    { key: "s", header: "Against the estimate", numeric: true, cell: (r) => {
      const up = beat(r), w = r.surprise_pct == null ? 0 : Math.max(3, (Math.abs(r.surprise_pct) / max) * 50);
      return (
        <span className="eps-surp">
          <span className="eps-track" aria-hidden="true"><span className="eps-zero" />{r.surprise_pct != null && <span className={`eps-bar ${up ? "beat" : "neg"}`} data-v={r.surprise_pct} style={up ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }} />}</span>
          {r.surprise_pct == null ? <span className="k-muted">–</span> : <Signed value={r.surprise_pct}>{pct(r.surprise_pct)}</Signed>}
        </span>);
    } },
    ...(gaap ? [{ key: "g", header: "GAAP EPS", numeric: true, cell: (r: Row) => (r.gaap != null ? num(r.gaap, 2) : "–") }] : []),
  ];
  return (
    <div className="k-stack">
      <DataTable label="Results versus expectations" rows={rows} rowKey={(r) => r.period} columns={columns} />
      <p className="k-note">{beats} of {rows.length} quarters beat analysts' earnings-per-share estimate.{" "}
        {/* what the EPS counts, so an adjusted figure is never read as the filed one (DD-031) */}
        {basis === "adjusted" ? "EPS as the estimates count it: adjusted (non-GAAP); the GAAP diluted EPS from the company's filings is in its own column."
          : basis === "gaap" ? "EPS is the GAAP diluted figure from the company's filings, quarters dated by their filing." : ""}</p>
    </div>
  );
}

/** What the AI read says, as one table (UI-CO item 3): the area on the left, its figures on the right: the worked-out numbers by area, the valuation
 * line, the notable figures, where the company sits and what to watch. No bars, grades or colours: the numbers are the whole story. */
type ReadRow = { id: string; area: string; body: ReactNode };
function ReadTable({ r }: { r: CompanyAI }) {
  const rows: ReadRow[] = [
    ...(r.valuation_note ? [{ id: "valuation", area: "Valuation", body: <span className="k-small">{r.valuation_note}</span> }] : []),
    // facts only: one list of figures that stand out, not "strengths" and "risks" (round 39)
    ...(r.bull.length > 0 || r.bear.length > 0 ? [{ id: "notable", area: "Notable figures", body: <ul className="k-list" data-testid="notable-figures">{[...r.bull, ...r.bear].map((b) => <li key={b}>{b}</li>)}</ul> }] : []),
    ...(r.position ? [{ id: "position", area: "Where it sits", body: <span className="k-small">{r.position}</span> }] : []),
    ...(r.watch.length > 0 ? [{ id: "watch", area: "What to watch", body: <ul className="k-list">{r.watch.map((w) => <li key={w}>{w}</li>)}</ul> }] : []),
  ];
  // TABLE-SWEEP (owner, 29 Oct): the worked-out figures are rows of their own table (area, figure, value), not a label/value list
  // inside a cell of the table below (on a phone that was a list in a card)
  const figs = (r.facts ?? []).flatMap((f) => f.items.map((i, n) => ({ id: `${f.id}-${n}`, area: f.label, label: i.label, text: i.text })));
  if (!rows.length && !figs.length) return null;
  return (
    <>
      {figs.length > 0 && <DataTable label="The AI read's figures" rows={figs} rowKey={(x) => x.id}
        columns={[{ key: "a", header: "Area", rowHeader: true, cell: (x) => x.area },
          { key: "k", header: "Figure", wrap: true, cell: (x) => x.label },
          { key: "v", header: "Value", wrap: true, cell: (x) => <>{x.text}{stageMeaning(x.text) && <Info label={`About ${x.text}`}>{stageMeaning(x.text)}</Info>}</> }]} />}
      {rows.length > 0 && <div className="ai-table">
        <DataTable label="The AI read, by area" rows={rows} rowKey={(x) => x.id} stack={false}
          columns={[{ key: "a", header: "The numbers", rowHeader: true, cell: (x) => <b className="k-small">{x.area}</b> },
            { key: "f", header: "The figures", cell: (x) => x.body }]} />
      </div>}
    </>
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
        return (
          <a key={i} className="inv-news-row" href={safeHref(n.url)} target="_blank" rel="noopener noreferrer">
            <span>{n.headline}</span>
            <span className="k-note">{[n.source, newsWhen(n.at), n.similar ? `${n.similar} similar ${n.similar === 1 ? "story" : "stories"}` : null].filter(Boolean).join(" · ")} ↗</span>
          </a>
        );
      })}
    </div>
  );
}

/** Companies as small tiles that open them: the symbol, its name, the price and the day's change (a neutral pill). */
/** The Invest home's watchlist as a table (LIVE3-015: tiles two across left an empty cell beside an odd one, and "Tables
 * everywhere"): the stock with its name and any exchange or F&O note under it, its price and the day's change; each opens the
 * company (its F&O lot changes are on the watchlist page). The prices are asked again each minute while they are live, each row kept until its new price comes (LIVE-1). */
export function WatchTable({ region, symbols, names, label = "Your watchlist" }: { region: Region; symbols: string[]; names?: Record<string, string | null>; label?: string }) {
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
  useLiveRefresh(!!q && Object.values(q).some((x) => liveQuote(x?.at)), () => {
    researchApi.quotes(region, symbols).then((r) => setQ((cur) => ({ ...cur, ...Object.fromEntries(Object.entries(r).filter(([, x]) => x?.price != null)) }))).catch(() => undefined);
  });
  const ccy = region === "IN" ? "INR" : "USD";
  return (
    <div className="watch-table">
      {/* on a phone a card a row (the app's phone pattern): beside a stock's name and its surveillance note the Change column ran off
          a 390px screen */}
      <DataTable csv={`watchlist ${label}`} label={label} rows={symbols} rowKey={(s) => s} stack
        columns={[
          { key: "s", header: "Stock", rowHeader: true, wrap: true, cell: (s) => (
            <>
              <Link className="link" to={`/research/${region}/${encodeURIComponent(s)}`}><b>{s}</b></Link>
              {names?.[s] && <span className="k-sub-line">{names[s]}</span>}
              {/* the exchange's surveillance note only: an F&O lot change is the watchlist page's and the company's (LIVE2-015: derivatives
                  jargon on the home's summary, and a two-line pill that pushed the Change column off a phone) */}
              <span className="watch-notes"><SurvBadges region={region} symbol={s} /></span>
            </>) },
          { key: "p", header: "Price", numeric: true, cell: (s) => (q == null ? <span className="skel" /> : q[s]?.price != null ? price(q[s]!.price!, ccy) : "–") },
          { key: "d", header: "Change", numeric: true, cell: (s) => (q?.[s]?.change_pct != null ? <Delta value={q[s]!.change_pct}>{pct(q[s]!.change_pct!, 2)}</Delta> : q == null ? "" : "–") },
        ]} />
    </div>
  );
}

/** Companies as a table (UI-CO): the name with its symbol, the price and the day's change; each name opens the company. */
export function QuoteTable({ region, symbols, label }: { region: Region; symbols: string[]; label: string }) {
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
  const ccy = region === "IN" ? "INR" : "USD";
  return (
    <div className="dd-fit"><DataTable csv={`watchlist ${label}`} label={label} rows={symbols} rowKey={(s) => s} stack={false}
      columns={[{ key: "c", header: "Company", rowHeader: true, cell: (s) => <Link className="link" to={`/research/${region}/${encodeURIComponent(s)}`}><b>{s}</b></Link> },
        { key: "p", header: "Price", numeric: true, cell: (s) => (q == null ? <span className="skel" /> : q[s]?.price != null ? price(q[s]!.price!, ccy) : "–") },
        { key: "d", header: "Change", numeric: true, cell: (s) => (q?.[s]?.change_pct != null ? <Delta value={q[s]!.change_pct}>{pct(q[s]!.change_pct!, 2)}</Delta> : "–") }]} /></div>
  );
}

/** " (16 months old)" when a newer quarter's shareholding should have been filed by now (within 21 days of its end). */
function holdersAge(asOf: string): string {
  const n = staleQuarter(asOf, 21);
  return n != null ? ` (${monthsOld(n)})` : "";
}

export function Shareholding({ s }: { s: NonNullable<Company["shareholding"]> }) {
  // a table: who, their share (with its bar) and the change over the last year, in percentage points
  return (
    <div className="k-stack">
      <div className="dd-fit"><DataTable label="Who owns it" rows={s.rows} rowKey={(r) => r.label} stack={false}
        columns={[{ key: "h", header: "Holder", rowHeader: true, cell: (r) => holderRowName(r.label) },
          { key: "v", header: "Share", numeric: true, cell: (r) => <span className="dd-share"><span>{r.value.toFixed(1)}%</span><Meter pct={Math.min(100, r.value)} /></span> },
          { key: "c", header: "Change in a year", numeric: true, cell: (r) => (r.change != null && Math.abs(r.change) >= 0.05 ? <Signed value={r.change}>{r.change > 0 ? "+" : "−"}{Math.abs(r.change).toFixed(1)} pts</Signed> : "–") }]} /></div>
      <p className="k-note">{`As of ${s.as_of}${holdersAge(s.as_of)}. The change is over the last year, in percentage points.${s.note ? ` ${s.note}` : ""}`}</p>
    </div>
  );
}

export function QuarterTable({ q, bank = false }: { q: NonNullable<Company["quarters"]>; bank?: boolean }) {
  const f = (v: number | null) => (v == null ? "–" : num(Math.round(v), 0));
  const rows = [
    { name: "Sales", cells: q.sales.map(f) }, { name: "Net profit", cells: q.profit.map(f) },
    // a bank reports a financing margin there, not an EBITDA margin (R7O-001)
    { name: bank ? "Financing margin" : "EBITDA margin", cells: q.opm.map((v) => (v == null ? "–" : `${v}%`)) },
  ].filter((r) => !(r.name === "Financing margin" && r.cells.every((c) => c === "–")));   // a bank's margin the source gets wrong is left out, not shown as dashes (R10O-011)
  return (
    <DataTable scrollEnd label="The last quarters, in ₹ cr" rows={rows} rowKey={(r) => r.name}
      columns={[{ key: "m", header: "₹ cr", rowHeader: true, cell: (r) => r.name },
        ...q.cols.map((c, i) => ({ key: c, header: c, numeric: true, cell: (r: (typeof rows)[number]) => r.cells[i] }))]} />
  );
}

/* ---------- AI read ---------- */
export { aiLimited, aiReason } from "../lib/aiReason";

export function AIRead({ region, symbol, onTest }: { region: Region; symbol: string; onTest: (idea: Idea) => void }) {
  const [r, setR] = useState<CompanyAI | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const shown = useRef(`${region}:${symbol}`);
  const rf = useStoredRefresh();
  // Refresh: the read written again for everyone (or "already fresh" / none left today, said under the head), the read shown kept if it fails
  const refresh = () => {
    const at = `${region}:${symbol}`;
    const alive = () => shown.current === at;
    rf.run(async () => { const got = await researchApi.companyAI(region, symbol, true, alive); if (alive()) { setR(got); setError(null); } return got; });
  };
  const load = async (refresh = false) => {
    const at = `${region}:${symbol}`;
    const alive = () => shown.current === at;
    setBusy(true); setError(null);
    try { const got = await researchApi.companyAI(region, symbol, refresh, alive); if (alive()) setR(got); }
    catch (e) { if (alive()) setError((e as Error).message); }
    finally { if (alive()) setBusy(false); }
  };
  useEffect(() => {
    shown.current = `${region}:${symbol}`;
    setR(null); load();
    return () => { shown.current = ""; };         // left the page: its read stops being asked for
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [region, symbol]);
  return (
    <div className="ai-read">
      <Card label="AI read">
        <CardHead title="AI read" info={"A written read from the live numbers on this page, with no scores or ratings. \"The numbers\" are worked out from the reported results and daily prices, not by the AI. Segment shares are estimates. A starting point for ideas, not advice."}
          actions={error || !r ? undefined : <StoredStamp at={r.generated_at} tz={marketTz(region)} busy={busy || rf.busy} onRefresh={refresh} />} />
        {r && !error && <StoredNote busy={rf.busy} state={rf.state} at={r.generated_at} tz={marketTz(region)} />}
        {/* a missing AI read is not a fault with the company's numbers: one calm line and one way to ask again */}
        {error ? (
          <div className="k-row ai-read-off" role="status">
            <span className="k-small k-muted">No AI read right now{aiReason(error)} The numbers on this page don't depend on it.</span>
            {/* asking again can't help when the day's cap is the reason (R8O-002) */}
            {!aiLimited(error) && <button type="button" className="btn quiet sm" disabled={busy} onClick={() => load(true)}>{busy ? "Asking…" : "Ask again"}</button>}
          </div>
        )
          : !r ? <Skeleton label="Reading the numbers" lines={3} /> : (
            <>
              {r.summary && <p className="inv-summary">{r.summary}</p>}
              <ReadTable r={r} />
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
      {/* ADS-1: under a written read only (not while it loads or when there is none), and for Free accounts only: AiAd shows nothing on Basic and Pro */}
      {r && !error && <AiAd seed={symbol} />}
    </div>
  );
}

export function SourcesNote({ sources }: { sources: Company["sources"] }) {
  const bad = sources.filter((s) => !s.ok);
  if (!bad.length) return null;
  return <Notice tone="warn" role="status">{missingLine(sources)}</Notice>;
}
