import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";
import { blankStrategy, parseStrategyText, STARTERS } from "../lib/rules";
import type { Notebook } from "../lib/types";
import { IdeaComposer, type Built } from "../components/IdeaComposer";
import { Loading, VerdictBadge } from "../components/ui";

export function useCreateNotebook() {
  const nav = useNavigate();
  const { refreshNotebooks, fail } = useApp();
  return async (b: Built) => {
    try {
      const nb = await api<Notebook>("/notebooks", {
        method: "POST",
        body: { name: b.strategy.name, question: b.question, strategy: b.strategy, instrument: b.instrument?.id ?? null },
      });
      await refreshNotebooks();
      nav(`/n/${nb.id}`, { state: { gaps: b.gaps } });
    } catch (e) {
      fail(e);
    }
  };
}

export function Starters() {
  const create = useCreateNotebook();
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

export function NewNotebook() {
  const create = useCreateNotebook();
  return (
    <div className="stack" style={{ gap: 28, maxWidth: 900 }}>
      <div className="stack" style={{ gap: 10 }}>
        <span className="eyebrow">New notebook</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 48px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          What trading idea do you want to test?
        </h1>
        <p className="muted" style={{ fontSize: 17 }}>Write it the way you'd explain it to a friend. We'll turn it into exact rules and ask about anything that's missing.</p>
      </div>
      <ol className="how" aria-label="How StratLab works">
        <li><b>1. Describe it</b><span>In plain words. We turn it into rules you can read and edit.</span></li>
        <li><b>2. Test it honestly</b><span>On years of real prices, after real costs, with four checks for luck.</span></li>
        <li><b>3. Trade it on paper</b><span>If the verdict says the edge is real, watch it live with fake money.</span></li>
      </ol>
      <IdeaComposer onBuilt={create} autoFocus />
      <div className="stack">
        <h2 className="h2">Or start from a classic idea</h2>
        <Starters />
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
