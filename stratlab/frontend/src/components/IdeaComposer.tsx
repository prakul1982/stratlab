import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { blankStrategy, detectInstrument, detectTf, nameFor, parseStrategyText, questionFrom, riskForCurrency } from "../lib/rules";
import type { Cond, Instrument, Risk, Session, Strategy, Tf, Group } from "../lib/types";
import { Info } from "./ui";

export interface Built {
  strategy: Strategy;
  instrument: Instrument | null;
  question: string;
  gaps: { mentioned: string[]; notes: string[]; instName: string | null; usedAI: boolean; fallback: string };
  group?: Group | null;   // a strategy that trades a list of instruments together
}

interface AIOut {
  entry: Cond[]; exit: Cond[]; entryJoin: "all" | "any" | "score"; tf: Tf | null; name: string | null; instrument: string | null;
  market?: string | null; risk: Partial<Risk>; mentioned: string[]; notes: string[]; usage?: { ai_used: number; ai_limit: number | null };
  side?: "long" | "short" | "both"; shortEntry?: Cond[]; shortExit?: Cond[];
  minScore?: number; session?: Session; product?: Strategy["product"];
}

/** Well-known names per market, used in the examples until you pick an instrument. */
const SAMPLE: Record<string, [string, string, string]> = {
  IN: ["NIFTY 50", "RELIANCE", "HDFCBANK"], CRYPTO: ["Bitcoin", "Ethereum", "Solana"], US: ["SPY", "AAPL", "NVDA"],
  UK: ["SHEL.L", "VOD.L", "HSBA.L"], EU: ["SAP.DE", "ASML.AS", "MC.PA"], JP: ["7203.T", "6758.T", "9984.T"],
  FX: ["EUR/USD", "GBP/USD", "USD/JPY"],
};

/** Example ideas in the market (and on the instrument) you picked, so one click never tests the wrong thing. */
function examplesFor(market?: string, symbol?: string | null): { placeholder: string; list: string[] } {
  const [a, b, c] = symbol ? [symbol, symbol, symbol] : SAMPLE[market || ""] ?? ["it", "it", "it"];
  const on = (x: string) => (x === "it" ? "" : ` ${x}`);
  return {
    placeholder: `e.g. Buy${on(a)} when the 20-day average crosses above the 50-day, with a 2% stop loss`,
    list: [
      `Buy${on(a)} when the 20 EMA crosses above the 50 EMA, stop loss 2%`,
      `Buy${on(b)} when RSI drops below 30, sell when it goes back above 55`,
      `Buy${on(c)} when price is above the 200-day average and RSI crosses above 50`,
      `Short${on(a)} when the price falls below the lowest low of the last 20 days, with a 5% trailing stop`,
    ],
  };
}

