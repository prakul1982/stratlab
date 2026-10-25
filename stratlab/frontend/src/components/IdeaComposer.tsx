import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { blankStrategy, detectInstrument, detectTf, meaningful, nameFor, noRuleNote, parseStrategyText, proNames, questionFrom, riskForCurrency, ruleLines, ruleWarnings, usesPro, withDefaultExit } from "../lib/rules";
import { listing } from "../lib/offer";
import { usePlanPrice } from "../lib/currency";
import { PlanActions } from "./PlanInterest";
import type { Cond, Instrument, Risk, Session, Strategy, Tf, Group } from "../lib/types";
import { Info } from "./ui";
import { Notice } from "./kit";
import "../pages/trade/trade.css";

export interface Built {
  strategy: Strategy;
  instrument: Instrument | null;
  question: string;
  gaps: { mentioned: string[]; notes: string[]; instName: string | null; instMarket?: string | null; usedAI: boolean; fallback: string; warnings?: string[] };
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

/** Example ideas in the market (and on the instrument) you picked, so one click never tests the wrong thing. The last two
 * use Basic's indicators (the lowest low of past days, Stage 2 and the Supertrend): tagged so on Free, where they can't be
 * built (DP1-003). */
export function examplesFor(market?: string, symbol?: string | null): { placeholder: string; list: string[]; basic: string[] } {
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
    basic: [
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

/** Why an idea on Basic's indicators isn't built on a plan without them (the server words its own the same way). */
export const lockedNote = (names: string[]) => {
  const said = listing(names);
  return `${said.charAt(0).toUpperCase()}${said.slice(1)} ${names.length === 1 ? "is" : "are"} on the Basic plan. On Free, notebook rules use price, SMA, EMA and RSI, so this idea wasn't built: leaving that part out would test a different idea. No AI build was used.`;
};

/** Turn a sentence into rules: the AI builder, or the simple converter when the AI can't run (or hands back no rule).
 * Returns the built strategy, or a note saying what's missing (`system`: the fault is ours, not the wording's).
 * `confirm`: the simple converter made the rules, which can be wrong, so they are shown for a yes first (DP1-004).
 * `locked`: the idea uses indicators the plan doesn't have, so nothing was built (DP1-002). `allIndicators`: whether the
 * plan has every indicator (unknown: taken as yes, and the server says so).
 * Throws only on errors worth showing as-is. */
export async function buildIdea(idea: string, market?: string, opts: { allIndicators?: boolean } = {}): Promise<{ built: Built | null; note: string; usedAI: boolean; system?: boolean; options?: boolean; confirm?: boolean; locked?: boolean }> {
  let out: AIOut, usedAI = true, fallback = "";
  let parsedDropped: string[] = [];   // rules the simple converter read and left out as meaningless: said, never silent
  let parsedUnread: string[] = [];    // clauses the simple converter could not read at all: said, never guessed at (DA-002)
  try {
    out = await api<AIOut>("/ai/strategy", { method: "POST", body: { text: idea } });
  } catch (e) {
    const err = e as ApiError;
    // an options idea (a single option, a straddle, a multi-leg position) is refused whole: no rules are made from a part of it (DA-001)
    if (err.code === "options_idea") return { built: null, usedAI: false, system: false, options: true, note: err.message };
    // an idea built on Basic's indicators is refused whole on Free, by name, and costs no build (DP1-002, DP1-003)
    if (err.code === "indicator_plan") return { built: null, usedAI: false, system: false, locked: true, note: err.message };
    if (!(["ai_busy", "ai_limit", "ai_daily_limit", "ai_failed", "no_backend", "network"].includes(err.code || "") || err.status >= 500)) throw e;
    usedAI = false;
    // the converter can get an idea wrong ("crosses below 6" from "idea 6"), so it is said, never used quietly (DP1-004)
    fallback = err.code === "ai_limit" || err.code === "ai_daily_limit"
      ? `${err.message} The simple converter read your idea instead, and it can get an idea wrong, so check the rules it made.`
      : "The AI builder isn't available right now, so the simple converter read your idea (it understands SMA, EMA, RSI and price rules). It can get an idea wrong, so check the rules it made.";
    const p = parseStrategyText(idea);
    parsedDropped = p.dropped;
    parsedUnread = p.unread;
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
    parsedDropped = p.dropped;
    parsedUnread = p.unread;
    if (p.entry.length) {
      const mentioned = Object.keys(p.risk);
      const tf = detectTf(idea), inst = detectInstrument(idea);
      if (p.exit.length) mentioned.push("exit");
      if (tf) mentioned.push("tf");
      if (inst) mentioned.push("instrument");
      fallback = "The AI builder gave back no rules for this, so the simple converter read your idea (it understands SMA, EMA, RSI and price rules). It can get an idea wrong, so check the rules it made.";
      out = { ...out, entry: p.entry, exit: p.exit, entryJoin: "all", tf: out.tf ?? tf, instrument: out.instrument ?? inst, risk: { ...out.risk, ...p.risk }, mentioned, side: p.side };
    }
  }
  const unreadNote = (parsedUnread.length ? `The simple converter couldn't read "${parsedUnread.slice(0, 2).join('"; "')}". Check the rules.` : "").slice(0, 280);
  if (!out.entry?.length) {
    const r = noRuleNote(idea, out.notes);
    // a clause the converter couldn't read is the reason, not "your wording looks fine, it's on our side"
    const why = unreadNote && r.system ? "Describe the rule with price, SMA, EMA or RSI, or build the rules by hand." : r.note;
    return { built: null, usedAI, system: r.system && !unreadNote, note: [fallback, unreadNote, why].filter(Boolean).join(" ") };
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
  // a trailing stop asked for is the stop: the notebook's default 2% stop is not added beside it, where it would decide nearly
  // every exit unseen (DA-008)
  if ((strategy.risk.trail ?? 0) > 0 && !mentioned.includes("sl") && out.risk?.sl === undefined && !("sl" in extra)) {
    strategy.risk = { ...strategy.risk, sl: 0 };
    mentioned.push("sl");
  }
  if (!strategy.entry.length) {
    const r = noRuleNote(idea, out.notes);
    return { built: null, usedAI, system: r.system, note: (fallback ? fallback + " " : "") + r.note };
  }
  // the simple converter reads the lowest low of past days and Stage 2 too: on a plan without them nothing is built from
  // part of the idea (DP1-003)
  if (fallback && opts.allIndicators === false && usesPro(strategy)) return { built: null, usedAI, system: false, locked: true, note: lockedNote(proNames(strategy)) };
  const built = withDefaultExit(strategy, mentioned);
  return {
    usedAI, note: fallback, confirm: !!fallback,
    // the sell rule the questions offer as the default is the one the notebook runs until the person picks another
    built: { strategy: built, instrument, question: questionFrom(idea, instrument?.symbol),
      gaps: { mentioned, notes: out.notes || [], instName: out.instrument, instMarket: out.market ?? (market && market !== "CSV" ? market : null), usedAI, fallback,
        warnings: [...ruleWarnings(idea, built, [...Object.values(checked).flatMap((x) => x.dropped), ...parsedDropped], [out.instrument, instrument?.symbol, instrument?.name]),
          ...(unreadNote ? [unreadNote] : [])].slice(0, 10) } },
  };
}

export function IdeaComposer({ onBuilt, busyLabel = "Build my notebook", autoFocus, initial = "", market, symbol, byHand = true }: {
  /** false when what was built couldn't be kept (the notebook wasn't made): the words stay in the box to try again */
  onBuilt: (b: Built) => Promise<boolean | void> | boolean | void; busyLabel?: string; autoFocus?: boolean; initial?: string;
  /** Offer "Build the rules by hand" when a build finds no rule (off where that would wipe rules already written). */
  byHand?: boolean;
  /** The market and instrument already chosen: the examples use them, and names in the idea are looked up there. */
  market?: string; symbol?: string | null;
}) {
  const ex = examplesFor(market, symbol);
  const { me, refreshMe, fail, allIndicators } = useApp();
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [stuck, setStuck] = useState(false);     // a build found no rule: offer another go, the classic ideas, the manual builder
  const [options, setOptions] = useState(false);   // the idea trades options: the way on is the Options builder, not another go (DA-001)
  const [locked, setLocked] = useState(false);     // the idea uses Basic's indicators: the plan and its price, not another go (DP1-002)
  // rules the simple converter made, shown for a yes before a notebook is made from them (DP1-004)
  const [pending, setPending] = useState<{ built: Built; idea: string } | null>(null);
  const basicPrice = usePlanPrice(!allIndicators ? "basic" : null);

  const building = useRef(false);            // Ctrl+Enter in the box while a build runs must not start a second one
  const build = async (idea = text) => {
    if (building.current) return;
    idea = idea.trim();
    setStuck(false);
    setOptions(false);
    setLocked(false);
    setPending(null);
    if (idea.length < 5) { setNote("Describe your idea first, for example: \"Buy NIFTY 50 when it's above the 50-day average\"."); return; }
    building.current = true;
    setBusy(true);
    setNote(null);
    try {
      const r = await buildIdea(idea, market, { allIndicators: me ? allIndicators : undefined });
      if (!r.built) { setNote(r.note); setOptions(!!r.options); setLocked(!!r.locked); setStuck(!r.options && !r.locked); return; }
      if (r.confirm) { setNote(r.note); setPending({ built: r.built, idea }); return; }
      if ((await onBuilt(r.built)) !== false) setText("");
    } catch (e) {
      fail(e);
    } finally {
      // the count of builds left, read again after every try: one that made no rules costs none, and the box must say the
      // number the server holds, not the one from before (DP1-001)
      refreshMe();
      building.current = false;
      setBusy(false);
    }
  };
  const keep = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      if ((await onBuilt(pending.built)) !== false) { setText(""); setPending(null); setNote(null); }
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  // an example on Basic's indicators, picked on Free: said at once, nothing sent and no build used (DP1-003)
  const pick = (idea: string) => {
    setText(idea);
    if (!allIndicators && me && ex.basic.includes(idea)) {
      const named = idea.includes("Supertrend") ? ["the market stage (Stage 2)", "Supertrend"] : ["the highest high or lowest low of past candles"];
      setPending(null); setOptions(false); setStuck(false); setLocked(true); setNote(lockedNote(named));
      return;
    }
    void build(idea);
  };

  const classic = typeof document !== "undefined" ? document.getElementById("classic-ideas") : null;
  const buildByHand = async () => {
    const idea = text.trim();
    const p = parseStrategyText(idea), s = blankStrategy(nameFor(blankStrategy(), symbol ?? undefined));
    setBusy(true);
    try {
      if (await onBuilt({ strategy: { ...s, text: idea, risk: { ...s.risk, ...p.risk } }, instrument: null, question: questionFrom(idea, symbol),
        gaps: { mentioned: Object.keys(p.risk), notes: [], instName: null, usedAI: false, fallback: "" } }) !== false) setText("");
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
        {u && <span className="k-small k-muted k-row">{u.ai_limit == null ? `Unlimited AI builds${u.ai_builds_per_day ? ` (up to ${u.ai_builds_per_day} a day)` : ""}` : `${Math.max(0, u.ai_limit - u.ai_used)} of ${u.ai_limit} AI builds left this month`}
          <Info>The AI turns your sentence into exact rules. If it's unavailable, a simple built-in converter takes over (it understands SMA, EMA, RSI and price rules).</Info></span>}
      </div>
      {note && (
        <Notice tone="warn" role="status" actions={options ? <Link className="btn sm" to="/options">Open the Options builder</Link> : locked ? <>
          <PlanActions />
          {classic && <button type="button" className="btn quiet sm" onClick={() => classic.scrollIntoView({ behavior: "smooth" })}>Classic ideas</button>}
        </> : pending ? <>
          <button type="button" className="btn sm" disabled={busy} onClick={() => void keep()}>Build with these rules</button>
          {classic && <button type="button" className="btn quiet sm" onClick={() => classic.scrollIntoView({ behavior: "smooth" })}>Classic ideas (no AI build)</button>}
          {byHand && <button type="button" className="btn quiet sm" disabled={busy} onClick={() => void buildByHand()}>Build the rules by hand</button>}
        </> : stuck ? <>
          <button type="button" className="btn sm" disabled={busy} onClick={() => build()}>Try again</button>
          {classic && <button type="button" className="btn quiet sm" onClick={() => classic.scrollIntoView({ behavior: "smooth" })}>Classic ideas</button>}
          {byHand && <button type="button" className="btn quiet sm" disabled={busy} onClick={() => void buildByHand()}>Build the rules by hand</button>}
        </> : undefined}>
          <span className="k-stack k-tight">
            <span>{note}{locked && basicPrice ? ` ${basicPrice}` : ""}</span>
            {pending && (
              <span className="k-stack k-tight" data-testid="converter-read">
                <span>It read your idea as:</span>
                <ul className="k-list">{ruleLines(pending.built.strategy, pending.built.gaps.mentioned).map((l) => <li key={l}>{l}</li>)}</ul>
                {(pending.built.gaps.warnings ?? []).map((w) => <span key={w}>{w}</span>)}
              </span>
            )}
          </span>
        </Notice>
      )}
      <div className="k-stack k-tight">
        <span className="k-small k-muted">Not sure what to write? Try one of these:</span>
        <div className="examples">
          {ex.list.map((idea) => (
            <button key={idea} type="button" disabled={busy} onClick={() => pick(idea)}>
              <span aria-hidden="true">→</span>{idea}
              {/* an example the plan can't build is tagged before it is picked (DP1-003) */}
              {me && !allIndicators && ex.basic.includes(idea) && <span className="k-small k-muted" data-testid="example-basic"> · Basic</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
