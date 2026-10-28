import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { writtenAt, asOf, dayIn, fmtDate, marketTz, pct, price, quoteAt, safeHref, signed } from "../lib/format";
import { HELP } from "../lib/help";
import { marketState } from "../lib/marketHours";
import { eyebrowOf } from "../lib/eyebrow";
import {
  REGION_NAME, SETTLING, atPrice, holderRowName, STARTER_TICKERS, THEME_IDEAS, bigMoney, canonTicker, linkLabel, settlingNow, indexWhen, metricText, monthsOld, priceLabel, pulseClosedDay, pulseLede, researchApi, resultsFiled, scaleFor, staleQuarter, trendValue, useRegion, useWatchlist, watchNote, withMore,
  type Company, type CompareAI, type Idea, type IndexLevel, type PulseAI, type PulseData, type Quote, type Region, type SectorAI, type WatchItem,
} from "../lib/research";
import { askAgain, PULSE_PENDING_EVERY_MS, PULSE_SLOW_MS, pulseLoad } from "../lib/pulseLoad";
import { bseTwinMoved, delistedLine, regionOf } from "../lib/researchFormat";
import {
  AIRead, aiLimited, aiReason, Change, EarningsBars, MarginCascade, MetricsGrid, NewsList, PriceChart, QuarterTable, QuoteGrid, Rail52, RegionSwitch,
  Shareholding, SourcesNote, StarButton, TrendBars,
} from "../components/Research";
import { preloadPriceChart } from "../charts/price/lazy";
import { loadSurveillance } from "../lib/surveillance";
import { loadEtfGaps } from "../lib/etfGaps";
import { loadFoChanges } from "../lib/foChanges";
import { AlertButton } from "../components/AlertForm";
import { alertsApi } from "../lib/alerts";
import { Trash } from "../components/Icons";
import { liveQuote, useLiveRefresh } from "../lib/liveRefresh";
import { useShareCompany } from "../components/ShareCompany";
import { MoreMenu } from "../components/MoreMenu";
import { suggestions, type Suggestion } from "../components/CompanyCombobox";
import { rememberName, useDocTitle } from "../lib/title";
import { DealsPanel } from "../components/Deals";
import { BizUpdatesPanel } from "../components/BizUpdates";
import { NamedHoldersPanel } from "../components/NamedHolders";
import { SurvBadges } from "../components/Surveillance";
import { EtfGapBadge, EtfGapDetailView } from "../components/EtfGap";
import { typingFirst } from "../lib/typingFirst";
import { FoBadges } from "../components/FoBadges";
import { IndexBadges } from "../components/IndexBadges";
import { FilingsPanel } from "../components/Filings";
import { UsFilingsCards } from "../components/UsFilings";
import { CompanyActions } from "../components/CorpActions";
import { RouteSeg, WATCH_VIEWS } from "../components/RouteSeg";
import {
  Badge, Card, CardHead, ChartFrame, DataTable, Delta, EmptyState, ErrorState, Field, FormActions, FormGrid, PageHeader, PageNav, Signed, Skeleton, Stat, StatRow, StockPicker,
} from "../components/kit";
import { resultDay, type ResultRow } from "./ResultsPage";
import { pairKey, quotesInBatches } from "../lib/investUi";

export { ResultsPage, resultDay, type ResultRow } from "./ResultsPage";
export { ScanPage, RotationPage, FilingsPage } from "./ResearchScans";

/** Hand a company (and optionally an idea) to the New notebook page. */
function useTestOnStratLab() {
  const nav = useNavigate();
  return (c: { region: Region; symbol: string; instrument_id?: string | null }, idea?: Idea) =>
    nav("/new", { state: { prefill: { market: c.region, symbol: c.symbol, instrumentId: c.instrument_id ?? null, text: idea?.text ?? "" } } });
}

/** The day's index levels: a figure for each, with its change (today's only when it is today's, R7T-003) and where it sits
 * against its 52-week high. */

/** The day a quote's change is of when it isn't today in the market's time zone: the server's `change_day`, else the
 *  quote's own session day. Null for today's. */
function sessionOf(q: { change_day?: string | null; at?: string | null } | null | undefined, tz: string): string | null {
  if (!q) return null;
  if (q.change_day) return q.change_day;
  const d = q.at ? dayIn(q.at, tz) : null, today = dayIn(new Date(), tz);
  return d && today && d < today ? d : null;
}

/** An index level as the exchange states it, to two decimals (22,600.00; 73,123.83): the same figure the mood's text
 * quotes, not a rounded one beside it (DE-017: the cards said 22,600 and 73,124 while the text said 73,123.83). */
