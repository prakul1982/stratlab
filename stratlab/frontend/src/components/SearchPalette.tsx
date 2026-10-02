import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { match, resolve } from "../lib/features";
import { askExamples, useRotating } from "../lib/rotating";
import type { Experiment, Instrument, Notebook } from "../lib/types";
import { buildIdea, findInstrument } from "./IdeaComposer";
import { Book, Compass, Lens, Search, Sparkle, Upload } from "./Icons";

interface Idea { title: string; text: string; why: string; market: string; symbol: string | null; tf: string }
interface Row { key: string; icon: ReactNode; title: string; sub?: string; run: () => void }
interface Ask { action: string; text?: string; market?: string | null; symbol?: string | null; page?: string | null; answer?: string; title?: string | null; fallback?: boolean }

const PAGES: Record<string, string> = { paper: "/paper", options: "/options", library: "/library", research: "/research", import: "/import",
  notebooks: "/", new: "/new", account: "/account", plans: "/plans", themes: "/research/themes", pulse: "/research/pulse", watchlist: "/research/watchlist" };
const HISTORY = { "1d": 1825, "1h": 365 } as Record<string, number>;

const LAST_MARKET = "stratlab.lastMarket";
const lastMarket = () => { try { return localStorage.getItem(LAST_MARKET) || "IN"; } catch { return "IN"; } };
/** Investor phrasings that should open a page directly, before any AI guessing. `name` is a company to look up. */
type Intent = { title: string; sub: string; to?: string; deep?: string; compare?: [string, string] };
export function intentFor(q: string): Intent | null {
  const t = q.trim();
  let m = t.match(/^(?:deep ?dive|deepdive)(?:\s+(?:on|of|into|for))?\s+(.+)$/i) || t.match(/^(.+?)\s+deep ?dive$/i);
  if (m) return { title: `Deep dive: ${m[1]}`, sub: "Its business, 10 years of numbers, capex plans and whether management delivered", deep: m[1] };
  m = t.match(/^compare\s+(.+?)\s+(?:and|vs\.?|versus|with)\s+(.+)$/i);
  if (m) return { title: `Compare ${m[1]} and ${m[2]}`, sub: "Side by side, with an AI read", compare: [m[1], m[2]] };
  if (/\bsector(s)?\b.*\b(lead|leading|rotat|strong|weak|lagging|improving)|sector rotation/i.test(t))
    return { title: "Sector rotation", sub: "Which sectors lead, weaken, lag or improve against the market", to: "/research/rotation" };
  if (/red flags?|\bqip\b|pledge|fund ?raise|auditor resign/i.test(t))
    return { title: "Red flags in your watchlist", sub: "Fund raises, pledges, resignations and defaults filed in the last 3 months", to: "/research/filings" };
  if (/stage ?(2|two)|supertrend|\bst ?s2\b/i.test(t))
    return { title: "Stage 2 + Supertrend scan", sub: "Which stocks are in Stage 2 with the Supertrend up",
             to: /nifty ?50/i.test(t) ? "/research/scan?set=nifty50" : /bank ?nifty/i.test(t) ? "/research/scan?set=banknifty" : "/research/scan" };
  if (/investor home|my watchlist|my portfolio|watchlist overview/i.test(t))
    return { title: "Investor home", sub: "Every watchlist company: trend, sector, red flags, checklist", to: "/research/investor" };
  return null;
}

