import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { match, resolve } from "../lib/features";
import type { Instrument } from "../lib/types";
import { Book, Compass, Lens, Search, Sparkle, Upload } from "./Icons";

interface Idea { title: string; text: string; why: string; market: string; symbol: string | null; tf: string }
interface Row { key: string; icon: ReactNode; title: string; sub?: string; run: () => void }

const LAST_MARKET = "stratlab.lastMarket";
const lastMarket = () => { try { return localStorage.getItem(LAST_MARKET) || "IN"; } catch { return "IN"; } };
const isQuestion = (q: string) => /\?|^(what|which|how|why|best|good|suggest|give|show|find|any)\b|\b(ideas?|strateg(y|ies) for|suggestions?)\b/i.test(q.trim());
const looksLikeCode = (q: string) => /\n.*\n/.test(q) || /(\/\/@version|strategy\(|def |import |=>|\{[\s\S]*"entry")/.test(q);

/** One box for everything: a stock, an idea, a question, a feature's name or a pasted script. Opens with Ctrl+K. */
export function SearchPalette({ onClose }: { onClose: () => void }) {
  const { notebooks, fail } = useApp();
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

  useEffect(() => { input.current?.focus(); }, []);
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

  const rows = useMemo(() => {
    const out: { group: string; items: Row[] }[] = [];
    if (!text) {
      out.push({ group: "Try", items: [
        { key: "t1", icon: <Sparkle size={18} />, title: "Buy NIFTY when RSI drops below 30", sub: "Type an idea to test it", run: () => setQ("Buy NIFTY when RSI drops below 30, sell above 55") },
        { key: "t2", icon: <Compass size={18} />, title: "Momentum ideas for bank stocks", sub: "Ask for ideas", run: () => setQ("momentum ideas for bank stocks") },
        { key: "t3", icon: <Lens size={18} />, title: "RELIANCE", sub: "Look up a stock or coin", run: () => setQ("RELIANCE") },
        { key: "t4", icon: <Search size={18} />, title: "walk forward", sub: "Find any feature", run: () => setQ("walk forward") },
      ] });
      return out;
    }
    const act: Row[] = [];
    if (code) act.push({ key: "imp", icon: <Upload size={18} />, title: "Import this strategy", sub: "Pine Script, Python, a config file…", run: () => go("/import", { importText: q }) });
    else {
      if (words >= 3 && !isQuestion(text)) act.push({ key: "test", icon: <Sparkle size={18} />, title: `Test “${text.length > 60 ? text.slice(0, 60) + "…" : text}”`, sub: "Build the rules and run a verdict", run: () => testIdea(text) });
      act.push({ key: "ideas", icon: <Compass size={18} />, title: thinking ? "Thinking of ideas…" : `Get strategy ideas for “${text.length > 40 ? text.slice(0, 40) + "…" : text}”`,
        sub: "4 testable ideas, each one click from a verdict", run: () => { if (!thinking) getIdeas(); } });
    }
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
  }, [text, q, code, words, ideas, ideasFor, thinking, insts, notebooks, loc.pathname]);

  const flat = rows.flatMap((g) => g.items);
  useEffect(() => { setSel(0); }, [text]);
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
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search or ask anything">
        <div className="palette-in">
          <Search size={20} />
          <textarea ref={input} rows={Math.min(6, Math.max(1, q.split("\n").length))} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key}
            placeholder="Search or ask anything: a stock, an idea, a feature, or paste a strategy" aria-label="Search or ask anything" />
          <kbd className="small muted">Esc</kbd>
        </div>
        <div className="palette-list" ref={list} role="listbox">
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
        <div className="palette-foot small muted"><span>↑↓ to move · Enter to open</span><span>Shift+Enter for a new line</span></div>
      </div>
    </div>
  );
}
