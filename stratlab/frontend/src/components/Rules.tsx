import { useEffect, useRef, useState, type ReactNode } from "react";
import { useApp } from "../lib/app";
import { money, TF_NAME } from "../lib/format";
import { DEFAULTS, INDICATORS, mkRef, OPS, opSay, refName } from "../lib/rules";
import { HELP } from "../lib/help";
import { Info } from "./ui";
import { Pencil } from "./Icons";
import type { Cond, Op, Ref, RefType, Risk, Strategy, Tf } from "../lib/types";

/* A highlighted word in a rule sentence that opens a small editor when clicked. */
function Pop({ label, cls = "", children, title }: { label: ReactNode; cls?: string; children: (close: () => void) => ReactNode; title: string }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const out = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", out);
    document.addEventListener("keydown", esc);
    wrap.current?.querySelector<HTMLElement>(".popover select, .popover input, .popover button")?.focus();
    return () => { document.removeEventListener("mousedown", out); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <span ref={wrap} style={{ position: "relative", display: "inline-block" }}>
      <button type="button" className={`token ${cls}`} aria-label={`${title}: ${typeof label === "string" ? label : ""}`} aria-expanded={open}
        onClick={() => setOpen((o) => !o)}>{label}</button>
      {open && <div className="popover stack" style={{ top: "calc(100% + 6px)", left: 0, gap: 10, fontSize: 15, lineHeight: 1.4 }}>{children(() => setOpen(false))}</div>}
    </span>
  );
}

function RefEditor({ value, onChange, allowNum, isPro }: { value: Ref; onChange: (r: Ref) => void; allowNum: boolean; isPro: boolean }) {
  const def = DEFAULTS[value.t];
  return (
    <>
      <label className="field">What
        <select value={value.t} onChange={(e) => {
          const t = e.target.value as RefType;
          onChange(t === "num" ? { t, v: value.t === "num" ? value.v : 50 } : mkRef(t));
        }}>
          {INDICATORS.map((i) => <option key={i.t} value={i.t} disabled={i.pro && !isPro && i.t !== value.t}>{i.name}{i.pro && !isPro ? " (Pro)" : ""}</option>)}
          {allowNum && <option value="num">A number</option>}
        </select>
      </label>
      {value.t === "num" && (
        <label className="field">Value<input type="number" step="any" value={value.v ?? ""} onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (Number.isFinite(v)) onChange({ ...value, v });
        }} /></label>
      )}
      {def && (
        <label className="field">{value.t.startsWith("macd") ? "Fast length" : value.t === "supertrend" ? "ATR length" : "Length (candles)"}
          <input type="number" min={1} max={500} value={value.p ?? def[0]} onChange={(e) => {
            const p = parseInt(e.target.value, 10);
            if (p >= 1 && p <= 500) onChange({ ...value, p });
          }} /></label>
      )}
      {def && def[1] != null && (
        <label className="field">{value.t.startsWith("macd") ? "Slow length" : value.t.startsWith("bb") ? "Std devs" : value.t === "stoch_k" ? "Smoothing" : "Multiplier"}
          <input type="number" min={0.1} step="0.1" value={value.m ?? def[1]} onChange={(e) => {
            const m = parseFloat(e.target.value);
            if (m > 0 && m <= 500) onChange({ ...value, m });
          }} /></label>
      )}
    </>
  );
}

function CondSentence({ c, lead, onChange, onDelete, isPro }: {
  c: Cond; lead: ReactNode; onChange: (c: Cond) => void; onDelete: () => void; isPro: boolean;
}) {
  const refTok = (side: "l" | "r") => (
    <Pop title={side === "l" ? "Left side" : "Right side"} label={refName(c[side])} cls={c[side].t === "num" ? "plain" : ""}>
      {() => <RefEditor value={c[side]} allowNum={side === "r"} isPro={isPro} onChange={(r) => onChange({ ...c, [side]: r })} />}
    </Pop>
  );
  return (
    <p className="sentence">
      {lead} {refTok("l")}{" "}
      <Pop title="Condition" label={opSay(c.op)} cls="plain">
        {(close) => (
          <>
            <div className="stack" style={{ gap: 6 }}>
              {OPS.map((o) => (
                <button key={o.op} className={`btn sm ${o.op === c.op ? "" : "quiet"}`} onClick={() => { onChange({ ...c, op: o.op as Op }); close(); }}>{o.say}</button>
              ))}
            </div>
            <p className="hint">"Crosses" is true only on the candle where it happens. "Is above" is true on every candle while it stays above.</p>
            <button className="btn danger sm" onClick={() => { onDelete(); close(); }}>Remove this rule</button>
          </>
        )}
      </Pop>{" "}
      {refTok("r")}.
    </p>
  );
}

