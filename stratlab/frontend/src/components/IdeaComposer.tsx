import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { blankStrategy, detectInstrument, detectTf, meaningful, nameFor, noRuleNote, parseStrategyText, questionFrom, riskForCurrency, ruleWarnings, withDefaultExit } from "../lib/rules";
import type { Cond, Instrument, Risk, Session, Strategy, Tf, Group } from "../lib/types";
import { Info } from "./ui";
import { Notice } from "./kit";
import "../pages/trade/trade.css";

export interface Built {
  strategy: Strategy;
  instrument: Instrument | null;
  question: string;
  gaps: { mentioned: string[]; notes: string[]; instName: string | null; usedAI: boolean; fallback: string; warnings?: string[] };
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
  MCX: ["GOLDM", "CRUDEOIL", "SILVERM"], CDS: ["USDINR", "EURINR", "GBPINR"], CMDTY: ["gold", "WTI crude", "silver"],
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
      `Buy${on(b)} when it's in Stage 2 and the price is above the Supertrend, sell when it crosses back below`,
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
      ?? rows.find((r) => ["EQ", "INDEX", "CRYPTO", "ETF", "FX"].includes(r.type || "") || (r.type === "FUT" && (r.market === "MCX" || r.market === "CDS" || r.market === "CMDTY"))) ?? null;
  } catch {
    return null;
  }
}

/** Turn a sentence into rules: the AI builder, or the simple converter when the AI can't run (or hands back no rule).
 * Returns the built strategy, or a note saying what's missing (`system`: the fault is ours, not the wording's).
 * Throws only on errors worth showing as-is. */
export async function buildIdea(idea: string, market?: string): Promise<{ built: Built | null; note: string; usedAI: boolean; system?: boolean }> {
  let out: AIOut, usedAI = true, fallback = "";
  try {
    out = await api<AIOut>("/ai/strategy", { method: "POST", body: { text: idea } });
  } catch (e) {
    const err = e as ApiError;
    if (!(["ai_busy", "ai_limit", "ai_daily_limit", "ai_failed", "no_backend", "network"].includes(err.code || "") || err.status >= 500)) throw e;
    usedAI = false;
    fallback = err.code === "ai_limit" || err.code === "ai_daily_limit"
      ? `${err.message} We used the simple converter instead.`
      : "The AI builder isn't available right now, so we used the simple converter (it understands SMA, EMA, RSI and price rules).";
    const p = parseStrategyText(idea);
    const mentioned = Object.keys(p.risk);
    const tf = detectTf(idea), inst = detectInstrument(idea);
    if (p.exit.length) mentioned.push("exit");
    if (tf) mentioned.push("tf");
    if (inst) mentioned.push("instrument");
    out = { entry: p.entry, exit: p.exit, entryJoin: "all", tf, name: null, instrument: inst, risk: p.risk, mentioned, notes: [], side: p.side };
  }
  if (!out.entry?.length && usedAI) {
    // the AI answered with no rule: the simple converter gets a go before anyone is told their wording is the problem
    const p = parseStrategyText(idea);
    if (p.entry.length) {
      const mentioned = Object.keys(p.risk);
      const tf = detectTf(idea), inst = detectInstrument(idea);
      if (p.exit.length) mentioned.push("exit");
      if (tf) mentioned.push("tf");
      if (inst) mentioned.push("instrument");
      fallback = "The AI builder gave back no rules for this, so we used the simple converter (it understands SMA, EMA, RSI and price rules).";
      out = { ...out, entry: p.entry, exit: p.exit, entryJoin: "all", tf: out.tf ?? tf, instrument: out.instrument ?? inst, risk: { ...out.risk, ...p.risk }, mentioned, side: p.side };
    }
  }
  if (!out.entry?.length) {
    const r = noRuleNote(idea, out.notes);
    return { built: null, usedAI, system: r.system, note: (fallback ? fallback + " " : "") + r.note };
  }
  const instrument = out.instrument ? await findInstrument(out.instrument, out.market || (market && market !== "CSV" ? market : null)) : null;
  // what the sentence plainly says about the money side ("no stop loss", "stop loss 3%", "after 15 bars") stands when the
  // builder gave no value of its own for it, and counts as said, so no question asks it again (R11C-005)
  const said = parseStrategyText(idea).risk;
  const extra = Object.fromEntries(Object.entries(said).filter(([k]) => !(k in (out.risk || {}))));
  const mentioned = [...new Set([...(out.mentioned || []), ...Object.keys(extra)])];
  // rules that can't mean anything are left out, and said (R11C-004: "Price crosses below 0" from "after 15 bars")
  const checked = { entry: meaningful(out.entry), exit: meaningful(out.exit || []), shortEntry: meaningful(out.shortEntry ?? []), shortExit: meaningful(out.shortExit ?? []) };
  const s = blankStrategy(out.name || nameFor({ ...blankStrategy(), entry: checked.entry.kept }, instrument?.symbol));
  const strategy: Strategy = {
    ...s, text: idea, entry: checked.entry.kept, exit: checked.exit.kept, entryJoin: out.entryJoin || "all", tf: out.tf || "1d",
    side: out.side === "short" || out.side === "both" ? out.side : "long", shortEntry: checked.shortEntry.kept, shortExit: checked.shortExit.kept,
    minScore: out.minScore ?? 0, session: out.session ?? s.session, product: out.product ?? "auto",
    risk: riskForCurrency({ ...s.risk, ...extra, ...out.risk }, instrument?.currency),
  };
  if (!strategy.entry.length) {
    const r = noRuleNote(idea, out.notes);
    return { built: null, usedAI, system: r.system, note: (fallback ? fallback + " " : "") + r.note };
  }
  const built = withDefaultExit(strategy, mentioned);
  return {
    usedAI, note: fallback,
    // the sell rule the questions offer as the default is the one the notebook runs until the person picks another
    built: { strategy: built, instrument, question: questionFrom(idea, instrument?.symbol),
      gaps: { mentioned, notes: out.notes || [], instName: out.instrument, usedAI, fallback,
        warnings: ruleWarnings(idea, built, Object.values(checked).flatMap((x) => x.dropped), [out.instrument, instrument?.symbol, instrument?.name]) } },
  };
}

