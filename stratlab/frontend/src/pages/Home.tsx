import { Explore } from "../components/Explore";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";
import { blankStrategy, parseStrategyText, riskForCurrency, STARTERS } from "../lib/rules";
import type { Instrument, Notebook } from "../lib/types";
import { HELP } from "../lib/help";
import { InstrumentSearch } from "../components/InstrumentSearch";
import { IdeaComposer, type Built } from "../components/IdeaComposer";
import { ImportStrategy } from "../components/ImportStrategy";
import { Pin, Search, Sparkle, Upload } from "../components/Icons";
import { Info, Loading, VerdictBadge } from "../components/ui";
import { CompanySearch } from "../components/CompanySearch";
import { askExamples, useRotating } from "../lib/rotating";
import { FirstSteps } from "../components/FirstSteps";
import { PromoCountdown } from "../components/PromoCountdown";

export type Where = { market: string; instrument: Instrument | null };

export function useCreateNotebook(where?: Where | null) {
  const nav = useNavigate();
  const loc = useLocation();
  const { refreshNotebooks, fail } = useApp();
  return async (b: Built) => {
    // what you picked above wins over what the idea text mentions
    const instrument = where?.instrument ?? (where?.market === "CSV" ? null : b.instrument);
    const strategy = instrument ? { ...b.strategy, risk: riskForCurrency(b.strategy.risk, instrument.currency) } : b.strategy;
    try {
      const nb = await api<Notebook>("/notebooks", {
        method: "POST",
        body: { name: strategy.name, question: b.question, strategy, instrument: instrument?.id ?? null },
      });
      if (b.group && !where?.instrument) {
        await api(`/notebooks/${nb.id}`, { method: "PUT", body: { group: b.group } });
      }
      await refreshNotebooks();
      if (new URLSearchParams(loc.search).get("then") === "group" && !b.group) nav(`/n/${nb.id}/market#group`);
      else if (where?.market === "CSV") nav(`/n/${nb.id}/market`, { state: { market: "CSV" } });
      else nav(`/n/${nb.id}`, { state: { gaps: { ...b.gaps, mentioned: instrument ? [...b.gaps.mentioned, "instrument"] : b.gaps.mentioned } } });
    } catch (e) {
      fail(e);
    }
  };
}

/** The big "type anything" bar: opens the search box, which works out what you mean and does it. */
function AskBar() {
  const { focus } = useApp();
  const example = useRotating(askExamples(focus));
  return (
    <button className="ask-bar" onClick={() => window.dispatchEvent(new Event("stratlab:search"))}>
      <Sparkle size={20} />
      <span className="stack" style={{ gap: 2, minWidth: 0 }}>
        <b>Ask or do anything</b>
        <span className="small muted ask-example" aria-live="off">Try: “{example}”</span>
      </span>
      <kbd className="small muted">{/Mac/.test(navigator.platform) ? "⌘K" : "Ctrl K"}</kbd>
    </button>
  );
}

