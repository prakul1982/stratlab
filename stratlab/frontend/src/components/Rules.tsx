import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { money, TF_NAME } from "../lib/format";
import { DEFAULTS, defaultExit, INDICATOR_GROUPS, INDICATORS, MAX_RULES, meaningful, mkRef, NO_SESSION, OPS, opSay, rebuiltRisk, refName, selfMultipleNote, NO_STOP_SIZE_NOTE, sizedWithoutStop, stopWords, switchStopUnit } from "../lib/rules";
import { HELP } from "../lib/help";
import { CANDLE_LIMITS, CANDLE_SIZES, CANDLE_UNITS, candleCheck } from "../lib/intervals";
import { Info } from "./ui";
import { Pencil } from "./Icons";
import { Block, More } from "./More";
import { buildIdea, type Built } from "./IdeaComposer";
import { Card, CardHead, ChipBar, Disclosure, Field, FormGrid, Notice, PlanNote, Select, TimeInput, usePopover } from "./kit";
import type { Cond, HigherTf, Op, Ref, RefType, Risk, Session, Strategy, Tf } from "../lib/types";
import "../pages/trade/trade.css";

/* A highlighted word in a rule sentence that opens a small editor when clicked. */
function Pop({ label, cls = "", children, title, plain }: { label: ReactNode; cls?: string; children: (close: () => void) => ReactNode; title: string;
  /** a link-like button (an "+ Add …" line) instead of a highlighted word, named by its own text */
  plain?: boolean }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  // focus into the editor; Esc or a click outside closes it, and focus goes back to the word
  usePopover(open, setOpen, btn, panel, { outside: wrap });
  return (
    <span ref={wrap} className="k-pop-wrap">
      <button ref={btn} type="button" className={plain ? cls : `token ${cls}`} aria-label={plain ? undefined : `${title}: ${typeof label === "string" ? label : ""}`} aria-expanded={open}
        aria-haspopup={plain ? "dialog" : undefined}
        onClick={() => setOpen((o) => !o)}>{label}</button>
      {open && <div ref={panel} className="popover k-popover">{children(() => setOpen(false))}</div>}
    </span>
  );
}

const TF_ORDER: Tf[] = ["5m", "15m", "1h", "1d"];
const HTF_NAME: Record<HigherTf, string> = { "15m": "15-minute candles", "1h": "1-hour candles", "1d": "Daily candles" };
const HTF_ONE: Record<HigherTf, string> = { "15m": "15-minute", "1h": "1-hour", "1d": "daily" };

/** A number box for the small editors: the kit's Field with its hint behind an (i). What is typed stays in the box while
 * it is typed (an empty box, "0.", a number out of range on its way to one in range); each number is handed to `onValid`,
 * which keeps it only if it's in range, and leaving the box puts back the value the rules hold. */
function NumField({ label, value, min, max, step, hint, onValid }: { label: string; value: number | string; min?: number; max?: number; step?: number | string; hint?: ReactNode; onValid: (v: number) => void }) {
  const [txt, setTxt] = useState(String(value));
  // the rules changed elsewhere: show their value, unless the box already says that number ("1.50" for 1.5)
  useEffect(() => { setTxt((t) => (t !== "" && parseFloat(t) === Number(value) ? t : String(value))); }, [value]);
  return (
    <Field label={label} info={hint} type="number" min={min} max={max} step={step} value={txt}
      onChange={(e) => { setTxt(e.target.value); const v = parseFloat(e.target.value); if (Number.isFinite(v)) onValid(v); }}
      onBlur={() => setTxt(String(value))} />
  );
}

