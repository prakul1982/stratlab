import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { money } from "../lib/format";
import { useApp } from "../lib/app";
import { INDIA_FEED, reconnectAt, type DataNote } from "../lib/dataBack";
import { defaultExit, opSay, refName, statedIn } from "../lib/rules";
import type { Instrument, Strategy } from "../lib/types";
import { Badge, Card, CardHead, Notice } from "./kit";
import "../pages/trade/trade.css";

/** What the idea didn't say, and the answers given so far: kept with the notebook, so the questions are still there
 * after the person leaves and comes back (R5O-010). */
export interface GapInfo {
  mentioned: string[]; notes: string[]; instName: string | null; usedAI: boolean; fallback: string; answered?: Record<string, string>;
  /** The market the builder gave the instrument's name ("IN" for RELIANCE): known by name while its data can't be searched (DA-004). */
  instMarket?: string | null;
  /** What didn't come out of the words as written: a rule left out, a number not in the rules (R11C-004). */
  warnings?: string[];
}

interface Opt { label: string; explain: string; rec?: boolean; apply: (s: Strategy) => Strategy | "pick-market" | { instrument: Instrument } }
interface Q { id: string; short: string; title: string; why: string; options: Opt[] }

const plain = (r: Strategy["entry"][number]["l"]) => refName(r);

