import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, pct, price, safeHref, signClass } from "../lib/format";
import { HELP } from "../lib/help";
import {
  REGION_NAME, STARTER_TICKERS, THEME_IDEAS, bigMoney, researchApi, scaleFor, useRegion, useWatchlist,
  type Company, type CompareAI, type Idea, type IndexLevel, type NewsItem, type PulseAI, type Region, type SectorAI,
} from "../lib/research";
import {
  AIRead, Change, CompanySearch, EarningsBars, MarginCascade, MetricsGrid, NewsList, Panel, PriceChart,
  QuarterTable, QuoteGrid, Rail52, ResearchNav, Shareholding, SourcesNote, StarButton, TrendBars,
} from "../components/Research";
import { AsOf, Info, Loading } from "../components/ui";
import { AlertButton } from "../components/AlertForm";
import { ShareCompanyButton } from "../components/ShareCompany";
import { DealsPanel } from "../components/Deals";
import { SurvBadges } from "../components/Surveillance";
import { EtfGapBadge, EtfGapDetailView } from "../components/EtfGap";
import { FoBadges } from "../components/FoBadges";
import { FilingRow, FilingsPanel, SummaryLine, type FilingItem, type FilingSummary } from "../components/Filings";
import { CompanyActions } from "../components/CorpActions";
import { QUADRANTS, QuadrantTag, RotationChart, useAnimate, type Quadrant, type RotationRow } from "../components/Rotation";
import { Earlier } from "../components/Earlier";

/** Hand a company (and optionally an idea) to the New notebook page. */
function useTestOnStratLab() {
  const nav = useNavigate();
  return (c: { region: Region; symbol: string; instrument_id?: string | null }, idea?: Idea) =>
    nav("/new", { state: { prefill: { market: c.region, symbol: c.symbol, instrumentId: c.instrument_id ?? null, text: idea?.text ?? "" } } });
}

function Header({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <span className="eyebrow">{eyebrow}</span>
      <h1 className="page-title">{title}</h1>
      {sub && <p className="page-sub">{sub}</p>}
    </div>
  );
}

function IndexStrip({ indices }: { indices: IndexLevel[] | null }) {
  if (!indices) return <div className="row muted small" style={{ gap: 8 }}><span className="spinner" />Loading the market…</div>;
  if (!indices.length) return <p className="small muted">Index levels are unavailable right now.</p>;
  return (
    <div className="index-strip">
      {indices.map((i) => (
        <div key={i.name} className="stack" style={{ gap: 2 }}>
          <span className="eyebrow" style={{ fontSize: 11 }}>{i.name}</span>
          <span className="serif num" style={{ fontSize: 26, lineHeight: 1.1 }}>{Math.round(i.price).toLocaleString(i.name.includes("NIFTY") || i.name === "SENSEX" ? "en-IN" : "en-US")}</span>
          <span className="small"><span className={`num ${signClass(i.change_pct)}`}>{pct(i.change_pct, 2)}</span> today
            {i.from_high_pct != null && <span className="muted"> · {i.from_high_pct > -0.5 ? "near its 52-week high" : `${Math.abs(i.from_high_pct).toFixed(1)}% below its 52-week high`}</span>}</span>
        </div>
      ))}
    </div>
  );
}

