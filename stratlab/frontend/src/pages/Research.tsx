import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, asOf, dayIn, fmtDate, marketTz, pct, price, quoteAt, safeHref, signed } from "../lib/format";
import { HELP } from "../lib/help";
import { eyebrowOf } from "../lib/eyebrow";
import {
  REGION_NAME, STARTER_TICKERS, THEME_IDEAS, bigMoney, indexWhen, metricText, monthsOld, priceLabel, researchApi, resultsFiled, scaleFor, staleQuarter, trendValue, useRegion, useWatchlist, withMore,
  type Company, type CompareAI, type Idea, type IndexLevel, type NewsItem, type PulseAI, type Quote, type Region, type SectorAI,
} from "../lib/research";
import {
  AIRead, aiLimited, aiReason, Change, EarningsBars, MarginCascade, MetricsGrid, NewsList, PriceChart, QuarterTable, QuoteGrid, Rail52, RegionSwitch,
  Shareholding, SourcesNote, StarButton, TrendBars,
} from "../components/Research";
import { preloadPriceChart } from "../charts/price/lazy";
import { loadSurveillance } from "../lib/surveillance";
import { loadEtfGaps } from "../lib/etfGaps";
import { loadFoChanges } from "../lib/foChanges";
import { AlertButton } from "../components/AlertForm";
import { useShareCompany } from "../components/ShareCompany";
import { MoreMenu } from "../components/MoreMenu";
import { suggestions, type Suggestion } from "../components/CompanyCombobox";
import { rememberName, useDocTitle } from "../lib/title";
import { DealsPanel } from "../components/Deals";
import { BizUpdatesPanel } from "../components/BizUpdates";
import { NamedHoldersPanel } from "../components/NamedHolders";
import { SurvBadges } from "../components/Surveillance";
import { EtfGapBadge, EtfGapDetailView } from "../components/EtfGap";
import { FoBadges } from "../components/FoBadges";
import { IndexBadges } from "../components/IndexBadges";
import { FilingsPanel } from "../components/Filings";
import { CompanyActions } from "../components/CorpActions";
import { RouteSeg, WATCH_VIEWS } from "../components/RouteSeg";
import {
  Badge, Card, CardHead, ChartFrame, DataTable, Delta, EmptyState, ErrorState, Field, FormActions, FormGrid, PageHeader, PageNav, Signed, Skeleton, Stat, StatRow, StockPicker,
} from "../components/kit";
import { resultDay, type ResultRow } from "./ResultsPage";

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
export function IndexStrip({ indices }: { indices: IndexLevel[] | null }) {
  if (!indices) return <Skeleton label="Loading the market" lines={2} />;
  if (!indices.length) return <EmptyState title="Index levels are unavailable right now">They come back on their own; this page checks again when you open it.</EmptyState>;
  return (
    <StatRow label="Index levels">
      {indices.map((i) => (
        <Stat key={i.name} item label={i.name} value={Math.round(i.price).toLocaleString(i.name.includes("NIFTY") || i.name === "SENSEX" ? "en-IN" : "en-US")}
          delta={i.change_pct != null ? <Delta value={i.change_pct} tone={i.stale ? "neutral" : "auto"}>{pct(i.change_pct, 2)}</Delta> : undefined}
          note={<span data-testid="index-when" data-stale={i.stale ? "1" : undefined}>{indexWhen(i, (d) => fmtDate(d, { year: false }))}{i.from_high_pct != null && ` · ${i.from_high_pct > -0.5 ? "near its 52-week high" : `${Math.abs(i.from_high_pct).toFixed(1)}% below its 52-week high`}`}</span>} />
      ))}
    </StatRow>
  );
}

/** A box that finds a company by name or symbol and opens its page. */
function OpenCompany({ region, label = "Company", autoFocus }: { region: Region; label?: string; autoFocus?: boolean }) {
  const nav = useNavigate();
  return (
    <Field label={label}>
      {(id) => <StockPicker id={id} market={region} autoFocus={autoFocus} clearOnPick
        placeholder={region === "IN" ? "Search by name or symbol, like HDFC Bank or TITAN" : "Search by name or ticker, like Nvidia or AAPL"}
        onPick={(s, r) => nav(`/research/${r}/${encodeURIComponent(s)}`)} />}
    </Field>
  );
}

