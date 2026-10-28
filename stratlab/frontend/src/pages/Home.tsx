import { Explore } from "../components/Explore";
import { TileGrid } from "../components/TileGrid";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { findPrefill, type Prefill } from "../lib/prefill";
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
import { Badge, Card, CardHead, ChipBar, EmptyState, ErrorState, Notice, PageHeader, Seg, Skeleton } from "../components/kit";
import "./trade/trade.css";
import { scrollBehavior } from "../lib/motion";

export type Where = { market: string; instrument: Instrument | null };

export function useCreateNotebook(where?: Where | null) {
  const nav = useNavigate();
  const loc = useLocation();
  const { refreshNotebooks, fail, notify } = useApp();
  /** Make the notebook and open it. True once it is made; false when it couldn't be (said), so the words or the pasted
   * script that built it stay to try again. */
  return async (b: Built): Promise<boolean> => {
    // what you picked above wins over what the idea text mentions
    const instrument = where?.instrument ?? (where?.market === "CSV" ? null : b.instrument);
    const strategy = instrument ? { ...b.strategy, risk: riskForCurrency(b.strategy.risk, instrument.currency, { market: instrument.market, type: instrument.type, tf: b.strategy.tf }) } : b.strategy;
    let nb: Notebook;
    try {
      nb = await api<Notebook>("/notebooks", {
        method: "POST",
        body: { name: strategy.name, question: b.question, strategy, instrument: instrument?.id ?? null },
      });
    } catch (e) {
      fail(e);
      return false;
    }
    try {
      if (b.group && !where?.instrument) {
        // the notebook exists by now: a group that couldn't be attached is said, not a reason to leave it unopened (a second try would make a second notebook)
        try { await api(`/notebooks/${nb.id}`, { method: "PUT", body: { group: b.group } }); }
        catch { notify("The notebook was made, but its group couldn't be set. Pick it under Testing on."); }
      }
      await refreshNotebooks();
      if (new URLSearchParams(loc.search).get("then") === "group" && !b.group) nav(`/n/${nb.id}/market#group`);
      else if (where?.market === "CSV") nav(`/n/${nb.id}/market`, { state: { market: "CSV" } });
      else nav(`/n/${nb.id}`, { state: { gaps: { ...b.gaps, mentioned: instrument ? [...b.gaps.mentioned, "instrument"] : b.gaps.mentioned } } });
    } catch (e) {
      fail(e);            // the notebook is made (a second try would make a second one): it is opened, and the rest said
      nav(`/n/${nb.id}`);
    }
    return true;
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
      <CardHead title="1. Where do you want to test it?" info={`${HELP.markets} Picking a stock or coin is optional: if your idea names one, we'll find it for you.`} infoLabel="About markets" />
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
      {/* the "optional" hint is behind the (i) in the heading, not a line far from the search box (VR1-042) */}
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


/** When Research hands over a company (and maybe an idea), pick its market and instrument up front. A public company
 * page links here as /new?market=IN&symbol=RELIANCE. */
function usePrefill(setWhere: (w: Where) => void, setMissing: (s: string) => void): Prefill | null {
  const loc = useLocation();
  const q = new URLSearchParams(loc.search);
  const market = (q.get("market") || "").toUpperCase(), symbol = q.get("symbol") || "";
  const prefill = (loc.state as { prefill?: Prefill } | null)?.prefill
    ?? (/^(IN|US)$/.test(market) && /^[A-Za-z0-9&.-]{1,20}$/.test(symbol) ? { market, symbol } : null);
  useEffect(() => {
    if (!prefill) return;
    let live = true;
    setWhere({ market: prefill.market, instrument: null });
    setMissing("");
    (async () => {
      const inst = await findPrefill(prefill, api);
      if (!live) return;
      if (inst) setWhere({ market: prefill.market, instrument: inst });
      else if (prefill.symbol) setMissing(`Couldn't find ${prefill.symbol} in ${prefill.market}. Pick the instrument below.`);
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
  const [missing, setMissing] = useState("");
  const prefill = usePrefill(setWhere, setMissing);
  const loc = useLocation();
  const [importing, setImporting] = useState(new URLSearchParams(loc.search).has("import"));
  const importRef = useRef<HTMLElement>(null);
  useEffect(() => { if (importing && new URLSearchParams(loc.search).has("import")) importRef.current?.scrollIntoView({ behavior: scrollBehavior() }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (where.market || !markets.length) return;
    // start where you left off last time, if that market is usable
    let last = "";
    try { last = localStorage.getItem(LAST_MARKET) || ""; } catch { /* private mode */ }
    const usable = (id: string) => markets.some((m) => m.id === id && m.status !== "soon");
    setWhere({ market: usable(last) ? last : markets.find((m) => m.id === "IN" && m.status === "live") ? "IN" : "CRYPTO", instrument: null });
  }, [markets, where.market]);
  // "where you left off" is the market of the last notebook made here, not of the last chip glanced at: a look at Crypto made the page open on
  // Crypto for good for a person with no crypto notebook (LIVE1A-003)
  const make = useCreateNotebook(where);
  const create = async (b: Built) => {
    const ok = await make(b);
    if (ok && where.market) try { localStorage.setItem(LAST_MARKET, where.market); } catch { /* private mode */ }
    return ok;
  };
  return (
    <div className="k-page">{/* the same 1080px column as every app page (VR1-040: a 920px column ended 160px short of the rest) */}
      <PageHeader eyebrow="Trade · Build and test" title="What trading idea do you want to test?"
        lede="Write it the way you'd explain it to a friend. We'll turn it into exact rules and ask about anything that's missing."
        actions={!hide.includes("import") ? <button type="button" className="btn quiet sm" onClick={() => { setImporting(true); window.setTimeout(() => importRef.current?.scrollIntoView({ behavior: scrollBehavior() }), 50); }}>
          <Upload size={16} />Import a strategy
        </button> : undefined} />
      {new URLSearchParams(loc.search).get("then") === "group" && !prefill?.symbol && (
        <Notice>Testing on a group: describe the rules here (or name the group, like "on NIFTY 50 stocks"). Next you'll pick the stocks or coins.</Notice>
      )}
      {missing && <Notice tone="warn">{missing}</Notice>}
      {prefill?.symbol ? (
        <Notice>From Research: testing {prefill.text ? "an idea" : "a strategy"} on {prefill.symbol}. Check the rules below, then build.</Notice>
      ) : (
        <p className="k-small k-muted">Not sure what to test? <Link to="/research" className="link">Research a company first</Link>: its AI read suggests ideas you can test in one click.</p>
      )}
      {/* no "1, 2, 3" strip here: the two numbered sections below are the steps (VR1-041: "1. Describe it" over "1. Where do you want to test it?") */}
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
      {/* the import button is in the header and the library is in the menu: each is offered once here (LIVE1A-003) */}
      <Explore title="More you can do" hide={[...hide, "import", "library"]} />
    </div>
  );
}

const VERDICT_RANK: Record<string, number> = { edge: 0, mixed: 1, not_enough: 2, luck: 3, no_edge: 4 };
type Sort = "recent" | "name" | "verdict";

/** `hide`: tools the page around it already links to, so each shows once (see Explore). */
export function NotebooksHome({ hide = [] }: { hide?: string[] }) {
  const { notebooks, notebooksFailed, refreshNotebooks, fail } = useApp();
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
  if (notebooks === null) return <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Your notebooks" /><Card><Skeleton label="Opening your notebooks" onRetry={() => { void refreshNotebooks(); }} /></Card></div>;
  if (notebooksFailed && notebooks.length === 0) return (
    <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Your notebooks" />
      <ErrorState title="Your notebooks couldn't be read" action={{ label: "Try again", onClick: () => { void refreshNotebooks(); } }}>Nothing was changed. Check your connection and try again.</ErrorState></div>
  );
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
      {/* each card: the notebook's name as its title, its question in two lines under it (whole in its tooltip), what it was
          last tested on, a pin that says what it does, and one height per row (DA-032: the long question in large serif was cut
          mid-quote, the name was tiny caps below, the pin had no words and the cards' heights differed) */}
      <TileGrid className="k-cards nb-cards">
        {shown.map((n) => {
          const inst = n.instrument && "symbol" in n.instrument ? n.instrument.symbol : null;
          const count = n.summary?.experiments ?? 0;
          const question = n.question && n.question.trim() !== n.name.trim() ? n.question : "";
          return (
            <Card key={n.id} label={n.name}>
              <CardHead title={<Link to={`/n/${n.id}`} className="k-title-link">{n.name}</Link>}
                actions={<button type="button" className={`k-pin${n.pinned ? " on" : ""}`} aria-pressed={!!n.pinned} aria-label={n.pinned ? `Unpin ${n.name}` : `Pin ${n.name} to the top`}
                  title={n.pinned ? "Unpin it" : "Keep it at the top of the list"} onClick={() => togglePin(n.id, !n.pinned)}><Pin size={16} filled={!!n.pinned} /></button>} />
              {question && <p className="k-small k-muted nb-question" title={question}>{question}</p>}
              <span className="k-note">{inst ? `Tested on ${inst}` : "No instrument picked yet"}</span>
              <div className="k-spread k-push">
                <VerdictBadge v={n.summary?.last_verdict} />
                <span className="k-note">{count} experiment{count === 1 ? "" : "s"} · {ago(n.updated_at)}</span>
              </div>
            </Card>
          );
        })}
      </TileGrid>
      <Explore hide={hide} />
    </div>
  );
}
