import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { money } from "../lib/format";
import { refName } from "../lib/rules";
import type { Instrument, Strategy } from "../lib/types";
import { Badge, Card, CardHead, Notice } from "./kit";
import "../pages/trade/trade.css";

export interface GapInfo { mentioned: string[]; notes: string[]; instName: string | null; usedAI: boolean; fallback: string }

interface Opt { label: string; explain: string; rec?: boolean; apply: (s: Strategy) => Strategy | "pick-market" | { instrument: Instrument } }
interface Q { id: string; short: string; title: string; why: string; options: Opt[] }

const plain = (r: Strategy["entry"][number]["l"]) => refName(r);

function questions(s: Strategy, gaps: GapInfo, hasInstrument: boolean, defaults: Instrument[], currency: string): Q[] {
  const m = new Set(gaps.mentioned), qs: Q[] = [], first = s.entry[0], r = s.risk;
  if (!hasInstrument) {
    qs.push({ id: "inst", short: "Instrument", title: "What do you want to test it on?",
      why: gaps.instName ? `We couldn't find "${gaps.instName}". Pick one, or search every market.` : "The same rules can behave very differently on different markets.",
      options: [
        ...defaults.slice(0, 5).map((i, k) => ({ label: i.symbol, rec: k === 0, explain: i.market === "CRYPTO" ? "Crypto, trades 24/7" : i.type === "INDEX" ? "Indian index" : i.exchange || "",
          apply: () => ({ instrument: i }) })),
        { label: "Something else", explain: "Search any stock or coin, or upload your own data.", apply: () => "pick-market" as const },
      ] });
  }
  s.entry.forEach((c, k) => {
    if ((c.op === "gt" || c.op === "lt") && c.r.t !== "num") {
      const w = c.op === "gt" ? "above" : "below";
      qs.push({ id: `style${k}`, short: "Buy timing", title: `Buy only when it first crosses ${w}, or any time it's ${w}?`,
        why: `"${plain(c.l)} is ${w} ${plain(c.r)}" stays true on every candle, not just once. That decides how often you trade.`,
        options: [
          { label: `Only when it first crosses ${w}`, rec: true, explain: "Buys once, on the candle where it moves across.",
            apply: (st) => ({ ...st, entry: st.entry.map((x, i) => (i === k ? { ...x, op: x.op === "gt" ? "xa" : "xb" } : x)) }) },
          { label: `Any time it's ${w}`, explain: "Buys straight away, and again after every exit while it stays there.", apply: (st) => st },
        ] });
    }
  });
  if (!m.has("exit")) {
    const opts: Opt[] = [];
    if (first && first.r.t !== "num" && (first.op === "gt" || first.op === "xa"))
      opts.push({ label: `Sell when ${plain(first.l)} drops below ${plain(first.r)}`, rec: true, explain: "Exit when the entry condition no longer holds.",
        apply: (st) => ({ ...st, exit: [{ l: { ...first.l }, op: "xb", r: { ...first.r } }] }) });
    if (first && first.l.t === "rsi" && (first.op === "lt" || first.op === "xb"))
      opts.push({ label: "Sell when RSI rises back above 55", rec: true, explain: "Exit once RSI is back above 55.",
        apply: (st) => ({ ...st, exit: [{ l: { ...first.l }, op: "xa", r: { t: "num", v: 55 } }] }) });
    opts.push({ label: "Only my stop loss and target", rec: !opts.length, explain: "Exit only at a fixed loss or gain.", apply: (st) => ({ ...st, exit: [] }) });
    qs.push({ id: "exit", short: "Sell rule", title: "When should it sell?", why: "Your idea says when to buy but not when to sell.", options: opts });
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
    qs.push({ id: "tgt", short: "Target", title: "Take profit at a fixed gain?", why: hasExit ? "Your sell rule will close trades; a target also closes a trade at a fixed gain." : "Without a sell rule, a target is what closes a trade at a gain.",
      options: [
        ...(hasExit ? [{ label: "No target, let the sell rule decide", rec: true, explain: "Trades run until the sell rule fires.", apply: (st: Strategy) => ({ ...st, risk: { ...st.risk, tgt: 0 } }) }] : []),
        { label: `${+(sl * 2).toFixed(2)}% (2× the stop)`, rec: !hasExit, explain: "A gain of twice the stop.", apply: (st) => ({ ...st, risk: { ...st.risk, tgt: +(sl * 2).toFixed(2) } }) },
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

export function GapsCard({ s, gaps, hasInstrument, currency, onStrategy, onInstrument, onPickMarket, onDone }: {
  s: Strategy; gaps: GapInfo; hasInstrument: boolean; currency: string;
  onStrategy: (s: Strategy) => void; onInstrument: (i: Instrument) => void; onPickMarket: () => void; onDone: () => void;
}) {
  const [answered, setAnswered] = useState<Record<string, string>>({});
  const [defaults, setDefaults] = useState<Instrument[]>([]);
  useEffect(() => { api<Instrument[]>("/instruments/defaults").then(setDefaults).catch(() => {}); }, []);
  const all = questions(s, gaps, hasInstrument, defaults, currency);
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
        {gaps.notes.length > 0 && <ul className="k-list muted">{gaps.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        {Object.entries(answered).map(([id, label]) => (
          <div key={id} className="k-row k-small"><Badge tone="ok" dot={false}>✓</Badge>{all.find((q) => q.id === id)?.short ?? "Answer"}: <b>{label}</b></div>
        ))}
        {now ? (
          <>
            <CardHead title={now.title} actions={<span className="k-note">{Object.keys(answered).length + 1} of {Object.keys(answered).length + open.length}</span>} />
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