function RefEditor({ value, onChange, allowNum, allIndicators, tf }: { value: Ref; onChange: (r: Ref) => void; allowNum: boolean; allIndicators: boolean; tf: Tf }) {
  const def = DEFAULTS[value.t];
  const about = INDICATORS.find((i) => i.t === value.t)?.friendly;
  // a Basic indicator stays in the list with its plan, and picking it says why it can't be used here and what it costs,
  // leaving the rule as it was (DP1-007: about 30 options were disabled, and a click on one did nothing)
  const [askedFor, setAskedFor] = useState<string | null>(null);
  const opt =(i: (typeof INDICATORS)[number]) => (
    <option key={i.t} value={i.t}>{i.name}{i.pro && !allIndicators ? " (Basic)" : ""}</option>
  );
  const higher = (["15m", "1h", "1d"] as HigherTf[]).filter((h) => TF_ORDER.indexOf(h) > TF_ORDER.indexOf(tf));
  return (
    <>
      <Field label="What">{(id) => (
        <select id={id} className="k-input" value={value.t} onChange={(e) => {
          const t = e.target.value as RefType;
          const ind = INDICATORS.find((i) => i.t === t);
          if (ind?.pro && !allIndicators && t !== value.t) { setAskedFor(ind.name); return; }
          setAskedFor(null);
          onChange(t === "num" ? { t, v: value.t === "num" ? value.v : 50 } : { ...mkRef(t), ago: value.ago, k: value.k, tf: value.tf });
        }}>
          {INDICATOR_GROUPS.map(([g, label]) => <optgroup key={g} label={label}>{INDICATORS.filter((i) => i.group === g).map(opt)}</optgroup>)}
          {allowNum && <option value="num">A number</option>}
        </select>
      )}</Field>
      {askedFor && <div data-testid="indicator-locked"><PlanNote plan="basic">{askedFor} is on the Basic plan, with every indicator beyond price, SMA, EMA and RSI. Your rule is unchanged.</PlanNote></div>}
      {about?.endsWith(".") && <p className="k-note">{about}</p>}
      {value.t === "num" && <NumField label="Value" step="any" value={value.v ?? ""} onValid={(v) => onChange({ ...value, v })} />}
      {def && (
        <NumField label={value.t.startsWith("macd") ? "Fast length" : value.t === "supertrend" ? "ATR length" : value.t === "stage" ? "Average length" : "Length (candles)"}
          min={1} max={500} value={value.p ?? def[0]} onValid={(p) => { if (Number.isInteger(p) && p >= 1 && p <= 500) onChange({ ...value, p }); }} />
      )}
      {def && def[1] != null && (
        <NumField label={value.t.startsWith("macd") ? "Slow length" : value.t.startsWith("bb") ? "Std devs" : value.t === "stoch_k" ? "Smoothing" : value.t === "stage" ? "Slope over (candles)" : "Multiplier"}
          min={0.1} step="0.1" value={value.m ?? def[1]} onValid={(m) => { if (m > 0 && m <= 500) onChange({ ...value, m }); }} />
      )}
      {value.t !== "num" && (
        <Disclosure open={!!(value.ago || value.k || value.tf)} summary="More: earlier candles, multiplier, timeframe">
          <NumField label="Candles ago" min={0} max={100} value={value.ago ?? 0} hint={value.tf ? `0 = the last ${HTF_ONE[value.tf]} candle that has closed. 1 = the one before it.` : "0 = this candle. 1 = the one before it."}
            onValid={(n) => { if (Number.isInteger(n) && n >= 0 && n <= 100) onChange({ ...value, ago: n || null }); }} />
          <NumField label="Multiply by" min={0.01} max={100} step="0.1" value={value.k ?? 1} hint={'For rules like "the lower wick is more than 1.5 × the body".'}
            onValid={(k) => { if (k > 0 && k <= 100) onChange({ ...value, k: k === 1 ? null : k }); }} />
          {higher.length > 0 && (
            <Field label="Timeframe" info="A higher timeframe only uses candles that have finished, so the test never peeks ahead.">{(id) => (
              <Select id={id} value={value.tf ?? ""} onChange={(v) => onChange({ ...value, tf: (v || null) as HigherTf | null })}
                options={[{ value: "", label: `This strategy's candles (${TF_NAME[tf].toLowerCase()})` }, ...higher.map((h) => ({ value: h, label: HTF_NAME[h] }))]} />
            )}</Field>
          )}
        </Disclosure>
      )}
    </>
  );
}