/** Step 1 of a new notebook: the market and instrument to test on. */
function WhereToTest({ where, setWhere }: { where: Where; setWhere: (w: Where) => void }) {
  const { markets } = useApp();
  const usable = markets.filter((m) => m.status !== "soon");
  const soon = markets.filter((m) => m.status === "soon");
  const market = markets.find((m) => m.id === where.market);
  return (
    <section className="card stack" style={{ gap: 16 }} aria-labelledby="where-h">
      <h2 id="where-h" className="h2 row" style={{ gap: 0 }}>1. Where do you want to test it?<Info>{HELP.markets}</Info></h2>
      <div className="seg" role="radiogroup" aria-label="Market">
        {usable.map((m) => (
          <button key={m.id} role="radio" aria-checked={where.market === m.id} aria-pressed={where.market === m.id}
            onClick={() => setWhere({ market: m.id, instrument: null })}>
            {m.symbol === "+" ? "" : m.symbol + " "}{m.name}{m.status === "offline" ? " (offline)" : ""}
          </button>
        ))}
      </div>
      {soon.length > 0 && <p className="hint">Coming soon: {soon.map((m) => m.name).join(", ")}. Until then, use "Your own data" with a CSV.</p>}
      {where.market === "CSV" ? (
        <p className="small muted">You'll upload your CSV of candles right after the notebook is created.</p>
      ) : where.instrument ? (
        <div className="row wrap" style={{ gap: 10 }}>
          <span className="pill" style={{ fontSize: 15 }}>✓ {where.instrument.symbol} · {market?.name}</span>
          <button className="link" onClick={() => setWhere({ ...where, instrument: null })}>Pick another</button>
        </div>
      ) : market && market.status === "live" ? (
        <InstrumentSearch market={market} compact onPick={(i) => setWhere({ market: where.market, instrument: i })} />
      ) : market ? (
        <p className="small" style={{ color: "var(--orange-ink)" }}>{market.name} data is offline right now. Pick another market, or write your idea now and choose later.</p>
      ) : null}
      {!where.instrument && where.market !== "CSV" && <p className="hint">Optional: if your idea names a stock or coin, we'll find it for you.</p>}
    </section>
  );
}

function Starters({ where }: { where?: Where | null }) {
  const create = useCreateNotebook(where);
  const start = (i: number) => {
    const st = STARTERS[i];
    const p = parseStrategyText(st.text);
    const s = blankStrategy(st.title);
    create({
      strategy: { ...s, text: st.text, entry: p.entry, exit: p.exit, risk: { ...s.risk, ...p.risk } },
      instrument: null, question: st.question,
      gaps: { mentioned: ["exit", "tf", ...Object.keys(p.risk)], notes: [], instName: null, usedAI: true, fallback: "" },
    });
  };
  return (
    <div className="grid4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
      {STARTERS.map((st, i) => (
        <button key={st.title} className="card" style={{ textAlign: "left", cursor: "pointer", display: "flex", flexDirection: "column", gap: 6 }} onClick={() => start(i)}>
          <span className={`badge ${i < 2 ? "next" : "warn"}`} style={{ alignSelf: "flex-start" }}>{st.level}</span>
          <b style={{ fontSize: 16 }}>{st.title}</b>
          <span className="small muted">{st.why}</span>
        </button>
      ))}
    </div>
  );
}

const LAST_MARKET = "stratlab.lastMarket";

type Prefill = { market: string; symbol?: string; instrumentId?: string | null; text?: string };

/** When Research hands over a company (and maybe an idea), pick its market and instrument up front. A public company
 * page links here as /new?market=IN&symbol=RELIANCE. */
function usePrefill(setWhere: (w: Where) => void): Prefill | null {
  const loc = useLocation();
  const q = new URLSearchParams(loc.search);
  const market = (q.get("market") || "").toUpperCase(), symbol = q.get("symbol") || "";
  const prefill = (loc.state as { prefill?: Prefill } | null)?.prefill
    ?? (/^(IN|US)$/.test(market) && /^[A-Za-z0-9&.-]{1,20}$/.test(symbol) ? { market, symbol } : null);
  useEffect(() => {
    if (!prefill) return;
    let live = true;
    setWhere({ market: prefill.market, instrument: null });
    (async () => {
      let inst: Instrument | null = null;
      try {
        if (prefill.instrumentId) inst = await api<Instrument>(`/instruments/${encodeURIComponent(prefill.instrumentId)}`);
        else if (prefill.symbol) {
          const rows = await api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(prefill.symbol)}&market=${prefill.market}`);
          inst = rows.find((r) => r.symbol.toUpperCase() === prefill.symbol!.toUpperCase() && !r.fno) ?? null;
        }
      } catch { inst = null; }
      if (live && inst) setWhere({ market: prefill.market, instrument: inst });
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc.key]);
  return prefill;
}

export function NewNotebook() {
  const { markets } = useApp();
  const [where, setWhere] = useState<Where>({ market: "", instrument: null });
  const prefill = usePrefill(setWhere);
  const loc = useLocation();
  const [importing, setImporting] = useState(new URLSearchParams(loc.search).has("import"));
  const importRef = useRef<HTMLElement>(null);
  useEffect(() => { if (importing && new URLSearchParams(loc.search).has("import")) importRef.current?.scrollIntoView({ behavior: "smooth" }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (where.market || !markets.length) return;
    // start where you left off last time, if that market is usable
    let last = "";
    try { last = localStorage.getItem(LAST_MARKET) || ""; } catch { /* private mode */ }
    const usable = (id: string) => markets.some((m) => m.id === id && m.status !== "soon");
    setWhere({ market: usable(last) ? last : markets.find((m) => m.id === "IN" && m.status === "live") ? "IN" : "CRYPTO", instrument: null });
  }, [markets, where.market]);
  useEffect(() => { if (where.market) try { localStorage.setItem(LAST_MARKET, where.market); } catch { /* private mode */ } }, [where.market]);
  const create = useCreateNotebook(where);
  return (
    <div className="stack" style={{ gap: 28, maxWidth: 960, margin: "0 auto" }}>
      <div className="stack" style={{ gap: 10 }}>
        <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
          <span className="eyebrow">New notebook</span>
          <button className="btn outline sm" onClick={() => { setImporting(true); window.setTimeout(() => importRef.current?.scrollIntoView({ behavior: "smooth" }), 50); }}>
            <Upload size={16} />Import a strategy
          </button>
        </div>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 48px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          What trading idea do you want to test?
        </h1>
        <p className="muted" style={{ fontSize: 17 }}>Write it the way you'd explain it to a friend. We'll turn it into exact rules and ask about anything that's missing.</p>
        {new URLSearchParams(loc.search).get("then") === "group" && !prefill?.symbol && (
          <p className="edit-hint">Testing on a group: describe the rules here (or name the group, like "on NIFTY 50 stocks"). Next you'll pick the stocks or coins.</p>
        )}
        {prefill?.symbol ? (
          <p className="edit-hint">From Research: testing {prefill.text ? "an idea" : "a strategy"} on {prefill.symbol}. Check the rules below, then build.</p>
        ) : (
          <p className="small muted">Not sure what to test? <Link to="/research" className="link">Research a company first</Link>: its AI read suggests ideas you can test in one click.</p>
        )}
      </div>
      <AskBar />
      <ol className="how" aria-label="How StratLab works">
        <li><b>1. Describe it</b><span>In plain words. We turn it into rules you can read and edit.</span></li>
        <li><b>2. Test it honestly</b><span>On years of real prices, after real costs, with four checks for luck.</span></li>
        <li><b>3. Trade it on paper</b><span>If the verdict says the edge is real, watch it live with fake money.</span></li>
      </ol>
      <WhereToTest where={where} setWhere={setWhere} />
      <section className="card stack" style={{ gap: 14 }} aria-labelledby="idea-h">
        <h2 id="idea-h" className="h2">2. Describe your idea</h2>
        <IdeaComposer key={prefill?.text ?? ""} initial={prefill?.text ?? ""} onBuilt={create} market={where.market} symbol={where.instrument?.symbol} />
      </section>
      {importing && (
        <section ref={importRef} className="card stack" style={{ gap: 14 }} aria-labelledby="import-h">
          <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
            <h2 id="import-h" className="h2 row" style={{ gap: 10 }}><Upload size={20} />Import a strategy</h2>
            <button className="btn quiet sm" onClick={() => setImporting(false)}>Close</button>
          </div>
          <p className="small muted">A StratLab export, TradingView Pine Script, Python, MetaTrader, AmiBroker, or a written description. It becomes a notebook you can test like any other.</p>
          <ImportStrategy onBuilt={create} market={where.market} />
        </section>
      )}
      <div className="stack">
        <h2 className="h2">Or start from a classic idea</h2>
        <Starters where={where} />
      </div>
      <Explore title="More you can do" />
    </div>
  );
}

/** The home page for someone who came to invest: start from a company or a question, not from a trading rule. */
function InvestorStart() {
  const { notebooks } = useApp();
  const nav = useNavigate();
  const [region, setRegion] = useState<"IN" | "US">("IN");
  const quick: [string, string, string][] = [
    ["Sectors leading right now", "Which sectors are beating the market, and their stocks", "/research/rotation"],
    ["Stage 2 stocks in NIFTY 50", "Rising trend with the Supertrend up", "/research/scan?set=nifty50"],
    ["Red flags in my watchlist", "Fund raises, pledges, resignations, defaults", "/research/filings"],
    ["My watchlist at a glance", "Trend, sector, red flags and checklist for each", "/research/investor"],
  ];
  const popular = region === "IN" ? ["RELIANCE", "HDFCBANK", "TCS", "APOLLOHOSP", "TITAN", "LT"] : ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"];
  return (
    <div className="stack" style={{ gap: 28, maxWidth: 960, margin: "0 auto" }}>
      <div className="stack" style={{ gap: 10 }}>
        <span className="eyebrow">Your research desk</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 48px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          Which company do you want to look into?
        </h1>
        <p className="muted" style={{ fontSize: 17 }}>The numbers, the business in its own words, red flags and whether management delivers. Facts, not tips.</p>
      </div>
      <section className="card stack" style={{ gap: 14 }}>
        <div className="seg" role="radiogroup" aria-label="Market" style={{ alignSelf: "flex-start" }}>
          {(["IN", "US"] as const).map((r) => <button key={r} role="radio" aria-checked={region === r} aria-pressed={region === r} onClick={() => setRegion(r)}>{r === "IN" ? "₹ India" : "$ United States"}</button>)}
        </div>
        <CompanySearch region={region} autoFocus />
        <div className="row wrap" style={{ gap: 8 }}>
          <span className="small muted">Popular:</span>
          {popular.map((p) => <button key={p} className="chip" onClick={() => nav(`/research/${region}/${p}`)}>{p}</button>)}
        </div>
      </section>
      <div className="stack" style={{ gap: 10 }}>
        <h2 className="h2">Or start from a question</h2>
        <div className="explore-grid">
          {quick.map(([t, sub, to]) => (
            <button key={t} className="card explore-card" onClick={() => nav(to)}><b>{t}</b><span className="small muted">{sub}</span></button>
          ))}
        </div>
      </div>
      <AskBar />
      {!!notebooks?.length && <p className="small muted">You also have {notebooks.length} trading notebook{notebooks.length === 1 ? "" : "s"}: <Link className="link" to="/notebooks">open them</Link>.</p>}
      <Explore title="Everything else" skip={["find"]} />
    </div>
  );
}

const VERDICT_RANK: Record<string, number> = { edge: 0, mixed: 1, not_enough: 2, luck: 3, no_edge: 4 };
type Sort = "recent" | "name" | "verdict";

export function Home() {
  const { focus, notebooks } = useApp();
  return (
    <>
      <PromoCountdown />
      <FirstSteps />
      {focus === "invest" && notebooks !== null ? <InvestorStart /> : <NotebooksHome />}
    </>
  );
}

export function NotebooksHome() {
  const { notebooks, me, refreshNotebooks, fail } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<Sort>(() => { try { return (localStorage.getItem("stratlab.nbSort") as Sort) || "recent"; } catch { return "recent"; } });
  useEffect(() => { try { localStorage.setItem("stratlab.nbSort", sort); } catch { /* private mode */ } }, [sort]);
  const shown = useMemo(() => {
    const words = q.trim().toLowerCase();
    const rows = (notebooks ?? []).filter((n) => !words || [n.name, n.question, n.instrument && "symbol" in n.instrument ? n.instrument.symbol : ""]
      .join(" ").toLowerCase().includes(words));
    const key = (n: (typeof rows)[number]) => sort === "name" ? n.name.toLowerCase()
      : sort === "verdict" ? String(VERDICT_RANK[n.summary?.last_verdict ?? ""] ?? 9) : "";
    // pinned first; within each group keep the server's most-recent-first order unless sorting by name or verdict
    return [...rows].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned) || (sort === "recent" ? 0 : key(a).localeCompare(key(b))));
  }, [notebooks, q, sort]);
  if (notebooks === null) return <Loading label="Opening your notebooks" />;
  if (notebooks.length === 0) return <NewNotebook />;

  const togglePin = async (id: string, pinned: boolean) => {
    try { await api(`/notebooks/${id}`, { method: "PUT", body: { pinned } }); await refreshNotebooks(); } catch (e) { fail(e); }
  };

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="spread" style={{ alignItems: "flex-end", flexWrap: "wrap", gap: 14 }}>
        <div className="stack" style={{ gap: 8 }}>
          <span className="eyebrow">{me?.email ?? "Your lab"}</span>
          <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Your notebooks</h1>
        </div>
        <div className="row wrap" style={{ gap: 10 }}>
          <button className="btn" onClick={() => nav("/new")}>Test a new idea</button>
        </div>
      </div>
      <AskBar />
      {notebooks.length > 3 && (
        <div className="row wrap" style={{ gap: 10 }}>
          <label className="search-box" style={{ flex: "1 1 260px" }}>
            <Search size={18} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a notebook: name, stock or question" aria-label="Search notebooks" />
          </label>
          <div className="seg" role="radiogroup" aria-label="Sort notebooks">
            {([["recent", "Recent"], ["name", "Name"], ["verdict", "Best verdict"]] as [Sort, string][]).map(([k, label]) => (
              <button key={k} role="radio" aria-checked={sort === k} aria-pressed={sort === k} onClick={() => setSort(k)}>{label}</button>
            ))}
          </div>
        </div>
      )}
      {shown.length === 0 && <p className="muted">No notebooks match "{q}".</p>}
      <div className="grid2">
        {shown.map((n) => {
          const inst = n.instrument && "symbol" in n.instrument ? n.instrument.symbol : "No instrument yet";
          const count = n.summary?.experiments ?? 0;
          return (
            <div key={n.id} className="card stack nb-card" style={{ gap: 12, position: "relative" }}>
              <button className={`pin-btn${n.pinned ? " on" : ""}`} aria-pressed={!!n.pinned} aria-label={n.pinned ? `Unpin ${n.name}` : `Pin ${n.name} to the top`}
                title={n.pinned ? "Unpin" : "Pin to the top"} onClick={() => togglePin(n.id, !n.pinned)}><Pin size={16} filled={!!n.pinned} /></button>
              <button className="nb-card-body stack" style={{ gap: 12 }} onClick={() => nav(`/n/${n.id}`)}>
                <span className="eyebrow" style={{ paddingRight: 36 }}>{n.name} · {inst}</span>
                <span className="serif" style={{ fontSize: 22, lineHeight: 1.25 }}>{n.question || n.name}</span>
                <div className="spread" style={{ flexWrap: "wrap" }}>
                  <VerdictBadge v={n.summary?.last_verdict} />
                  <span className="small muted">{count} experiment{count === 1 ? "" : "s"} · {ago(n.updated_at)}</span>
                </div>
              </button>
            </div>
          );
        })}
      </div>
      <Explore />
    </div>
  );
}