/* ================= Companies (home) ================= */
export function ResearchHome() {
  const [region, setRegion] = useRegion();
  const { items } = useWatchlist();
  const [pulse, setPulse] = useState<{ indices: IndexLevel[]; headlines: NewsItem[] } | null>(null);
  useEffect(() => { setPulse(null); researchApi.pulse(region).then(setPulse).catch(() => setPulse({ indices: [], headlines: [] })); }, [region]);
  const mine = (items ?? []).filter((w) => w.region === region);
  return (
    <div className="stack" style={{ gap: 26 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <Header eyebrow={`Research · ${REGION_NAME[region]}`} title="Find something worth testing"
        sub="Look up any company: price, valuation, growth, news and an AI read. When an idea looks promising, test it honestly on years of real prices in one click." />
      <div className="stack" style={{ gap: 12 }}>
        <CompanySearch region={region} autoFocus />
        <div className="row wrap" style={{ gap: 8 }}>
          <span className="small muted">Try:</span>
          {STARTER_TICKERS[region].map((s) => <Link key={s} to={`/research/${region}/${s}`} className="btn quiet sm">{s}</Link>)}
        </div>
      </div>
      <Panel title={`${REGION_NAME[region]} today`} info={HELP.researchPulse} right={<Link to={`/research/pulse?region=${region}`} className="link">Full market pulse →</Link>}>
        <IndexStrip indices={pulse?.indices ?? null} />
      </Panel>
      <div className="grid2">
        <Panel title="Your watchlist" right={<Link to="/research/watchlist" className="link">All →</Link>}>
          <QuoteGrid region={region} symbols={mine.slice(0, 6).map((w) => w.symbol)} names={Object.fromEntries(mine.map((w) => [w.symbol, w.name]))}
            empty={<p className="small muted">Press Watch on any company to keep it here, with live prices.</p>} />
        </Panel>
        <Panel title="Explore a theme" info={HELP.researchThemes} right={<Link to={`/research/themes?region=${region}`} className="link">Themes →</Link>}>
          <div className="row wrap" style={{ gap: 8 }}>
            {THEME_IDEAS[region].map((t) => <Link key={t} to={`/research/themes?region=${region}&q=${encodeURIComponent(t)}`} className="btn quiet sm">{t}</Link>)}
          </div>
        </Panel>
      </div>
      {pulse && pulse.headlines.length > 0 && <Panel title="Market headlines"><NewsList items={pulse.headlines} limit={6} /></Panel>}
    </div>
  );
}

/* ================= One company ================= */
export function CompanyPage() {
  const { region: r = "IN", symbol = "" } = useParams();
  const region: Region = r.toUpperCase() === "US" ? "US" : "IN";
  const sym = symbol.toUpperCase();
  const { fail, focus } = useApp();
  const test = useTestOnStratLab();
  const [c, setC] = useState<Company | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<{ next: ResultRow | null; last: ResultRow | null } | null>(null);
  useEffect(() => {
    let live = true;
    setC(null); setError(null); setResults(null);
    researchApi.company(region, sym).then((x) => live && setC(x)).catch((e) => live && setError((e as Error).message));
    api<{ next: ResultRow | null; last: ResultRow | null }>(`/research/results/${region}/${encodeURIComponent(sym)}`)
      .then((x) => live && setResults(x)).catch(() => undefined);      // the calendar is a nice-to-have here
    return () => { live = false; };
  }, [region, sym, fail]);
  const nextResults = results?.next?.date ?? c?.next_earnings?.date ?? null;

  if (error) return (
    <div className="stack" style={{ gap: 20 }}>
      <ResearchNav region={region} />
      <div className="card stack" style={{ gap: 12 }}><h1 className="h2">Couldn't open {sym}</h1><p className="muted">{error}</p>
        <CompanySearch region={region} /></div>
    </div>
  );
  if (!c) return <div className="stack" style={{ gap: 20 }}><ResearchNav region={region} /><Loading label={`Pulling live data for ${sym}`} /></div>;

  const ccy = c.currency || (region === "IN" ? "INR" : "USD");
  const wiki = c.about.wiki;
  return (
    <div className="stack" style={{ gap: 22 }}>
      <ResearchNav region={region} />
      <section className="stack" style={{ gap: 16 }}>
        <div className="spread" style={{ alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
          <div className="stack" style={{ gap: 6, minWidth: 0, flex: "1 1 320px" }}>
            <span className="eyebrow">{c.exchange || REGION_NAME[region]} · {c.symbol}{c.industry ? ` · ${c.industry}` : ""}</span>
            <h1 className="serif" style={{ fontSize: "clamp(32px, 4.4vw, 50px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.05 }}>{c.name}</h1>
            {c.market_cap != null && <span className="small muted">Market value {bigMoney(c.market_cap, ccy)}</span>}
            <SurvBadges region={region} symbol={c.symbol} />
            {region === "IN" && <EtfGapBadge symbol={c.symbol} />}
            <FoBadges region={region} symbol={c.symbol} />
            <AsOf parts={[["Prices", c.as_of], ["Reported numbers", c.numbers_at]]} />
          </div>
          <Change q={c.quote} currency={ccy} />
        </div>
        <div className="toolbar">
          {(region === "IN" || region === "US") && focus === "invest" && <Link className="btn blue sm" to={`/research/${region}/${encodeURIComponent(c.symbol)}/deep`}>Deep dive: business, capex, management →</Link>}
          {c.testable && <button className={`btn ${focus === "invest" && region === "IN" ? "outline" : "blue"} sm`} onClick={() => test(c)}>Test a strategy on {c.symbol} →</button>}
          {(region === "IN" || region === "US") && focus !== "invest" && <Link className="btn outline sm" to={`/research/${region}/${encodeURIComponent(c.symbol)}/deep`}>Deep dive: business, capex, management →</Link>}
          <StarButton region={region} symbol={c.symbol} name={c.name} />
          {nextResults && <Link className="btn quiet sm" to={`/research/results?region=${region}`}>Results on {resultDay(nextResults)}</Link>}
          {!nextResults && results?.last?.out && (results.last.out.url
            ? <a className="btn quiet sm" href={safeHref(results.last.out.url)} target="_blank" rel="noopener noreferrer">Results filed {resultDay(results.last.out.at)} ↗</a>
            : <Link className="btn quiet sm" to={`/research/results?region=${region}`}>Results filed {resultDay(results.last.out.at)}</Link>)}
          <AlertButton region={region} symbol={c.symbol} />
          <Link className="btn quiet sm" to={`/research/compare?region=${region}&a=${c.symbol}`}>Compare</Link>
          <ShareCompanyButton region={region} symbol={c.symbol} />
          {c.links.map((l) => <a key={l.url} className="btn quiet sm" href={safeHref(l.url)} target="_blank" rel="noopener noreferrer">{l.label} ↗</a>)}
          {c.website && <a className="btn quiet sm" href={safeHref(c.website)} target="_blank" rel="noopener noreferrer">Website ↗</a>}
        </div>
      </section>
      <SourcesNote sources={c.sources} />
      <section className="card"><PriceChart region={region} symbol={c.symbol} currency={ccy} /></section>
      {region === "IN" && <EtfGapDetailView symbol={c.symbol} quiet />}

      <div className="rs-grid">
        {(wiki || c.about.profile) && (
          <Panel title="What they do" info="From Wikipedia and the company's own profile: facts, not AI.">
            {wiki?.description && <p className="serif" style={{ fontSize: 18 }}>{wiki.description}</p>}
            <p className="small" style={{ lineHeight: 1.65 }}>{wiki?.extract || c.about.profile}</p>
            {wiki && c.about.profile && <p className="small muted" style={{ lineHeight: 1.6 }}>{c.about.profile}</p>}
            <div className="row wrap small" style={{ gap: 14 }}>{c.facts.map((f) => <span key={f.label}><span className="muted">{f.label}</span> <b>{f.value}</b></span>)}</div>
            {wiki && <a className="link small" href={safeHref(wiki.url)} target="_blank" rel="noopener noreferrer">More on Wikipedia ↗</a>}
          </Panel>
        )}
        {c.range52.low != null && <Panel title="Where the price sits" info={HELP.research52}><Rail52 q={c.quote} low={c.range52.low} high={c.range52.high} currency={ccy} /></Panel>}
        {c.margins && c.margins.gross != null && <Panel title="Where a sale goes" info={HELP.researchMargins}><MarginCascade {...c.margins} /></Panel>}
      </div>

      {c.metrics.length > 0 && (
        <Panel title="Key numbers" info={HELP.researchMetrics} span="full">
          <MetricsGrid groups={c.metrics} currency={ccy} industry={c.industry} />
        </Panel>
      )}

      <div className="rs-grid">
        {c.trend && (
          <Panel title="Sales and profit, by year">
            {(() => {   // Indian figures are in crore; large, exact-enough charts read in lakh crore (see scaleFor)
              const t = c.trend!, inr = /cr/i.test(t.unit);
              const pick = (ps: typeof t.revenue) => {
                const s = inr ? scaleFor(ps.map((p) => p.v), false) : null;
                return s && s.k > 1 ? { points: ps.map((p) => ({ ...p, v: p.v / s.k })), unit: s.unit } : { points: ps, unit: t.unit };
              };
              const r = pick(t.revenue), pr = pick(t.profit);
              return <>
                <TrendBars points={r.points} label={t.revenue_label} unit={r.unit} />
                <TrendBars points={pr.points} label={t.profit_label} unit={pr.unit} tone="blue" />
              </>;
            })()}
          </Panel>
        )}
        {c.earnings.length > 1 && <Panel title="Results versus expectations" info={HELP.researchEarnings}><EarningsBars rows={c.earnings} /></Panel>}
        {c.shareholding && c.shareholding.rows.length > 0 && <Panel title="Who owns it" info={HELP.researchHolding}><Shareholding s={c.shareholding} /></Panel>}
        {((c.pros?.length ?? 0) > 0 || (c.cons?.length ?? 0) > 0) && (
          <Panel title="Strengths and concerns" info="Automatic checks on the company's reported numbers.">
            <ul className="bullets small">{c.pros?.map((p) => <li key={p} className="pos-dot">{p}</li>)}</ul>
            <ul className="bullets small">{c.cons?.map((p) => <li key={p} className="neg-dot">{p}</li>)}</ul>
          </Panel>
        )}
        {c.insider && c.insider.rows.length > 0 && (
          <Panel title="Insider trades" info="Shares bought or sold by the company's own directors and officers, from filings.">
            <span className={`small num ${signClass(c.insider.net)}`}>Net {c.insider.net > 0 ? "+" : ""}{Math.round(c.insider.net).toLocaleString()} shares across recent filings</span>
            {c.insider.rows.map((t, i) => (
              <div key={i} className="spread small" style={{ borderBottom: "1px solid var(--line)", padding: "6px 0" }}>
                <span>{t.name}</span><span className={`num ${signClass(t.change)}`}>{t.change > 0 ? "+" : ""}{t.change.toLocaleString()} <span className="muted tiny">{t.date}</span></span>
              </div>
            ))}
          </Panel>
        )}
      </div>

      {region === "IN" && <Panel title="Filings and red flags" id="filings" span="full"
        info="What the company told the exchange: fund raises (QIP, preferential, rights), pledges, resignations, defaults, regulator action, rating changes, results and calls."><FilingsPanel symbol={sym} /></Panel>}

      {region === "IN" && <Panel title="Deals and insider trades" id="deals" span="full"
        info="Who bought or sold, from exchange disclosures: promoters', directors' and key staff's own trades and pledges, holders crossing 5% and moving 2% at a time (substantial acquisitions), and bulk and block deals with the named client."><DealsPanel symbol={sym} /></Panel>}

      {c.quarters && c.quarters.cols.length > 0 && <Panel title="Last quarters" span="full"><QuarterTable q={c.quarters} /></Panel>}

      <Panel title="Corporate actions" id="corporate-actions" span="full"
        info="Dividends, bonus issues, splits, buybacks and rights issues, with ex-dates and record dates, as the company announced them."><CompanyActions region={region} symbol={c.symbol} /></Panel>

      <AIRead region={region} symbol={c.symbol} onTest={(i) => test(c, i)} />

      <div className="rs-grid">
        {c.peers.length > 0 && <Panel title="Similar companies" info="Companies in the same industry. Tap one to open it."><QuoteGrid region={region} symbols={c.peers} /></Panel>}
        <Panel title="Latest news"><NewsList items={c.news} /></Panel>
      </div>
      <p className="hint">AI text is written from the numbers above and may contain mistakes. Facts, not advice.</p>
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
  const go = (t: string) => { const p = new URLSearchParams(params); p.set("q", t); p.set("region", region); setParams(p); };
  const coLink = (t: string) => (t ? `/research/${region}/${encodeURIComponent(t)}` : "");
  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <Header eyebrow={`Themes · ${REGION_NAME[region]}`} title="Map a theme, find the companies in it"
        sub="Type a sector or trend. The AI maps who's involved along the chain, from raw materials to the end customer, and lists the listed companies linked to each step." />
      <form className="row" style={{ gap: 10 }} onSubmit={(e) => { e.preventDefault(); go(text); }}>
        <input className="input" style={{ flex: 1 }} value={text} onChange={(e) => setText(e.target.value)} placeholder={region === "IN" ? "India defence, railways capex…" : "AI data centers, grid electrification…"} aria-label="Theme" />
        <button className="btn" disabled={busy}>{busy ? "Mapping…" : "Map it"}</button>
      </form>
      <div className="row wrap" style={{ gap: 8 }}>{THEME_IDEAS[region].map((t) => <button key={t} className="btn quiet sm" onClick={() => go(t)}>{t}</button>)}</div>
      {error && <div className="banner">{error}</div>}
      {busy && !r && <Loading label={`Mapping "${q}" (takes about 20 seconds the first time)`} />}
      {r && (
        <>
          <section className="card stack" style={{ gap: 12 }}>
            <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
              <h2 className="serif" style={{ fontSize: 34, fontWeight: 400 }}>{r.sector}</h2>
              <span className="row small muted" style={{ gap: 10 }}>Written {ago(new Date(r.generated_at * 1000).toISOString())}
                <button className="btn quiet sm" disabled={busy} onClick={() => run(q, true)}>{busy ? "Mapping…" : "Refresh"}</button></span>
            </div>
            <p style={{ fontSize: 17, lineHeight: 1.6 }}>{r.summary}</p>
            <div className="row wrap" style={{ gap: 24 }}>
              {r.market_size && <div className="stack" style={{ gap: 2 }}><span className="eyebrow">Market size</span><b className="serif" style={{ fontSize: 22 }}>{r.market_size}</b></div>}
              {r.cagr != null && <div className="stack" style={{ gap: 2 }}><span className="eyebrow">Growth {r.cagr_note}</span><b className="serif pos" style={{ fontSize: 22 }}>{r.cagr}% a year</b></div>}
              {r.etfs.length > 0 && <div className="stack" style={{ gap: 2 }}><span className="eyebrow">Funds to track</span><span className="small">{r.etfs.map((e) => `${e.ticker} (${e.name})`).join(" · ")}</span></div>}
            </div>
          </section>
          {r.screen.length > 0 && (
            <Panel title="Listed companies across the chain" info="Listed companies with the most direct link to this theme, in value-chain order. Not ranked and not a list to buy: open any to see its numbers." span="full">
              {r.screen.map((s) => (
                <div key={s.ticker + s.name} className="screen-row">
                  <div className="stack" style={{ gap: 3, minWidth: 0, flex: 1 }}>
                    <span><b>{s.name}</b> <span className="num small" style={{ color: "var(--blue-ink)" }}>{s.ticker}</span> {s.layer && <span className="badge skip">{s.layer}</span>}</span>
                    <span className="small muted">{s.one_line}</span>
                  </div>
                  {s.ticker && <Link className="btn quiet sm" to={coLink(s.ticker)}>Open →</Link>}
                </div>
              ))}
            </Panel>
          )}
          {r.clusters.length > 0 && (
            <Panel title="Who's in it" span="full" info="Groups of companies involved in the theme. Tap a ticker to open the company.">
              {r.core && <p className="small">Everything converges on <b>{r.core}</b>.</p>}
              <div className="cluster-grid">
                {r.clusters.map((cl) => (
                  <div key={cl.name} className="cluster">
                    <b className="small">{cl.name}</b>
                    <div className="row wrap" style={{ gap: 6 }}>{cl.companies.map((co) => co.ticker
                      ? <Link key={co.name} className="chip-link" to={coLink(co.ticker)}><b>{co.ticker}</b> {co.name}</Link>
                      : <span key={co.name} className="chip-link muted">{co.name} (private)</span>)}</div>
                  </div>
                ))}
              </div>
            </Panel>
          )}
          {r.value_chain.length > 0 && (
            <Panel title="The value chain: where the margin sits" span="full">
              {r.value_chain.map((l, i) => (
                <div key={l.layer} className="stack" style={{ gap: 8, padding: "12px 0", borderTop: i ? "1px solid var(--line)" : undefined }}>
                  <span className="row" style={{ gap: 10 }}><span className="badge next">Layer {i + 1}</span><b className="serif" style={{ fontSize: 18 }}>{l.layer}</b></span>
                  <p className="small" style={{ lineHeight: 1.6 }}>{l.description}</p>
                  <div className="row wrap" style={{ gap: 6 }}>{l.companies.map((co) => co.ticker
                    ? <Link key={co.name} className="chip-link" to={coLink(co.ticker)}><b>{co.ticker}</b> {co.name}</Link>
                    : <span key={co.name} className="chip-link muted">{co.name}</span>)}</div>
                </div>
              ))}
            </Panel>
          )}
          <div className="grid2">
            {r.sub_themes.length > 0 && <Panel title="Sub-themes">{r.sub_themes.map((s) => <div key={s.name} className="stack" style={{ gap: 4 }}><b>{s.name}</b><span className="small muted">{s.detail}</span></div>)}</Panel>}
            <div className="stack">
              {r.tailwinds.length > 0 && <Panel title="Tailwinds"><ul className="bullets small">{r.tailwinds.map((t) => <li key={t} className="pos-dot">{t}</li>)}</ul></Panel>}
              {r.risks.length > 0 && <Panel title="Risks"><ul className="bullets small">{r.risks.map((t) => <li key={t} className="neg-dot">{t}</li>)}</ul></Panel>}
            </div>
          </div>
          <p className="hint">Written by AI from its general knowledge: check the numbers at the source before relying on them.</p>
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
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <Header eyebrow={`Market pulse · ${REGION_NAME[region]}`} title="How the market feels today" sub="Live index levels and headlines, with an AI read of the mood, what's moving and where money is flowing." />
      <section className="card"><IndexStrip indices={data?.indices ?? null} /></section>
      <section className="card stack" style={{ gap: 12 }}>
        <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
          <h2 className="h2 row" style={{ gap: 0 }}>The mood<Info>{HELP.researchPulse}</Info></h2>
          <span className="row small muted" style={{ gap: 10 }}>{ai && `Written ${ago(new Date(ai.generated_at * 1000).toISOString())}`}
            <button className="btn quiet sm" disabled={busy} onClick={() => loadAI(true)}>{busy ? "Reading…" : "Refresh"}</button></span>
        </div>
        {aiErr ? <p className="small" style={{ color: "var(--orange-ink)" }}>{aiErr}</p>
          : !ai ? <div className="row muted" style={{ gap: 10 }}><span className="spinner" />Reading the tape…</div>
            : ai.tone ? <p className="serif" style={{ fontSize: 20, lineHeight: 1.5 }}>{ai.tone}</p>
              : <p className="small muted">No AI read of today's mood yet. Press Refresh to write one.</p>}
      </section>
      {ai && (ai.hot.length > 0 || ai.flows.length > 0) && (
        <div className="grid2">
          {ai.hot.length > 0 && <Panel title="In today's headlines">
            {ai.hot.map((h) => (
              <div key={h.ticker + h.name} className="stack" style={{ gap: 4, paddingBottom: 10, borderBottom: "1px solid var(--line)" }}>
                <span><b>{h.name}</b> {h.ticker && <Link className="num small" to={`/research/${region}/${encodeURIComponent(h.ticker)}`}>{h.ticker} →</Link>}</span>
                <span className="small muted">{h.why}</span>
              </div>
            ))}
          </Panel>}
          {ai.flows.length > 0 && <Panel title="Where money is flowing">
            {ai.flows.map((f) => (
              <div key={f.title} className="stack" style={{ gap: 4, paddingBottom: 10, borderBottom: "1px solid var(--line)" }}>
                <span className="row" style={{ gap: 8 }}><b>{f.title}</b><span className={`badge ${f.direction === "INFLOW" ? "next" : f.direction === "OUTFLOW" ? "fail" : "skip"}`}>{f.direction.toLowerCase()}</span></span>
                <span className="small muted">{f.detail}</span>
              </div>
            ))}
          </Panel>}
        </div>
      )}
      {ai && ai.themes.length > 0 && (
        <Panel title="Themes in play" span="full">
          <div className="idea-grid">
            {ai.themes.map((t) => (
              <Link key={t.theme} className="idea-card" to={`/research/themes?region=${region}&q=${encodeURIComponent(t.theme)}`} style={{ textDecoration: "none", color: "inherit" }}>
                <b>{t.theme}</b><span className="small muted">{t.detail}</span>{t.example && <span className="tiny" style={{ color: "var(--blue-ink)" }}>e.g. {t.example}</span>}
              </Link>
            ))}
          </div>
        </Panel>
      )}
      {data && <Panel title="Headlines" span="full"><NewsList items={data.headlines} limit={14} /></Panel>}
    </div>
  );
}

/* ================= Compare ================= */
export function ComparePage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const a = params.get("a") ?? "", b = params.get("b") ?? "";
  const [res, setRes] = useState<{ a: Company; b: Company; ai: CompareAI } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const setSide = (k: "a" | "b", v: string) => { const p = new URLSearchParams(params); p.set(k, v); p.set("region", region); setParams(p); };
  useEffect(() => {
    if (!a || !b) { setRes(null); return; }
    let live = true;
    setRes(null); setError(null);
    researchApi.compare(region, a, b).then((x) => live && setRes(x)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [a, b, region]);
  const Pick = ({ k, v }: { k: "a" | "b"; v: string }) => (
    <div className="stack" style={{ gap: 6, flex: "1 1 260px" }}>
      <span className="label">{k === "a" ? "First company" : "Second company"}{v && <b style={{ marginLeft: 8 }}>{v}</b>}</span>
      <CompanySearch region={region} onPick={(s) => setSide(k, s)} placeholder={v ? `Change ${v}…` : k === "a" ? "First company, e.g. TCS" : "Second company, e.g. Infosys"} />
    </div>
  );
  const rows = (c: Company) => Object.fromEntries(c.metrics.flatMap((g) => g.items.map((i) => [i.label, i])));
  const labels = res ? Array.from(new Set([...res.a.metrics, ...res.b.metrics].flatMap((g) => g.items.map((i) => i.label)))) : [];
  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <Header eyebrow={`Compare · ${REGION_NAME[region]}`} title="Two companies, side by side" sub="Pick two companies to line up their numbers, with an AI summary of where they differ." />
      <div className="row wrap" style={{ gap: 16 }}><Pick k="a" v={a} /><Pick k="b" v={b} /></div>
      {error && <div className="banner">{error}</div>}
      {a && b && !res && !error && <Loading label={`Comparing ${a} and ${b}`} />}
      {res && (
        <>
          {res.ai && !res.ai.error && res.ai.verdict && (
            <section className="card stack" style={{ gap: 10 }}>
              <span className="eyebrow">AI comparison</span>
              <p className="serif" style={{ fontSize: 20, lineHeight: 1.45 }}>{res.ai.verdict}</p>
              {res.ai.differences.length > 0 && <ul className="bullets small">{res.ai.differences.map((d) => <li key={d}>{d}</li>)}</ul>}
            </section>
          )}
          {res.ai?.error && <p className="small muted">AI comparison unavailable: {res.ai.error}</p>}
          <div className="grid2">
            {([["a", res.a], ["b", res.b]] as const).map(([k, c]) => (
              <section key={k} className="card stack" style={{ gap: 12 }}>
                <div className="spread" style={{ alignItems: "flex-start", gap: 10 }}>
                  <div className="stack" style={{ gap: 2, minWidth: 0 }}><b className="serif" style={{ fontSize: 24 }}>{c.name}</b><span className="small muted">{c.symbol} · {bigMoney(c.market_cap, c.currency)}</span></div>
                  <Change q={c.quote} currency={c.currency} />
                </div>
                <div className="row wrap" style={{ gap: 8 }}>
                  <Link className="btn quiet sm" to={`/research/${region}/${encodeURIComponent(c.symbol)}`}>Open →</Link>
                  <StarButton region={region} symbol={c.symbol} name={c.name} />
                </div>
              </section>
            ))}
          </div>
          <section className="card" style={{ padding: 0 }}>
            <div className="table-wrap" style={{ margin: 0 }}>
              <table className="cmp-table">
                <thead><tr><th>Measure</th><th>{res.a.symbol}</th><th>{res.b.symbol}</th></tr></thead>
                <tbody>{labels.map((l) => {
                  const x = rows(res.a)[l], y = rows(res.b)[l];
                  const f = (m: typeof x, c: Company) => (m ? (m.unit.startsWith("%") ? `${m.value.toFixed(1)}%` : m.unit === "money" ? price(m.value, c.currency) : m.value.toFixed(2)) : "–");
                  return <tr key={l}><td>{l}</td><td className="num">{f(x, res.a)}</td><td className="num">{f(y, res.b)}</td></tr>;
                })}</tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

/* ================= Watchlist ================= */
export function WatchlistPage() {
  const [region, setRegion] = useRegion();
  const { items, toggle } = useWatchlist();
  const { fail } = useApp();
  const mine = (items ?? []).filter((w) => w.region === region);
  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <Header eyebrow={`Watchlist · ${REGION_NAME[region]}`} title="Companies you're watching" sub="Press Watch on any company page to add it. Saved to your account, so it's here on every device." />
      {items === null ? <Loading label="Opening your watchlist" /> : mine.length === 0 ? (
        <div className="card stack" style={{ gap: 12 }}><p className="muted">Nothing in your {REGION_NAME[region]} watchlist yet.</p><CompanySearch region={region} /></div>
      ) : (
        <>
          <QuoteGrid region={region} symbols={mine.map((w) => w.symbol)} names={Object.fromEntries(mine.map((w) => [w.symbol, w.name]))} />
          <div className="row wrap" style={{ gap: 8 }}>
            <AlertButton region={region} choices={mine.map((w) => ({ region: w.region, symbol: w.symbol }))} />
            {mine.map((w) => <button key={w.symbol} className="btn quiet sm" onClick={() => toggle(w).catch(fail)}>Remove {w.symbol}</button>)}
          </div>
        </>
      )}
    </div>
  );
}

/* ---------- Stage 2 + Supertrend scan (Basic and up) ---------- */
interface ScanRow {
  id: string; symbol: string; name: string | null; currency: string | null; price: number; chg: number | null;
  stage: number | null; stage_days: number | null; st_up: boolean; st_days: number; signal: "fresh" | "st_s2" | "stage2" | null;
}
interface ScanOut { name: string; market: Region; rows: ScanRow[]; missing: string[]; problems: string[]; counts: Record<string, number> }
interface ScanSets { sets: { id: string; name: string; count: number }[]; alerts: boolean; template: unknown; fresh_days: number; rotation_sets?: { id: string; name: string }[] }

const STAGE_NAME: Record<number, string> = { 1: "Stage 1 · basing", 2: "Stage 2 · advancing", 3: "Stage 3 · topping", 4: "Stage 4 · declining" };
const SIGNAL: Record<string, [string, string]> = {
  fresh: ["Fresh ST S2", "pass"], st_s2: ["In ST S2", "pass"], stage2: ["Stage 2, Supertrend down", "warn"],
};

export function ScanPage() {
  const [region, setRegion] = useRegion();
  const { fail, notify, refreshNotebooks, me } = useApp();
  const nav = useNavigate();
  const [sets, setSets] = useState<ScanSets | null>(null);
  const [setId, setSetId] = useState(() => new URLSearchParams(window.location.search).get("set") || "watchlist");
  const [out, setOut] = useState<ScanOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [only, setOnly] = useState(false);
  const pro = !!me?.plan_info?.features?.scans;

  useEffect(() => {
    setOut(null);
    api<ScanSets>(`/research/scan/sets?region=${region}`).then((s) => {
      setSets(s);
      setSetId((cur) => s.sets.some((x) => x.id === cur && (x.id !== "watchlist" || x.count)) ? cur : (s.sets.find((x) => x.id !== "watchlist" || x.count)?.id ?? "watchlist"));
    }).catch(fail);
  }, [region, fail]);

  const runScan = async () => {
    setBusy(true);
    try { setOut(await api<ScanOut>("/research/scan", { method: "POST", body: { region, set: setId } })); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const toggleAlerts = async () => {
    if (!sets) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/scan/alerts", { method: "PUT", body: { on: !sets.alerts } });
      setSets({ ...sets, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message after each close when a watchlist stock gives an ST S2 signal." : "ST S2 alerts off.");
    } catch (e) { fail(e); }
  };
  const testIt = async () => {
    if (!out || !sets) return;
    const members = out.rows.map((r) => ({ id: r.id, symbol: r.symbol }));
    if (members.length < 2) { notify("A group test needs at least two stocks."); return; }
    try {
      const nb = await api<{ id: string }>("/notebooks", { method: "POST", body: {
        name: `ST S2 on ${out.name}`.slice(0, 80), question: "Does Stage 2 + Supertrend work on this group?",
        strategy: sets.template, group: { id: setId, name: out.name.slice(0, 60), market: region, members: members.slice(0, 50), maxOpen: 5 } } });
      await refreshNotebooks();
      nav(`/n/${nb.id}`);
    } catch (e) { fail(e); }
  };

  const rows = (out?.rows ?? []).filter((r) => !only || r.signal === "fresh" || r.signal === "st_s2");
  const cur = sets?.sets.find((s) => s.id === setId);
  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <Header eyebrow={`Scan · ${REGION_NAME[region]}`} title="Stage 2 + Supertrend"
        sub="Which stocks are in Stage 2 (the price above a rising 150-day average) and have the Supertrend pointing up (a line that follows the price and flips when the trend turns). Both together are called ST S2 here. Facts from the charts, not advice." />
      {!pro && <div className="banner"><span>The Stage 2 + Supertrend scan and its alert are on the Basic plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>}
      <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
        <span className="chip-select"><select aria-label="Group to scan" value={setId} onChange={(e) => { setSetId(e.target.value); setOut(null); }}>
          {(sets?.sets ?? []).map((s) => <option key={s.id} value={s.id} disabled={s.id === "watchlist" && !s.count}>{s.name} ({s.count})</option>)}
        </select></span>
        <button className="btn" disabled={busy || !pro || !cur?.count} onClick={runScan}>{busy ? "Scanning…" : "Scan"}</button>
        {sets && <label className="row small" style={{ gap: 8, marginLeft: "auto" }}>
          <input type="checkbox" checked={sets.alerts} disabled={!pro} onChange={toggleAlerts} />
          Alert me after each close when a watchlist stock newly meets both (ST S2)
          <Info>{"Checked once a day after the market closes, for the stocks in your watchlist. Sent by phone notification, Telegram or email, whichever you set up on the Account page."}</Info>
        </label>}
      </div>
      {cur && cur.id === "watchlist" && !cur.count && <p className="small muted">Your {REGION_NAME[region]} watchlist is empty. Press Watch on company pages to add stocks, or scan a ready-made group.</p>}
      {!out && !busy && pro && !!cur?.count && <p className="small muted">Pick a group and press Scan to see each stock's stage and Supertrend direction.</p>}
      {busy && <Loading label="Reading each stock's daily chart" />}
      {out && !busy && (
        <section className="card stack" style={{ gap: 12 }}>
          <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
            <div className="stack" style={{ gap: 2 }}>
              <b>{out.name}</b>
              <span className="small muted">{out.counts.fresh} fresh ST S2 (Supertrend turned up in the last {sets?.fresh_days ?? 5} days) · {out.counts.st_s2} already in ST S2 · {out.counts.stage2} in Stage 2 only</span>
            </div>
            <div className="row wrap" style={{ gap: 8 }}>
              <label className="row small" style={{ gap: 6 }}><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} />Only ST S2</label>
              <button className="btn quiet sm" onClick={testIt}>Backtest ST S2 on this group</button>
            </div>
          </div>
          {rows.length === 0 ? <p className="small muted">Nothing matches right now.</p> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Stock</th><th className="num">Price</th><th>Stage</th><th>Supertrend</th><th>Signal</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.id}>
                  <td><Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}`}>{r.symbol}</Link>{r.name && r.name !== r.symbol && <div className="tiny muted">{r.name}</div>}
                    {(region === "IN" || region === "US") && <Link className="link tiny" to={`/research/${region}/${encodeURIComponent(r.symbol)}/deep`}>Deep dive →</Link>}</td>
                  <td className="num">{price(r.price, r.currency ?? (region === "IN" ? "INR" : "USD"))}<div className={`tiny ${signClass(r.chg)}`}>{r.chg == null ? "" : pct(r.chg, 2)}</div></td>
                  <td>{r.stage ? STAGE_NAME[r.stage] : "–"}{r.stage_days ? <div className="tiny muted">{r.stage_days} day{r.stage_days === 1 ? "" : "s"}</div> : null}</td>
                  <td>{r.st_up ? "Up" : "Down"}<div className="tiny muted">for {r.st_days} day{r.st_days === 1 ? "" : "s"}</div></td>
                  <td>{r.signal ? <span className={`badge ${SIGNAL[r.signal][1]}`}>{SIGNAL[r.signal][0]}</span> : <span className="tiny muted">–</span>}</td>
                </tr>))}</tbody>
            </table></div>
          )}
          {(out.missing.length > 0 || out.problems.length > 0) && <p className="tiny muted">Skipped: {[...out.missing, ...out.problems].join(" · ")}</p>}
        </section>
      )}
      <p className="small muted" style={{ maxWidth: "80ch" }}>Stage uses the 150-day average and its 20-day slope; Supertrend uses 10 days and 3× the average daily range (ATR). Past signals don't predict future returns, and nothing here is investment advice.</p>
    </div>
  );
}

interface RotationOut {
  name: string; market: Region; benchmark: string; interval: "weekly" | "daily"; tail: number;
  rows: RotationRow[]; skipped: string[]; as_of: string | null; parent: { symbol: string; name: string } | null;
}

const ARROW = (deg: number | null) => deg == null ? "–" : ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"][Math.round(((deg + 360) % 360) / 45) % 8];

export function RotationPage() {
  const [region, setRegion] = useRegion();
  const { fail } = useApp();
  const [sets, setSets] = useState<ScanSets | null>(null);
  const [setId, setSetId] = useState("sectors");
  const [backTo, setBackTo] = useState<string | null>(null);        // the set a sector's stocks were opened from
  const [interval, setIv] = useState<"weekly" | "daily">("weekly");
  const [tail, setTail] = useState(4);
  const [askTail, setAskTail] = useState(4);
  const [picked, setPicked] = useState<Set<string> | null>(null);   // null = the default set (main sectors)
  const [focus, setFocus] = useState<string | null>(null);          // the slider settles before it asks the server
  const [out, setOut] = useState<RotationOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, animate] = useAnimate(out?.tail ?? tail);

  useEffect(() => {
    api<ScanSets>(`/research/scan/sets?region=${region}`).then(setSets).catch(fail);
  }, [region, fail]);

  useEffect(() => {
    const t = window.setTimeout(() => setAskTail(tail), 250);
    return () => window.clearTimeout(t);
  }, [tail]);

  useEffect(() => {
    let live = true;
    setBusy(true);
    api<RotationOut>(`/research/rotation?region=${region}&set=${encodeURIComponent(setId)}&interval=${interval}&tail=${askTail}`)
      .then((r) => { if (live) setOut(r); }).catch((e) => { if (live) { setOut(null); fail(e); } })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [region, setId, interval, askTail, fail]);

  useEffect(() => { setPicked(null); setFocus(null); }, [region, setId]);

  const groups = (sets?.sets ?? []).filter((s) => s.count >= 2);
  const indexSets = sets?.rotation_sets ?? [{ id: "sectors", name: region === "IN" ? "NSE sector indices" : "S&P 500 sectors" }];
  const isIndex = indexSets.some((x) => x.id === setId);
  const drilled = setId.startsWith("sector:");
  const openStocks = (r: RotationRow) => { setBackTo(setId); setSetId(`sector:${r.symbol}`); };
  const all = out?.rows ?? [];
  const isOn = (r: RotationRow) => (picked ? picked.has(r.id) : r.core !== false);
  const rows = all.filter(isOn);
  const toggle = (r: RotationRow) => {
    const next = new Set(all.filter(isOn).map((x) => x.id));
    if (next.has(r.id)) { next.delete(r.id); if (focus === r.id) setFocus(null); } else next.add(r.id);
    setPicked(next);
  };
  const names = (q: Quadrant, extra?: (r: RotationRow) => boolean) => all.filter((r) => r.quadrant === q && (!extra || extra(r))).map((r) => r.name);
  const entered = all.filter((r) => r.quadrant === "leading" && r.moved && r.moved !== "leading").map((r) => r.name);
  const unit = interval === "weekly" ? "week" : "day";
  const few = (xs: string[], n = 5) => !xs.length ? "none" : xs.length <= n + 1 ? xs.join(", ") : `${xs.slice(0, n).join(", ")} and ${xs.length - n} more`;
  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={(r) => { setRegion(r); setSetId("sectors"); setBackTo(null); }} />
      <Header eyebrow={`Rotation · ${REGION_NAME[region]}`} title="Sector rotation"
        sub="Where each sector (or stock) stands against the market, and which way it's moving. Right of centre = stronger than the benchmark; above centre = gaining pace. Most move clockwise through the four corners." />
      <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
        <span className="chip-select"><select aria-label="What to compare" value={setId} onChange={(e) => { setSetId(e.target.value); setBackTo(null); }}>
          <optgroup label="Indices">{indexSets.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</optgroup>
          {groups.length > 0 && <optgroup label="Stocks">{groups.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.count})</option>)}</optgroup>}
          {drilled && <option value={setId}>{out?.name ?? "A sector's stocks"}</option>}
        </select></span>
        <div className="seg" role="group" aria-label="Candle size">
          {(["weekly", "daily"] as const).map((v) => <button key={v} aria-pressed={interval === v} onClick={() => setIv(v)}>{v === "weekly" ? "Weekly" : "Daily"}</button>)}
        </div>
        <label className="row small" style={{ gap: 8 }}>
          Trail
          <input type="range" min={1} max={12} value={tail} onChange={(e) => setTail(+e.target.value)} aria-label="Trail length" />
          <span className="mono">{tail} {unit}{tail === 1 ? "" : "s"}</span>
        </label>
        <button className="btn quiet sm" disabled={!out || busy || step !== null || (out?.tail ?? 1) < 2} onClick={animate}>{step !== null ? "Playing…" : "Animate"}</button>
      </div>
      {drilled && (
        <button className="link small" style={{ alignSelf: "flex-start", background: "none", border: 0, padding: 0, cursor: "pointer" }}
          onClick={() => { setSetId(backTo ?? "sectors"); setBackTo(null); }}>← Back to {indexSets.find((x) => x.id === (backTo ?? "sectors"))?.name ?? "sectors"}</button>
      )}
      {busy && !out && <Loading label="Comparing each one with the market" />}
      {out && (
        <section className="card stack" style={{ gap: 14, opacity: busy ? 0.6 : 1 }}>
          <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
            <div className="stack" style={{ gap: 2 }}>
              <b>{out.name} vs {out.benchmark}</b>
              <span className="small muted">{rows.length} of {all.length} shown · {out.interval === "weekly" ? "weekly" : "daily"} closes{out.as_of ? ` to ${out.as_of}` : ""}{step !== null ? ` · replaying ${unit} ${step} of ${out.tail}` : ""}</span>
            </div>
            <div className="rot-legend" aria-label="Legend">
              {QUADRANTS.map((q) => <span key={q.id} title={q.says}><QuadrantTag q={q.id} /></span>)}
            </div>
          </div>
          {all.length > 0 && (
            <div className="rot-read">
              {([["leading", `Leading: stronger than ${drilled && out.parent ? out.parent.name : "the market"} and still gaining`], ["improving", "Improving: weaker, but picking up"],
                 ["weakening", "Weakening: stronger, but losing pace"], ["lagging", "Lagging: weaker and still slipping"]] as [Quadrant, string][]).map(([q, says]) => (
                <div key={q}><QuadrantTag q={q} /><span className="muted small">{says.split(": ")[1]}</span>
                  <span className="small">{few(names(q))}</span></div>
              ))}
              {entered.length > 0 && <p className="small" style={{ margin: 0 }}>Moved into Leading over the last {out.tail} {unit}s: <b>{few(entered)}</b></p>}
            </div>
          )}
          {rows.length === 0 ? <p className="small muted">{all.length ? "Tick a few below to draw them." : "Not enough price history to draw this yet."}</p>
            : <RotationChart rows={rows} benchmark={out.benchmark} step={step} focus={focus} onFocus={setFocus} />}
          {all.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>Each dot is where it is now; the faint line is where it came from. Hover or tap a dot, or a row below, to follow one.</p>}
          {all.length > 0 && (
            <div className="row wrap small" style={{ gap: 8 }}>
              <button className="btn quiet sm" onClick={() => setPicked(new Set(all.map((r) => r.id)))}>Show all {all.length}</button>
              {all.some((r) => r.core === false) && <button className="btn quiet sm" onClick={() => setPicked(null)}>Main sectors only</button>}
              <button className="btn quiet sm" onClick={() => setPicked(new Set())}>Clear</button>
            </div>
          )}
          {all.length > 0 && (
            <div className="table-wrap"><table>
              <thead><tr><th style={{ width: 36 }}><span className="sr-only">Show on chart</span></th><th>{isIndex ? "Index" : "Stock"}</th><th>Now</th><th className="num">Strength</th><th className="num">Momentum</th><th>Heading</th><th>{out.tail} {unit}s ago</th></tr></thead>
              <tbody>{all.map((r) => (
                <tr key={r.id} className={focus === r.id ? "rot-row on" : "rot-row"} onClick={() => isOn(r) && setFocus(focus === r.id ? null : r.id)}>
                  <td onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={isOn(r)} onChange={() => toggle(r)} aria-label={`Show ${r.name} on the chart`} /></td>
                  <td>{isIndex
                    ? <span className="row" style={{ gap: 10, justifyContent: "space-between" }}>{r.name}
                        {(r.stocks ?? 0) > 0 && <button className="btn quiet sm" onClick={(e) => { e.stopPropagation(); openStocks(r); }} title={`Its ${r.stocks} main stocks against the ${r.name} index`}>Stocks →</button>}</span>
                    : <Link className="link" onClick={(e) => e.stopPropagation()} to={`/research/${region}/${encodeURIComponent(r.name)}`}>{r.name}</Link>}</td>
                  <td><QuadrantTag q={r.quadrant} /></td>
                  <td className="num mono">{r.x.toFixed(2)}</td>
                  <td className="num mono">{r.y.toFixed(2)}</td>
                  <td aria-label={r.heading == null ? "no move" : `${Math.round(r.heading)} degrees`}>{ARROW(r.heading)}</td>
                  <td>{r.moved ? (r.moved === r.quadrant ? <span className="small muted">same</span> : <QuadrantTag q={r.moved} />) : "–"}</td>
                </tr>))}</tbody>
            </table></div>
          )}
          {out.skipped.length > 0 && <p className="tiny muted">Skipped (not enough history or not available): {out.skipped.join(" · ")}</p>}
        </section>
      )}
      <p className="small muted" style={{ maxWidth: "80ch" }}>
        {drilled && out?.parent ? `Here each stock is measured against the ${out.parent.name} index itself, so Leading means it's beating its own sector. These are the sector's largest stocks, not its full official list. ` : ""}
        Strength: each one's price divided by {drilled && out?.parent ? `the ${out.parent.name} index` : region === "IN" ? "the Nifty 500" : "the S&P 500"}, compared with its own last 14 {unit}s (100 = its usual level). Momentum: the same for the change in that strength. StratLab's own calculation. Where something sits today doesn't predict where it goes next, and nothing here is investment advice.
      </p>
    </div>
  );
}

/* ---------- Results calendar ---------- */
interface ResultNumber { label: string; value: string }
export interface ResultRow {
  region: Region; symbol: string; name: string | null; date: string; when: string | null; purpose: string; url: string | null;
  mine?: boolean; out?: { at: string; title: string; url: string | null; numbers: ResultNumber[] } | null;
}
interface ResultsView {
  region: Region; scope: "mine" | "all"; today: string; updated_at: string | null; more: number; mine_count: number; alerts: boolean; note: string;
  weeks: { label: string; from: string; to: string; rows: ResultRow[] }[];
}

/** "Thu 15 Oct", from an ISO date, without the browser's time zone moving it a day. */
export function resultDay(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

function ResultLine({ r, showMine }: { r: ResultRow; showMine: boolean }) {
  return (
    <div className="result-row">
      <span className="row wrap" style={{ gap: 8 }}>
        <Link className="btn quiet sm" to={`/research/${r.region}/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
        {r.name && <span className="small muted">{r.name}</span>}
        {showMine && r.mine && <span className="badge">Yours</span>}
      </span>
      <span className="small">{r.purpose}{r.when ? `, ${r.when}` : ""}</span>
      {r.out && (
        <span className="small">
          Results filed {resultDay(r.out.at)}{r.out.url ? <>: <a className="link" href={safeHref(r.out.url)} target="_blank" rel="noopener noreferrer">{r.out.title} ↗</a></> : `: ${r.out.title}`}
          {r.out.numbers.length > 0 && <span className="muted"> · {r.out.numbers.map((n) => `${n.label} ${n.value}`).join(" · ")} (as stated)</span>}
        </span>
      )}
    </div>
  );
}

export function ResultsPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const scope = params.get("scope") === "all" ? "all" : "mine";
  const { fail, notify } = useApp();
  const [q, setQ] = useState("");
  const [data, setData] = useState<ResultsView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    const t = setTimeout(() => {
      const qs = new URLSearchParams({ region, scope, q: scope === "all" ? q : "" });
      api<ResultsView>(`/research/results?${qs}`).then((x) => live && setData(x)).catch((e) => live && setError((e as Error).message));
    }, q ? 300 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [region, scope, q]);

  const setScope = (s: "mine" | "all") => { const p = new URLSearchParams(params); p.set("scope", s); setParams(p, { replace: true }); };
  const toggleAlerts = async () => {
    if (!data) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/results/alerts", { method: "PUT", body: { on: !data.alerts } });
      setData({ ...data, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message on the morning of each results day for your stocks, and when the results are filed." : "Results messages off.");
    } catch (e) { fail(e); }
  };
  const empty = data && data.weeks.every((w) => w.rows.length === 0);

  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <Header eyebrow={`Results calendar · ${REGION_NAME[region]}`} title="Results this week and next"
        sub={region === "IN" ? "Board meetings companies have called to consider their financial results, from their filings with the exchange."
          : "The dates US companies have set for their quarterly results, and the earnings release once it's filed."} />
      <div className="row wrap" style={{ gap: 12 }}>
        <div className="seg" role="radiogroup" aria-label="Which companies">
          <button role="radio" aria-checked={scope === "mine"} aria-pressed={scope === "mine"} onClick={() => setScope("mine")}>My stocks</button>
          <button role="radio" aria-checked={scope === "all"} aria-pressed={scope === "all"} onClick={() => setScope("all")}>All companies</button>
        </div>
        {scope === "all" && <input className="input" style={{ flex: "1 1 200px", maxWidth: 320 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a company" aria-label="Find a company" />}
      </div>
      {data && (
        <label className="row small" style={{ gap: 8 }}>
          <input type="checkbox" checked={data.alerts} onChange={toggleAlerts} />
          Message me on the morning of a results day for my stocks, and when the results are filed
          <Info>Sent by phone notification or Telegram, whichever you set up on the Account page. If you get the My Stocks newsletter, it lists the week's results dates too.</Info>
        </label>
      )}
      {error && <p className="small muted">{error}</p>}
      {!data && !error && <Loading label="Opening the results calendar" />}
      {data && empty && (
        <div className="card stack" style={{ gap: 10 }}>
          <p className="muted">{scope === "mine"
            ? (data.mine_count ? `None of your ${REGION_NAME[region]} stocks has a results date in these two weeks.` : `You have no ${REGION_NAME[region]} stocks yet: they come from your watchlist, notebooks and paper sessions.`)
            : q ? "No company by that name has a results date in these two weeks." : "No results dates announced for these two weeks yet."}</p>
          {scope === "mine" && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setScope("all")}>See all companies</button>}
        </div>
      )}
      {data && !empty && data.weeks.map((w) => {
        const days = [...new Set(w.rows.map((r) => r.date))];
        const ahead = days.filter((d) => d >= data.today), past = days.filter((d) => d < data.today);     // the days gone by fold away
        const day = (d: string) => (
          <div key={d} className="stack" style={{ gap: 8 }}>
            <span className="eyebrow">{resultDay(d)}{d === data.today ? " · today" : ""}</span>
            {w.rows.filter((r) => r.date === d).map((r) => <ResultLine key={`${r.symbol}-${r.date}`} r={r} showMine={scope === "all"} />)}
          </div>
        );
        return (
          <section key={w.label} className="card stack" style={{ gap: 14 }}>
            <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
              <h2 className="h3">{w.label}</h2>
              <span className="small muted">{resultDay(w.from)} to {resultDay(w.to)}</span>
            </div>
            {days.length === 0 ? <span className="small muted">Nothing announced for this week yet.</span>
              : ahead.length ? ahead.map(day) : <span className="small muted">Nothing left this week.</span>}
            <Earlier label="Earlier this week" count={w.rows.filter((r) => r.date < data.today).length} className="in-card">
              {past.map(day)}
            </Earlier>
          </section>
        );
      })}
      {data && data.more > 0 && <p className="tiny muted">And {data.more} more. Find a company by name to narrow the list.</p>}
      {data && <p className="small muted" style={{ maxWidth: "80ch" }}>{data.note}{data.updated_at ? ` Updated ${ago(data.updated_at)}.` : ""}</p>}
    </div>
  );
}

interface FilingsOverview {
  rows: { symbol: string; summary: FilingSummary; flags: FilingItem[] }[]; problems: string[]; days: number; alerts: boolean; send_at: string;
}

export function FilingsPage() {
  const { fail, notify, me } = useApp();
  const pro = !!me?.plan_info?.features?.filings;
  const [data, setData] = useState<FilingsOverview | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!pro) return;
    setBusy(true);
    api<FilingsOverview>("/research/filings").then(setData).catch(fail).finally(() => setBusy(false));
  }, [pro, fail]);

  const toggleAlerts = async () => {
    if (!data) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/filings/alerts", { method: "PUT", body: { on: !data.alerts } });
      setData({ ...data, alerts: r.alerts });
      notify(r.alerts ? `You'll get a message each evening (${data.send_at} IST) when a watchlist stock files a red flag.` : "Filing alerts off.");
    } catch (e) { fail(e); }
  };

  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region="IN" />
      <Header eyebrow="Red flags · India" title="Filings and red flags"
        sub="What your watchlist companies told the exchange in the last 3 months: fund raises (QIP, preferential, rights, warrants), promoter pledges, auditor and director resignations, defaults, regulator action and rating downgrades." />
      {!pro && <div className="banner"><span>Red flags for your whole watchlist, with an evening alert, are on the Basic plan. Each company's own page shows its red flags on every plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>}
      {data && (
        <label className="row small" style={{ gap: 8 }}>
          <input type="checkbox" checked={data.alerts} onChange={toggleAlerts} />
          Message me each evening when a watchlist stock files a red flag or something to look closer at
          <Info>{`Checked once a day at ${data.send_at} IST, for the India stocks in your watchlist. Sent by phone notification, Telegram or email, whichever you set up on the Account page.`}</Info>
        </label>
      )}
      {busy && <Loading label="Reading each company's filings" />}
      {data && !busy && (data.rows.length === 0 && data.problems.length === 0
        ? <div className="card dashed stack" style={{ gap: 10, alignItems: "flex-start" }}><p className="muted">Your watchlist has no India stocks yet. Open a company and press <b>Watch</b>: its filings show up here.</p><Link to="/research?region=IN" className="btn sm">Find a company</Link></div>
        : (
          <div className="stack" style={{ gap: 14 }}>
            {data.rows.map((r) => (
              <section key={r.symbol} className="card stack" style={{ gap: 10 }}>
                <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
                  <span className="row" style={{ gap: 12 }}>
                    <Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}#filings`}><b>{r.symbol}</b></Link>
                    <Link className="link tiny" to={`/research/IN/${encodeURIComponent(r.symbol)}/deep`}>Deep dive →</Link>
                  </span>
                  <SummaryLine s={r.summary} />
                </div>
                {r.flags.length > 0 ? <div className="filings">{r.flags.map((i) => <FilingRow key={i.id} i={i} />)}</div>
                  : <span className="tiny muted">Nothing flagged in the last {data.days} days.</span>}
              </section>
            ))}
            {data.problems.length > 0 && <p className="tiny muted">Couldn't read: {data.problems.join(" · ")}</p>}
          </div>
        ))}
      <p className="small muted" style={{ maxWidth: "80ch" }}>From the companies' own filings with the exchange. Labels come from fixed keyword rules; a label is a reason to read the filing, not a verdict on the company, and nothing here is investment advice.</p>
    </div>
  );
}