function questions(s: Strategy, gaps: GapInfo, hasInstrument: boolean, defaults: Instrument[], currency: string, dataNote?: DataNote | null): Q[] {
  // what the idea said, at the build or in the words the rules were last rebuilt from, is never asked again (R11C-005: a
  // 3% stop given in "Edit in words" was asked again, and "Use the default answers" put 2% over it)
  const m = new Set([...gaps.mentioned, ...statedIn(s.text)]), qs: Q[] = [], r = s.risk;
  const together = s.entry.length > 1;
  const sell = s.side === "short";                 // a short idea sells first: its questions say sell, never buy (DA-006)
  if (!hasInstrument) {
    // India's data is offline (the banner says so): an Indian name is known, just not searchable until the login, at the time the banner gives (DA-004)
    const india = !!gaps.instName && !!dataNote && (INDIA_FEED.has(gaps.instMarket ?? "") || /\b(nifty|sensex)\b/i.test(gaps.instName));
    const back = reconnectAt(dataNote);
    qs.push({ id: "inst", short: "Instrument", title: "What do you want to test it on?",
      why: india ? `"${gaps.instName}" is an Indian listing, and Indian price data is offline right now, so it can't be looked up yet. ${back ? `It reconnects on ${back}.` : "It reconnects with the next daily data login."} Pick another market now, or come back then.`
        : gaps.instName ? `We couldn't find "${gaps.instName}". Pick one, or search every market.` : "The same rules can behave very differently on different markets.",
      options: [
        ...defaults.slice(0, 5).map((i, k) => ({ label: i.symbol, rec: k === 0, explain: i.market === "CRYPTO" ? "Crypto, trades 24/7" : i.type === "INDEX" ? "Indian index" : i.exchange || "",
          apply: () => ({ instrument: i }) })),
        { label: "Something else", explain: "Search any stock or coin, or upload your own data.", apply: () => "pick-market" as const },
      ] });
  }
  s.entry.forEach((c, k) => {
    if ((c.op === "gt" || c.op === "lt") && c.r.t !== "num") {
      const w = c.op === "gt" ? "above" : "below";
      // beside another condition it is a filter, a state that holds while the other one fires: a one-time cross of it
      // would almost never fall on the same candle (R11C-006: "price above the 200-day SMA" with RSI under 30 became a
      // cross, and 0 trades in 5 years). On its own, the cross stays the default.
      const act = sell ? "Sell short" : "Buy";
      qs.push({ id: `style${k}`, short: sell ? "Entry timing" : "Buy timing", title: `${act} only when it first crosses ${w}, or any time it's ${w}?`,
        why: together
          ? `"${plain(c.l)} is ${w} ${plain(c.r)}" is one of ${s.entry.length} ${sell ? "short" : "buy"} conditions. As a state it holds on every candle it stays ${w}, so the other conditions decide when to ${sell ? "sell short" : "buy"}; a one-time cross rarely falls on the same candle as them.`
          : `"${plain(c.l)} is ${w} ${plain(c.r)}" stays true on every candle, not just once. That decides how often you trade.`,
        options: [
          { label: `Only when it first crosses ${w}`, rec: !together, explain: `${sell ? "Sells short" : "Buys"} once, on the candle where it moves across.`,
            apply: (st) => ({ ...st, entry: st.entry.map((x, i) => (i === k ? { ...x, op: x.op === "gt" ? "xa" : "xb" } : x)) }) },
          { label: `Any time it's ${w}`, rec: together, apply: (st) => st,
            explain: together ? `A filter: ${sell ? "sells short" : "buys"} when the other conditions fire while it holds.` : `${sell ? "Sells short" : "Buys"} straight away, and again after every exit while it stays there.` },
        ] });
    }
  });
  if (!m.has("exit")) {
    // the default sell rule is already in the rules (withDefaultExit), so leaving this question changes nothing
    const opts: Opt[] = [];
    const dflt = defaultExit(s);
    if (dflt.length) {
      const d = dflt[0];
      // worded as the rule is: "crosses below", not "drops below" over a rule that says crosses (DA-006)
      opts.push({ label: `${sell ? "Buy back" : "Sell"} when ${plain(d.l)} ${opSay(d.op)} ${d.r.t === "num" ? d.r.v : plain(d.r)}`, rec: true,
        explain: "Exit when the entry condition no longer holds.", apply: (st) => ({ ...st, exit: defaultExit(st) }) });
    }
    opts.push({ label: r.tgt > 0 ? "Only my stop loss and target" : "No sell rule, only my stop loss", rec: !opts.length,
      explain: r.tgt > 0 ? "Exit only at a fixed loss or gain." : "A trade closes only if the stop loss is hit, or at the end of the test.", apply: (st) => ({ ...st, exit: [] }) });
    qs.push({ id: "exit", short: "Sell rule", title: "When should it sell?",
      why: dflt.length ? "Your idea says when to buy but not when to sell. Until you choose, the default below is the sell rule." : "Your idea says when to buy but not when to sell, and no sell rule is set.",
      options: opts });
  }
  if (!m.has("tf")) {
    qs.push({ id: "tf", short: "Candles", title: "How long should each candle be?", why: "Your rules are checked once per candle.",
      options: [
        { label: "1 day", rec: true, explain: "Trades lasting days to weeks. Fewest signals.", apply: (st) => ({ ...st, tf: "1d" }) },
        { label: "1 hour", explain: "Trades last hours to days. More signals.", apply: (st) => ({ ...st, tf: "1h" }) },
        { label: "15 min", explain: "Intraday: several trades a day.", apply: (st) => ({ ...st, tf: "15m" }) },
      ] });
  }
  if (!m.has("sl")) {
    const lv = s.tf === "1d" ? [1, 2, 4] : [0.5, 1, 2];
    qs.push({ id: "sl", short: "Stop loss", title: "How big a loss will you accept on one trade?", why: "A stop loss sells automatically if the price falls this far.",
      options: [
        { label: `${lv[0]}% (smallest)`, explain: "Small losses; normal wiggles may hit it.", apply: (st) => ({ ...st, risk: { ...st.risk, sl: lv[0] } }) },
        { label: `${lv[1]}% (middle)`, rec: true, explain: "Room for normal moves; losses stay moderate.", apply: (st) => ({ ...st, risk: { ...st.risk, sl: lv[1] } }) },
        { label: `${lv[2]}% (widest)`, explain: "More room, bigger losses, smaller positions.", apply: (st) => ({ ...st, risk: { ...st.risk, sl: lv[2] } }) },
        { label: "No stop loss", explain: "A losing trade runs until the sell rule fires.", apply: (st) => ({ ...st, risk: { ...st.risk, sl: 0 } }) },
      ] });
  }
  if (!m.has("tgt")) {
    const sl = r.sl || 2, hasExit = s.exit.length > 0;
    // never a target the person didn't ask for: "No target" is the default, and it is what the rules hold (R5O-010)
    qs.push({ id: "tgt", short: "Target", title: "Take profit at a fixed gain?", why: hasExit ? "Your sell rule will close trades; a target also closes a trade at a fixed gain." : "Without a sell rule, a target is what closes a trade at a gain.",
      options: [
        { label: hasExit ? "No target, let the sell rule decide" : "No target", rec: true, explain: hasExit ? "Trades run until the sell rule fires." : "Trades close at the stop loss or at the end of the test.",
          apply: (st: Strategy) => ({ ...st, risk: { ...st.risk, tgt: 0 } }) },
        { label: `${+(sl * 2).toFixed(2)}% (2× the stop)`, explain: "A gain of twice the stop.", apply: (st) => ({ ...st, risk: { ...st.risk, tgt: +(sl * 2).toFixed(2) } }) },
        { label: `${+(sl * 3).toFixed(2)}% (3× the stop)`, explain: "A bigger gain; fewer trades reach it.", apply: (st) => ({ ...st, risk: { ...st.risk, tgt: +(sl * 3).toFixed(2) } }) },
      ] });
  }
  if (!m.has("riskPct")) {
    qs.push({ id: "risk", short: "Risk per trade", title: "How much should one trade risk?", why: `If the stop loss hits, you lose about this much of ${money(r.capital, currency)}.`,
      options: [0.5, 1, 2].map((v) => ({ label: `${v}% (${money((r.capital * v) / 100, currency)})`, rec: v === 1,
        explain: v === 0.5 ? "The smallest of the three." : v === 1 ? "The middle one." : "The largest: bigger swings both ways.",
        apply: (st: Strategy) => ({ ...st, risk: { ...st.risk, riskPct: v } }) })) });
  }
  return qs;
}

