import { useEffect, useRef, useState, type ReactNode } from "react";
import { useApp } from "../lib/app";
import { money, TF_NAME } from "../lib/format";
import { DEFAULTS, INDICATORS, mkRef, NO_SESSION, OPS, opSay, refName } from "../lib/rules";
import { HELP } from "../lib/help";
import { Info } from "./ui";
import { Pencil } from "./Icons";
import type { Cond, HigherTf, Op, Ref, RefType, Risk, Session, Strategy, Tf } from "../lib/types";

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

const TF_ORDER: Tf[] = ["5m", "15m", "1h", "1d"];
const HTF_NAME: Record<HigherTf, string> = { "15m": "15-minute candles", "1h": "1-hour candles", "1d": "Daily candles" };

function RefEditor({ value, onChange, allowNum, isPro, tf }: { value: Ref; onChange: (r: Ref) => void; allowNum: boolean; isPro: boolean; tf: Tf }) {
  const def = DEFAULTS[value.t];
  const opt = (i: (typeof INDICATORS)[number]) => (
    <option key={i.t} value={i.t} disabled={i.pro && !isPro && i.t !== value.t}>{i.name}{i.pro && !isPro ? " (Pro)" : ""}</option>
  );
  const higher = (["15m", "1h", "1d"] as HigherTf[]).filter((h) => TF_ORDER.indexOf(h) > TF_ORDER.indexOf(tf));
  return (
    <>
      <label className="field">What
        <select value={value.t} onChange={(e) => {
          const t = e.target.value as RefType;
          onChange(t === "num" ? { t, v: value.t === "num" ? value.v : 50 } : { ...mkRef(t), ago: value.ago, k: value.k, tf: value.tf });
        }}>
          <optgroup label="Price and indicators">{INDICATORS.filter((i) => !i.group).map(opt)}</optgroup>
          <optgroup label="The candle">{INDICATORS.filter((i) => i.group === "candle").map(opt)}</optgroup>
          <optgroup label="The trading day">{INDICATORS.filter((i) => i.group === "day").map(opt)}</optgroup>
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
      {value.t !== "num" && (
        <details className="ref-more" open={!!(value.ago || value.k || value.tf)}>
          <summary>More: earlier candles, multiplier, timeframe</summary>
          <div className="stack" style={{ gap: 10, marginTop: 8 }}>
            <label className="field">Candles ago<input type="number" min={0} max={100} value={value.ago ?? 0} onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              if (n >= 0 && n <= 100) onChange({ ...value, ago: n || null });
            }} /><span className="hint">0 = this candle. 1 = the one before it.</span></label>
            <label className="field">Multiply by<input type="number" min={0.01} max={100} step="0.1" value={value.k ?? 1} onChange={(e) => {
              const k = parseFloat(e.target.value);
              if (k > 0 && k <= 100) onChange({ ...value, k: k === 1 ? null : k });
            }} /><span className="hint">For rules like "the lower wick is more than 1.5 × the body".</span></label>
            {higher.length > 0 && (
              <label className="field">Timeframe<select value={value.tf ?? ""} onChange={(e) => onChange({ ...value, tf: (e.target.value || null) as HigherTf | null })}>
                <option value="">This strategy's candles ({TF_NAME[tf].toLowerCase()})</option>
                {higher.map((h) => <option key={h} value={h}>{HTF_NAME[h]}</option>)}
              </select><span className="hint">A higher timeframe only uses candles that have finished, so the test never peeks ahead.</span></label>
            )}
          </div>
        </details>
      )}
    </>
  );
}

