import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";
import { blankStrategy, parseStrategyText, riskForCurrency, STARTERS } from "../lib/rules";
import type { Instrument, Notebook } from "../lib/types";
import { HELP } from "../lib/help";
import { InstrumentSearch } from "../components/InstrumentSearch";
import { IdeaComposer, type Built } from "../components/IdeaComposer";
import { Info, Loading, VerdictBadge } from "../components/ui";

export type Where = { market: string; instrument: Instrument | null };

export function useCreateNotebook(where?: Where | null) {
  const nav = useNavigate();
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
      await refreshNotebooks();
      if (where?.market === "CSV") nav(`/n/${nb.id}/market`, { state: { market: "CSV" } });
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

export function Starters({ where }: { where?: Where | null }) {
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

type Prefill = { market: string; symbol?: string; instrumentId?: string | null; text?: string };

/** When Research hands over a company (and maybe an idea), pick its market and instrument up front. */
function usePrefill(setWhere: (w: Where) => void): Prefill | null {
  const loc = useLocation();
  const prefill = (loc.state as { prefill?: Prefill } | null)?.prefill ?? null;
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
  useEffect(() => {
    if (!where.market && markets.length) setWhere({ market: markets.find((m) => m.id === "IN" && m.status === "live") ? "IN" : "CRYPTO", instrument: null });
  }, [markets, where.market]);
  const create = useCreateNotebook(where);
  return (
    <div className="stack" style={{ gap: 28, maxWidth: 960, margin: "0 auto" }}>
      <div className="stack" style={{ gap: 10 }}>
        <span className="eyebrow">New notebook</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 48px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          What trading idea do you want to test?
        </h1>
        <p className="muted" style={{ fontSize: 17 }}>Write it the way you'd explain it to a friend. We'll turn it into exact rules and ask about anything that's missing.</p>
        {prefill?.symbol ? (
          <p className="edit-hint">From Research: testing {prefill.text ? "an idea" : "a strategy"} on {prefill.symbol}. Check the rules below, then build.</p>
        ) : (
          <p className="small muted">Not sure what to test? <Link to="/research" className="link">Research a company first</Link>: its AI read suggests ideas you can test in one click.</p>
        )}
      </div>
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
      <div className="stack">
        <h2 className="h2">Or start from a classic idea</h2>
        <Starters where={where} />
      </div>
    </div>
  );
}

export function Home() {
  const { notebooks, me } = useApp();
  const nav = useNavigate();
  if (notebooks === null) return <Loading label="Opening your notebooks" />;
  if (notebooks.length === 0) return <NewNotebook />;
  return (
    <div className="stack" style={{ gap: 28 }}>
      <div className="spread" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
        <div className="stack" style={{ gap: 8 }}>
          <span className="eyebrow">{me?.email ?? "Your lab"}</span>
          <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Your notebooks</h1>
        </div>
        <button className="btn" onClick={() => nav("/new")}>Test a new idea</button>
      </div>
      <div className="grid2">
        {notebooks.map((n) => {
          const inst = n.instrument && "symbol" in n.instrument ? n.instrument.symbol : "No instrument yet";
          const count = n.summary?.experiments ?? 0;
          return (
            <button key={n.id} className="card stack" style={{ textAlign: "left", cursor: "pointer", gap: 12 }} onClick={() => nav(`/n/${n.id}`)}>
              <span className="eyebrow">{n.name} · {inst}</span>
              <span className="serif" style={{ fontSize: 22, lineHeight: 1.25 }}>{n.question || n.name}</span>
              <div className="spread" style={{ flexWrap: "wrap" }}>
                <VerdictBadge v={n.summary?.last_verdict} />
                <span className="small muted">{count} experiment{count === 1 ? "" : "s"} · {ago(n.updated_at)}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