export function indexLevel(name: string, price: number): string {
  return price.toLocaleString(name.includes("NIFTY") || name === "SENSEX" ? "en-IN" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function IndexStrip({ indices, missing }: { indices: IndexLevel[] | null; missing?: string[] }) {
  if (!indices) return <Skeleton label="Loading the market" lines={2} />;
  if (!indices.length) return <EmptyState title="Index levels are unavailable right now">They come back on their own; this page checks again when you open it.</EmptyState>;
  return (
    <>
    <StatRow label="Index levels">
      {indices.map((i) => (
        <Stat key={i.name} item label={i.name} value={indexLevel(i.name, i.price)}
          delta={i.change_pct != null ? <Delta value={i.change_pct} tone={i.stale ? "neutral" : "auto"}>{pct(i.change_pct, 2)}</Delta> : undefined}
          note={<span data-testid="index-when" data-stale={i.stale ? "1" : undefined}>{indexWhen(i, (d) => fmtDate(d, { year: false }))}{i.from_high_pct != null && <> · <span className="nowrap">{i.from_high_pct > -0.5 ? "near its 52-week high" : `${Math.abs(i.from_high_pct).toFixed(1)}% below its 52-week high`}</span></>}</span>} />
      ))}
    </StatRow>
    {!!missing?.length && <p className="k-small k-muted" data-testid="index-missing">{missing.join(", ")} couldn't load.</p>}
    </>
  );
}

/** A box that finds a company by name or symbol and opens its page. */
function OpenCompany({ region, label = "Company", autoFocus, query }: { region: Region; label?: string; autoFocus?: boolean; query?: string }) {
  const nav = useNavigate();
  return (
    <Field label={label}>
      {(id) => <StockPicker id={id} market={region} autoFocus={autoFocus} clearOnPick search={query}
        placeholder={region === "IN" ? "Search by name or symbol, like HDFC Bank or TITAN" : "Search by name or ticker, like Nvidia or AAPL"}
        onPick={(s, r) => nav(`/research/${r}/${encodeURIComponent(s)}`)} />}
    </Field>
  );
}

/** The market's index levels and headlines for a region, as the pulse pages load them: asked again while the server's first
 * read is pending, "Still loading…" with Retry after PULSE_SLOW_MS, an error with Try again when the request failed
 * (R24-001: on an iPhone the skeleton stayed for ever). */
function usePulse(region: Region) {
  const [data, setData] = useState<PulseData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
  const [again, setAgain] = useState(0);
  useEffect(() => {
    let live = true, tries = 0;
    let next: ReturnType<typeof setTimeout> | undefined;
    setData(null); setError(null); setSlow(false);
    const late = setTimeout(() => { if (live) setSlow(true); }, PULSE_SLOW_MS);
    const load = () => researchApi.pulse(region).then((d) => {
      if (!live) return;
      if (askAgain(d.pending, tries++)) { next = setTimeout(load, PULSE_PENDING_EVERY_MS); return; }
      if (d.pending) { setSlow(true); return; }
      setData(d);
    }).catch((e) => { if (live) setError((e as Error).message || "The index levels couldn't be read."); });
    load();
    return () => { live = false; clearTimeout(late); if (next) clearTimeout(next); };
  }, [region, again]);
  // the levels again each minute while they're live, in place: a failed read keeps the ones shown
  const reload = () => { researchApi.pulse(region).then((d) => { if (!d.pending && d.indices.length) setData((cur) => (cur ? d : cur)); }).catch(() => undefined); };
  useLiveRefresh(!!data?.indices.some((i) => i.live), reload);
  return { data, error, slow, state: pulseLoad({ data, error, slow }), retry: () => setAgain((n) => n + 1), reload };
}

/** The index levels card's body for each loading state. */
function PulseLevels({ p }: { p: ReturnType<typeof usePulse> }) {
  if (p.state === "error") return <ErrorState title="The index levels couldn't be read" action={{ label: "Try again", onClick: p.retry }}>{p.error}</ErrorState>;
  if (p.state === "slow") {
    return (
      <div className="k-row" role="status" data-testid="pulse-slow">
        <span className="k-small k-muted">Still loading… The index levels are taking longer than usual.</span>
        <button type="button" className="btn quiet sm" onClick={p.retry}>Retry</button>
      </div>
    );
  }
  return <IndexStrip indices={p.data?.indices ?? null} missing={p.data?.missing} />;
}

/* ================= Companies (home) ================= */
/** "Look up a company": finding a company, with the market's levels and headlines beside it. It is not a second home:
 * themes and tools are on the Invest home and in the menu (DD-002). */
export function ResearchHome() {
  const [region, setRegion] = useRegion();
  // ?q= (Ctrl K's "deep dive …" for a name it couldn't place): the box opens with it typed, its matches listed
  const [params] = useSearchParams();
  const q = (params.get("q") ?? "").slice(0, 40);
  const p = usePulse(region);
  const pulse = p.data;
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research")} title="Look up a company"
        lede={<>Search any Indian or US company for its price, valuation, growth, news and an AI read. Your watchlist, results days and red flags are on the <Link to="/invest" className="link">Invest home</Link>.</>} />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      <Card>
        <CardHead title="Find a company" />
        <OpenCompany key={q} region={region} autoFocus={typingFirst()} query={q || undefined} />
        <div className="k-row">
          <span className="k-small k-muted">Try</span>
          {STARTER_TICKERS[region].map((s) => <Link key={s} to={`/research/${region}/${s}`} className="btn quiet sm">{s}</Link>)}
        </div>
      </Card>
      <Card>
        <CardHead title={`${REGION_NAME[region]} today`} info={HELP.researchPulse} actions={<Link to={`/research/pulse?region=${region}`} className="btn quiet sm">Full market pulse →</Link>} />
        <PulseLevels p={p} />
      </Card>
      {pulse && pulse.headlines.length > 0 && <Card><CardHead title="Market headlines" /><NewsList items={pulse.headlines} limit={6} /></Card>}
    </div>
  );
}

/* ================= One company ================= */
/** An outside page in a new tab (only http and https addresses). */
const openOut = (url: string) => { const h = safeHref(url); if (h) window.open(h, "_blank", "noopener,noreferrer"); };

/** A symbol that isn't listed: say so plainly, offer the listed companies whose name or symbol is close, and a search box.
 * Nothing failed, so there is no "Try again". */
function NoSuchCompany({ region, sym, eyebrow }: { region: Region; sym: string; eyebrow: string }) {
  const [near, setNear] = useState<Suggestion[] | null>(null);
  const [other, setOther] = useState<Suggestion[]>([]);
  useEffect(() => {
    let live = true;
    const q = sym.replace(/[^A-Z0-9&]/gi, "").slice(0, 6);       // the start of what was typed finds near spellings
    (q.length >= 2 ? suggestions(q, region) : Promise.resolve([])).then((r) => live && setNear(r.slice(0, 5))).catch(() => live && setNear([]));
    // the other market's company of that name (RC6-002: "BERKSHIRE" with India chosen was a dead end, though the US list has it)
    setOther([]);
    if (q.length >= 2) suggestions(q, region === "IN" ? "US" : "IN").then((r) => live && setOther(r.slice(0, 3))).catch(() => undefined);
    return () => { live = false; };
  }, [region, sym]);
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrow} title={`No listed company called ${sym}`} />
      <Card>
        <EmptyState title={`${sym} isn't ${region === "IN" ? "an NSE symbol or BSE code" : "a US ticker"} we know`}>
          {region === "IN" ? "Use the NSE symbol (like RELIANCE or TCS), the BSE code for a company listed only on BSE, or search by name below." : "Use the exact ticker (like AAPL or NVDA), or search by name below."}
        </EmptyState>
        {near && near.length > 0 && (
          <div className="k-row" aria-label="Close matches">
            <span className="k-small k-muted">Did you mean</span>
            {near.map((s) => <Link key={`${s.market}:${s.id}`} className="btn quiet sm" to={`/research/${s.market}/${encodeURIComponent(s.id)}`} title={s.name}>{s.symbol}</Link>)}
          </div>
        )}
        {other.length > 0 && (
          <div className="k-row" aria-label={`Matches in ${region === "IN" ? "the United States" : "India"}`}>
            <span className="k-small k-muted">In {region === "IN" ? "the United States" : "India"}</span>
            {other.map((s) => <Link key={`${s.market}:${s.id}`} className="btn quiet sm" to={`/research/${s.market}/${encodeURIComponent(s.id)}`} title={s.name}>{s.symbol}</Link>)}
          </div>
        )}
        <OpenCompany region={region} label="Look up a company" autoFocus={typingFirst()} />
      </Card>
    </div>
  );
}
/** A market research doesn't cover (/research/XX/TCS): said so, with the two markets it does, never India's page
 * opened silently (DD-005). */
function NoSuchMarket({ market, sym }: { market: string; sym: string }) {
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research")} title={`No market called ${market.toUpperCase().slice(0, 12)}`} />
      <Card>
        <EmptyState title="Research covers India and the US">
          Company pages are at /research/IN/ for India and /research/US/ for the US.
        </EmptyState>
        {sym && <div className="k-row">
          <Link className="btn quiet sm" to={`/research/IN/${encodeURIComponent(sym)}`}>{sym.toUpperCase()} in India</Link>
          <Link className="btn quiet sm" to={`/research/US/${encodeURIComponent(sym)}`}>{sym.toUpperCase()} in the US</Link>
        </div>}
      </Card>
    </div>
  );
}

export function CompanyPage() {
  const { region: r = "IN", symbol = "" } = useParams();
  if (!regionOf(r)) return <NoSuchMarket market={r} sym={symbol.slice(0, 20)} />;
  return <CompanyView />;
}