const isQuestion = (q: string) => /\?|^(what|which|how|why|best|good|suggest|give|show|find|any)\b|\b(ideas?|strateg(y|ies) for|suggestions?)\b/i.test(q.trim());
const looksLikeCode = (q: string) => /\n.*\n/.test(q) || /(\/\/@version|strategy\(|def |import |=>|\{[\s\S]*"entry")/.test(q);

/** One box for everything: a stock, an idea, a question, a feature's name or a pasted script. Opens with Ctrl+K. */
export function SearchPalette({ onClose }: { onClose: () => void }) {
  const { notebooks, markets, fail, refreshMe, refreshNotebooks, focus } = useApp();
  const example = useRotating(askExamples(focus));
  const [steps, setSteps] = useState<string[] | null>(null);
  const [answer, setAnswer] = useState<{ q: string; text: string; problem?: boolean } | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const [q, setQ] = useState("");
  const [insts, setInsts] = useState<Instrument[]>([]);
  const [ideas, setIdeas] = useState<Idea[] | null>(null);
  const [ideasFor, setIdeasFor] = useState("");
  const [thinking, setThinking] = useState(false);
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const text = q.trim();
  const words = text.split(/\s+/).filter(Boolean).length;
  const code = looksLikeCode(q);
  const intent = useMemo(() => (looksLikeCode(q) ? null : intentFor(q)), [q]);

  useEffect(() => { if (!steps) input.current?.focus(); }, [steps]);   // back to typing once the work is done
  useEffect(() => {
    setInsts([]);
    if (code || text.length < 2 || words > 3) return;
    const t = window.setTimeout(() => {
      api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(text.slice(0, 40))}`).then((r) => setInsts(r.slice(0, 5))).catch(() => setInsts([]));
    }, 220);
    return () => window.clearTimeout(t);
  }, [text, words, code]);

  const go = (to: string, state?: unknown) => { onClose(); nav(to, state ? { state } : undefined); };
  const testIdea = (t: string, market = lastMarket(), symbol?: string | null) => go("/new", { prefill: { market, symbol: symbol ?? undefined, text: t } });
  const getIdeas = async () => {
    setThinking(true); setIdeasFor(text);
    try { setIdeas((await api<{ ideas: Idea[] }>("/search/ideas", { method: "POST", body: { q: text } })).ideas); setSel(0); }
    catch (e) { fail(e); } finally { setThinking(false); }
  };

  const step = (s: string) => setSteps((x) => [...(x ?? []), s]);

  /** Build the rules, save them as a notebook, then test them (or start paper trading), and open the result. */
  const buildAndRun = async (a: Ask, paper: boolean) => {
    step("Turning your words into exact rules…");
    const r = await buildIdea(a.text || text, a.market ?? lastMarket());
    if (r.usedAI) refreshMe();
    if (!r.built) throw new Error(r.note);
    const b = r.built;
    const inst = b.instrument ?? (a.symbol ? await findInstrument(a.symbol, a.market) : null);
    step(`Saving it as a notebook${inst ? ` on ${inst.symbol}` : ""}…`);
    const nb = await api<Notebook>("/notebooks", { method: "POST", body: { name: b.strategy.name, question: b.question, strategy: b.strategy, instrument: inst?.id ?? null } });
    await refreshNotebooks();
    if (!inst) {           // nothing named to trade: the notebook asks what to test it on
      go(`/n/${nb.id}`, { gaps: b.gaps });
      return;
    }
    if (paper) {
      step("Starting paper trading with fake money…");
      const snap = await api<{ id: string }>("/live/sessions", { method: "POST", body: { strategy: b.strategy, instrument: inst.id } });
      refreshMe();
      go(`/paper/${snap.id}`);
      return;
    }
    const tf = b.strategy.tf, market = markets.find((m) => m.id === inst.market);
    const want = HISTORY[tf] ?? 60, days = Math.min(want, market?.max_days?.[tf as keyof typeof market.max_days] ?? want);
    step(`Testing it on ${days >= 365 ? `${Math.round(days / 365)} years` : `${days} days`} of real ${inst.symbol} prices…`);
    const out = await api<{ experiment: Experiment }>(`/notebooks/${nb.id}/experiments`, { method: "POST", body: { days, label: "From search" } });
    refreshMe();
    go(`/n/${nb.id}/e/${out.experiment.v}`);
  };

  const runIntent = async (it: Intent) => {
    if (it.to) return go(it.to);
    setSteps([it.deep ? `Finding ${it.deep}…` : "Finding both companies…"]);
    try {
      if (it.deep) {
        const inst = await findInstrument(it.deep, "IN");
        setSteps(null);
        return go(inst && !inst.fno ? `/research/IN/${encodeURIComponent(inst.symbol)}/deep` : `/research?q=${encodeURIComponent(it.deep)}`);
      }
      const [a, b] = await Promise.all(it.compare!.map((n) => findInstrument(n, "IN")));
      setSteps(null);
      const qs = [a && `a=${encodeURIComponent(a.symbol)}`, b && `b=${encodeURIComponent(b.symbol)}`].filter(Boolean).join("&");
      return go(`/research/compare?region=IN${qs ? "&" + qs : ""}`);   // a name that wasn't found is left for the user to pick
    } catch (e) { setSteps(null); fail(e); }
  };

  /** Work out what the line means, then do it. */
  const doIt = async () => {
    if (steps || !text) return;
    if (intent) return runIntent(intent);
    setAnswer(null);
    setSteps(["Working out what you mean…"]);
    try {
      const a = await api<Ask>("/ask", { method: "POST", body: { q: text } });
      if (a.action === "test" || a.action === "paper") return await buildAndRun(a, a.action === "paper");
      setSteps(null);
      if (a.action === "import") return go("/import", { importText: q });
      if (a.action === "answer") {
        setAnswer({ q: text, text: a.answer || "The AI isn't available to answer right now. The matches below may help, or try again in a minute." });
        return;
      }
      if (a.action === "ideas") return getIdeas();
      if (a.action === "research" && a.symbol) {
        const inst = await findInstrument(a.symbol, a.market === "US" ? "US" : "IN");
        const mk = inst?.market === "US" ? "US" : "IN";
        return go(inst && !inst.fno ? `/research/${mk}/${encodeURIComponent(inst.symbol)}` : "/research");
      }
      if (a.action === "library") return go(`/library?q=${encodeURIComponent(a.text ?? "")}`);
      if (a.action === "options") return go("/options");
      if (a.action === "open") return go(PAGES[a.page ?? ""] ?? "/");
      getIdeas();
    } catch (e) {
      setSteps(null);
      setAnswer({ q: text, text: `Couldn't finish that: ${(e as Error).message}`, problem: true });
    }
  };

  const rows = useMemo(() => {
    const out: { group: string; items: Row[] }[] = [];
    if (!text) {
      const subs: Record<string, string> = {
        "Deep dive Apollo Hospitals": "Business, 10 years of numbers, capex plans, management's record",
        "Which sectors are leading right now?": "Sector rotation against the market",
        "Red flags in my watchlist": "Fund raises, pledges, resignations, defaults",
        "Stage 2 stocks in NIFTY 50": "The Stage 2 + Supertrend scan",
        "Compare TCS and Infosys": "Side by side, with an AI read",
        "Test: buy NIFTY when RSI drops below 30": "Builds the rules, runs the test, shows the verdict",
        "Paper trade a 20/50 EMA cross on Bitcoin": "Builds it and starts paper trading",
        "Short straddle on BANKNIFTY": "Opens options paper trading",
        "What is a walk-forward test?": "Ask anything about investing, trading or StratLab",
        "Momentum ideas for bank stocks": "Ideas you can test in one click",
      };
      out.push({ group: "Try", items: askExamples(focus).slice(0, 6).map((ex, n) => ({
        key: `t${n}`, icon: intentFor(ex) ? <Lens size={18} /> : <Sparkle size={18} />, title: ex, sub: subs[ex], run: () => setQ(ex) })) });
      return out;
    }
    const act: Row[] = [];
    if (code) act.push({ key: "imp", icon: <Upload size={18} />, title: "Import this strategy", sub: "Pine Script, Python, a config file…", run: () => go("/import", { importText: q }) });
    else {
      act.push({ key: "do", icon: <Sparkle size={18} />, title: `Do it: “${text.length > 60 ? text.slice(0, 60) + "…" : text}”`,
        sub: isQuestion(text) ? "Get an answer, or ideas you can test" : words >= 3 ? "StratLab works out what you mean and does it: test, paper trade, research…" : "Research it, test it, or get ideas",
        run: () => { doIt(); } });
      if (words >= 3 && !isQuestion(text)) act.push({ key: "edit", icon: <Book size={18} />, title: "Write it up in a new notebook first", sub: "Check the rules before anything runs", run: () => testIdea(text) });
      act.push({ key: "ideas", icon: <Compass size={18} />, title: thinking ? "Thinking of ideas…" : `Get strategy ideas for “${text.length > 40 ? text.slice(0, 40) + "…" : text}”`,
        sub: "4 testable ideas, each one click from a verdict", run: () => { if (!thinking) getIdeas(); } });
    }
    if (intent) act.unshift({ key: "intent", icon: <Lens size={18} />, title: intent.title, sub: intent.sub, run: () => { runIntent(intent); } });
    out.push({ group: "Do", items: act });
    if (ideas && ideasFor === text) out.push({ group: "Ideas", items: ideas.map((i, n) => ({
      key: `idea${n}`, icon: <Sparkle size={18} />, title: i.title, sub: `${i.symbol ? i.symbol + " · " : ""}${i.text}`, run: () => testIdea(i.text, i.market, i.symbol) })) });
    const feats = code ? [] : match(text, 5);
    if (feats.length) {
      const latest = notebooks?.[0] ? { id: notebooks[0].id } : null;
      out.push({ group: "Features", items: feats.map((f) => ({ key: f.id, icon: <Search size={18} />, title: f.title, sub: f.what, run: () => go(resolve(f.to, loc.pathname, latest)) })) });
    }
    const nbs = (notebooks ?? []).filter((n) => !code && n.name.toLowerCase().includes(text.toLowerCase())).slice(0, 4);
    if (nbs.length) out.push({ group: "Your notebooks", items: nbs.map((n) => ({ key: n.id, icon: <Book size={18} />, title: n.name, sub: n.question ?? undefined, run: () => go(`/n/${n.id}`) })) });
    if (insts.length) out.push({ group: "Markets", items: insts.flatMap((i) => {
      const research = (i.market === "IN" || i.market === "US") && !i.fno && i.type !== "INDEX";
      const mk = i.market || "IN";
      const rows: Row[] = [{ key: `t-${i.id}`, icon: <Sparkle size={18} />, title: `Test an idea on ${i.symbol}`, sub: [i.name, mk].filter(Boolean).join(" · "), run: () => testIdea("", mk, i.symbol) }];
      if (research) rows.unshift({ key: `r-${i.id}`, icon: <Lens size={18} />, title: `${i.symbol}: research`, sub: i.name, run: () => go(`/research/${mk}/${encodeURIComponent(i.symbol)}`) });
      return rows;
    }).slice(0, 8) });
    // a short search that names a feature ("walk forward") should open it on Enter
    if (words <= 2 && feats.length) {
      const f = out.findIndex((g) => g.group === "Features");
      out.unshift(...out.splice(f, 1));
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, q, code, words, ideas, ideasFor, thinking, insts, notebooks, loc.pathname, steps, intent, focus]);

  const flat = rows.flatMap((g) => g.items);
  useEffect(() => { setSel(0); setAnswer((a) => (a && a.q !== text ? null : a)); }, [text]);
  useEffect(() => { list.current?.querySelector(`[data-i="${sel}"]`)?.scrollIntoView({ block: "nearest" }); }, [sel]);
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(flat.length - 1, s + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); flat[sel]?.run(); }
  };

  let i = -1;
  return (
    <div className="modal-back palette-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Ask or do anything"
        onKeyDown={(e) => { if (e.key === "Escape" && e.target !== input.current) { e.preventDefault(); onClose(); } }}>
        <div className="palette-in">
          <Sparkle size={20} />
          <textarea ref={input} rows={Math.min(6, Math.max(1, q.split("\n").length))} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key}
            placeholder={`Try: ${example}`} aria-label="Search or ask anything" disabled={!!steps} />
          <kbd className="small muted">Esc</kbd>
        </div>
        {steps && (
          <div className="palette-work" role="status" aria-live="polite">
            {steps.map((s, n) => <div key={n} className={`row small${n === steps.length - 1 ? "" : " muted"}`} style={{ gap: 10 }}>
              {n === steps.length - 1 ? <span className="spin" aria-hidden /> : <span aria-hidden>✓</span>}{s}</div>)}
          </div>
        )}
        {answer && !steps && (
          <div className={`palette-answer${answer.problem ? " problem" : ""}`} role="status">
            <span className="eyebrow">{answer.problem ? "Not done" : "Answer"}</span><p>{answer.text}</p>
            {!answer.problem && <span className="small muted">An explanation, not advice. Test any idea before trusting it.</span>}</div>
        )}
        <div className="palette-list" ref={list} role="listbox" hidden={!!steps}>
          {rows.map((g) => (
            <div key={g.group} className="stack" style={{ gap: 2 }}>
              <div className="eyebrow palette-group">{g.group}</div>
              {g.items.map((r) => {
                i += 1;
                const n = i;
                return (
                  <button key={r.key} data-i={n} role="option" aria-selected={n === sel} className={`palette-row${n === sel ? " on" : ""}`}
                    onMouseEnter={() => setSel(n)} onClick={r.run}>
                    <span className="palette-icon">{r.icon}</span>
                    <span className="stack" style={{ gap: 1, minWidth: 0 }}><b>{r.title}</b>{r.sub && <span className="small muted palette-sub">{r.sub}</span>}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div className="palette-foot small muted"><span>Enter does it · ↑↓ to pick something else</span><span>Shift+Enter for a new line</span></div>
      </div>
    </div>
  );
}