/* ================= Companies (home) ================= */
export function ResearchHome() {
  const [region, setRegion] = useRegion();
  const [pulse, setPulse] = useState<{ indices: IndexLevel[]; headlines: NewsItem[] } | null>(null);
  useEffect(() => { setPulse(null); researchApi.pulse(region).then(setPulse).catch(() => setPulse({ indices: [], headlines: [] })); }, [region]);
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research")} title="Look up a company"
        lede="Search any Indian or US company for its price, valuation, growth, news and an AI read. Your watchlist, results days and red flags are on the Invest home." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      <Card>
        <CardHead title="Find a company" />
        <OpenCompany region={region} autoFocus />
        <div className="k-row">
          <span className="k-small k-muted">Try</span>
          {STARTER_TICKERS[region].map((s) => <Link key={s} to={`/research/${region}/${s}`} className="btn quiet sm">{s}</Link>)}
        </div>
      </Card>
      <Card>
        <CardHead title={`${REGION_NAME[region]} today`} info={HELP.researchPulse} actions={<Link to={`/research/pulse?region=${region}`} className="btn quiet sm">Full market pulse →</Link>} />
        <IndexStrip indices={pulse?.indices ?? null} />
      </Card>
      <Card>
        <CardHead title="Explore a theme" info={HELP.researchThemes} actions={<Link to={`/research/themes?region=${region}`} className="btn quiet sm">Themes →</Link>} />
        <div className="k-row">
          {THEME_IDEAS[region].map((t) => <Link key={t} to={`/research/themes?region=${region}&q=${encodeURIComponent(t)}`} className="btn quiet sm">{t}</Link>)}
        </div>
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
  useEffect(() => {
    let live = true;
    const q = sym.replace(/[^A-Z0-9&]/gi, "").slice(0, 6);       // the start of what was typed finds near spellings
    (q.length >= 2 ? suggestions(q, region) : Promise.resolve([])).then((r) => live && setNear(r.slice(0, 5))).catch(() => live && setNear([]));
    return () => { live = false; };
  }, [region, sym]);
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrow} title={`No listed company called ${sym}`} />
      <Card>
        <EmptyState title={`${sym} isn't a ${region === "IN" ? "NSE symbol or BSE code" : "US ticker"} we know`}>
          {region === "IN" ? "Use the NSE symbol (like RELIANCE or TCS), the BSE code for a company listed only on BSE, or search by name below." : "Use the exact ticker (like AAPL or NVDA), or search by name below."}
        </EmptyState>
        {near && near.length > 0 && (
          <div className="k-row" aria-label="Close matches">
            <span className="k-small k-muted">Did you mean</span>
            {near.map((s) => <Link key={`${s.market}:${s.id}`} className="btn quiet sm" to={`/research/${s.market}/${encodeURIComponent(s.id)}`} title={s.name}>{s.symbol}</Link>)}
          </div>
        )}
        <OpenCompany region={region} label="Look up a company" autoFocus />
      </Card>
    </div>
  );
}
export function CompanyPage() {
  const { region: r = "IN", symbol = "" } = useParams();
  const region: Region = r.toUpperCase() === "US" ? "US" : "IN";
  const sym = symbol.toUpperCase();
  const { fail, focus } = useApp();
  const test = useTestOnStratLab();
  const [c, setC] = useState<Company | null>(null);
  const [error, setError] = useState<{ message: string; missing: boolean } | null>(null);
  const [results, setResults] = useState<{ next: ResultRow | null; last: ResultRow | null } | null>(null);
  const [tries, setTries] = useState(0);
  const nav = useNavigate();
  const share = useShareCompany(region, sym);
  // the name and the symbol, then the price (R8O-009); the name is kept for the next first frame (lib/title titleFor)
  useDocTitle(c ? `${c.name || c.symbol}${c.name && c.name.toUpperCase() !== c.symbol ? ` (${c.symbol})` : ""}${c.quote?.price != null ? ` ${price(c.quote.price, c.currency || (region === "IN" ? "INR" : "USD"))}` : ""}` : null);
  useEffect(() => { if (c) rememberName(region, c.symbol, c.name); }, [c, region]);
  useEffect(() => {
    let live = true;
    setC(null); setError(null); setResults(null);
    // the price, header and tables first (lean); the news, the encyclopedia entry and the peers come from slower sources and
    // fill in behind them, so a slow one holds up only its own card (R10O-009: company pages settled in 9 to 30 s)
    researchApi.company(region, sym, true).then((x) => {
      if (!live) return;
      setC(x);
      if (x.lazy?.length) researchApi.companyMore(region, sym).then((m) => live && setC((cur) => (cur && cur.symbol === x.symbol ? withMore(cur, m) : cur)))
        .catch(() => live && setC((cur) => (cur ? { ...cur, lazy: undefined } : cur)));       // no news this time: the card says so
    }).catch((e) => live && setError({ message: (e as Error).message, missing: (e as ApiError).status === 404 }));
    // what the page shows under the company's name loads alongside it, not after it
    preloadPriceChart();
    if (region === "IN") { void loadSurveillance(); void loadEtfGaps(); void loadFoChanges(); }
    api<{ next: ResultRow | null; last: ResultRow | null }>(`/research/results/${region}/${encodeURIComponent(sym)}`)
      .then((x) => live && setResults(x)).catch(() => undefined);      // the calendar is a nice-to-have here
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
      <Card><Skeleton label={`Pulling live data for ${sym}`} lines={5} /></Card>
    </div>
  );

  const ccy = c.currency || (region === "IN" ? "INR" : "USD");
  const wiki = c.about.wiki;
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
        asOf={c.as_of} asOfLabel="Prices as of" asOfTz={marketTz(region)} actions={c.quarters?.cols.length ? <Badge>Latest results: quarter to {c.quarters.cols[c.quarters.cols.length - 1]}{resultsAge(c.quarters.cols[c.quarters.cols.length - 1])}</Badge> : c.numbers_at ? <Badge>Reported numbers as of {asOf(c.numbers_at, { tz: marketTz(region) })}</Badge> : undefined} />
      <Card>
        <div className="inv-head">
          <div className="k-stack">
            {c.market_cap != null && <Stat label="Market value" value={bigMoney(c.market_cap, ccy)} />}
            <div className="inv-badges">
              <SurvBadges region={region} symbol={c.symbol} />
              {region === "IN" && <EtfGapBadge symbol={c.symbol} price={c.quote?.price} day={c.quote?.at ? dayIn(c.quote.at) : null} />}
              <FoBadges region={region} symbol={c.symbol} />
              <IndexBadges region={region} symbol={c.symbol} />
            </div>
          </div>
          <div className="k-stack inv-head-price">
            <Change q={c.quote} currency={ccy} closed={c.market_open === false} preOpen={c.phase === "pre_open"} />
            <Rail52 q={c.quote} low={c.range52.low} high={c.range52.high} currency={ccy} compact />
            {/* the next results day is a fact about the company: a line with a link, not another button */}
            {nextResults && <Link className="link k-small" to={`/research/results?region=${region}`}>Results on {resultDay(nextResults)}</Link>}
            {filedNow && (results?.next?.out?.url
              ? <a className="link k-small" href={safeHref(results.next.out.url)} target="_blank" rel="noopener noreferrer">Results filed {resultDay(results.next.out.at)} ↗</a>
              : <Link className="link k-small" to={`/research/results?region=${region}`}>Results filed {resultDay(nextDay!)}{latestQuarter ? ` · quarter to ${latestQuarter}` : ""}</Link>)}
            {!nextResults && !filedNow && results?.last?.out && (results.last.out.url
              ? <a className="link k-small" href={safeHref(results.last.out.url)} target="_blank" rel="noopener noreferrer">Results filed {resultDay(results.last.out.at)} ↗</a>
              : <Link className="link k-small" to={`/research/results?region=${region}`}>Results filed {resultDay(results.last.out.at)}</Link>)}
          </div>
        </div>
        {/* one main action (what this person came for), Watch and an alert; the rest under More */}
        <div className="k-row">
          {/* the page's two main paths are both buttons: the one this person came for first and solid, the other beside it */}
          {lead === "deep" ? deep("") : <button className="btn sm" onClick={() => test(c)}>Test a strategy on {c.symbol} →</button>}
          {lead === "deep" ? (c.testable && <button className="btn quiet sm" onClick={() => test(c)}>Test a strategy</button>) : deep("quiet")}
          <Link className="btn quiet sm" to={`/research/compare?region=${region}&a=${encodeURIComponent(c.symbol)}`}>Compare</Link>
          <StarButton region={region} symbol={c.symbol} name={c.name} />
          <AlertButton region={region} symbol={c.symbol} />
          <MoreMenu items={[
            { label: share.busy ? "Making the card…" : "Share", run: () => { void share.run(); } },
            ...(region === "IN" ? [{ label: "Test a SIP", run: () => nav(`/money/sip-test?symbol=${encodeURIComponent(c.symbol)}`) }] : []),
            ...c.links.map((l) => ({ label: `${l.label} ↗`, run: () => openOut(l.url) })),
            ...(c.website ? [{ label: "Company website ↗", run: () => openOut(c.website!) }] : []),
          ]} />
        </div>
      </Card>
      <SourcesNote sources={c.sources} />
      <PageNav items={[{ id: "co-chart", label: "Price chart" }, { id: "co-numbers", label: "Key numbers" },
        ...(c.shareholding && c.shareholding.rows.length > 0 ? [{ id: "co-owners", label: "Who owns it" }] : []),
        ...(region === "IN" ? [{ id: "filings", label: "Filings" }, { id: "deals", label: "Deals" }] : []),
        { id: "corporate-actions", label: "Corporate actions" }, { id: "co-news", label: "News" }]} />
      <Card id="co-chart"><PriceChart region={region} symbol={c.symbol} currency={ccy} price={c.quote?.price} asOf={c.as_of} /></Card>
      {region === "IN" && <EtfGapDetailView symbol={c.symbol} price={c.quote?.price} day={c.quote?.at ? dayIn(c.quote.at) : null} quiet />}

      <div className={c.margins && c.margins.gross != null && (wiki || c.about.profile) ? "k-cols" : "k-stack"}>
        {(wiki || c.about.profile) && (
          <Card>
            <CardHead title="What they do" info="From an encyclopedia entry and the company's own profile: facts, not AI." />
            {wiki?.description && <p className="k-sub">{wiki.description}</p>}
            <p className="k-small">{wiki?.extract || c.about.profile}</p>
            {wiki && c.about.profile && <p className="k-small k-muted">{c.about.profile}</p>}
            {c.facts.some((f) => !/market cap/i.test(f.label)) && <dl className="k-dl">{c.facts.filter((f) => !/market cap/i.test(f.label)).map((f) => <div key={f.label}><dt>{f.label}</dt><dd>{f.value}</dd></div>)}</dl>}
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
            <TrendBars points={trend.prof.points} label={trend.t.profit_label} unit={trend.prof.unit} tone="blue" />
          </div>
        </ChartFrame>
      )}

      <div className="k-cols">
        {c.earnings.length > 1 && <Card><CardHead title="Results versus expectations" info={HELP.researchEarnings} /><EarningsBars rows={c.earnings} /></Card>}
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

      {region === "IN" && <Card id="filings"><CardHead title="Filings and red flags"
        info="What the company told the exchange: fund raises (QIP, preferential, rights), pledges, resignations, defaults, regulator action, rating changes, results and calls." /><FilingsPanel symbol={sym} /></Card>}

      {region === "IN" && <BizUpdatesPanel symbol={sym} wrap={wrap("Business updates", "business-updates",
        "Monthly or quarterly numbers the company files between results (sales volumes, deposits and advances, and the like), copied from its own filing with the line and page each comes from.")} />}

      {region === "IN" && <NamedHoldersPanel symbol={sym} wrap={wrap("Named holders", "named-holders",
        "From the latest quarterly shareholding pattern: the promoter group's members and every public holder above 1%, with the change since the quarter before.")} />}

      {region === "IN" && <Card id="deals"><CardHead title="Deals and insider trades"
        info="Who bought or sold, from exchange disclosures: promoters', directors' and key staff's own trades and pledges, holders crossing 5% and moving 2% at a time (substantial acquisitions), and bulk and block deals with the named client." /><DealsPanel symbol={sym} /></Card>}

      {c.quarters && c.quarters.cols.length > 0 && <Card><CardHead title="Last quarters" /><QuarterTable q={c.quarters} bank={!!c.bank} /></Card>}

      <Card id="corporate-actions"><CardHead title="Corporate actions"
        info="Dividends, bonus issues, splits, buybacks and rights issues, with ex-dates and record dates, as the company announced them." /><CompanyActions region={region} symbol={c.symbol} /></Card>

      <AIRead region={region} symbol={c.symbol} onTest={(i) => test(c, i)} />

      <div className="k-cols">
        {c.peers.length > 0 && <Card><CardHead title="Similar companies" info="Companies in the same industry. Tap one to open it." /><QuoteGrid region={region} symbols={c.peers} /></Card>}
        <Card id="co-news"><CardHead title="Latest news" />{c.lazy?.length ? <Skeleton label="Loading the latest news" lines={2} /> : <NewsList items={c.news} />}</Card>
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
  const run = async (theme: string, refresh = false) => {
    if (!theme.trim()) return;
    setBusy(true); setError(null); if (!refresh) setR(null);
    try { setR(await researchApi.sector(region, theme, refresh)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { setText(q); if (q) run(q); else setR(null); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [q, region]);
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
            <CardHead title={r.sector} actions={<><span className="k-note">Written {ago(new Date(r.generated_at * 1000).toISOString())}</span>
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
              <CardHead title="Who's in it" info="Groups of companies involved in the theme. Every ticker is checked against the exchange lists; a company without one isn't listed there. Tap a ticker to open the company." />
              {r.core && <p className="k-small">Everything converges on <b>{r.core}</b>.</p>}
              <div className="inv-clusters">
                {r.clusters.map((cl) => (
                  <div key={cl.name} className="inv-cluster">
                    <b className="k-small">{cl.name}</b>
                    <div className="k-row">{cl.companies.map((co) => co.ticker
                      ? <Link key={co.name} className="inv-chip" to={coLink(co.ticker)}><b>{co.ticker}</b> {co.name}</Link>
                      : <span key={co.name} className="inv-chip off">{co.name} (not listed)</span>)}</div>
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
          <div className="k-cols">
            {r.sub_themes.length > 0 && <Card><CardHead title="Sub-themes" />{r.sub_themes.map((s) => <div key={s.name} className="k-stack"><b>{s.name}</b><span className="k-small k-muted">{s.detail}</span></div>)}</Card>}
            {r.tailwinds.length > 0 && <Card><CardHead title="Tailwinds" /><ul className="k-list">{r.tailwinds.map((t) => <li key={t}>{t}</li>)}</ul></Card>}
            {r.risks.length > 0 && <Card><CardHead title="Risks" /><ul className="k-list">{r.risks.map((t) => <li key={t}>{t}</li>)}</ul></Card>}
          </div>
          <p className="k-note">Written by AI from its general knowledge: check the numbers at the source before relying on them.</p>
        </>
      )}
    </div>
  );
}

/* ================= Market pulse ================= */
export function PulsePage() {
  const [region, setRegion] = useRegion();
  const [data, setData] = useState<{ indices: IndexLevel[]; headlines: NewsItem[] } | null>(null);
  const [ai, setAi] = useState<PulseAI | null>(null);
  const [aiErr, setAiErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const loadAI = async (refresh = false) => {
    setBusy(true); setAiErr(null);
    try { setAi(await researchApi.pulseAI(region, "", refresh)); } catch (e) { setAiErr((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => {
    setData(null); setAi(null);
    researchApi.pulse(region).then(setData).catch(() => setData({ indices: [], headlines: [] }));
    loadAI();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region]);
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/pulse")} title="How the market feels today"
        lede="Live index levels and headlines, with an AI read of the mood, what's moving and where money is flowing." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>
      <Card><CardHead title={`${REGION_NAME[region]} index levels`} /><IndexStrip indices={data?.indices ?? null} /></Card>
      <Card>
        <CardHead title="The mood" info={HELP.researchPulse}
          actions={ai?.tone && !aiErr ? <><span className="k-note">Written {ago(new Date(ai.generated_at * 1000).toISOString())}</span><button className="btn quiet sm" disabled={busy} onClick={() => loadAI(true)}>{busy ? "Reading…" : "Refresh"}</button></> : undefined} />
        {/* "Written" only beside a read that exists; no read is one calm line and one button, like a company's AI read */}
        {aiErr || (ai && !ai.tone) ? (
          <div className="k-row ai-read-off" role="status">
            <span className="k-small k-muted">No AI read of the mood right now{aiReason(aiErr)} The index levels and headlines don't depend on it.</span>
            {!aiLimited(aiErr) && <button type="button" className="btn quiet sm" disabled={busy} onClick={() => loadAI(true)}>{busy ? "Asking…" : "Ask again"}</button>}
          </div>
        ) : !ai ? <Skeleton label="Reading the tape" lines={2} /> : <p className="inv-summary">{ai.tone}</p>}
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
            <CardHead title="Where money is flowing" />
            <div className="inv-rows">
              {ai.flows.map((f) => (
                <div key={f.title} className="inv-row">
                  <span className="k-row"><b>{f.title}</b><Badge tone="plain" dot={false}>{f.direction.toLowerCase()}</Badge></span>
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
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const a = params.get("a") ?? "", b = params.get("b") ?? "";
  const [res, setRes] = useState<{ a: Company; b: Company; ai: CompareAI } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const setSide = (k: "a" | "b", v: string) => { const p = new URLSearchParams(params); p.set(k, v); p.set("region", region); setParams(p); };
  useEffect(() => {
    if (!a || !b) { setRes(null); return; }
    let live = true;
    setRes(null); setError(null);
    researchApi.compare(region, a, b).then((x) => live && setRes(x)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [a, b, region]);
  // only the AI's part is asked again; the numbers already on the page stay
  const askAgain = () => {
    setAsking(true);
    researchApi.compare(region, a, b, true).then((x) => setRes((r) => (r ? { ...r, ai: x.ai } : x))).catch(() => {}).finally(() => setAsking(false));
  };
  // each measure under its section ("5Y CAGR" is in Sales growth and in Profit growth): keyed by both, so one never
  // stands in for the other, and each section is labelled
  const key = (g: string, l: string) => `${g} · ${l}`;
  const rows = (c: Company) => Object.fromEntries(c.metrics.flatMap((g) => g.items.map((i) => [key(g.title, i.label), i])));
  const groups = res ? [...res.a.metrics, ...res.b.metrics] : [];
  const sections = Array.from(new Set(groups.map((g) => g.title)))
    .map((t) => ({ title: t, labels: Array.from(new Set(groups.filter((g) => g.title === t).flatMap((g) => g.items.map((i) => i.label)))) }));
  const ra = res ? rows(res.a) : {}, rb = res ? rows(res.b) : {};
  // each figure as its company page writes it (₹3.7 lakh cr, 0.44, 9.7%), never a bare number without its unit
  const show = (m: Company["metrics"][number]["items"][number] | undefined, c: Company) => (m ? metricText(m, c.currency) : "–");
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
      {error && <ErrorState title="The two couldn't be compared">{error}</ErrorState>}
      {(!a || !b) && !error && <EmptyState title="Pick two companies">Type a name in each box above. Their numbers line up here.</EmptyState>}
      {a && b && !res && !error && <Card><Skeleton label={`Comparing ${a} and ${b}`} lines={4} /></Card>}
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
                {!aiLimited(res.ai?.error ?? null) && <button type="button" className="btn quiet sm" disabled={asking} onClick={askAgain}>{asking ? "Asking…" : "Ask again"}</button>}
              </div>
            )}
          </Card>
          <div className="k-cols">
            {([["a", res.a], ["b", res.b]] as const).map(([k, c]) => (
              <Card key={k}>
                <CardHead title={c.name} actions={<>
                  <Link className="btn quiet sm" to={`/research/${region}/${encodeURIComponent(c.symbol)}`}>Open →</Link>
                  <StarButton region={region} symbol={c.symbol} name={c.name} /></>} />
                <StatRow>
                  <Stat label={priceLabel(c).label ?? "Price"} value={c.quote?.price != null ? price(c.quote.price, c.currency) : "–"}
                    delta={c.quote?.change_pct != null ? <Delta value={c.quote.change_pct}>{pct(c.quote.change_pct, 2)}</Delta> : undefined} note={priceLabel(c).since} />
                  <Stat label="Market value" value={bigMoney(c.market_cap, c.currency)} note={c.symbol} />
                </StatRow>
              </Card>
            ))}
          </div>
          <Card>
            <CardHead title="The numbers side by side" />
            {sections.map((sec) => (
              <div key={sec.title} className="k-stack">
                <span className="k-eyebrow">{sec.title}</span>
                <DataTable label={`${sec.title} for both companies`} rows={sec.labels} rowKey={(l) => l}
                  columns={[{ key: "m", header: "Measure", rowHeader: true, cell: (l) => l },
                    { key: "a", header: res.a.symbol, numeric: true, cell: (l) => show(ra[key(sec.title, l)], res.a) },
                    { key: "b", header: res.b.symbol, numeric: true, cell: (l) => show(rb[key(sec.title, l)], res.b) }]} />
              </div>
            ))}
          </Card>
        </>
      )}
    </div>
  );
}

/* ================= Watchlist ================= */
export function WatchlistPage() {
  const [region, setRegion] = useRegion();
  const { items, toggle, has } = useWatchlist();
  const { fail, notify } = useApp();
  const [quotes, setQuotes] = useState<Record<string, Quote | null> | null>(null);
  const mine = (items ?? []).filter((w) => w.region === region);
  const key = mine.map((w) => w.symbol).join(",");
  useEffect(() => {
    let live = true;
    setQuotes(null);
    if (!mine.length) return;
    researchApi.quotes(region, mine.map((w) => w.symbol)).then((r) => live && setQuotes(r)).catch(() => live && setQuotes({}));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region, key]);
  const add = (symbol: string, r: Region) => {
    if (has(r, symbol)) { notify(`${symbol} is already in your watchlist.`); return; }
    toggle({ region: r, symbol, name: null }).then(() => notify(`${symbol} added to your watchlist.`)).catch(fail);
  };
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/watchlist")} title="Companies you're watching"
        lede="Press Watch on any company page to add it, or add one here. Saved to your account, so it's here on every device." />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /><RouteSeg label="Watchlist view" views={WATCH_VIEWS} /></div>
      <Card>
        <CardHead title="Add a company" />
        <Field label="Company">{(id) => <StockPicker id={id} market={region} clearOnPick onPick={add} placeholder="Search by name or symbol, like RELIANCE" />}</Field>
      </Card>
      {items === null ? <Card><Skeleton label="Opening your watchlist" lines={3} /></Card> : mine.length === 0 ? (
        <Card><EmptyState title={`Nothing in your ${REGION_NAME[region]} watchlist yet`}>Add a company above, or press Watch on a company page.</EmptyState></Card>
      ) : (
        <Card>
          <CardHead title={`Your ${REGION_NAME[region]} watchlist`} actions={<AlertButton region={region} choices={mine.map((w) => ({ region: w.region, symbol: w.symbol }))} />} />
          <DataTable label="Your watchlist" rows={mine} rowKey={(w) => `${w.region}:${w.symbol}`}
            columns={[
              { key: "s", header: "Company", rowHeader: true, wrap: true, cell: (w) => (
                <><Link className="link" to={`/research/${w.region}/${encodeURIComponent(w.symbol)}`}><b>{w.symbol}</b></Link>
                  {w.name && <span className="k-sub-line">{w.name}</span>}</>) },
              { key: "p", header: "Price", numeric: true, cell: (w) => {
                const q = quotes?.[w.symbol];
                if (quotes == null) return "…";
                if (q?.price == null) return "–";
                const at = quoteAt(q.at, marketTz(region));
                return <>{price(q.price, region === "IN" ? "INR" : "USD")}{at && <span className="k-sub-line">{at}</span>}</>;
              } },
              { key: "c", header: "Today", numeric: true, cell: (w) => { const x = quotes?.[w.symbol]?.change_pct; return x == null ? "–" : <Delta value={x}>{pct(x, 2)}</Delta>; } },
              { key: "b", header: "Flags", cell: (w) => <><SurvBadges region={region} symbol={w.symbol} /><FoBadges region={region} symbol={w.symbol} plain /></> },
              { key: "r", header: "", action: true, cell: (w) => <button className="btn quiet sm" aria-label={`Remove ${w.symbol} from your watchlist`} onClick={() => toggle(w).catch(fail)}>Remove</button> },
            ]} />
        </Card>
      )}
    </div>
  );
}
