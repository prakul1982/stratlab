import { useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { blankStrategy, riskForCurrency } from "../lib/rules";
import type { Cond, Instrument, Risk, Strategy, Tf } from "../lib/types";
import { findInstrument, type Built } from "./IdeaComposer";
import { Upload } from "./Icons";
import { Info } from "./ui";

interface ImportOut {
  source: string; source_name: string; used_ai: boolean;
  strategy?: Strategy; instrument_id?: string | null;                       // a StratLab export
  entry?: Cond[]; exit?: Cond[]; entryJoin?: "all" | "any"; side?: "long" | "short"; tf?: Tf | null; name?: string | null;
  instrument?: string | null; market?: string | null; risk?: Partial<Risk>; mentioned?: string[]; notes: string[];
}

const ACCEPT = ".json,.pine,.txt,.py,.afl,.mq4,.mq5,.md";
const HELP_TEXT = "Bring in a strategy you already have. A StratLab export loads exactly as it was. TradingView Pine Script, Python (Backtrader, backtesting.py and the like), MetaTrader, AmiBroker or a written description are translated into StratLab rules by the AI; Pine Script also works without it. Anything that can't be translated is listed on the notebook so you can decide what to do.";

/** Import a strategy from a file or pasted text, then hand it over like an idea the AI built. */
export function ImportStrategy({ onBuilt, market }: { onBuilt: (b: Built) => Promise<void> | void; market?: string }) {
  const { refreshMe, fail } = useApp();
  const [text, setText] = useState("");
  const [file, setFile] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const readFile = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > 200_000) { setNote("That file is too big to be a strategy. Pick the strategy file itself (under 200 KB)."); return; }
    setText((await f.text()).slice(0, 20000));
    setFile(f.name);
    setNote(null);
  };

  const run = async () => {
    if (text.trim().length < 5) { setNote("Choose a file or paste your strategy first."); return; }
    setBusy(true);
    setNote(null);
    try {
      const out = await api<ImportOut>("/import/strategy", { method: "POST", body: { text, filename: file } });
      if (out.used_ai) refreshMe();
      let strategy: Strategy, instrument: Instrument | null = null;
      if (out.strategy) {
        instrument = out.instrument_id ? await api<Instrument>(`/instruments/${encodeURIComponent(out.instrument_id)}`).catch(() => null) : null;
        strategy = out.strategy;
      } else {
        instrument = out.instrument ? await findInstrument(out.instrument, out.market || (market && market !== "CSV" ? market : null)) : null;
        const s = blankStrategy(out.name || `Imported ${out.source_name} strategy`);
        strategy = { ...s, text: `Imported from ${out.source_name}${file ? ` (${file})` : ""}`, entry: out.entry || [], exit: out.exit || [],
          entryJoin: out.entryJoin || "all", tf: out.tf || "1d", side: out.side === "short" ? "short" : "long",
          risk: riskForCurrency({ ...s.risk, ...(out.risk || {}) }, instrument?.currency) };
      }
      const fallback = !out.strategy && !out.used_ai ? "The AI translator was busy, so StratLab's built-in Pine Script reader was used. It covers moving averages, RSI, crossovers and percent stops." : "";
      await onBuilt({
        strategy, instrument,
        question: `Does the imported "${strategy.name}" strategy hold up?`,
        gaps: { mentioned: out.mentioned || ["exit", "sl", "tgt", "tf", "instrument"], notes: out.notes || [], instName: out.instrument ?? null, usedAI: out.used_ai, fallback },
      });
      setText(""); setFile("");
    } catch (e) {
      const err = e as ApiError;
      if (["nothing_imported", "bad_import", "ai_busy", "ai_failed", "ai_limit", "ai_daily_limit"].includes(err.code || "")) setNote(err.message);
      else fail(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="import-drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); readFile(e.dataTransfer.files[0]); }}>
        <Upload size={22} />
        <span className="small">{file ? <b>{file}</b> : <>Drop a strategy file here, or</>}</span>
        <button type="button" className="btn quiet sm" onClick={() => input.current?.click()}>{file ? "Choose another file" : "Choose a file"}</button>
        <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => readFile(e.target.files?.[0])} />
      </div>
      <label className="sr-only" htmlFor="import-text">Or paste the strategy</label>
      <textarea id="import-text" className="input mono" value={text} maxLength={20000} spellCheck={false}
        style={{ minHeight: 130, fontSize: 13, lineHeight: 1.5 }}
        placeholder={'…or paste it here: a StratLab export, TradingView Pine Script, Python, MetaTrader, AmiBroker or plain words.\n\nstrategy("Golden cross")\nif ta.crossover(ta.sma(close, 50), ta.sma(close, 200))\n    strategy.entry("Long", strategy.long)'}
        onChange={(e) => { setText(e.target.value); if (!e.target.value) setFile(""); }} />
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <button className="btn" disabled={busy} onClick={run}>{busy ? "Reading your strategy…" : "Import and build my notebook"}</button>
        <span className="small muted row" style={{ gap: 0 }}>Uses one AI build, except StratLab exports<Info>{HELP_TEXT}</Info></span>
      </div>
      {note && <p className="small" style={{ color: "var(--orange-ink)" }} role="alert">{note}</p>}
    </div>
  );
}