function CondSentence({ c, lead, onChange, onDelete, allIndicators, tf, scored }: {
  c: Cond; lead: ReactNode; onChange: (c: Cond) => void; onDelete: () => void; allIndicators: boolean; tf: Tf; scored?: boolean;
}) {
  const refTok = (side: "l" | "r") => (
    <Pop title={side === "l" ? "Left side" : "Right side"} label={refName(c[side])} cls={c[side].t === "num" ? "plain" : ""}>
      {() => <RefEditor value={c[side]} allowNum={side === "r"} allIndicators={allIndicators} tf={tf} onChange={(r) => onChange({ ...c, [side]: r })} />}
    </Pop>
  );
  return (
    <div className="cond-row">
    <p className="sentence">
      {lead} {refTok("l")}{" "}
      <Pop title="Condition" label={opSay(c.op)} cls="plain">
        {(close) => (
          <>
            <div className="k-stack">
              {OPS.map((o) => (
                <button type="button" key={o.op} className={`btn sm ${o.op === c.op ? "" : "quiet"}`} onClick={() => { onChange({ ...c, op: o.op as Op }); close(); }}>{o.say}</button>
              ))}
            </div>
            <p className="k-note">"Crosses" is true only on the candle where it happens. "Is above" is true on every candle while it stays above.</p>
          </>
        )}
      </Pop>{" "}
      {refTok("r")}
      {scored && <>{" "}<NumTok title="Weight in the score" value={c.w ?? 1} min={0.1} max={10} step={0.5} render={(v) => `(worth ${v})`}
        onChange={(v) => onChange({ ...c, w: v })} hint="How many points this rule adds to the score when it's true." /></>}.
    </p>
    <button type="button" className="cond-x" onClick={onDelete} aria-label="Remove this rule" title="Remove this rule">×</button>
    </div>
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
        <Field label={title} info={hint} type="number" defaultValue={value} min={min} max={max} step={step}
          onKeyDown={(e) => { if (e.key === "Enter") close(); }}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (Number.isFinite(v) && v >= min && (max == null || v <= max)) onChange(v);
          }} />
      )}
    </Pop>
  );
}

