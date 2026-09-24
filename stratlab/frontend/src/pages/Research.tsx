import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { ago, pct, price, signClass } from "../lib/format";
import { HELP } from "../lib/help";
import {
  REGION_NAME, STARTER_TICKERS, THEME_IDEAS, bigMoney, researchApi, saveRegion, savedRegion, useWatchlist,
  type Company, type CompareAI, type Idea, type IndexLevel, type NewsItem, type PulseAI, type Region, type SectorAI,
} from "../lib/research";
import {
  AIRead, Analysts, Change, Composite, CompanySearch, EarningsBars, MarginCascade, MetricsGrid, NewsList, Panel, PriceChart,
  QuarterTable, QuoteGrid, Rail52, ResearchNav, Shareholding, SourcesNote, StarButton, TrendBars, ValuationGauge,
} from "../components/Research";
import { Info, Loading } from "../components/ui";

function useRegion(): [Region, (r: Region) => void] {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("region")?.toUpperCase();
  const [region, setRegionState] = useState<Region>(fromUrl === "US" || fromUrl === "IN" ? fromUrl : savedRegion());
  const setRegion = (r: Region) => {
    setRegionState(r); saveRegion(r);
    const p = new URLSearchParams(params); p.set("region", r); setParams(p, { replace: true });
  };
  return [region, setRegion];
}

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
      <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>{title}</h1>
      {sub && <p className="muted" style={{ fontSize: 17, maxWidth: 760 }}>{sub}</p>}
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
          <span className={`small num ${signClass(i.change_pct)}`}>{pct(i.change_pct, 2)} today
            {i.from_high_pct != null && <span className="muted"> · {i.from_high_pct > -0.5 ? "near its 52-week high" : `${Math.abs(i.from_high_pct).toFixed(1)}% below its high`}</span>}</span>
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
  const { fail } = useApp();
  const test = useTestOnStratLab();
  const [c, setC] = useState<Company | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setC(null); setError(null);
    researchApi.company(region, sym).then((x) => live && setC(x)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [region, sym, fail]);

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
            {c.market_cap != null && <span className="small muted">Market value {bigMoney(c.market_cap, ccy)}{c.next_earnings ? ` · Next results ${c.next_earnings.date}` : ""}</span>}
          </div>
          <Change q={c.quote} currency={ccy} />
        </div>
        <div className="toolbar">
          {c.testable && <button className="btn blue sm" onClick={() => test(c)}>Test a strategy on {c.symbol} →</button>}
          <StarButton region={region} symbol={c.symbol} name={c.name} />
          <Link className="btn quiet sm" to={`/research/compare?region=${region}&a=${c.symbol}`}>Compare</Link>
          {c.links.map((l) => <a key={l.url} className="btn quiet sm" href={l.url} target="_blank" rel="noopener noreferrer">{l.label} ↗</a>)}
          {c.website && <a className="btn quiet sm" href={c.website} target="_blank" rel="noopener noreferrer">Website ↗</a>}
        </div>
      </section>
      <SourcesNote sources={c.sources} />
      <section className="card"><PriceChart region={region} symbol={c.symbol} currency={ccy} /></section>

      <div className="rs-grid">
        {(wiki || c.about.profile) && (
          <Panel title="What they do" info="From Wikipedia and the company's own profile: facts, not AI.">
            {wiki?.description && <p className="serif" style={{ fontSize: 18 }}>{wiki.description}</p>}
            <p className="small" style={{ lineHeight: 1.65 }}>{wiki?.extract || c.about.profile}</p>
            {wiki && c.about.profile && <p className="small muted" style={{ lineHeight: 1.6 }}>{c.about.profile}</p>}
            <div className="row wrap small" style={{ gap: 14 }}>{c.facts.map((f) => <span key={f.label}><span className="muted">{f.label}</span> <b>{f.value}</b></span>)}</div>
            {wiki && <a className="link small" href={wiki.url} target="_blank" rel="noopener noreferrer">More on Wikipedia ↗</a>}
          </Panel>
        )}
        {c.range52.low != null && <Panel title="Where the price sits" info={HELP.research52}><Rail52 q={c.quote} low={c.range52.low} high={c.range52.high} currency={ccy} /></Panel>}
        {c.margins && c.margins.gross != null && <Panel title="Where a sale goes" info={HELP.researchMargins}><MarginCascade {...c.margins} /></Panel>}
        {c.analysts && <Panel title="What analysts say"><Analysts a={c.analysts} /></Panel>}
      </div>

      {c.metrics.length > 0 && (
        <Panel title="Key numbers" info={HELP.researchMetrics} span="full">
          <MetricsGrid groups={c.metrics} currency={ccy} industry={c.industry} />
        </Panel>
      )}

      <div className="rs-grid">
        {c.trend && (
          <Panel title="Sales and profit, by year">
            <TrendBars points={c.trend.revenue} label={c.trend.revenue_label} unit={c.trend.unit} />
            <TrendBars points={c.trend.profit} label={c.trend.profit_label} unit={c.trend.unit} tone="blue" />
          </Panel>
        )}
        {c.earnings.length > 1 && <Panel title="Results versus expectations" info={HELP.researchEarnings}><EarningsBars rows={c.earnings} /></Panel>}
        {c.shareholding && c.shareholding.rows.length > 0 && <Panel title="Who owns it" info={HELP.researchHolding}><Shareholding s={c.shareholding} /></Panel>}
        {((c.pros?.length ?? 0) > 0 || (c.cons?.length ?? 0) > 0) && (
          <Panel title="Strengths and concerns" info="Automatic checks from Screener.in's data.">
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

      {c.quarters && c.quarters.cols.length > 0 && <Panel title="Last quarters" span="full"><QuarterTable q={c.quarters} /></Panel>}

      <AIRead region={region} symbol={c.symbol} onTest={(i) => test(c, i)} />

      <div className="rs-grid">
        {c.peers.length > 0 && <Panel title="Similar companies" info="Companies in the same industry. Tap one to open it."><QuoteGrid region={region} symbols={c.peers} /></Panel>}
        <Panel title="Latest news"><NewsList items={c.news} /></Panel>
      </div>
      <p className="hint">Data from {Array.from(new Set(c.sources.filter((s) => s.ok).map((s) => s.source))).join(", ") || "public sources"}. Scores and AI text are estimates, not advice.</p>
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
      <Header eyebrow={`Themes · ${REGION_NAME[region]}`} title="Map a theme, find the shovels"
        sub="Type a sector or trend. The AI maps who's involved, where the money flows, and ranks the companies worth a closer look." />
      <form className="row" style={{ gap: 10 }} onSubmit={(e) => { e.preventDefault(); go(text); }}>
        <input className="input" style={{ flex: 1, minHeight: 52 }} value={text} onChange={(e) => setText(e.target.value)} placeholder={region === "IN" ? "India defence, railways capex…" : "AI data centers, grid electrification…"} aria-label="Theme" />
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
            <Panel title="Ranked: the companies to look at" info="The AI's ranking of who benefits most, with a 0-100 score. A shortlist to research and test, not a buy list." span="full">
              {r.screen.map((s, i) => (
                <div key={s.ticker + s.name} className="screen-row">
                  <span className="serif muted" style={{ fontSize: 22 }}>{i + 1}</span>
                  <Composite v={s.composite} size={28} />
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
            : <p className="serif" style={{ fontSize: 20, lineHeight: 1.5 }}>{ai.tone}</p>}
      </section>
      {ai && (
        <div className="grid2">
          <Panel title="Moving now">
            {ai.hot.map((h) => (
              <div key={h.ticker + h.name} className="stack" style={{ gap: 4, paddingBottom: 10, borderBottom: "1px solid var(--line)" }}>
                <span><b>{h.name}</b> {h.ticker && <Link className="num small" to={`/research/${region}/${encodeURIComponent(h.ticker)}`}>{h.ticker} →</Link>}</span>
                <span className="small muted">{h.why}</span>
              </div>
            ))}
          </Panel>
          <Panel title="Where money is flowing">
            {ai.flows.map((f) => (
              <div key={f.title} className="stack" style={{ gap: 4, paddingBottom: 10, borderBottom: "1px solid var(--line)" }}>
                <span className="row" style={{ gap: 8 }}><b>{f.title}</b><span className={`badge ${f.direction === "INFLOW" ? "next" : f.direction === "OUTFLOW" ? "fail" : "skip"}`}>{f.direction.toLowerCase()}</span></span>
                <span className="small muted">{f.detail}</span>
              </div>
            ))}
          </Panel>
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
      <CompanySearch region={region} onPick={(s) => setSide(k, s)} placeholder={v ? `Change ${v}…` : "Search…"} />
    </div>
  );
  const rows = (c: Company) => Object.fromEntries(c.metrics.flatMap((g) => g.items.map((i) => [i.label, i])));
  const labels = res ? Array.from(new Set([...res.a.metrics, ...res.b.metrics].flatMap((g) => g.items.map((i) => i.label)))) : [];
  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <Header eyebrow={`Compare · ${REGION_NAME[region]}`} title="Two companies, side by side" sub="Pick two companies to line up their numbers, with an AI verdict on which looks stronger and for whom." />
      <div className="row wrap" style={{ gap: 16 }}><Pick k="a" v={a} /><Pick k="b" v={b} /></div>
      {error && <div className="banner">{error}</div>}
      {a && b && !res && !error && <Loading label={`Comparing ${a} and ${b}`} />}
      {res && (
        <>
          {res.ai && !res.ai.error && res.ai.verdict && (
            <section className="card stack" style={{ gap: 10 }}>
              <span className="eyebrow">AI verdict{res.ai.winner && res.ai.winner !== "SPLIT" ? ` · edge: ${res.ai.winner}` : " · split"}</span>
              <p className="serif" style={{ fontSize: 20, lineHeight: 1.45 }}>{res.ai.verdict}</p>
              {res.ai.differences.length > 0 && <ul className="bullets small">{res.ai.differences.map((d) => <li key={d}>{d}</li>)}</ul>}
            </section>
          )}
          {res.ai?.error && <p className="small muted">AI verdict unavailable: {res.ai.error}</p>}
          <div className="grid2">
            {([["a", res.a], ["b", res.b]] as const).map(([k, c]) => (
              <section key={k} className="card stack" style={{ gap: 12 }}>
                <div className="spread" style={{ alignItems: "flex-start", gap: 10 }}>
                  <div className="stack" style={{ gap: 2, minWidth: 0 }}><b className="serif" style={{ fontSize: 24 }}>{c.name}</b><span className="small muted">{c.symbol} · {bigMoney(c.market_cap, c.currency)}</span></div>
                  <Change q={c.quote} currency={c.currency} />
                </div>
                {res.ai && !res.ai.error && <div className="row" style={{ gap: 18 }}><Composite v={res.ai[k].composite} size={34} /><div style={{ flex: 1 }}><ValuationGauge tag={res.ai[k].valuation} /></div></div>}
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
            {mine.map((w) => <button key={w.symbol} className="btn quiet sm" onClick={() => toggle(w).catch(fail)}>Remove {w.symbol}</button>)}
          </div>
        </>
      )}
    </div>
  );
}