export function IdeaComposer({ onBuilt, busyLabel = "Build my notebook", autoFocus, initial = "", market, symbol, byHand = true }: {
  onBuilt: (b: Built) => Promise<void> | void; busyLabel?: string; autoFocus?: boolean; initial?: string;
  /** Offer "Build the rules by hand" when a build finds no rule (off where that would wipe rules already written). */
  byHand?: boolean;
  /** The market and instrument already chosen: the examples use them, and names in the idea are looked up there. */
  market?: string; symbol?: string | null;
}) {
  const ex = examplesFor(market, symbol);
  const { me, refreshMe, fail } = useApp();
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [stuck, setStuck] = useState(false);     // a build found no rule: offer another go, the classic ideas, the manual builder

  const build = async (idea = text) => {
    idea = idea.trim();
    setStuck(false);
    if (idea.length < 5) { setNote("Describe your idea first, for example: \"Buy NIFTY 50 when it's above the 50-day average\"."); return; }
    setBusy(true);
    setNote(null);
    try {
      const r = await buildIdea(idea, market);
      if (r.usedAI) refreshMe();
      if (!r.built) { setNote(r.note); setStuck(true); return; }
      await onBuilt(r.built);
      setText("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const classic = typeof document !== "undefined" ? document.getElementById("classic-ideas") : null;
  const buildByHand = async () => {
    const idea = text.trim();
    const p = parseStrategyText(idea), s = blankStrategy(nameFor(blankStrategy(), symbol ?? undefined));
    setBusy(true);
    try {
      await onBuilt({ strategy: { ...s, text: idea, risk: { ...s.risk, ...p.risk } }, instrument: null, question: questionFrom(idea, symbol),
        gaps: { mentioned: Object.keys(p.risk), notes: [], instName: null, usedAI: false, fallback: "" } });
      setText("");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const u = me?.usage;
  return (
    <div className="k-stack">
      <label className="sr-only" htmlFor="idea">Describe your trading idea</label>
      <textarea id="idea" className="k-textarea k-idea" autoFocus={autoFocus} value={text} maxLength={2000}
        placeholder={ex.placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) build(); }} />
      <div className="k-row">
        <button type="button" className="btn" disabled={busy} onClick={() => build()}>{busy ? "Building…" : busyLabel}</button>
        {u && <span className="k-small k-muted k-row">{u.ai_limit == null ? "Unlimited AI builds" : `${Math.max(0, u.ai_limit - u.ai_used)} of ${u.ai_limit} AI builds left this month`}
          <Info>The AI turns your sentence into exact rules. If it's unavailable, a simple built-in converter takes over (it understands SMA, EMA, RSI and price rules).</Info></span>}
      </div>
      {note && (
        <Notice tone="warn" role="status" actions={stuck ? <>
          <button type="button" className="btn sm" disabled={busy} onClick={() => build()}>Try again</button>
          {classic && <button type="button" className="btn quiet sm" onClick={() => classic.scrollIntoView({ behavior: "smooth" })}>Classic ideas</button>}
          {byHand && <button type="button" className="btn quiet sm" disabled={busy} onClick={() => void buildByHand()}>Build the rules by hand</button>}
        </> : undefined}>{note}</Notice>
      )}
      <div className="k-stack k-tight">
        <span className="k-small k-muted">Not sure what to write? Try one of these:</span>
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