function TimeTok({ value, empty, title, onChange, hint }: { value: string; empty: string; title: string; onChange: (v: string) => void; hint: string }) {
  return (
    <Pop title={title} label={value || empty} cls={value ? "risk" : "missing"}>
      {(close) => (
        <>
          <Field label={title} info={hint}>{(id) => <TimeInput id={id} value={value} onChange={onChange} onEnter={close} allowEmpty />}</Field>
          {value && <button type="button" className="btn quiet sm" onClick={() => { onChange(""); close(); }}>Clear</button>}
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
        <div className="k-stack">
          {options.map(([v, label, help]) => (
            <button type="button" key={v} className={`btn sm k-choice-btn ${v === value ? "" : "quiet"}`}
              onClick={() => { onChange(v); close(); }}>{label}{help ? <span className="k-note">&nbsp;· {help}</span> : null}</button>
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

export function RulesCard({ s, currency, onChange, onRebuilt, defaultStop }: {
  s: Strategy; currency: string; onChange: (s: Strategy) => void;
  /** The stop loss is the notebook's default: the idea never set one and no question about it was answered (DA-008). */
  defaultStop?: boolean;
  /** Called after "Edit in words" rebuilds the rules, with what the new words said and didn't say. */
  onRebuilt?: (gaps: Built["gaps"]) => void;
}) {
  const { allIndicators, refreshMe, me } = useApp();
  const [rewrite, setRewrite] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [rewriteNote, setRewriteNote] = useState("");
  const [rewriteOptions, setRewriteOptions] = useState(false);     // the words describe an options idea: the Options builder is the way on (DA-001)
  const [rewriteWarnings, setRewriteWarnings] = useState<string[]>([]);
  const [unitNote, setUnitNote] = useState<string | null>(null);
  const rebuild = async () => {
    if (rewrite === null) return;
    setRebuilding(true); setRewriteNote(""); setRewriteWarnings([]); setRewriteOptions(false);
    try {
      const out = await buildIdea(rewrite.trim(), undefined, { allIndicators: me ? allIndicators : undefined });
      refreshMe();            // the builds left, as the server now counts them: one that made no rules costs none (DP1-001)
      if (!out.built) { setRewriteNote(out.note); setRewriteOptions(!!out.options); return; }
      const n = out.built.strategy;
      // the stop, target, trail and time limit come from the words; risk per trade, sizing and the rest only when the words
      // state them; the capital stays (as the box says)
      onChange({ ...s, text: n.text, entry: n.entry, exit: n.exit, entryJoin: n.entryJoin, side: n.side, shortEntry: n.shortEntry, shortExit: n.shortExit,
        minScore: n.minScore, tf: n.tf, session: n.session, product: n.product,
        risk: rebuiltRisk(s.risk, n.risk, out.built.gaps.mentioned, true) });
      setRewrite(null);
      setHandEdited(false);
      if (out.note) setRewriteNote(out.note);
      // a rule left out or a number that didn't make it into the rules is said where the rules are (R11C-004)
      setRewriteWarnings([...(out.built.gaps.warnings ?? []), ...out.built.gaps.notes]);
      onRebuilt?.(out.built.gaps);
    } catch (e) { setRewriteNote((e as Error).message); } finally { setRebuilding(false); }
  };
  // a rule changed by hand since the words were written: the words no longer say what the rules do, and rebuilding from
  // them would undo the change without a word (R62-002)
  const [handEdited, setHandEdited] = useState(false);
  const RULE_KEYS = ["entry", "exit", "shortEntry", "shortExit", "entryJoin", "side", "tf"];
  const set = (patch: Partial<Strategy>) => {
    if (Object.keys(patch).some((k) => RULE_KEYS.includes(k))) setHandEdited(true);
    onChange({ ...s, ...patch });
  };
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
  const riskAmount = (r.capital * r.riskPct) / 100;
  // the VWAP the rules use: restarted each day on intraday candles, a rolling average on daily ones (DA-005)
  const vwapRef = [...s.entry, ...s.exit, ...shortEntry, ...shortExit].flatMap((c) => [c.l, c.r]).find((x) => x.t === "vwap");

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
      <CondSentence key={`${key}${i}`} c={c} lead={lead(i)} allIndicators={allIndicators} tf={s.tf} scored={entry && scored}
        onChange={(nc) => set({ [key]: conds.map((x, k) => (k === i ? nc : x)) } as Partial<Strategy>)}
        onDelete={() => set({ [key]: conds.filter((_, k) => k !== i) } as Partial<Strategy>)} />
    ));
  const entryLead = (conds: Cond[], word: ReactNode) => (i: number) =>
    conds.length > 1 || scored ? <span className="k-muted">{i + 1}.</span> : <b>{word} when</b>;
  const joinLine = (conds: Cond[], word: ReactNode) => (conds.length > 1 || scored) && (
    <p className="sentence"><b>{word}</b> when {joinTok}{scored && <>{" "}(score at least{" "}
      <NumTok title="Score needed" value={s.minScore ?? 0} min={0} max={120} step={0.5} missing="all of them"
        onChange={(v) => set({ minScore: v })} hint="Add up the points of the rules that are true; enter when the total reaches this. 0 means every rule must be true." />)</>}:</p>
  );
  const unitTok = (kind: "stop" | "tgt") => kind === "stop"
    ? <Choice title="Stop measured in" value={stopType} onChange={(v) => { const x = switchStopUnit(r, v); setRisk(x.risk); setUnitNote(x.note); }} options={STOP_UNITS.map(([v, l, h]) => [v, l, h])} />
    : <Choice title="Target measured in" value={tgtType} onChange={(v) => setRisk({ tgtType: v })} options={TGT_UNITS.map(([v, l, h]) => [v, l, h])} />;
  // the server keeps at most 12 rules in a list: a 13th is never added here to be refused later
  const full = (key: "entry" | "exit" | "shortEntry" | "shortExit") => ((s[key] as Cond[] | undefined) ?? []).length >= MAX_RULES;
  const addRule = (key: "entry" | "exit" | "shortEntry" | "shortExit", c: Cond) => { if (!full(key)) set({ [key]: [...((s[key] as Cond[] | undefined) ?? []), c] } as Partial<Strategy>); };
  const fullNote = <p className="k-note">{MAX_RULES} rules is the most a list can hold. Remove one to add another.</p>;

  // how many advanced settings are in use, so "More settings" says so while closed
  const moreOn = [r.maxBars, intraday && (sess.start || sess.end), intraday && sess.squareoff, intraday && sess.maxTradesDay,
    intraday && sess.cooldown, intraday && sess.dailyLossPct, (r.sizing ?? "risk") === "capital"].filter(Boolean).length;
  const addBtn = (key: "entry" | "exit" | "shortEntry" | "shortExit", c: Cond, label: string) => full(key) ? fullNote : (
    <button type="button" className="add-rule" onClick={() => addRule(key, c)}>+ {label}</button>
  );
  // "+ Add an exit rule" opens a short list of common sell rules to start from, instead of adding one on its own (R5O-010)
  const exitPick = (key: "exit" | "shortExit", label: string) => {
    if (full(key)) return fullNote;
    const closesShort = key === "shortExit" || short;
    const turn = closesShort ? [] : defaultExit(s);
    const common: Cond[] = [
      ...turn,
      { l: { t: "price" }, op: closesShort ? "xa" : "xb", r: { t: "sma", p: 20 } },
      { l: { t: "ema", p: 20 }, op: closesShort ? "xa" : "xb", r: { t: "ema", p: 50 } },
      { l: { t: "rsi", p: 14 }, op: closesShort ? "xb" : "xa", r: { t: "num", v: closesShort ? 30 : 70 } },
    ];
    const choices = common.filter((c, i, all) => all.findIndex((x) => JSON.stringify(x) === JSON.stringify(c)) === i);
    const say = (c: Cond) => `${refName(c.l)} ${opSay(c.op)} ${c.r.t === "num" ? c.r.v : refName(c.r)}`;
    return (
      <Pop title={label} label={`+ ${label}`} cls="add-rule" plain>
        {(close) => (
          <div className="k-stack">
            <b className="k-small">{closesShort ? "Buy back when…" : "Sell when…"}</b>
            {choices.map((c, i) => (
              <button key={say(c)} type="button" className="btn quiet sm" onClick={() => { addRule(key, c); close(); }}>
                {say(c)}{i === 0 && turn.length ? " (the entry turning back)" : ""}
              </button>
            ))}
            <p className="k-note">Tap any word of the rule afterwards to change it.</p>
          </div>
        )}
      </Pop>
    );
  };
  const candlePick = (
    <Pop title="Candle size" label={`${TF_NAME[s.tf].toLowerCase()} candles`} cls="plain">
      {(close) => (
        <div className="k-stack">
          <ChipBar label="Candle size" options={CANDLE_SIZES.map((c) => ({ value: c.value, label: `${TF_NAME[c.value]}` }))} value={s.tf}
            onChange={(v) => { set({ tf: v as Tf }); close(); }}
            custom={{ storageKey: `stratlab.chips.candles.${me?.id ?? "anon"}`, units: CANDLE_UNITS, defaultUnit: "min", validate: candleCheck() }} />
          <p className="k-note">Daily candles suit swing trades that last days to weeks. Shorter candles mean more trades and more noise, and unlock the intraday session rules. {CANDLE_LIMITS}</p>
        </div>
      )}
    </Pop>
  );

  return (
    <Card id="rules-h" label="The rules">
      <CardHead title="The rules" info={HELP.rules} infoLabel="About the rules" actions={
        <button type="button" className="btn quiet sm" onClick={() => setRewrite(rewrite === null ? (s.text || "") : null)}>
          <Pencil size={15} />{rewrite === null ? "Edit in words" : "Close"}
        </button>} />
      {rewrite !== null && (
        <div className="rewrite k-stack">
          <label className="k-small k-muted" htmlFor="rewrite">Describe the whole strategy the way you'd like it. The rules below are rebuilt from it; the market and your capital stay.</label>
          <textarea id="rewrite" className="k-textarea" rows={3} value={rewrite} onChange={(e) => setRewrite(e.target.value)}
            placeholder="e.g. Buy when the 20 EMA crosses above the 50 EMA and RSI is above 50, sell when it crosses back, 2% stop" />
          {handEdited && <Notice tone="warn" role="note">These words are from before you changed the rules by hand. Rebuilding replaces the rules below with what the words say, so update the words first if you want to keep your changes.</Notice>}
          <div className="k-row">
            <button type="button" className="btn sm" disabled={rebuilding || rewrite.trim().length < 5} onClick={rebuild}>{rebuilding ? "Rebuilding…" : "Rebuild the rules"}</button>
            {rewriteNote && <Notice tone="warn" role="status" actions={rewriteOptions ? <Link className="btn sm" to="/options">Open the Options builder</Link> : undefined}>{rewriteNote}</Notice>}
          </div>
        </div>
      )}
      {rewrite === null && (rewriteNote || rewriteWarnings.length > 0) && (
        <div className="k-stack k-tight" data-testid="rebuild-warnings">
          {rewriteNote && <Notice tone="warn" role="status">{rewriteNote}</Notice>}
          {rewriteWarnings.map((w) => <Notice key={w} tone="warn" role="status">{w}</Notice>)}
        </div>
      )}
      <p className="k-small k-muted">Tap any highlighted word to change it: the indicator, its length, the condition or a number.</p>
      {vwapRef && (
        <p className="k-note" data-testid="vwap-note">
          {intraday ? "VWAP here is the day's VWAP: it restarts at each trading day's open, so its length isn't used."
            : `On daily candles VWAP is a rolling ${vwapRef.p ?? DEFAULTS.vwap?.[0] ?? 20}-candle average, not the day's VWAP. Pick 5-minute, 15-minute or 1-hour candles to use the day's VWAP.`}
        </p>
      )}
      {[...s.entry, ...s.exit, ...(s.shortEntry ?? []), ...(s.shortExit ?? [])].map(selfMultipleNote).filter((n): n is string => !!n).map((n) => (
        <Notice key={n} tone="warn" role="status">{n} A run is refused while it is in the notebook.</Notice>
      ))}
      {meaningful([...s.entry, ...s.exit, ...(s.shortEntry ?? []), ...(s.shortExit ?? [])].filter((c) => !selfMultipleNote(c))).dropped.map((d) => (
        <Notice key={d} tone="warn" role="status">"{d}" can't mean anything as a rule. A run is refused while a rule that can never be true is in the notebook.</Notice>
      ))}

      <Block title={both ? "Entry: long" : "Entry"}>
        {joinLine(s.entry, sideTok("long"))}
        {s.entry.length === 0 && <p className="sentence k-muted">{sideTok("long")} when… no entry rule yet.</p>}
        {list("entry", s.entry, (i) => s.entry.length > 1 || scored ? <span className="k-muted">{i + 1}.</span> : <b>{sideTok("long")} when</b>, true)}
        {addBtn("entry", { l: { t: "price" }, op: short ? "lt" : "gt", r: { t: "sma", p: 50 } }, "Add an entry rule")}
      </Block>
      {both && (
        <Block title="Entry: short">
          {joinLine(shortEntry, "Sell short")}
          {shortEntry.length === 0 && <p className="sentence k-muted">No short entry rule yet.</p>}
          {list("shortEntry", shortEntry, entryLead(shortEntry, "Sell short"), true)}
          {addBtn("shortEntry", { l: { t: "price" }, op: "lt", r: { t: "sma", p: 50 } }, "Add a short entry rule")}
        </Block>
      )}

      <Block title="Exit" info={s.entry.length > 0 ? <Info label="Crosses or is above?">{HELP.crosses}</Info> : undefined}>
        {list("exit", s.exit, (i) => i === 0 ? <b>{short ? "Buy back" : "Sell"} when</b> : <b>or when</b>, false)}
        {both && list("shortExit", shortExit, (i) => i === 0 ? <b>Buy back a short when</b> : <b>or when</b>, false)}
        {!s.exit.length && !shortExit.length && <p className="sentence k-muted" data-testid="no-sell-rule">No sell rule yet.{intraday && sess.squareoff ? ` Every open trade closes at ${sess.squareoff}, the square-off time.` : ""}</p>}
        <p className="sentence">
          {/* "at a 3% stop or a 6% target", "at a 3% stop, with no target", "with no stop loss and at a 6% target": never
              "or a no target" (R6O-010) */}
          {s.exit.length || shortExit.length ? "Also close" : <b>Close</b>}{r.sl > 0 ? " at a " : " with "}
          <NumTok title="Stop loss" value={r.sl} missing="no stop loss" max={stopType === "pct" ? 99 : 100000} step={stopType === "swing" ? 1 : 0.1}
            render={(v) => `${v}`} onChange={(v) => { setRisk({ sl: v }); setUnitNote(null); }} hint="0 turns it off. Tap the word after the number to change the unit." />
          {/* "3% stop", never "3 % stop" (R6O-010): no space before a percent sign */}
          {r.sl > 0 && <>{stopType === "pct" ? "" : " "}{unitTok("stop")}</>}{r.tgt > 0 ? (r.sl > 0 ? " or a " : " and at a ") : (r.sl > 0 ? ", with " : " and ")}
          <NumTok title="Target" value={r.tgt} missing="no target" max={100000} render={(v) => `${v}`}
            onChange={(v) => setRisk({ tgt: v })} hint={tgtType === "r" ? "A multiple of the stop distance: 2 means twice what you risk." : "0 turns it off."} />
          {r.tgt > 0 && <>{tgtType === "pct" ? "" : " "}{unitTok("tgt")}</>}.
          <Info label="What are a stop loss and a target?"><b>Stop loss:</b> {HELP.stop}<br /><br /><b>Target:</b> {HELP.target}<br /><br /><b>Units:</b> {HELP.stopUnits}</Info>
        </p>
        {/* a trailing stop is an exit like the stop loss: shown with the rules, not only inside More settings (DA-008) */}
        {(r.trail ?? 0) > 0 && (
          <p className="sentence" data-testid="trail-line">
            Also close if the price {short ? "rises" : "falls"}{" "}
            <NumTok title="Trailing stop (%)" value={r.trail ?? 0} suffix="%" missing="off" max={50} onChange={(v) => setRisk({ trail: v })}
              hint="Moves the stop with the best price since the trade opened, staying this far behind it. It never moves back. 0 turns it off." />{" "}
            from its best since the trade opened (a trailing stop).
          </p>
        )}
        {defaultStop && r.sl > 0 && (
          <p className="k-note" data-testid="default-stop-note">The {stopWords(r.sl, stopType)} is a default: your idea didn't set a stop loss. Change it above, or set it to 0 to test without one.</p>
        )}
        {unitNote && <Notice tone="warn" role="status" className="stop-unit-note">{unitNote}</Notice>}
        {/* below the block's rules, like the entry's add button */}
        {exitPick("exit", both ? "Add a sell rule" : "Add an exit rule")}
        {both && exitPick("shortExit", "Add a buy-back rule")}
      </Block>

      <Block title="Size and candles">
        {(r.sizing ?? "risk") === "risk" && sizedWithoutStop(r) ? (
          <p className="sentence" data-testid="risk-line">
            <b>Position size:</b> {NO_STOP_SIZE_NOTE}{" "}
            <Info label="Why does risk per trade not apply?">{HELP.risk} It needs a stop loss or a trailing stop. Without one, each trade takes up to {r.maxAlloc}% of your capital ({money((r.capital * r.maxAlloc) / 100, currency)}).</Info>
          </p>
        ) : (r.sizing ?? "risk") === "risk" ? (
          <p className="sentence" data-testid="risk-line">
            <b>Risk per trade:</b>{" "}
            <NumTok title="Risk per trade (% of your capital)" value={r.riskPct} suffix="%" min={0.1} max={100}
              onChange={(v) => setRisk({ riskPct: v })} hint="The share of your starting capital you would lose if the stop loss is hit. After losses it is the share of what is left, so trades shrink; after a profit the size does not grow." />{" "}of your capital{" "}
            <span className="k-amount" data-testid="risk-amount">({money(riskAmount, currency)})</span>
            {/* with only a trailing stop, the size is measured from it: said, so "1%" doesn't read as clashing with a 5% trail (DP1-011) */}
            {!(r.sl > 0) && (r.trail ?? 0) > 0 && <span className="k-small k-muted" data-testid="risk-from-trail"> if the {r.trail}% trailing stop is hit, so each trade is sized to that</span>}
            <Info label="What does risk per trade mean?">{HELP.risk} With {r.riskPct}% of {money(r.capital, currency)}, that is {money(riskAmount, currency)} if the {r.sl > 0 ? "stop loss" : "trailing stop"} is hit.</Info>
          </p>
        ) : (
          <p className="sentence">
            <b>Put</b>{" "}<NumTok title="Capital per trade" value={r.perTrade ?? 0} min={0} step={1000} missing="all" render={(v) => money(v, currency)}
              onChange={(v) => setRisk({ perTrade: v })} hint="The margin each trade uses. 0 uses the max capital per trade % below." />
            {(r.leverage ?? 1) > 1 && <>{" "}× <NumTok title="Leverage" value={r.leverage ?? 1} min={1} max={20} step={0.5} render={(v) => `${v} leverage`} onChange={(v) => setRisk({ leverage: v })} hint="The position is this many times the capital per trade (intraday margin)." /></>}{" "}
            on each trade, from your capital.
          </p>
        )}
        <p className="sentence">
          <b>Your capital:</b>{" "}
          <NumTok title="Capital" value={r.capital} min={1} step={1000} render={(v) => money(v, currency)} onChange={(v) => setRisk({ capital: v })}
            hint="Pretend money the test starts with." />{" "}checked on {candlePick}.
          <Info label="What do capital and candles mean?"><b>Capital:</b> {HELP.capital}<br /><br /><b>Candles:</b> {HELP.candles}</Info>
        </p>
      </Block>

      <More id="rules" what={intraday ? "trailing stop, time limit, intraday limits, costs" : "trailing stop, time limit, costs, sizing"} on={moreOn}>
        <p className="sentence">
          Trailing stop:{" "}
          <NumTok title="Trailing stop (%)" value={r.trail ?? 0} suffix="%" missing="off" max={50} onChange={(v) => setRisk({ trail: v })}
            hint="Moves the stop with the best price since the trade opened, staying this far behind it. It never moves back. 0 turns it off." />. Time limit:{" "}
          <NumTok title="Close after (candles)" value={r.maxBars ?? 0} step={1} max={5000} missing="none" render={(v) => `${v} candle${v === 1 ? "" : "s"}`}
            onChange={(v) => setRisk({ maxBars: Math.round(v) })} hint="Closes a trade that's still open after this many candles, at the close. 0 turns it off." /> (a trade still open after that many candles is closed).
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
              hint="Any open trade closes on the candle that ends at this time. Indian intraday (MIS) costs apply when set." />, trades per day:{" "}
            <NumTok title="Trades per day" value={sess.maxTradesDay} step={1} max={100} missing="no limit" render={(v) => `at most ${v}`}
              onChange={(v) => setSess({ maxTradesDay: Math.round(v) })} hint="0 means no limit." />, wait{" "}
            <NumTok title="Cooldown (candles)" value={sess.cooldown} step={1} max={500} missing="no candles" render={(v) => `${v} candle${v === 1 ? "" : "s"}`}
              onChange={(v) => setSess({ cooldown: Math.round(v) })} hint="After a trade closes, skip this many candles before entering again." />{" "}after each trade, daily loss limit:{" "}
            <NumTok title="Daily loss cap (% of capital)" value={sess.dailyLossPct} max={100} missing="no limit" suffix="%"
              onChange={(v) => setSess({ dailyLossPct: v })} hint="Once the day's loss (including the open trade) reaches this % of capital, the trade is closed and nothing more happens until the next market day. 0 means no limit." />.
            <Info label="Intraday session rules">{HELP.session}</Info>
          </p>
        )}
        <span className="k-eyebrow">Costs and position size</span>
        <FormGrid label="Costs and position size">
          <Field label="Position size" wide>{(id) => (
            <Select id={id} value={r.sizing ?? "risk"} onChange={(v) => setRisk({ sizing: v as Risk["sizing"] })}
              options={[{ value: "risk", label: "By risk (% of capital)" }, { value: "capital", label: "Fixed capital per trade" }]} />
          )}</Field>
          {(r.sizing ?? "risk") === "capital" && <>
            <NumField label="Capital per trade" min={0} step={1000} value={r.perTrade ?? 0} onValid={(v) => { if (v >= 0) setRisk({ perTrade: v }); }} />
            <NumField label="Leverage (×)" min={1} max={20} step={0.5} value={r.leverage ?? 1} onValid={(v) => { if (v >= 1 && v <= 20) setRisk({ leverage: v }); }} />
          </>}
          <NumField label="Max capital per trade (%)" min={1} max={100} value={r.maxAlloc} onValid={(v) => { if (v >= 1 && v <= 100) setRisk({ maxAlloc: v }); }} />
          <NumField label={`Brokerage per order (${currency || "flat"})`} min={0} step={1} value={r.brokerage} onValid={(v) => { if (v >= 0) setRisk({ brokerage: v }); }} />
          <NumField label="Slippage (%)" min={0} max={5} step={0.01} value={r.slippage} onValid={(v) => { if (v >= 0 && v <= 5) setRisk({ slippage: v }); }} />
          {currency === "INR" && (
            <Field label="Indian stock costs" hint="Automatic uses intraday (MIS) costs when the strategy squares off the same day, and delivery (CNC) costs otherwise.">{(id) => (
              <Select id={id} value={s.product ?? "auto"} onChange={(v) => set({ product: v as Strategy["product"] })}
                options={[{ value: "auto", label: "Automatic" }, { value: "delivery", label: "Delivery (CNC)" }, { value: "intraday", label: "Intraday (MIS)" }]} />
            )}</Field>
          )}
        </FormGrid>
        <p className="k-note">By risk: quantity = risk amount ÷ distance to the stop, capped by max capital per trade. Fixed capital: quantity = capital per trade × leverage ÷ price. Taxes and exchange fees are added for you per market.</p>
      </More>
    </Card>
  );
}
