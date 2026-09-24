import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { blankStrategy, detectInstrument, detectTf, nameFor, parseStrategyText, questionFrom, riskForCurrency } from "../lib/rules";
import type { Cond, Instrument, Risk, Strategy, Tf } from "../lib/types";
import { Info } from "./ui";

export interface Built {
  strategy: Strategy;
  instrument: Instrument | null;
  question: string;
  gaps: { mentioned: string[]; notes: string[]; instName: string | null; usedAI: boolean; fallback: string };
}

interface AIOut {
  entry: Cond[]; exit: Cond[]; entryJoin: "all" | "any"; tf: Tf | null; name: string | null; instrument: string | null;
  market?: string | null; risk: Partial<Risk>; mentioned: string[]; notes: string[]; usage?: { ai_used: number; ai_limit: number | null };
}

const EXAMPLES = [
  "Buy NIFTY 50 when the 20 EMA crosses above the 50 EMA, stop loss 2%",
  "Buy Bitcoin when RSI drops below 30, sell when it goes back above 55",
  "Buy Reliance when price is above the 200-day average and RSI crosses above 50",
];

async function findInstrument(name: string, market?: string | null): Promise<Instrument | null> {
  const up = name.toUpperCase().replace(/\s+/g, " ").trim();
  const alias: Record<string, string> = { NIFTY: "NIFTY 50", BANKNIFTY: "NIFTY BANK", "BANK NIFTY": "NIFTY BANK", BITCOIN: "BTC-USD", BTC: "BTC-USD", ETHEREUM: "ETH-USD", ETH: "ETH-USD" };
  const q = alias[up] || up;
  try {
    const rows = await api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(q.slice(0, 40))}${market ? `&market=${market}` : ""}`);
    const norm = (s: string) => s.replace("/", "-").toUpperCase();
    return rows.find((r) => norm(r.symbol) === norm(q) || String(r.token).toUpperCase() === norm(q))
      ?? rows.find((r) => ["EQ", "INDEX", "CRYPTO"].includes(r.type || "")) ?? null;
  } catch {
    return null;
  }
}

export function IdeaComposer({ onBuilt, busyLabel = "Build my notebook", autoFocus }: {
  onBuilt: (b: Built) => Promise<void> | void; busyLabel?: string; autoFocus?: boolean;
}) {
  const { me, refreshMe, fail } = useApp();
  const [text, setText] = useState("");
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
          : `The AI builder couldn't run just now, so we used the simple converter (it understands SMA, EMA, RSI and price rules).`;
        const p = parseStrategyText(idea);
        const mentioned = Object.keys(p.risk);
        const tf = detectTf(idea), inst = detectInstrument(idea);
        if (p.exit.length) mentioned.push("exit");
        if (tf) mentioned.push("tf");
        if (inst) mentioned.push("instrument");
        out = { entry: p.entry, exit: p.exit, entryJoin: "all", tf, name: null, instrument: inst, risk: p.risk, mentioned, notes: [] };
      } else {
        setBusy(false);
        fail(e);
        return;
      }
    }
    if (usedAI) refreshMe();
    if (!out.entry?.length) {
      setBusy(false);
      setNote((fallback ? fallback + " " : "") + "We couldn't find a buy rule. Say when to buy, e.g. \"Buy when the price is above the 50-day average\"." +
        (out.notes?.length ? " " + out.notes.join(" ") : ""));
      return;
    }
    const instrument = out.instrument ? await findInstrument(out.instrument, out.market) : null;
    const s = blankStrategy(out.name || nameFor({ ...blankStrategy(), entry: out.entry }, instrument?.symbol));
    const strategy: Strategy = {
      ...s, text: idea, entry: out.entry, exit: out.exit || [], entryJoin: out.entryJoin || "all", tf: out.tf || "1d",
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
        placeholder="e.g. Buy NIFTY 50 when the 20-day average crosses above the 50-day, with a 2% stop loss"
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
          {EXAMPLES.map((ex) => (
            <button key={ex} type="button" disabled={busy} onClick={() => { setText(ex); build(ex); }}>
              <span aria-hidden="true">→</span>{ex}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
