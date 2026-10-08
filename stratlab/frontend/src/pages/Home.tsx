import { Explore } from "../components/Explore";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";
import { blankStrategy, parseStrategyText, riskForCurrency, STARTERS } from "../lib/rules";
import type { Instrument, Notebook } from "../lib/types";
import { HELP } from "../lib/help";
import { sipTestLink } from "../lib/sip";
import { InstrumentSearch } from "../components/InstrumentSearch";
import { IdeaComposer, type Built } from "../components/IdeaComposer";
import { ImportStrategy } from "../components/ImportStrategy";
import { Pin, Search, Upload } from "../components/Icons";
import { VerdictBadge } from "../components/ui";
import { Badge, Card, CardHead, ChipBar, EmptyState, Notice, PageHeader, Seg, Skeleton } from "../components/kit";
import "./trade/trade.css";

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

/** Step 1 of a new notebook: the market and instrument to test on. */
function WhereToTest({ where, setWhere }: { where: Where; setWhere: (w: Where) => void }) {
  const { markets } = useApp();
  const usable = markets.filter((m) => m.status !== "soon");
  const soon = markets.filter((m) => m.status === "soon");
  const market = markets.find((m) => m.id === where.market);
  return (
    <Card label="Where to test">
      <CardHead title="1. Where do you want to test it?" info={HELP.markets} infoLabel="About markets" />
      <ChipBar label="Market" value={where.market} onChange={(id) => setWhere({ market: id, instrument: null })}
        options={usable.map((m) => ({ value: m.id, label: `${[...m.symbol].length === 1 && m.symbol !== "+" ? m.symbol + " " : ""}${m.name}${m.status === "offline" ? " (offline)" : ""}` }))} />
      {soon.length > 0 && <p className="k-note">Coming soon: {soon.map((m) => m.name).join(", ")}. Until then, use "Your own data" with a CSV.</p>}
      {where.market === "CSV" ? (
        <p className="k-small k-muted">You'll upload your CSV of candles right after the notebook is created.</p>
      ) : where.instrument ? (
        <div className="k-row">
          <Badge tone="ok">{where.instrument.symbol} · {market?.name}</Badge>
          <button type="button" className="btn quiet sm" onClick={() => setWhere({ ...where, instrument: null })}>Pick another</button>
          {(() => { const to = sipTestLink({ ...where.instrument, market: where.instrument.market ?? where.market });
            return to ? <Link className="btn quiet sm" to={to}>Test as a SIP instead</Link> : null; })()}
        </div>
      ) : market && market.status === "live" ? (
        <InstrumentSearch market={market} compact onPick={(i) => setWhere({ market: where.market, instrument: i })} />
      ) : market ? (
        <Notice tone="warn">{market.name} data is offline right now. Pick another market, or write your idea now and choose later.</Notice>
      ) : null}
      {!where.instrument && where.market !== "CSV" && <p className="k-note">Optional: if your idea names a stock or coin, we'll find it for you.</p>}
    </Card>
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
    <div className="k-starters">
      {STARTERS.map((st, i) => (
        <button key={st.title} type="button" className="k-starter" onClick={() => start(i)}>
          <Badge tone={i < 2 ? "ok" : "warn"} dot={false}>{st.level}</Badge>
          <b>{st.title}</b>
          <span className="k-small k-muted">{st.why}</span>
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

/** `hide`: tools the page around it already links to (on the Trade home, the strip's Import card), offered once. */
export function NewNotebook({ hide = [] }: { hide?: string[] }) {
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
    <div className="k-page k-narrow">
      <PageHeader eyebrow="Trade · Build and test" title="What trading idea do you want to test?"
        lede="Write it the way you'd explain it to a friend. We'll turn it into exact rules and ask about anything that's missing."
        actions={!hide.includes("import") ? <button type="button" className="btn quiet sm" onClick={() => { setImporting(true); window.setTimeout(() => importRef.current?.scrollIntoView({ behavior: "smooth" }), 50); }}>
          <Upload size={16} />Import a strategy
        </button> : undefined} />
      {new URLSearchParams(loc.search).get("then") === "group" && !prefill?.symbol && (
        <Notice>Testing on a group: describe the rules here (or name the group, like "on NIFTY 50 stocks"). Next you'll pick the stocks or coins.</Notice>
      )}
      {prefill?.symbol ? (
        <Notice>From Research: testing {prefill.text ? "an idea" : "a strategy"} on {prefill.symbol}. Check the rules below, then build.</Notice>
      ) : (
        <p className="k-small k-muted">Not sure what to test? <Link to="/research" className="link">Research a company first</Link>: its AI read suggests ideas you can test in one click.</p>
      )}
      <ol className="k-routes" aria-label="How StratLab works">
        <li><b>1. Describe it</b><span className="k-small k-muted">In plain words. We turn it into rules you can read and edit.</span></li>
        <li><b>2. Test it honestly</b><span className="k-small k-muted">On years of real prices, after real costs, with four checks for luck.</span></li>
        <li><b>3. Trade it on paper</b><span className="k-small k-muted">If the verdict says the edge is real, watch it live with fake money.</span></li>
      </ol>
      <WhereToTest where={where} setWhere={setWhere} />
      <Card label="Describe your idea">
        <CardHead title="2. Describe your idea" />
        <IdeaComposer key={prefill?.text ?? ""} initial={prefill?.text ?? ""} onBuilt={create} market={where.market} symbol={where.instrument?.symbol} />
      </Card>
      {importing && (
        <section ref={importRef} className="k-card" aria-label="Import a strategy">
          <CardHead title="Import a strategy" actions={<button type="button" className="btn quiet sm" onClick={() => setImporting(false)}>Close</button>}
            info="A StratLab export, TradingView Pine Script, Python, MetaTrader, AmiBroker, or a written description. It becomes a notebook you can test like any other." />
          <ImportStrategy onBuilt={create} market={where.market} />
        </section>
      )}
      <section id="classic-ideas" className="k-stack" aria-label="Classic ideas">
        <h2 className="k-card-title">Or start from a classic idea</h2>
        <Starters where={where} />
      </section>
      <Explore title="More you can do" hide={hide} />
    </div>
  );
}

const VERDICT_RANK: Record<string, number> = { edge: 0, mixed: 1, not_enough: 2, luck: 3, no_edge: 4 };
type Sort = "recent" | "name" | "verdict";

/** `hide`: tools the page around it already links to, so each shows once (see Explore). */
export function NotebooksHome({ hide = [] }: { hide?: string[] }) {
  const { notebooks, refreshNotebooks, fail } = useApp();
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
  if (notebooks === null) return <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Your notebooks" /><Card><Skeleton label="Opening your notebooks" /></Card></div>;
  // /notebooks is always the list (the menu's "Notebooks"); with none yet it says so and offers the first, on /new
  if (notebooks.length === 0) return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Your notebooks" lede="Each notebook holds one idea: its rules, every test run on real prices after costs, and the verdict." />
      <EmptyState title="No notebooks yet" action={{ label: "Test your first idea", to: "/new" }}>
        Describe a trading idea in plain words; StratLab turns it into rules and tests it on years of real prices.
      </EmptyState>
    </div>
  );

  const togglePin = async (id: string, pinned: boolean) => {
    try { await api(`/notebooks/${id}`, { method: "PUT", body: { pinned } }); await refreshNotebooks(); } catch (e) { fail(e); }
  };

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Your notebooks"
        lede="Each notebook holds one idea: its rules, every test run on real prices after costs, and the verdict."
        actions={<button type="button" className="btn" onClick={() => nav("/new")}>Test a new idea</button>} />
      {notebooks.length > 3 && (
        <div className="k-toolbar">
          <label className="k-search">
            <Search size={18} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a notebook: name, stock or question" aria-label="Search notebooks" />
          </label>
          <Seg label="Sort notebooks" options={[{ value: "recent", label: "Recent" }, { value: "name", label: "Name" }, { value: "verdict", label: "Best verdict" }]} value={sort} onChange={(v) => setSort(v as Sort)} />
        </div>
      )}
      {shown.length === 0 && <EmptyState title={`No notebooks match "${q}"`}>Try a stock symbol or a word from the question.</EmptyState>}
      <div className="k-cards">
        {shown.map((n) => {
          const inst = n.instrument && "symbol" in n.instrument ? n.instrument.symbol : "No instrument yet";
          const count = n.summary?.experiments ?? 0;
          return (
            <Card key={n.id} label={n.name}>
              <CardHead title={<Link to={`/n/${n.id}`} className="k-title-link">{n.question || n.name}</Link>}
                actions={<button type="button" className={`k-pin${n.pinned ? " on" : ""}`} aria-pressed={!!n.pinned} aria-label={n.pinned ? `Unpin ${n.name}` : `Pin ${n.name} to the top`}
                  title={n.pinned ? "Unpin" : "Pin to the top"} onClick={() => togglePin(n.id, !n.pinned)}><Pin size={16} filled={!!n.pinned} /></button>} />
              <span className="k-eyebrow">{n.name} · {inst}</span>
              <div className="k-spread">
                <VerdictBadge v={n.summary?.last_verdict} />
                <span className="k-note">{count} experiment{count === 1 ? "" : "s"} · {ago(n.updated_at)}</span>
              </div>
            </Card>
          );
        })}
      </div>
      <Explore hide={hide} />
    </div>
  );
}