function CompanyView() {
  const { region: r = "IN", symbol = "" } = useParams();
  const region: Region = regionOf(r) ?? "IN";
  // BRK.B is BRK-B's page, at BRK-B's address (R13-001): the server answers either, the address says one
  const sym = canonTicker(region, symbol);
  const moved = sym !== symbol.toUpperCase();
  const { fail, focus } = useApp();
  const test = useTestOnStratLab();
  const [c, setC] = useState<Company | null>(null);
  const [error, setError] = useState<{ message: string; missing: boolean } | null>(null);
  const [results, setResults] = useState<{ next: ResultRow | null; last: ResultRow | null } | null>(null);
  const [tries, setTries] = useState(0);
  const nav = useNavigate();
  useEffect(() => { if (moved) nav(`/research/${region}/${encodeURIComponent(sym)}${window.location.search}`, { replace: true }); }, [moved, region, sym, nav]);
  const share = useShareCompany(region, sym);
  // the name and the symbol, then the price (R8O-009); the name is kept for the next first frame (lib/title titleFor)
  useDocTitle(c ? `${c.name || c.symbol}${c.name && c.name.toUpperCase() !== c.symbol ? ` (${c.symbol})` : ""}${c.quote?.price != null ? ` ${price(c.quote.price, c.currency || (region === "IN" ? "INR" : "USD"))}` : ""}` : null);
  useEffect(() => { if (c) rememberName(region, c.symbol, c.name); }, [c, region]);
  // the price and the day's change again each minute while the market trades; the rest of the page stays as read
  useLiveRefresh(!!c?.market_open && (c.quote?.at == null || liveQuote(c.quote.at)), () => {
    const s0 = c?.symbol;
    if (!s0) return;
    researchApi.quotes(region, [s0]).then((q) => {
      const x = q[s0];
      // the market value, the P/E and the year's range move with the price (RC7-007), not only the price beside them
      if (x?.price != null) setC((cur) => (cur && cur.symbol === s0 ? { ...atPrice(cur, cur.quote?.price, x.price), quote: { ...cur.quote, ...x }, as_of: x.at ?? cur.as_of } : cur));
    }).catch(() => undefined);
  });
  useEffect(() => {
    let live = true;
    setC(null); setError(null); setResults(null);
    // the price, header and tables first (lean); the news, the encyclopedia entry and the peers come from slower sources and
    // fill in behind them, so a slow one holds up only its own card (R10O-009: company pages settled in 9 to 30 s)
    researchApi.company(region, sym, true).then((x) => {
      if (!live) return;
      // a BSE code of a company NSE lists too opens its one page, at the NSE symbol's address (DD-003: 500325 is RELIANCE)
      if (bseTwinMoved(sym, x)) { nav(`/research/${region}/${encodeURIComponent(x.symbol)}${window.location.search}`, { replace: true }); return; }
      setC(x);
      // the results calendar under the page's own symbol (ZOMATO's page is ETERNAL's), not the one in the address
      api<{ next: ResultRow | null; last: ResultRow | null }>(`/research/results/${region}/${encodeURIComponent(x.symbol || sym)}`)
        .then((r) => live && setResults(r)).catch(() => undefined);      // the calendar is a nice-to-have here
      if (x.lazy?.length) researchApi.companyMore(region, sym).then((m) => live && setC((cur) => (cur && cur.symbol === x.symbol ? withMore(cur, m) : cur)))
        .catch(() => live && setC((cur) => (cur ? { ...cur, lazy: undefined, news_failed: true } : cur)));       // no news this time: the card says so
    }).catch((e) => live && setError({ message: (e as Error).message, missing: (e as ApiError).status === 404 }));
    // what the page shows under the company's name loads alongside it, not after it
    preloadPriceChart();
    if (region === "IN") { void loadSurveillance(); void loadEtfGaps(); void loadFoChanges(); }
    return () => { live = false; };
  }, [region, sym, fail, tries]);
  const nextDay = results?.next?.date ?? c?.next_earnings?.date ?? null;
  const latestQuarter = c?.quarters?.cols.length ? c.quarters.cols[c.quarters.cols.length - 1] : null;
  // a results day whose quarter is already in the table has brought its results: not "Results on" any more (R6O-016)
  const filedNow = !!results?.next?.out || resultsFiled(nextDay, latestQuarter, dayIn(new Date(), marketTz(region)) ?? "");
  const nextResults = filedNow ? null : nextDay;
  const eyebrow = eyebrowOf("/research");

  if (error?.missing) return <NoSuchCompany region={region} sym={sym} eyebrow={eyebrow} />;
  if (error) return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrow} title={`Couldn't open ${sym}`} />
      <Card>
        <ErrorState title={`${sym} couldn't be opened`} action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error.message}</ErrorState>
        <OpenCompany region={region} label="Look up another company" />
      </Card>
    </div>
  );
  if (!c) return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrow} title={sym} />
      <Card><Skeleton label={`Pulling live data for ${sym}`} lines={5} onRetry={() => setTries((n) => n + 1)} /></Card>
    </div>
  );

  const ccy = c.currency || (region === "IN" ? "INR" : "USD");
  const wiki = c.about.wiki;
  const shownFacts = c.facts.filter((f) => !/market cap/i.test(f.label) && !(/^listed$/i.test(f.label) && f.value.includes(c.symbol)));
  const deepTo = `/research/${region}/${encodeURIComponent(c.symbol)}/deep`;
  const lead = focus === "invest" || !c.testable ? "deep" : "test";
  const deep = (cls: string) => <Link className={`btn ${cls} sm`} to={deepTo} title="Business, capex and management">Deep dive →</Link>;
  const wrap = (title: string, id: string, info: string) => (body: React.ReactNode, right?: React.ReactNode) => (
    <Card id={id}><CardHead title={title} info={info} actions={right} />{body}</Card>
  );
  const trend = c.trend ? (() => {   // Indian figures are in crore; large, exact-enough charts read in lakh crore (see scaleFor)
    const t = c.trend, inr = /cr/i.test(t.unit);
    // one unit for the two charts side by side (sales and profit), so their labels never read in different units
    const s = inr ? scaleFor([...t.revenue, ...t.profit].map((p) => p.v), false) : null;
    const pick = (ps: typeof t.revenue) =>
      (s && s.k > 1 ? { points: ps.map((p) => ({ ...p, v: p.v / s.k })), unit: s.unit } : { points: ps, unit: t.unit });
    return { t, rev: pick(t.revenue), prof: pick(t.profit) };
  })() : null;
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrow} title={c.name} lede={`${c.exchange || REGION_NAME[region]} · ${c.symbol}${c.industry ? ` · ${c.industry}` : ""}`}
        asOf={c.as_of} asOfLabel={c.phase === "settling" ? "Provisional prices as of" : "Prices as of"} asOfTz={marketTz(region)} actions={c.quarters?.cols.length ? <Badge>Latest results: quarter to {c.quarters.cols[c.quarters.cols.length - 1]}{resultsAge(c.quarters.cols[c.quarters.cols.length - 1])}</Badge> : c.numbers_at ? <Badge>Reported numbers as of {asOf(c.numbers_at, { tz: marketTz(region) })}</Badge> : undefined} />
      <Card>
        <div className="inv-head">
          <div className="k-stack">
            {c.market_cap != null && <Stat label="Market value" value={bigMoney(c.market_cap, ccy)} />}
            {c.market_cap == null && c.cap_note && <p className="k-small k-muted" data-cap-check>{c.cap_note}</p>}
            <div className="inv-badges">
              <SurvBadges region={region} symbol={c.symbol} />
              {region === "IN" && <EtfGapBadge symbol={c.symbol} price={c.quote?.price} day={c.quote?.at ? dayIn(c.quote.at) : null} />}
              <FoBadges region={region} symbol={c.symbol} />
              <IndexBadges region={region} symbol={c.symbol} />
            </div>
            {/* a company that no longer trades says so first, and offers nothing that needs a live share (DD-012) */}
            {c.delisted && <p className="k-small" role="status" data-testid="delisted">{delistedLine(c.name, c.delisted, (d) => fmtDate(d))}
              {c.delisted.into_symbol && <> <Link className="link" to={`/research/${region}/${encodeURIComponent(c.delisted.into_symbol)}`}>{c.delisted.into ?? c.delisted.into_symbol} →</Link></>}</p>}
          </div>
          <div className="k-stack inv-head-price">
            <Change q={c.quote} currency={ccy} closed={c.market_open === false} preOpen={c.phase === "pre_open"} settling={c.phase === "settling"}
              quoteDay={c.quote_day} today={dayIn(new Date(), marketTz(region)) ?? undefined} />
            <Rail52 q={c.quote} low={c.range52.low} high={c.range52.high} since={c.range52.since} currency={ccy} compact />
            {/* the next results day is a fact about the company: a line with a link, not another button */}
            {nextResults && <Link className="link k-small" to={`/research/results?region=${region}`}>Results on {resultDay(nextResults)}</Link>}
            {filedNow && (results?.next?.out?.url
              ? <a className="link k-small" href={safeHref(results.next.out.url)} target="_blank" rel="noopener noreferrer">Results filed {resultDay(results.next.out.at)} ↗</a>
              : <Link className="link k-small" to={`/research/results?region=${region}`}>Results filed {resultDay(nextDay!)}{latestQuarter ? ` · quarter to ${latestQuarter}` : ""}</Link>)}
            {!nextResults && !filedNow && results?.last?.out && (results.last.out.url
              ? <a className="link k-small" href={safeHref(results.last.out.url)} target="_blank" rel="noopener noreferrer">Results filed {resultDay(results.last.out.at)} ↗</a>
              : <Link className="link k-small" to={`/research/results?region=${region}`}>Results filed {resultDay(results.last.out.at)}</Link>)}
          </div>
          {/* one main action (what this person came for), Watch and an alert; the rest under More. Inside the head, under the
              market value, so the left side has no empty block while the price column runs on (DD-019) */}
          <div className="k-row inv-actions">
            {/* the page's two main paths are both buttons: the one this person came for first and solid, the other beside it */}
            {!c.delisted && (lead === "deep" ? deep("") : <button className="btn sm" onClick={() => test(c)}>Test a strategy on {c.symbol} →</button>)}
            {!c.delisted && (lead === "deep" ? (c.testable && <button className="btn quiet sm" onClick={() => test(c)}>Test a strategy</button>) : deep("quiet"))}
            {!c.delisted && <Link className="btn quiet sm" to={`/research/compare?region=${region}&a=${encodeURIComponent(c.symbol)}`}>Compare</Link>}
            {!c.delisted && <StarButton region={region} symbol={c.symbol} name={c.name} />}
            {!c.delisted && <AlertButton region={region} symbol={c.symbol} />}
            <MoreMenu items={[
              { label: share.busy ? "Making the card…" : "Share", run: () => { void share.run(); } },
              ...(region === "IN" ? [{ label: "Test a SIP", run: () => nav(`/money/sip-test?symbol=${encodeURIComponent(c.symbol)}`) }] : []),
              ...c.links.map((l) => ({ label: `${linkLabel(l)} ↗`, run: () => openOut(l.url) })),
              ...(c.website ? [{ label: "Company website ↗", run: () => openOut(c.website!) }] : []),
            ]} />
          </div>
        </div>
      </Card>
      <SourcesNote sources={c.sources} />
      <PageNav items={[...(c.delisted ? [] : [{ id: "co-chart", label: "Price chart" }]), { id: "co-numbers", label: "Key numbers" },
        ...(c.shareholding && c.shareholding.rows.length > 0 ? [{ id: "co-owners", label: "Who owns it" }] : []),
        ...(region === "US" && !c.delisted ? [{ id: "us-owners", label: "Holders above 5%" }] : []),
        ...(region === "IN" ? [{ id: "filings", label: "Filings" }, { id: "deals", label: "Deals" }] : c.delisted ? [] : [{ id: "filings", label: "Filings" }]),
        { id: "corporate-actions", label: "Corporate actions" }, { id: "co-news", label: "News" }]} />
      {!c.delisted && <Card id="co-chart"><PriceChart region={region} symbol={c.symbol} currency={ccy} price={c.quote?.price} asOf={c.as_of} /></Card>}
      {region === "IN" && <EtfGapDetailView symbol={c.symbol} price={c.quote?.price} day={c.quote?.at ? dayIn(c.quote.at) : null} quiet />}

      {/* (the facts under "What they do": not the market cap, which has its own place, nor where it is listed, which the heading says) */}
      <div className={c.margins && c.margins.gross != null && (wiki || c.about.profile) ? "k-cols" : "k-stack"}>
        {(wiki || c.about.profile) && (
          <Card>
            <CardHead title="What they do" info="From an encyclopedia entry and the company's own profile: facts, not AI." />
            {/* the one-line description ("Indian multinational conglomerate") and then the entry's first sentence, which says it again; and "Listed: NSE ·
                RELIANCE" under a page headed "NSE · RELIANCE" (VR4-013): each is said once */}
            {wiki?.description && !(wiki.extract && wiki.extract.toLowerCase().includes(wiki.description.toLowerCase())) && <p className="k-sub">{wiki.description}</p>}
            <p className="k-small">{wiki?.extract || c.about.profile}</p>
            {wiki && c.about.profile && <p className="k-small k-muted">{c.about.profile}</p>}
            {shownFacts.length > 0 && <dl className="k-dl pairs">{shownFacts.map((f) => <div key={f.label}><dt>{f.label}</dt><dd>{f.value}</dd></div>)}</dl>}
            {wiki && <a className="link k-small" href={safeHref(wiki.url)} target="_blank" rel="noopener noreferrer">Read the full entry ↗</a>}
          </Card>
        )}
        {c.margins && c.margins.gross != null && <Card><CardHead title="Where a sale goes" info={HELP.researchMargins} /><MarginCascade {...c.margins} /></Card>}
      </div>

      {c.metrics.length > 0 && (
        <Card id="co-numbers">
          <CardHead title="Key numbers" info={HELP.researchMetrics} actions={<Link className="btn quiet sm" to={deepTo}>10 years in the deep dive →</Link>} />
          <MetricsGrid groups={c.metrics} currency={ccy} industry={c.industry} />
        </Card>
      )}

      {trend && (
        <ChartFrame title="Sales and profit, by year"
          table={{ label: "Sales and profit by year", rows: trend.rev.points.map((p) => ({ y: p.y, sales: p.v, profit: trend.prof.points.find((q) => q.y === p.y)?.v ?? null })), rowKey: (x) => x.y,
            columns: [{ key: "y", header: "Year", rowHeader: true, cell: (x) => x.y },
              { key: "s", header: `${trend.t.revenue_label} (${trend.rev.unit})`, numeric: true, cell: (x) => trendValue(x.sales, trend.rev.unit) },
              { key: "p", header: `${trend.t.profit_label} (${trend.prof.unit})`, numeric: true, cell: (x) => (x.profit == null ? "–" : trendValue(x.profit, trend.prof.unit)) }] }}>
          <div className="k-cols">
            <TrendBars points={trend.rev.points} label={trend.t.revenue_label} unit={trend.rev.unit} />
            <TrendBars points={trend.prof.points} label={trend.t.profit_label} unit={trend.prof.unit}
              baseSales={trend.rev.points.find((p) => p.y === trend.prof.points[0]?.y)?.v ?? null} />
          </div>
        </ChartFrame>
      )}

      <div className="k-cols">
        {c.earnings.length > 1 && <Card><CardHead title="Results versus expectations" info={HELP.researchEarnings} /><EarningsBars rows={c.earnings} basis={c.earnings_basis} /></Card>}
        {c.shareholding && c.shareholding.rows.length > 0 && <Card id="co-owners"><CardHead title="Who owns it" info={HELP.researchHolding} /><Shareholding s={c.shareholding} /></Card>}
        {c.insider && c.insider.rows.length > 0 && (
          <Card>
            <CardHead title="Insider trades" info="Shares bought or sold by the company's own directors and officers, from filings." />
            {/* the net is the sum of exactly the rows below, grouped as the company's market writes numbers */}
            <p className="k-small k-muted">Net <Signed value={c.insider.net} fmt={(v) => signed(Math.round(v), 0, region)} /> shares over the {c.insider.rows.length} filing{c.insider.rows.length === 1 ? "" : "s"} below</p>
            <DataTable label="Insider trades" rows={c.insider.rows} rowKey={(t) => `${t.name}-${t.date}-${t.change}`}
              columns={[{ key: "n", header: "Name", rowHeader: true, wrap: true, cell: (t) => t.name },
                { key: "c", header: "Shares", numeric: true, cell: (t) => <Signed value={t.change} fmt={(v) => signed(v, 0, region)} /> },
                { key: "d", header: "Date", numeric: true, cell: (t) => (t.date ? fmtDate(t.date) : "–") }]} />
          </Card>
        )}
      </div>

      {region === "US" && !c.delisted && <UsFilingsCards symbol={c.symbol} />}

      {region === "IN" && <Card id="filings"><CardHead title="Filings and red flags"
        info="What the company told the exchange: fund raises (QIP, preferential, rights), pledges, resignations, defaults, regulator action, rating changes, results and calls." /><FilingsPanel symbol={c.symbol} /></Card>}

      {region === "IN" && <BizUpdatesPanel symbol={c.symbol} wrap={wrap("Business updates", "business-updates",
        "Monthly or quarterly numbers the company files between results (sales volumes, deposits and advances, and the like), copied from its own filing with the line and page each comes from.")} />}

      {region === "IN" && <NamedHoldersPanel symbol={c.symbol} wrap={wrap("Named holders", "named-holders",
        "From the latest quarterly shareholding pattern: the promoter group's members and every public holder above 1%, with the change since the quarter before.")} />}

      {region === "IN" && <Card id="deals"><CardHead title="Deals and insider trades"
        info="Who bought or sold, from exchange disclosures: promoters', directors' and key staff's own trades and pledges, holders crossing 5% and moving 2% at a time (substantial acquisitions), and bulk and block deals with the named client." /><DealsPanel symbol={c.symbol} /></Card>}

      {c.quarters && c.quarters.cols.length > 0 && <Card><CardHead title="Last quarters" /><QuarterTable q={c.quarters} bank={!!c.bank} /></Card>}

      <Card id="corporate-actions"><CardHead title="Corporate actions"
        info="Dividends, bonus issues, splits, buybacks and rights issues, with ex-dates and record dates, as the company announced them." /><CompanyActions region={region} symbol={c.symbol} /></Card>

      <AIRead region={region} symbol={c.symbol} onTest={(i) => test(c, i)} />

      {/* CK-2 (R1): one card under the other: the news list is shorter than the peers' tiles, so side by side it left 120px of blank beside it */}
      <div className="k-stack">
        {c.peers.length > 0 && <Card><CardHead title="Similar companies" info="Companies in the same industry. Tap one to open it." /><div className={`co-peers co-peers-${c.peers.length === 4 ? 2 : Math.min(3, c.peers.length)}`}><QuoteGrid region={region} symbols={c.peers} /></div></Card>}
        <Card id="co-news"><CardHead title="Latest news" />{c.lazy?.length ? <Skeleton label="Loading the latest news" lines={2} />
          : c.news_failed && !c.news.length ? <p className="k-small k-muted" data-testid="news-failed">The news couldn't be loaded just now. It is read again when you open the page.</p>
          : <NewsList items={c.news} />}</Card>
      </div>
      <p className="k-note">AI text is written from the numbers above and may contain mistakes. Facts, not advice.</p>
    </div>
  );
}