function NumTok({ value, suffix = "", prefix = "", title, min = 0, max, step = 0.1, missing, render, onChange, hint }: {
  value: number; suffix?: string; prefix?: string; title: string; min?: number; max?: number; step?: number;
  missing?: string; render?: (v: number) => string; onChange: (v: number) => void; hint?: string;
}) {
  const label = missing && value === 0 ? missing : render ? render(value) : `${prefix}${value}${suffix}`;
  return (
    <Pop title={title} label={label} cls={missing && value === 0 ? "missing" : "risk"}>
      {(close) => (
        <>
          <label className="field">{title}
            <input type="number" defaultValue={value} min={min} max={max} step={step}
              onKeyDown={(e) => { if (e.key === "Enter") close(); }}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (Number.isFinite(v) && v >= min && (max == null || v <= max)) onChange(v);
              }} /></label>
          {hint && <p className="hint">{hint}</p>}
        </>
      )}
    </Pop>
  );
}

export function RulesCard({ s, currency, onChange }: { s: Strategy; currency: string; onChange: (s: Strategy) => void }) {
  const { isPro } = useApp();
  const set = (patch: Partial<Strategy>) => onChange({ ...s, ...patch });
  const setRisk = (patch: Partial<Risk>) => onChange({ ...s, risk: { ...s.risk, ...patch } });
  const r = s.risk;
  const short = s.side === "short";
  const open = short ? "Sell short" : "Buy", close = short ? "Buy back" : "Sell";
  const sideTok = (
    <Pop title="Long or short" label={open} cls="plain">
      {(done) => (
        <div className="stack" style={{ gap: 6 }}>
          <button className={`btn sm ${!short ? "" : "quiet"}`} onClick={() => { set({ side: "long" }); done(); }}>Buy (go long): profit when it rises</button>
          <button className={`btn sm ${short ? "" : "quiet"}`} onClick={() => { set({ side: "short" }); done(); }}>Sell short: profit when it falls</button>
          <p className="hint">{HELP.short}</p>
        </div>
      )}
    </Pop>
  );
  const lead = (i: number, side: "entry" | "exit") =>
    side === "exit" ? <b>{close} when</b> : i === 0 ? <b>{sideTok} when</b> : <b>{s.entryJoin === "all" ? "and when" : "or when"}</b>;

  return (
    <section className="card stack" aria-labelledby="rules-h" style={{ gap: 12 }}>
      <div className="spread" style={{ flexWrap: "wrap" }}>
        <h2 id="rules-h" className="h2 row" style={{ gap: 0 }}>The rules<Info>{HELP.rules}</Info></h2>
      </div>
      <p className="edit-hint"><Pencil size={16} />Tap any highlighted word below to change it: the indicator, its length, the condition or a number.</p>

      {s.entry.length > 1 && (
        <p className="sentence"><b>{sideTok}</b> when{" "}
          <Pop title="How entry rules combine" label={s.entryJoin === "all" ? "all of these" : "any of these"} cls="plain">
            {(close) => (
              <div className="stack" style={{ gap: 6 }}>
                <button className={`btn sm ${s.entryJoin === "all" ? "" : "quiet"}`} onClick={() => { set({ entryJoin: "all" }); close(); }}>All of these (every rule at once)</button>
                <button className={`btn sm ${s.entryJoin === "any" ? "" : "quiet"}`} onClick={() => { set({ entryJoin: "any" }); close(); }}>Any of these (one is enough)</button>
              </div>
            )}
          </Pop>{" "}happen:</p>
      )}
      {s.entry.length === 0 && <p className="sentence muted">No entry rule yet. Add one below, or describe your idea again.</p>}
      {s.entry.map((c, i) => (
        <CondSentence key={`e${i}`} c={c} lead={s.entry.length > 1 ? <span className="muted">{i + 1}.</span> : lead(i, "entry")} isPro={isPro}
          onChange={(nc) => set({ entry: s.entry.map((x, k) => (k === i ? nc : x)) })}
          onDelete={() => set({ entry: s.entry.filter((_, k) => k !== i) })} />
      ))}
      {s.entry.length > 0 && (
        <p className="hint row" style={{ gap: 0, marginTop: -6 }}>"Crosses above" or "is above"? They trade very differently.<Info>{HELP.crosses}</Info></p>
      )}
      {s.exit.map((c, i) => (
        <CondSentence key={`x${i}`} c={c} lead={i === 0 ? <b>{close} when</b> : <b>or when</b>} isPro={isPro}
          onChange={(nc) => set({ exit: s.exit.map((x, k) => (k === i ? nc : x)) })}
          onDelete={() => set({ exit: s.exit.filter((_, k) => k !== i) })} />
      ))}
      <p className="sentence">
        {s.exit.length ? `Also ${close.toLowerCase()}` : <b>{close}</b>} at a{" "}
        <NumTok title="Stop loss (%)" value={r.sl} suffix="% stop" missing="no stop loss" max={99} onChange={(v) => setRisk({ sl: v })}
          hint={short ? "Buys back if the price rises this far above where you sold. 0 turns it off." : "Sells if the price falls this far below where you bought. 0 turns it off."} />{" "}or a{" "}
        <NumTok title="Target (%)" value={r.tgt} suffix="% target" missing="no target" max={1000} onChange={(v) => setRisk({ tgt: v })}
          hint={short ? "Buys back if the price falls this far below where you sold. 0 turns it off." : "Sells if the price rises this far above where you bought. 0 turns it off."} />.
        <Info label="What are a stop loss and a target?"><b>Stop loss:</b> {HELP.stop}<br /><br /><b>Target:</b> {HELP.target}</Info>
      </p>
      <p className="sentence">
        Trail the stop by{" "}
        <NumTok title="Trailing stop (%)" value={r.trail ?? 0} suffix="%" missing="nothing (off)" max={50} onChange={(v) => setRisk({ trail: v })}
          hint={short ? "Moves the stop down as the price falls, staying this far above the lowest price since you sold. It never moves back up. 0 turns it off." : "Moves the stop up as the price rises, staying this far below the highest price since you bought. It never moves back down. 0 turns it off."} />{" "}and close any trade after{" "}
        <NumTok title="Close after (candles)" value={r.maxBars ?? 0} step={1} max={5000} missing="no time limit" render={(v) => `${v} candle${v === 1 ? "" : "s"}`}
          onChange={(v) => setRisk({ maxBars: Math.round(v) })} hint="Closes a trade that's still open after this many candles, at the close. 0 turns it off." />.
        <Info label="Trailing stops and time limits"><b>Trailing stop:</b> {HELP.trail}<br /><br /><b>Time limit:</b> {HELP.maxBars}</Info>
      </p>
      <p className="sentence">
        Risk{" "}<NumTok title="Risk per trade (%)" value={r.riskPct} suffix="%" min={0.1} max={100} onChange={(v) => setRisk({ riskPct: v })}
          hint="How much of your capital you'd lose if the stop loss hits. Most traders keep this at 1% or less." />{" "}of{" "}
        <NumTok title="Capital" value={r.capital} min={1} step={1000} render={(v) => money(v, currency)} onChange={(v) => setRisk({ capital: v })}
          hint="Pretend money the test starts with." />{" "}on each trade, checked on{" "}
        <Pop title="Candle size" label={`${TF_NAME[s.tf].toLowerCase()} candles`} cls="plain">
          {(close) => (
            <div className="stack" style={{ gap: 6 }}>
              {(["1d", "1h", "15m", "5m"] as Tf[]).map((tf) => (
                <button key={tf} className={`btn sm ${tf === s.tf ? "" : "quiet"}`} onClick={() => { set({ tf }); close(); }}>{TF_NAME[tf]} candles</button>
              ))}
              <p className="hint">Daily candles suit swing trades that last days to weeks. Shorter candles mean more trades and more noise.</p>
            </div>
          )}
        </Pop>.
        <Info label="What do risk, capital and candles mean?"><b>Risk:</b> {HELP.risk}<br /><br /><b>Capital:</b> {HELP.capital}<br /><br /><b>Candles:</b> {HELP.candles}</Info>
      </p>
      <div className="row wrap" style={{ gap: 8, marginTop: 4 }}>
        <button className="btn quiet sm" onClick={() => set({ entry: [...s.entry, { l: { t: "price" }, op: short ? "lt" : "gt", r: { t: "sma", p: 50 } }] })}>Add {short ? "a short" : "a buy"} rule</button>
        <button className="btn quiet sm" onClick={() => set({ exit: [...s.exit, { l: { t: "rsi", p: 14 }, op: short ? "lt" : "gt", r: { t: "num", v: short ? 30 : 70 } }] })}>Add {short ? "a buy-back" : "a sell"} rule</button>
      </div>
      <details>
        <summary className="small" style={{ cursor: "pointer", fontWeight: 600, color: "var(--blue)" }}>Costs and position size</summary>
        <div className="grid4" style={{ marginTop: 12 }}>
          <label className="field">Max capital per trade (%)<input type="number" min={1} max={100} value={r.maxAlloc}
            onChange={(e) => { const v = parseFloat(e.target.value); if (v >= 1 && v <= 100) setRisk({ maxAlloc: v }); }} /></label>
          <label className="field">Brokerage per order ({currency || "flat"})<input type="number" min={0} step={1} value={r.brokerage}
            onChange={(e) => { const v = parseFloat(e.target.value); if (v >= 0) setRisk({ brokerage: v }); }} /></label>
          <label className="field">Slippage (%)<input type="number" min={0} max={5} step={0.01} value={r.slippage}
            onChange={(e) => { const v = parseFloat(e.target.value); if (v >= 0 && v <= 5) setRisk({ slippage: v }); }} /></label>
        </div>
        <p className="hint" style={{ marginTop: 8 }}>Quantity = risk amount ÷ distance to the stop, capped by max capital per trade. Taxes and exchange fees are added for you per market.</p>
      </details>
    </section>
  );
}