export async function findInstrument(name: string, market?: string | null): Promise<Instrument | null> {
  const up = name.toUpperCase().replace(/\s+/g, " ").trim();
  const alias: Record<string, string> = { NIFTY: "NIFTY 50", BANKNIFTY: "NIFTY BANK", "BANK NIFTY": "NIFTY BANK", BITCOIN: "BTC-USD", BTC: "BTC-USD", ETHEREUM: "ETH-USD", ETH: "ETH-USD" };
  const q = alias[up] || up;
  try {
    const rows = await api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(q.slice(0, 40))}${market ? `&market=${market}` : ""}`);
    const norm = (s: string) => s.replace("/", "-").toUpperCase();
    return rows.find((r) => norm(r.symbol) === norm(q) || String(r.token).toUpperCase() === norm(q))
      ?? rows.find((r) => ["EQ", "INDEX", "CRYPTO", "ETF", "FX"].includes(r.type || "")) ?? null;
  } catch {
    return null;
  }
}

export function IdeaComposer({ onBuilt, busyLabel = "Build my notebook", autoFocus, initial = "", market, symbol }: {
  onBuilt: (b: Built) => Promise<void> | void; busyLabel?: string; autoFocus?: boolean; initial?: string;
  /** The market and instrument already chosen: the examples use them, and names in the idea are looked up there. */
  market?: string; symbol?: string | null;
}) {
  const ex = examplesFor(market, symbol);
  const { me, refreshMe, fail } = useApp();
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const build = async (idea = text) => {
    idea = idea.trim();
    if (idea.length < 5) { setNote("Describe your idea first, for example: \"Buy NIFTY 50 when it's above the 50-day average\"."); return; }
    setBusy(true);
    setNote(null);
    let out: AIOut, usedAI = true, fallback = "";
    try {
      out = await api<AIOut>("/ai/strategy", { method: "POST", body: { text: idea } });
    } catch (e) {
      const err = e as ApiError;
      if (["ai_busy", "ai_limit", "ai_daily_limit", "ai_failed", "no_backend", "network"].includes(err.code || "") || err.status >= 500) {
        usedAI = false;
        fallback = err.code === "ai_limit" || err.code === "ai_daily_limit"
          ? `${err.message} We used the simple converter instead.`
          : `The AI builder couldn't run just now, so we used the simple converter (it understands SMA, EMA, RSI and price rules). Account → Connection check shows why.`;
        const p = parseStrategyText(idea);
        const mentioned = Object.keys(p.risk);
        const tf = detectTf(idea), inst = detectInstrument(idea);
        if (p.exit.length) mentioned.push("exit");
        if (tf) mentioned.push("tf");
        if (inst) mentioned.push("instrument");
        out = { entry: p.entry, exit: p.exit, entryJoin: "all", tf, name: null, instrument: inst, risk: p.risk, mentioned, notes: [], side: p.side };
      } else {
        setBusy(false);
        fail(e);
        return;
      }
    }
    if (usedAI) refreshMe();
    if (!out.entry?.length) {
      setBusy(false);
      setNote((fallback ? fallback + " " : "") + "We couldn't find an entry rule. Say when to buy (or to short), e.g. \"Buy when the price is above the 50-day average\"." +
        (out.notes?.length ? " " + out.notes.join(" ") : ""));
      return;
    }
    const instrument = out.instrument ? await findInstrument(out.instrument, out.market || (market && market !== "CSV" ? market : null)) : null;
    const s = blankStrategy(out.name || nameFor({ ...blankStrategy(), entry: out.entry }, instrument?.symbol));
    const strategy: Strategy = {
      ...s, text: idea, entry: out.entry, exit: out.exit || [], entryJoin: out.entryJoin || "all", tf: out.tf || "1d",
      side: out.side === "short" || out.side === "both" ? out.side : "long", shortEntry: out.shortEntry ?? [], shortExit: out.shortExit ?? [],
      minScore: out.minScore ?? 0, session: out.session ?? s.session, product: out.product ?? "auto",
      risk: riskForCurrency({ ...s.risk, ...out.risk }, instrument?.currency),
    };
    try {
      await onBuilt({
        strategy, instrument, question: questionFrom(idea, instrument?.symbol),
        gaps: { mentioned: out.mentioned || [], notes: out.notes || [], instName: out.instrument, usedAI, fallback },
      });
      setText("");
    } finally {
      setBusy(false);
    }
  };

  const u = me?.usage;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <label className="sr-only" htmlFor="idea">Describe your trading idea</label>
      <textarea id="idea" className="input serif" autoFocus={autoFocus} value={text} maxLength={2000}
        style={{ fontSize: 20, minHeight: 130, lineHeight: 1.5, padding: "16px 18px" }}
        placeholder={ex.placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) build(); }} />
      <div className="spread" style={{ flexWrap: "wrap" }}>
        <button className="btn" disabled={busy} onClick={() => build()}>{busy ? "Building…" : busyLabel}</button>
        {u && <span className="small muted row" style={{ gap: 0 }}>{u.ai_limit == null ? "Unlimited AI builds" : `${Math.max(0, u.ai_limit - u.ai_used)} of ${u.ai_limit} AI builds left this month`}
          <Info>The AI turns your sentence into exact rules. If it's unavailable, a simple built-in converter takes over (it understands SMA, EMA, RSI and price rules).</Info></span>}
      </div>
      {note && <p className="small" style={{ color: "var(--orange-ink)" }} role="alert">{note}</p>}
      <div className="stack" style={{ gap: 8, marginTop: 4 }}>
        <span className="small muted">Not sure what to write? Try one of these:</span>
        <div className="examples">
          {ex.list.map((ex) => (
            <button key={ex} type="button" disabled={busy} onClick={() => { setText(ex); build(ex); }}>
              <span aria-hidden="true">→</span>{ex}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