export function GapsCard({ s, gaps, hasInstrument, currency, onStrategy, onInstrument, onPickMarket, onDone, onAnswered }: {
  s: Strategy; gaps: GapInfo; hasInstrument: boolean; currency: string;
  onStrategy: (s: Strategy) => void; onInstrument: (i: Instrument) => void; onPickMarket: () => void; onDone: () => void;
  /** Called with every answer so far, to keep them with the notebook. */
  onAnswered?: (answered: Record<string, string>) => void;
}) {
  const [answered, setAnsweredState] = useState<Record<string, string>>(gaps.answered ?? {});
  const latest = useRef(answered);         // several answers in one click ("Use the default answers") all count
  const setAnswered = (f: (a: Record<string, string>) => Record<string, string>) => {
    latest.current = f(latest.current);
    setAnsweredState(latest.current);
    onAnswered?.(latest.current);
  };
  const [defaults, setDefaults] = useState<Instrument[]>([]);
  useEffect(() => { api<Instrument[]>("/instruments/defaults").then(setDefaults).catch(() => {}); }, []);
  const { me } = useApp();
  const all = questions(s, gaps, hasInstrument, defaults, currency, me?.data_note);
  const open = all.filter((q) => !answered[q.id]);
  const now = open[0];

  const choose = (q: Q, o: Opt, cur: Strategy): Strategy => {
    const res = o.apply(cur);
    if (res === "pick-market") { onPickMarket(); return cur; }
    if ("instrument" in res) { onInstrument(res.instrument); setAnswered((a) => ({ ...a, [q.id]: o.label })); return cur; }
    setAnswered((a) => ({ ...a, [q.id]: o.label }));
    return res;
  };

  return (
    <Card label="Questions about your idea">
      <div aria-live="polite" className="k-stack">
        {!gaps.usedAI && gaps.fallback && <Notice tone="warn">{gaps.fallback}</Notice>}
        {(gaps.warnings ?? []).map((w) => <Notice key={w} tone="warn" role="status">{w}</Notice>)}
        {gaps.notes.length > 0 && <ul className="k-list muted">{gaps.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        {Object.entries(answered).map(([id, label]) => (
          <div key={id} className="k-row k-small"><Badge tone="ok" dot={false}>✓</Badge>{all.find((q) => q.id === id)?.short ?? "Answer"}: <b>{label}</b></div>
        ))}
        {now ? (
          <>
            <CardHead title={now.title} actions={<span className="k-note">Question {Object.keys(answered).length + 1} of {Object.keys(answered).length + open.length}</span>} />
            <p className="k-small k-muted">{now.why}</p>
            <div className="k-starters">
              {now.options.map((o) => (
                <button type="button" key={o.label} className="k-starter" onClick={() => onStrategy(choose(now, o, s))}>
                  {o.rec && <Badge tone="ok" dot={false}>Default</Badge>}
                  <b>{o.label}</b><span className="k-small k-muted">{o.explain}</span>
                </button>
              ))}
            </div>
            <div className="k-spread k-note">
              <span>We only ask about what your idea didn't say.</span>
              <button type="button" className="btn quiet sm" onClick={() => {
                let cur = s;
                for (const q of open) {
                  const o = q.options.find((x) => x.rec) ?? q.options[0];
                  if (q.id === "inst") continue;
                  cur = choose(q, o, cur);
                }
                onStrategy(cur);
              }}>Use the default answers</button>
            </div>
          </>
        ) : (
          <div className="k-spread">
            <div><b>Every detail is filled in.</b> <span className="k-muted">Check the rules below, then run your first experiment.</span></div>
            <button type="button" className="btn sm quiet" onClick={onDone}>Close</button>
          </div>
        )}
      </div>
    </Card>
  );
}