function CondSentence({ c, lead, onChange, onDelete, isPro, tf, scored }: {
  c: Cond; lead: ReactNode; onChange: (c: Cond) => void; onDelete: () => void; isPro: boolean; tf: Tf; scored?: boolean;
}) {
  const refTok = (side: "l" | "r") => (
    <Pop title={side === "l" ? "Left side" : "Right side"} label={refName(c[side])} cls={c[side].t === "num" ? "plain" : ""}>
      {() => <RefEditor value={c[side]} allowNum={side === "r"} isPro={isPro} tf={tf} onChange={(r) => onChange({ ...c, [side]: r })} />}
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
      {refTok("r")}
      {scored && <>{" "}<NumTok title="Weight in the score" value={c.w ?? 1} min={0.1} max={10} step={0.5} render={(v) => `(worth ${v})`}
        onChange={(v) => onChange({ ...c, w: v })} hint="How many points this rule adds to the score when it's true." /></>}.
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

function TimeTok({ value, empty, title, onChange, hint }: { value: string; empty: string; title: string; onChange: (v: string) => void; hint: string }) {
  return (
    <Pop title={title} label={value || empty} cls={value ? "risk" : "missing"}>
      {(close) => (
        <>
          <label className="field">{title}<input type="time" defaultValue={value} onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") close(); }} /></label>
          <p className="hint">{hint}</p>
          {value && <button className="btn quiet sm" onClick={() => { onChange(""); close(); }}>Clear</button>}
        </>
      )}
    </Pop>
  );
}

function Choice<T extends string>({ title, value, options, onChange, display }: {
  title: string; value: T; options: [T, string, string?][]; onChange: (v: T) => void; display?: string;
}) {
  const current = options.find((o) => o[0] === value) ?? options[0];
  return (
    <Pop title={title} label={display ?? current[1]} cls="plain">
      {(close) => (
        <div className="stack" style={{ gap: 6 }}>
          {options.map(([v, label, help]) => (
            <button key={v} className={`btn sm ${v === value ? "" : "quiet"}`} style={{ justifyContent: "flex-start", textAlign: "left", whiteSpace: "normal" }}
              onClick={() => { onChange(v); close(); }}>{label}{help ? <span className="muted" style={{ fontWeight: 400 }}>&nbsp;· {help}</span> : null}</button>
          ))}
        </div>
      )}
    </Pop>
  );
}

const STOP_UNITS: [NonNullable<Risk["stopType"]>, string, string][] = [
  ["pct", "% stop", "percent of the entry price"], ["points", "point stop", "price points"],
  ["atr", "× ATR stop", "a multiple of the average range (ATR 14)"], ["swing", "candle swing stop", "below the lowest low (above the highest high for a short) of the last N candles"],
];
const TGT_UNITS: [NonNullable<Risk["tgtType"]>, string, string][] = [
  ["pct", "% target", "percent of the entry price"], ["points", "point target", "price points"], ["r", "R target", "a multiple of the stop distance: 2R is twice the risk"],
];

export function RulesCard({ s, currency, onChange }: { s: Strategy; currency: string; onChange: (s: Strategy) => void }) {
  const { isPro } = useApp();
  const set = (patch: Partial<Strategy>) => onChange({ ...s, ...patch });
  const setRisk = (patch: Partial<Risk>) => onChange({ ...s, risk: { ...s.risk, ...patch } });
  const sess: Session = { ...NO_SESSION, ...(s.session ?? {}) };
  const setSess = (patch: Partial<Session>) => onChange({ ...s, session: { ...sess, ...patch } });
  const r = s.risk;
  const side = s.side ?? "long";
  const both = side === "both", short = side === "short";
  const scored = s.entryJoin === "score";
  const intraday = s.tf !== "1d";
  const shortEntry = s.shortEntry ?? [], shortExit = s.shortExit ?? [];
  const stopType = r.stopType ?? "pct", tgtType = r.tgtType ?? "pct";

  const sideTok = (_: string) => (
    <Choice title="Long, short or both" value={side} onChange={(v) => set({ side: v })} display={short ? "Sell short" : "Buy"} options={[
      ["long", "Buy (go long)", "profit when it rises"],
      ["short", "Sell short", "profit when it falls"],
      ["both", "Trade both ways", "long on some signals, short on others"],
    ]} />
  );
  const joinTok = (
    <Choice title="How entry rules combine" value={s.entryJoin} onChange={(v) => set({ entryJoin: v })} options={[
      ["all", "all of these", "every rule at once"], ["any", "any of these", "one is enough"],
      ["score", "enough of these", "a weighted score: each rule adds points"],
    ]} />
  );
  const list = (key: "entry" | "exit" | "shortEntry" | "shortExit", conds: Cond[], lead: (i: number) => ReactNode, entry: boolean) =>
    conds.map((c, i) => (
      <CondSentence key={`${key}${i}`} c={c} lead={lead(i)} isPro={isPro} tf={s.tf} scored={entry && scored}
        onChange={(nc) => set({ [key]: conds.map((x, k) => (k === i ? nc : x)) } as Partial<Strategy>)}
        onDelete={() => set({ [key]: conds.filter((_, k) => k !== i) } as Partial<Strategy>)} />
    ));
  const entryLead = (conds: Cond[], word: ReactNode) => (i: number) =>
    conds.length > 1 || scored ? <span className="muted">{i + 1}.</span> : <b>{word} when</b>;
  const joinLine = (conds: Cond[], word: ReactNode) => (conds.length > 1 || scored) && (
    <p className="sentence"><b>{word}</b> when {joinTok}{scored && <>{" "}(score at least{" "}
      <NumTok title="Score needed" value={s.minScore ?? 0} min={0} max={120} step={0.5} missing="all of them"
        onChange={(v) => set({ minScore: v })} hint="Add up the points of the rules that are true; enter when the total reaches this. 0 means every rule must be true." />)</>}:</p>
  );
  const unitTok = (kind: "stop" | "tgt") => kind === "stop"
    ? <Choice title="Stop measured in" value={stopType} onChange={(v) => setRisk({ stopType: v })} options={STOP_UNITS.map(([v, l, h]) => [v, l, h])} />
    : <Choice title="Target measured in" value={tgtType} onChange={(v) => setRisk({ tgtType: v })} options={TGT_UNITS.map(([v, l, h]) => [v, l, h])} />;
  const addRule = (key: "entry" | "exit" | "shortEntry" | "shortExit", c: Cond) => set({ [key]: [...((s[key] as Cond[] | undefined) ?? []), c] } as Partial<Strategy>);

  return (
    <section className="card stack" aria-labelledby="rules-h" style={{ gap: 12 }}>
      <div className="spread" style={{ flexWrap: "wrap" }}>
        <h2 id="rules-h" className="h2 row" style={{ gap: 0 }}>The rules<Info>{HELP.rules}</Info></h2>
      </div>
      <p className="edit-hint"><Pencil size={16} />Tap any highlighted word below to change it: the indicator, its length, the condition or a number.</p>

      {!both && <>
        {joinLine(s.entry, sideTok("long"))}
        {s.entry.length === 0 && <p className="sentence muted">{sideTok("long")} when… no entry rule yet. Add one below, or describe your idea again.</p>}
        {list("entry", s.entry, (i) => s.entry.length > 1 || scored ? <span className="muted">{i + 1}.</span> : <b>{sideTok("long")} when</b>, true)}
        {list("exit", s.exit, (i) => i === 0 ? <b>{short ? "Buy back" : "Sell"} when</b> : <b>or when</b>, false)}
      </>}
      {both && <>
        <h3 className="h3 side-h">Going long</h3>
        {joinLine(s.entry, sideTok("long"))}
        {s.entry.length === 0 && <p className="sentence muted">No long entry rule yet.</p>}
        {list("entry", s.entry, entryLead(s.entry, sideTok("long")), true)}
        {list("exit", s.exit, (i) => i === 0 ? <b>Sell when</b> : <b>or when</b>, false)}
        <h3 className="h3 side-h">Going short</h3>
        {joinLine(shortEntry, "Sell short")}
        {shortEntry.length === 0 && <p className="sentence muted">No short entry rule yet.</p>}
        {list("shortEntry", shortEntry, entryLead(shortEntry, "Sell short"), true)}
        {list("shortExit", shortExit, (i) => i === 0 ? <b>Buy back when</b> : <b>or when</b>, false)}
      </>}
      {s.entry.length > 0 && (
        <p className="hint row" style={{ gap: 0, marginTop: -6 }}>"Crosses above" or "is above"? They trade very differently.<Info>{HELP.crosses}</Info></p>
      )}

      <p className="sentence">
        {s.exit.length || shortExit.length ? "Also close" : <b>Close</b>} at a{" "}
        <NumTok title="Stop loss" value={r.sl} missing="no stop loss" max={stopType === "pct" ? 99 : 100000} step={stopType === "swing" ? 1 : 0.1}
          render={(v) => `${v}`} onChange={(v) => setRisk({ sl: v })} hint="0 turns it off. Tap the word after the number to change the unit." />
        {r.sl > 0 && <>{" "}{unitTok("stop")}</>}{" "}or a{" "}
        <NumTok title="Target" value={r.tgt} missing="no target" max={100000} render={(v) => `${v}`}
          onChange={(v) => setRisk({ tgt: v })} hint={tgtType === "r" ? "A multiple of the stop distance: 2 means twice what you risk." : "0 turns it off."} />
        {r.tgt > 0 && <>{" "}{unitTok("tgt")}</>}.
        <Info label="What are a stop loss and a target?"><b>Stop loss:</b> {HELP.stop}<br /><br /><b>Target:</b> {HELP.target}<br /><br /><b>Units:</b> {HELP.stopUnits}</Info>
      </p>
      <p className="sentence">
        Trail the stop by{" "}
        <NumTok title="Trailing stop (%)" value={r.trail ?? 0} suffix="%" missing="nothing (off)" max={50} onChange={(v) => setRisk({ trail: v })}
          hint="Moves the stop with the best price since the trade opened, staying this far behind it. It never moves back. 0 turns it off." />{" "}and close any trade after{" "}
        <NumTok title="Close after (candles)" value={r.maxBars ?? 0} step={1} max={5000} missing="no time limit" render={(v) => `${v} candle${v === 1 ? "" : "s"}`}
          onChange={(v) => setRisk({ maxBars: Math.round(v) })} hint="Closes a trade that's still open after this many candles, at the close. 0 turns it off." />.
        <Info label="Trailing stops and time limits"><b>Trailing stop:</b> {HELP.trail}<br /><br /><b>Time limit:</b> {HELP.maxBars}</Info>
      </p>
      {intraday && (
        <p className="sentence">
          <b>During the day:</b> enter only between{" "}
          <TimeTok title="First entry time" value={sess.start} empty="the open" onChange={(v) => setSess({ start: v })}
            hint="No new trades on candles that close before this time (the exchange's local time)." />{" "}and{" "}
          <TimeTok title="Last entry time" value={sess.end} empty="the close" onChange={(v) => setSess({ end: v })}
            hint="No new trades on candles that close after this time." />, square off at{" "}
          <TimeTok title="Square-off time" value={sess.squareoff} empty="never (hold overnight)" onChange={(v) => setSess({ squareoff: v })}
            hint="Any open trade closes on the candle that ends at this time. Indian intraday (MIS) costs apply when set." />, at most{" "}
          <NumTok title="Trades per day" value={sess.maxTradesDay} step={1} max={100} missing="any number of" render={(v) => `${v}`}
            onChange={(v) => setSess({ maxTradesDay: Math.round(v) })} hint="0 means no limit." />{" "}trade{sess.maxTradesDay === 1 ? "" : "s"} a day, wait{" "}
          <NumTok title="Cooldown (candles)" value={sess.cooldown} step={1} max={500} missing="no candles" render={(v) => `${v} candle${v === 1 ? "" : "s"}`}
            onChange={(v) => setSess({ cooldown: Math.round(v) })} hint="After a trade closes, skip this many candles before entering again." />{" "}after each trade, and stop for the day after losing{" "}
          <NumTok title="Daily loss cap (% of capital)" value={sess.dailyLossPct} max={100} missing="any amount" suffix="%"
            onChange={(v) => setSess({ dailyLossPct: v })} hint="Once the day's loss (including the open trade) reaches this % of capital, the trade is closed and nothing more happens until tomorrow." />.
          <Info label="Intraday session rules">{HELP.session}</Info>
        </p>
      )}
      <p className="sentence">
        {(r.sizing ?? "risk") === "risk" ? <>Risk{" "}<NumTok title="Risk per trade (%)" value={r.riskPct} suffix="%" min={0.1} max={100} onChange={(v) => setRisk({ riskPct: v })}
          hint="How much of your capital you'd lose if the stop loss hits. Most traders keep this at 1% or less." />{" "}of</>
          : <>Put{" "}<NumTok title="Capital per trade" value={r.perTrade ?? 0} min={0} step={1000} missing="all" render={(v) => money(v, currency)}
            onChange={(v) => setRisk({ perTrade: v })} hint="The margin each trade uses. 0 uses the max capital per trade % below." />
            {(r.leverage ?? 1) > 1 && <>{" "}× <NumTok title="Leverage" value={r.leverage ?? 1} min={1} max={20} step={0.5} render={(v) => `${v} leverage`} onChange={(v) => setRisk({ leverage: v })} hint="The position is this many times the capital per trade (intraday margin)." /></>}{" "}of</>}{" "}
        <NumTok title="Capital" value={r.capital} min={1} step={1000} render={(v) => money(v, currency)} onChange={(v) => setRisk({ capital: v })}
          hint="Pretend money the test starts with." />{" "}on each trade, checked on{" "}
        <Pop title="Candle size" label={`${TF_NAME[s.tf].toLowerCase()} candles`} cls="plain">
          {(close) => (
            <div className="stack" style={{ gap: 6 }}>
              {(["1d", "1h", "15m", "5m"] as Tf[]).map((tf) => (
                <button key={tf} className={`btn sm ${tf === s.tf ? "" : "quiet"}`} onClick={() => { set({ tf }); close(); }}>{TF_NAME[tf]} candles</button>
              ))}
              <p className="hint">Daily candles suit swing trades that last days to weeks. Shorter candles mean more trades and more noise, and unlock the intraday session rules.</p>
            </div>
          )}
        </Pop>.
        <Info label="What do risk, capital and candles mean?"><b>Risk:</b> {HELP.risk}<br /><br /><b>Capital:</b> {HELP.capital}<br /><br /><b>Candles:</b> {HELP.candles}</Info>
      </p>
      <div className="row wrap" style={{ gap: 8, marginTop: 4 }}>
        {!both ? <>
          <button className="btn quiet sm" onClick={() => addRule("entry", { l: { t: "price" }, op: short ? "lt" : "gt", r: { t: "sma", p: 50 } })}>Add {short ? "a short" : "a buy"} rule</button>
          <button className="btn quiet sm" onClick={() => addRule("exit", { l: { t: "rsi", p: 14 }, op: short ? "lt" : "gt", r: { t: "num", v: short ? 30 : 70 } })}>Add {short ? "a buy-back" : "a sell"} rule</button>
        </> : <>
          <button className="btn quiet sm" onClick={() => addRule("entry", { l: { t: "price" }, op: "gt", r: { t: "sma", p: 50 } })}>Add a long rule</button>
          <button className="btn quiet sm" onClick={() => addRule("exit", { l: { t: "rsi", p: 14 }, op: "gt", r: { t: "num", v: 70 } })}>Add a sell rule</button>
          <button className="btn quiet sm" onClick={() => addRule("shortEntry", { l: { t: "price" }, op: "lt", r: { t: "sma", p: 50 } })}>Add a short rule</button>
          <button className="btn quiet sm" onClick={() => addRule("shortExit", { l: { t: "rsi", p: 14 }, op: "lt", r: { t: "num", v: 30 } })}>Add a buy-back rule</button>
        </>}
      </div>
      <details>
        <summary className="small" style={{ cursor: "pointer", fontWeight: 600, color: "var(--blue)" }}>Costs and position size</summary>
        <div className="grid4" style={{ marginTop: 12 }}>
          <label className="field">Position size<select value={r.sizing ?? "risk"} onChange={(e) => setRisk({ sizing: e.target.value as Risk["sizing"] })}>
            <option value="risk">By risk (% of capital at the stop)</option>
            <option value="capital">Fixed capital per trade</option>
          </select></label>
          {(r.sizing ?? "risk") === "capital" && <>
            <label className="field">Capital per trade<input type="number" min={0} step={1000} value={r.perTrade ?? 0}
              onChange={(e) => { const v = parseFloat(e.target.value); if (v >= 0) setRisk({ perTrade: v }); }} /></label>
            <label className="field">Leverage (×)<input type="number" min={1} max={20} step={0.5} value={r.leverage ?? 1}
              onChange={(e) => { const v = parseFloat(e.target.value); if (v >= 1 && v <= 20) setRisk({ leverage: v }); }} /></label>
          </>}
          <label className="field">Max capital per trade (%)<input type="number" min={1} max={100} value={r.maxAlloc}
            onChange={(e) => { const v = parseFloat(e.target.value); if (v >= 1 && v <= 100) setRisk({ maxAlloc: v }); }} /></label>
          <label className="field">Brokerage per order ({currency || "flat"})<input type="number" min={0} step={1} value={r.brokerage}
            onChange={(e) => { const v = parseFloat(e.target.value); if (v >= 0) setRisk({ brokerage: v }); }} /></label>
          <label className="field">Slippage (%)<input type="number" min={0} max={5} step={0.01} value={r.slippage}
            onChange={(e) => { const v = parseFloat(e.target.value); if (v >= 0 && v <= 5) setRisk({ slippage: v }); }} /></label>
          {currency === "INR" && (
            <label className="field">Indian stock costs<select value={s.product ?? "auto"} onChange={(e) => set({ product: e.target.value as Strategy["product"] })}>
              <option value="auto">Automatic (intraday when squaring off)</option>
              <option value="delivery">Delivery (CNC)</option>
              <option value="intraday">Intraday (MIS)</option>
            </select></label>
          )}
        </div>
        <p className="hint" style={{ marginTop: 8 }}>By risk: quantity = risk amount ÷ distance to the stop, capped by max capital per trade. Fixed capital: quantity = capital per trade × leverage ÷ price. Taxes and exchange fees are added for you per market.</p>
      </details>
    </section>
  );
}