/* ================= Themes ================= */
export function ThemesPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const [r, setR] = useState<SectorAI | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);   // a late answer for an earlier theme or market is ignored, and doesn't clear "Mapping…" for the newer one
  const run = async (theme: string, refresh = false) => {
    if (!theme.trim()) return;
    const mine = ++seq.current;
    setBusy(true); setError(null); if (!refresh) setR(null);
    try { const out = await researchApi.sector(region, theme, refresh); if (mine === seq.current) setR(out); }
    catch (e) { if (mine === seq.current) setError((e as Error).message); }
    finally { if (mine === seq.current) setBusy(false); }
  };
  useEffect(() => {
    setText(q);
    if (q) run(q);
    else { seq.current++; setR(null); setError(null); setBusy(false); }
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [q, region]);
  const go = (t: string) => { if (!t.trim()) return; const p = new URLSearchParams(params); p.set("q", t); p.set("region", region); setParams(p); };
  const coLink = (t: string) => (t ? `/research/${region}/${encodeURIComponent(t)}` : "");
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/themes")} title="Map a theme, find the companies in it"
        lede="Type a sector or trend. The AI maps who's involved along the chain, from raw materials to the end customer, and lists the listed companies linked to each step." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      <Card>
        <FormGrid label="Map a theme" onSubmit={(e) => { e.preventDefault(); go(text); }}>
          <Field label="Theme" wide value={text} onChange={(e) => setText(e.target.value)} placeholder={region === "IN" ? "India defence, railways capex…" : "AI data centers, grid electrification…"} />
          <FormActions>
            <button className="btn" disabled={busy}>{busy ? "Mapping…" : "Map it"}</button>
            <span className="k-small k-muted">Or try</span>
            {THEME_IDEAS[region].map((t) => <button key={t} type="button" className="btn quiet sm" onClick={() => go(t)}>{t}</button>)}
          </FormActions>
        </FormGrid>
      </Card>
      {error && <ErrorState title="The theme couldn't be mapped" action={{ label: "Try again", onClick: () => run(q, true) }}>{error}</ErrorState>}
      {busy && !r && <Card><Skeleton label={`Mapping "${q}" (takes about 20 seconds the first time)`} lines={4} /></Card>}
      {r && (
        <>
          <Card>
            <CardHead title={r.sector} actions={<><span className="k-note">Written {writtenAt(r.generated_at, marketTz(region))}</span>
              <button className="btn quiet sm" disabled={busy} onClick={() => run(q, true)}>{busy ? "Mapping…" : "Refresh"}</button></>} />
            <p className="k-lede">{r.summary}</p>
            {(r.market_size || r.cagr != null || r.etfs.length > 0) && (
              <StatRow>
                {r.market_size && <Stat label="Market size" value={r.market_size} />}
                {r.cagr != null && <Stat label={`Growth ${r.cagr_note}`} value={`${r.cagr}% a year`} />}
                {r.etfs.length > 0 && <Stat label="Funds to track" value={r.etfs.map((e) => e.ticker).join(" · ")} note={r.etfs.map((e) => e.name).join(" · ")} />}
              </StatRow>
            )}
          </Card>
          {r.screen.length > 0 && (
            <Card>
              <CardHead title="Listed companies across the chain" info="Listed companies with the most direct link to this theme, in value-chain order. Not ranked and not a list to buy: open any to see its numbers." />
              <DataTable label="Listed companies linked to the theme" rows={r.screen} rowKey={(s) => s.ticker + s.name} sticky={r.screen.length > 12}
                columns={[{ key: "n", header: "Company", rowHeader: true, wrap: true, cell: (s) => <><b>{s.name}</b><span className="k-sub-line">{s.one_line}</span></> },
                  { key: "t", header: "Ticker", cell: (s) => s.ticker || "–" }, { key: "l", header: "Step in the chain", wrap: true, cell: (s) => s.layer || "–" },
                  { key: "o", header: "", action: true, cell: (s) => (s.ticker ? <Link className="btn quiet sm" to={coLink(s.ticker)}>Open →</Link> : null) }]} />
            </Card>
          )}
          {r.clusters.length > 0 && (
            <Card>
              <CardHead title="Who's in it" info="Groups of listed companies involved in the theme. Every company is checked against the exchange's list and named as the exchange lists it; one the list doesn't have is left out. Tap a ticker to open the company." />
              {r.core && <p className="k-small">Everything converges on <b>{r.core}</b>.</p>}
              <div className="inv-clusters">
                {r.clusters.map((cl) => (
                  <div key={cl.name} className="inv-cluster">
                    <b className="k-small">{cl.name}</b>
                    <div className="k-row">{cl.companies.map((co) => co.ticker
                      ? <Link key={co.name} className="inv-chip" to={coLink(co.ticker)}><b>{co.ticker}</b> {co.name}</Link>
                      : <span key={co.name} className="inv-chip off">{co.name}</span>)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {r.value_chain.length > 0 && (
            <Card>
              <CardHead title="The value chain: where the margin sits" />
              <ol className="inv-chain">
                {r.value_chain.map((l, i) => (
                  <li key={l.layer}>
                    <span className="k-row"><Badge tone="plain" dot={false}>Layer {i + 1}</Badge><b className="k-sub">{l.layer}</b></span>
                    <p className="k-small">{l.description}</p>
                    <div className="k-row">{l.companies.map((co) => co.ticker
                      ? <Link key={co.name} className="inv-chip" to={coLink(co.ticker)}><b>{co.ticker}</b> {co.name}</Link>
                      : <span key={co.name} className="inv-chip off">{co.name}</span>)}</div>
                  </li>
                ))}
              </ol>
            </Card>
          )}
          {r.exchange && r.exchange.companies.length > 0 && (
            <Card>
              <CardHead title="On the exchange's list for these industries" info="Every listed company the exchange classifies under the same industries as the map's companies, A to Z, from StratLab's list of listed companies. Ticked ones are named in the map above; the rest are in the same industry and the map doesn't name them." />
              <p className="k-small k-muted">{r.exchange.industries.join(" · ")}: {r.exchange.total.toLocaleString("en-IN")} compan{r.exchange.total === 1 ? "y" : "ies"}{r.exchange.total > r.exchange.companies.length ? `, the first ${r.exchange.companies.length} A to Z` : ""}.</p>
              <div className="k-row">{r.exchange.companies.map((co) => (
                <Link key={co.ticker} className={`inv-chip${co.named ? "" : " off"}`} to={coLink(co.ticker)}>{co.named ? "✓ " : ""}<b>{co.ticker}</b> {co.name}</Link>
              ))}</div>
            </Card>
          )}
          <div className="k-cols">
            {r.sub_themes.length > 0 && <Card><CardHead title="Sub-themes" />{r.sub_themes.map((s) => <div key={s.name} className="k-stack"><b>{s.name}</b><span className="k-small k-muted">{s.detail}</span></div>)}</Card>}
            {r.tailwinds.length > 0 && <Card><CardHead title="Tailwinds" /><ul className="k-list">{r.tailwinds.map((t) => <li key={t}>{t}</li>)}</ul></Card>}
            {r.risks.length > 0 && <Card><CardHead title="Risks" /><ul className="k-list">{r.risks.map((t) => <li key={t}>{t}</li>)}</ul></Card>}
          </div>
          <p className="k-note">Written by AI from its general knowledge, with no figures: there's no source here to check a budget, size or growth rate against. Companies are checked against the exchange's list.</p>
        </>
      )}
    </div>
  );
}

/* ================= Market pulse ================= */
export function PulsePage() {
  const [region, setRegion] = useRegion();
  const levels = usePulse(region);
  const data = levels.data;
  const [ai, setAi] = useState<PulseAI | null>(null);
  const [aiErr, setAiErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);   // a late answer for the market you left is ignored, and doesn't clear the newer read's busy
  const loadAI = async (refresh = false) => {
    const mine = ++seq.current;
    setBusy(true); setAiErr(null);
    try { const out = await researchApi.pulseAI(region, "", refresh); if (mine === seq.current) setAi(out); }
    catch (e) { if (mine === seq.current) setAiErr((e as Error).message); }
    finally { if (mine === seq.current) setBusy(false); }
  };
  useEffect(() => {
    setAi(null);
    loadAI();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region]);
  // the mood is written from a fresh read of the levels, which the cards above may not have had yet: they are read again at once, so the
  // sentence and the cards quote one set of figures (RC2A-024: cards 22,664 at +0.28%, the mood a minute later 22,684 at +0.37%)
  const cardsAt = data?.indices.map((i) => i.at).filter(Boolean).sort().pop() ?? null;
  const reloadCards = levels.reload;
  useEffect(() => { if (ai?.levels_at && cardsAt && ai.levels_at > cardsAt) reloadCards(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [ai?.levels_at]);
  const moodOlder = !!(ai?.levels_at && cardsAt && Date.parse(cardsAt) - Date.parse(ai.levels_at) > 120_000);
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/pulse")} title={pulseClosedDay(data?.indices) ? "How the market felt at the last close" : "How the market feels today"}
        lede={pulseLede(ai, (() => { const d = pulseClosedDay(data?.indices); return d ? fmtDate(d, { year: false }) : null; })(), !!data?.indices.some((i) => i.settling))}
        asOf={data?.indices.map((i) => i.at).filter(Boolean).sort().pop() ?? undefined} asOfLabel="Prices as of" asOfTz={marketTz(region)} />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      <Card><CardHead title={`${REGION_NAME[region]} index levels`} /><PulseLevels p={levels} /></Card>
      <Card>
        <CardHead title="The mood" info={HELP.researchPulse}
          actions={ai?.tone && !aiErr ? <><span className="k-note">Written {writtenAt(ai.generated_at, marketTz(region))}{ai.levels_at ? `, levels of ${asOf(ai.levels_at, { tz: marketTz(region) })}` : ""}</span><button className="btn quiet sm" disabled={busy} onClick={() => loadAI(true)}>{busy ? "Reading…" : "Refresh"}</button></> : undefined} />
        {/* "Written" only beside a read that exists; no read is one calm line and one button, like a company's AI read */}
        {aiErr || (ai && !ai.tone) ? (
          <div className="k-row ai-read-off" role="status">
            <span className="k-small k-muted">No AI read of the mood right now{aiReason(aiErr)} The index levels and headlines don't depend on it.</span>
            {!aiLimited(aiErr) && <button type="button" className="btn quiet sm" disabled={busy} onClick={() => loadAI(true)}>{busy ? "Asking…" : "Ask again"}</button>}
          </div>
        ) : !ai ? <Skeleton label="Reading the tape" lines={2} /> : (
          <>
            {/* the mood and the main story first, worked out from the moves and headlines; then the read (DD-001) */}
            {ai.mood && <p className="inv-summary" data-testid="pulse-mood"><b>{ai.mood}</b></p>}
            <p className="inv-summary">{ai.tone}</p>
            {moodOlder && ai.levels_at && <p className="k-note" data-testid="pulse-mood-older">The sentences above quote the levels of {asOf(ai.levels_at, { tz: marketTz(region) })}; the cards are newer.</p>}
            {ai.flows_source && <p className="k-note" data-testid="pulse-flows-source">{ai.flows_source}</p>}
          </>
        )}
      </Card>
      {ai && (ai.hot.length > 0 || ai.flows.length > 0) && (
        <div className="k-cols">
          {ai.hot.length > 0 && <Card>
            <CardHead title="In today's headlines" />
            <div className="inv-rows">
              {ai.hot.map((h) => (
                <div key={h.ticker + h.name} className="inv-row">
                  <span><b>{h.name}</b> {h.ticker && <Link className="link k-small" to={`/research/${region}/${encodeURIComponent(h.ticker)}`}>{h.ticker} →</Link>}</span>
                  <span className="k-small k-muted">{h.why}</span>
                </div>
              ))}
            </div>
          </Card>}
          {ai.flows.length > 0 && <Card>
            <CardHead title={ai.flows.some((f) => f.direction) ? "Where money is flowing" : "Money and markets in the headlines"} />
            <div className="inv-rows">
              {ai.flows.map((f) => (
                <div key={f.title} className="inv-row">
                  <span className="k-row"><b>{f.title}</b>{f.direction && <Badge tone="plain" dot={false}>{f.direction.toLowerCase()}</Badge>}</span>
                  <span className="k-small k-muted">{f.detail}</span>
                </div>
              ))}
            </div>
          </Card>}
        </div>
      )}
      {ai && ai.themes.length > 0 && (
        <Card>
          <CardHead title="Themes in play" />
          <div className="inv-themes">
            {ai.themes.map((t) => (
              <Link key={t.theme} className="inv-theme" to={`/research/themes?region=${region}&q=${encodeURIComponent(t.theme)}`}>
                <b>{t.theme}</b><span className="k-small k-muted">{t.detail}</span>{t.example && <span className="k-note">e.g. {t.example}</span>}
              </Link>
            ))}
          </div>
        </Card>
      )}
      {data && <Card><CardHead title="Headlines" /><NewsList items={data.headlines} limit={14} /></Card>}
    </div>
  );
}

/** " · 16 months old" when a newer quarter's results should be out by now (filed within 60 days of a quarter's end). */
function resultsAge(quarter: string): string {
  const n = staleQuarter(quarter, 60);
  return n != null ? ` · ${monthsOld(n)}` : "";
}

/* ================= Compare ================= */
export function ComparePage() {
  const [region, setRegionState] = useRegion();
  const [params, setParams] = useSearchParams();
  const a = params.get("a") ?? "", b = params.get("b") ?? "";
  const [res, setRes] = useState<{ a: Company; b: Company; ai: CompareAI } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sameMsg, setSameMsg] = useState<string | null>(null);        // the server found the two to be one company (DD-061)
  // "Asking…" is the pair's it was pressed for: another pair or market never shows it, and never gets its answer
  const [asking, setAsking] = useState<string | null>(null);
  const shownKey = pairKey(region, a, b);
  const pair = useRef(shownKey);
  pair.current = shownKey;
  const today = dayIn(new Date(), marketTz(region)) ?? undefined;
  const dayText = (d: string) => fmtDate(d, { year: false });
  const setSide = (k: "a" | "b", v: string) => { const p = new URLSearchParams(params); p.set(k, v); p.set("region", region); setParams(p); };
  // another market's companies aren't this market's: switching clears both boxes
  const setRegion = (r: Region) => {
    if (r === region) return;
    setRegionState(r);
    const p = new URLSearchParams(window.location.search); p.set("region", r); p.delete("a"); p.delete("b"); setParams(p, { replace: true });
  };
  // the same company in both boxes is a slip, said kindly, and never sent to the server (DD-061)
  const same = !!a && !!b && canonTicker(region, a) === canonTicker(region, b);
  useEffect(() => {
    setAsking(null);
    setSameMsg(null);
    if (!a || !b || same) { setRes(null); setError(null); return; }
    let live = true;
    setRes(null); setError(null);
    researchApi.compare(region, a, b).then((x) => live && setRes(x)).catch((e) => {
      if (!live) return;
      if ((e as ApiError).code === "same_symbol") setSameMsg((e as Error).message); else setError((e as Error).message);
    });
    return () => { live = false; };
  }, [a, b, region, same]);
  // both prices and day moves again each minute while their market trades; the rest of the page stays as read (LIVE-1)
  useLiveRefresh(!!res && [res.a, res.b].some((c) => c.market_open && (c.quote?.at == null || liveQuote(c.quote.at))), () => {
    const key = shownKey;
    const [sa, sb] = [res!.a.symbol, res!.b.symbol];
    researchApi.quotes(region, [sa, sb]).then((q) => {
      if (pair.current !== key) return;
      const lay = (c: Company, x: Quote | null | undefined) => (x?.price != null ? { ...atPrice(c, c.quote?.price, x.price), quote: { ...c.quote, ...x }, as_of: x.at ?? c.as_of } : c);
      setRes((cur) => (cur && cur.a.symbol === sa && cur.b.symbol === sb ? { ...cur, a: lay(cur.a, q[sa]), b: lay(cur.b, q[sb]) } : cur));
    }).catch(() => undefined);
  });
  // only the AI's part is asked again; the numbers already on the page stay. The answer is put on the page only while
  // the same pair is shown (a late answer for an earlier pair is dropped)
  const askAgain = () => {
    const key = shownKey;
    setAsking(key);
    researchApi.compare(region, a, b, true)
      .then((x) => { if (pair.current === key) setRes((r) => (r ? { ...r, ai: x.ai } : x)); })
      .catch(() => {})
      .finally(() => setAsking((k) => (k === key ? null : k)));
  };
  // each measure under its section ("5Y CAGR" is in Sales growth and in Profit growth): keyed by both, so one never
  // stands in for the other, and each section is labelled
  const key = (g: string, l: string) => `${g} · ${l}`;
  const rows = (c: Company) => Object.fromEntries(c.metrics.flatMap((g) => g.items.map((i) => [key(g.title, i.label), i])));
  const groups = res ? [...res.a.metrics, ...res.b.metrics] : [];
  const sections = Array.from(new Set(groups.map((g) => g.title)))
    .map((t) => ({ title: t, labels: Array.from(new Set(groups.filter((g) => g.title === t).flatMap((g) => g.items.map((i) => i.label)))) }));
  const ra = res ? rows(res.a) : {}, rb = res ? rows(res.b) : {};
  // who owns each, by the holder groups either company's latest shareholding pattern names (DD-060)
  const owners = res ? Array.from(new Set([res.a, res.b].flatMap((c) => c.shareholding?.rows.map((r) => r.label) ?? []))) : [];
  const held = (c: Company, l: string) => { const r = c.shareholding?.rows.find((x) => x.label === l); return r ? `${r.value.toFixed(1)}%` : "–"; };
  // each figure as its company page writes it (₹3.7 lakh cr, 0.44, 9.7%), never a bare number without its unit
  // a figure that compares two periods names them under it ("Jun 2026 vs Jun 2025"): the two companies' latest quarters
  // can differ, and a bare "Latest YoY" read as one period for both (R50-003)
  // and a qualifier the company's page gives a figure stays with it: TCS's 4.4% yield says it counts a ₹46 special dividend and is 2.6% without
  // it (RC2A-028)
  const QUALIFIES = /special|like-for-like|against a quarter|other income|n\/m|not meaningful/i;
  const show = (m: Company["metrics"][number]["items"][number] | undefined, c: Company) => {
    if (!m) return "–";
    const note = (m as { note?: string }).note;
    return <>{metricText(m, c.currency)}{(m as { period?: string }).period && <span className="k-sub-line">{(m as { period?: string }).period}</span>}
      {note && QUALIFIES.test(note) && <span className="k-sub-line" data-testid="cmp-note">{note}</span>}</>;
  };
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/compare")} title="Two companies, side by side" lede="Pick two companies to line up their numbers, with an AI summary of where they differ." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      <Card>
        <FormGrid label="The two companies" pair>
          <Field label="First company">{(id) => <StockPicker id={id} market={region} value={a} placeholder={a ? `Change ${a}…` : "Name or symbol, e.g. TCS"} onPick={(s) => setSide("a", s)} />}</Field>
          <Field label="Second company">{(id) => <StockPicker id={id} market={region} value={b} placeholder={b ? `Change ${b}…` : "Name or symbol, e.g. Infosys"} onPick={(s) => setSide("b", s)} />}</Field>
        </FormGrid>
      </Card>
      {same && <EmptyState title={`${a.toUpperCase()} is in both boxes`}>Pick a different company in one of them to line the two up.</EmptyState>}
      {sameMsg && <EmptyState title="That's one company twice">{sameMsg}</EmptyState>}
      {error && <ErrorState title="The two couldn't be compared">{error}</ErrorState>}
      {(!a || !b) && !error && <EmptyState title="Pick two companies">Type a name in each box above. Their numbers line up here.</EmptyState>}
      {a && b && !same && !sameMsg && !res && !error && <Card><Skeleton label={`Comparing ${a} and ${b}`} lines={4} /></Card>}
      {res && (
        <>
          <Card>
            <CardHead title="AI comparison" />
            {res.ai && !res.ai.error && res.ai.verdict ? (
              <>
                <p className="inv-summary">{res.ai.verdict}</p>
                {res.ai.differences.length > 0 && <ul className="k-list">{res.ai.differences.map((d) => <li key={d}>{d}</li>)}</ul>}
              </>
            ) : (
              // no comparison is one calm line and one button, like the company page's AI read
              <div className="k-row ai-read-off" role="status" data-testid="compare-ai-off">
                <span className="k-small k-muted">No AI comparison right now{aiReason(res.ai?.error ?? null)} The numbers below don't depend on it.</span>
                {!aiLimited(res.ai?.error ?? null) && <button type="button" className="btn quiet sm" disabled={asking === shownKey} onClick={askAgain}>{asking === shownKey ? "Asking…" : "Ask again"}</button>}
              </div>
            )}
          </Card>
          <div className="k-cols">
            {([["a", res.a], ["b", res.b]] as const).map(([k, c]) => (
              <Card key={k}>
                {/* both cards the same: the name, the two figures, then the same two buttons in a row (DD-060) */}
                <CardHead title={c.name} />
                <StatRow>
                  <Stat label={priceLabel(c, today, dayText).label ?? "Price"} value={c.quote?.price != null ? price(c.quote.price, c.currency) : "–"}
                    delta={c.quote?.change_pct != null ? <Delta value={c.quote.change_pct}>{pct(c.quote.change_pct, 2)}</Delta> : undefined} note={priceLabel(c, today, dayText).since || undefined} />
                  <Stat label="Market value" value={bigMoney(c.market_cap, c.currency)} note={c.symbol} />
                </StatRow>
                <div className="k-row">
                  <Link className="btn quiet sm" to={`/research/${region}/${encodeURIComponent(c.symbol)}`}>Open {c.symbol} →</Link>
                  <StarButton region={region} symbol={c.symbol} name={c.name} />
                </div>
              </Card>
            ))}
          </div>
          {/* the two prices on one % scale, from the start of the range shown (DD-060) */}
          <Card id="cmp-chart"><PriceChart region={region} symbol={res.a.symbol} currency={res.a.currency} price={res.a.quote?.price} compareWith={res.b.symbol} /></Card>
          <Card>
            <CardHead title="The numbers side by side" />
            {/* every section's columns line up: the same widths in each table, so TCS and INFY never shift (DD-060) */}
            <div className="k-stack cmp-sections">
            {sections.map((sec) => (
              <div key={sec.title} className="k-stack">
                <span className="k-eyebrow">{sec.title}</span>
                <DataTable stack label={`${sec.title} for both companies`} rows={sec.labels} rowKey={(l) => l}
                  columns={[{ key: "m", header: "Measure", rowHeader: true, cell: (l) => l },
                    { key: "a", header: res.a.symbol, numeric: true, cell: (l) => show(ra[key(sec.title, l)], res.a) },
                    { key: "b", header: res.b.symbol, numeric: true, cell: (l) => show(rb[key(sec.title, l)], res.b) }]} />
              </div>
            ))}
            {owners.length > 0 && (
              <div className="k-stack" data-testid="cmp-owners">
                <span className="k-eyebrow">Who owns it</span>
                <DataTable stack label="Who owns each company" rows={owners} rowKey={(l) => l}
                  columns={[{ key: "m", header: "Holder", rowHeader: true, cell: (l) => holderRowName(l) },
                    { key: "a", header: res.a.symbol, numeric: true, cell: (l) => held(res.a, l) },
                    { key: "b", header: res.b.symbol, numeric: true, cell: (l) => held(res.b, l) }]} />
                <span className="k-note">From each company's latest shareholding pattern: {[res.a, res.b].map((c) => `${c.symbol} as of ${c.shareholding?.as_of ?? "–"}`).join(", ")}.</span>
              </div>
            )}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

/* ================= Watchlist ================= */
export function WatchlistPage() {
  const [region, setRegion] = useRegion();
  const { items, toggle, has, failed, retry, save } = useWatchlist();
  const { fail, notify, markets } = useApp();
  const [quotes, setQuotes] = useState<Record<string, Quote | null> | null>(null);
  // between the US close and its settle point the prices are the day's last prints, said as the company header says it (R13-005)
  const settling = settlingNow(markets.find((m) => m.id === region));
  // the market closed (a weekend, a holiday, after the bell): its prices are the last session's, whatever the date is in
  // its own time zone (R90-005: the US tab said "Price · today" on an Indian Saturday morning, still Friday in New York)
  const shut = (() => { const m = markets.find((x) => x.id === region); return m ? !marketState(m).open : false; })();
  const mine = (items ?? []).filter((w) => w.region === region);
  const key = mine.map((w) => w.symbol).join(",");
  useEffect(() => {
    let live = true;
    setQuotes(null);
    if (!mine.length) return;
    // the server answers 24 symbols a request (each is a price read): a longer list is asked for 24 at a time, in turn,
    // and each batch's rows fill in as it comes (review 5c: every stock after the 24th showed "–")
    void quotesInBatches((syms) => researchApi.quotes(region, syms), mine.map((w) => w.symbol), (soFar) => setQuotes(soFar), () => live);
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region, key]);
  // beside each price: its P/E and where it sits under its 52-week high (the screener's daily figures), and how many of
  // your alerts watch it, so the list says more than the day's move (DD-072)
  const [facts, setFacts] = useState<Record<string, { pe: number | null; from_high: number | null }> | null>(null);
  const [alertCount, setAlertCount] = useState<Record<string, number>>({});
  useEffect(() => {
    let live = true;
    setFacts(null);
    if (!mine.length) return;
    api<{ facts: Record<string, { pe: number | null; from_high: number | null }> }>(`/research/watchlist/facts?region=${region}&symbols=${encodeURIComponent(mine.map((w) => w.symbol).join(","))}`)
      .then((r) => live && setFacts(r.facts)).catch(() => live && setFacts({}));
    alertsApi.list().then((r) => {
      if (!live) return;
      const n: Record<string, number> = {};
      for (const x of r.active) if (x.region === region) n[x.symbol] = (n[x.symbol] ?? 0) + 1;
      setAlertCount(n);
    }).catch(() => undefined);
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region, key]);
  const factText = (sym: string) => {
    const f = facts?.[sym];
    if (!f) return null;
    const parts = [f.pe != null ? `P/E ${f.pe.toFixed(1)}` : null,
      f.from_high != null ? (f.from_high > -0.5 ? "near its 52-week high" : `${Math.abs(f.from_high).toFixed(1)}% below its 52-week high`) : null].filter(Boolean);
    return parts.length ? parts.join(" · ") : null;
  };
  // read again each minute while the prices are live, each row kept until its new price comes
  useLiveRefresh(!!quotes && Object.values(quotes).some((q) => liveQuote(q?.at)), () => {
    void quotesInBatches((syms) => researchApi.quotes(region, syms), mine.map((w) => w.symbol),
      (soFar) => setQuotes((cur) => ({ ...cur, ...Object.fromEntries(Object.entries(soFar).filter(([, q]) => q?.price != null)) })), () => true);
  });
  const add = (symbol: string, r: Region, name?: string) => {
    if (has(r, symbol)) { notify(watchNote(symbol, true, false)); return; }
    toggle({ region: r, symbol, name: name?.slice(0, 120) ?? null }, true).then((changed) => notify(watchNote(symbol, true, changed))).catch(fail);
  };
  // a removal takes effect at once, with Undo in its message: it puts the company back where it was (DD-025)
  const remove = (w: WatchItem) => {
    const same = (x: WatchItem) => x.region === w.region && x.symbol === w.symbol;
    const at = Math.max(0, (items ?? []).findIndex(same));
    toggle(w, false).then((changed) => {
      if (!changed) return;
      notify(`${w.symbol} removed from your watchlist.`, { label: "Undo", run: () => {
        save((cur) => (cur.some(same) ? cur : [...cur.slice(0, at), w, ...cur.slice(at)])).then(() => notify(`${w.symbol} is back on your watchlist.`)).catch(fail);
      } });
    }).catch(fail);
  };
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/watchlist")} title="Companies you're watching"
        lede="Press Watch on any company page to add it, or add one here. Saved to your account, so it's here on every device." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /><RouteSeg label="Watchlist view" views={WATCH_VIEWS} /></div>
      {/* one field across the card, its title as its label: a card with a heading above a 40%-wide box was mostly empty (RC2A-039) */}
      <Card compact className="watch-add">
        <Field label="Add a company" wide>{(id) => <StockPicker id={id} market={region} clearOnPick listedOnly onPick={add} placeholder="Search by name or symbol, like RELIANCE" />}</Field>
      </Card>
      {items === null ? (failed
        ? <Card><ErrorState title="Your watchlist couldn't be opened" action={{ label: "Try again", onClick: retry }}>Nothing was changed. Adding or removing a company waits until it opens.</ErrorState></Card>
        : <Card><Skeleton label="Opening your watchlist" lines={3} /></Card>) : mine.length === 0 ? (
        <Card><EmptyState title={`Nothing in your ${REGION_NAME[region]} watchlist yet`}>Add a company above, or press Watch on a company page.</EmptyState></Card>
      ) : (
        <Card>
          <CardHead title={`Your ${REGION_NAME[region]} watchlist`} actions={<AlertButton region={region} choices={mine.map((w) => ({ region: w.region, symbol: w.symbol }))} />} />
          {/* cards on a phone from the start: the badges under a name arrive after the first draw, so the overflow check alone
              could still leave Actions past the edge (UI checker R18) */}
          <DataTable label="Your watchlist" stack rows={mine} rowKey={(w) => `${w.region}:${w.symbol}`}
            columns={[
              { key: "s", header: "Company", rowHeader: true, wrap: true, cell: (w) => (
                // the flags sit under the name, not in a column of their own, so a phone fits the row and its Remove (R63-003)
                <><Link className="link" to={`/research/${w.region}/${encodeURIComponent(w.symbol)}`}><b>{w.symbol}</b></Link>
                  {w.name && <span className="k-sub-line">{w.name}</span>}
                  {factText(w.symbol) && <span className="k-sub-line k-muted" data-testid="watch-facts">{factText(w.symbol)}</span>}
                  {alertCount[w.symbol] ? <span className="k-sub-line"><Link className="link" to="/alerts">{alertCount[w.symbol]} alert{alertCount[w.symbol] === 1 ? "" : "s"} on</Link></span> : null}
                  <span className="k-sub-line"><SurvBadges region={region} symbol={w.symbol} /><FoBadges region={region} symbol={w.symbol} plain /></span></>) },
              // the day's change sits under the price, not in a column of its own, so a 400px phone fits the row with its
              // Remove (R64-001: 440px of table in a 334px box, Remove and "Today" cut off)
              { key: "p", header: `Price · ${shut || Object.values(quotes ?? {}).some((q) => sessionOf(q, marketTz(region))) ? "last session" : "today"}`, numeric: true, cell: (w) => {
                const q = quotes?.[w.symbol];
                if (quotes == null || !(w.symbol in quotes)) return "…";       // its batch hasn't come yet
                if (q?.price == null) return "–";
                const at = quoteAt(q.at, marketTz(region));
                // out of hours the change is the last completed session's, and says its day (R41A): "today" only of today's
                // a quote from an earlier day in the market's own time zone (a US quote on a Saturday) is that session's
                // too, though the server needn't say so: its change is already the session's (R42-004: "Today" over Friday)
                const x = q.change_pct, d = sessionOf(q, marketTz(region));
                return <>{price(q.price, region === "IN" ? "INR" : "USD")}
                  {x != null && <span className="k-sub-line"><Delta value={x}>{pct(x, 2)}</Delta>{d && <span data-testid="watch-change-day"> · {fmtDate(d, { weekday: true, year: false })}</span>}</span>}
                  {at && <span className="k-sub-line">{at}</span>}{settling && <span className="k-sub-line" data-testid="watch-settling">{SETTLING}</span>}</>;
              } },
              // on a phone card Remove sits at the card's top right, not alone on a last row of its own (VR3-006)
              { key: "r", header: "", action: true, corner: true, cell: (w) => <button className="btn quiet sm icon-only" aria-label={`Remove ${w.symbol} from your watchlist`} title="Remove" onClick={() => remove(w)}><Trash size={16} /></button> },
            ]} />
        </Card>
      )}
    </div>
  );
}
