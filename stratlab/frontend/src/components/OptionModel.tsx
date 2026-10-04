import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money } from "../lib/format";
import { moneyCompact } from "../lib/chartFormat";
import { curve, legGreeks, NO_MOVE, scenario, type GreekModel, type ModelLeg, type NetGreeks, type OptionGreeks, type WhatIf } from "../lib/greeks";
import type { HeldLeg } from "../lib/options";
import type { OptChain, OptRoll } from "../lib/types";
import { PayoffChart, type PayoffCurve, type PayoffMarker } from "./Charts";

/* The pricing model's view of an options position, shared by the builder and the session page:
 *  - each leg's IV and Greeks, and the net Greeks of the whole position (every plan);
 *  - the payoff "today" from the model beside the one at expiry, before and after charges (every plan);
 *  - what-if sliders that move the underlying, shift every IV and pass days, re-pricing the curve, the Greeks and the
 *    P&L in the browser with lib/greeks.ts (Pro);
 *  - a roll preview: one leg closed and another strike or expiry opened, priced on today's bid and ask (Pro).
 * Every number here is a model estimate and says so, with its inputs: the forward, IV from the bid-ask middle, days
 * left and the rate. */

const MINUS = "−";
const inr = (v: number | null | undefined, dp = 0) => money(v, "INR", dp);
const signed = (v: number, dp: number) => (v < 0 ? MINUS : "") + Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp });
/** A small number to `n` significant figures: 0.00106, −0.159. */
const sig = (v: number, n = 3) => (v === 0 ? "0" : (v < 0 ? MINUS : "") + String(+Math.abs(v).toPrecision(n)));
const pts = (x: number) => Math.round(x).toLocaleString("en-IN");
const dayWord = (d: number) => `${+d.toFixed(2)} day${Math.abs(d - 1) < 1e-9 ? "" : "s"}`;
const pctIv = (v: number) => `${(v * 100).toFixed(1)}%`;
const shortDate = (e: string) => new Date(e + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/** A value that follows `value` at most every `ms` and always settles on the last one: the sliders re-price while
 * they're dragged without re-pricing on every pixel. */
export function useSmooth<T>(value: T, ms = 50): T {
  const [out, setOut] = useState(value);
  const last = useRef(0);
  useEffect(() => {
    const h = window.setTimeout(() => { last.current = Date.now(); setOut(value); }, Math.max(0, last.current + ms - Date.now()));
    return () => window.clearTimeout(h);
  }, [value, ms]);
  return out;
}

/** The model's inputs, in a line under every figure that uses them. */
export function ModelInputs({ m, extra }: { m: GreekModel; extra?: string }) {
  const time = new Date(m.as_of).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
  return (
    <p className="small muted model-inputs" data-testid="model-inputs">
      Model estimates, not prices: Black-76 on the forward {m.forward.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
      {m.forward_from === "parity" ? ` (from put-call parity at ${pts(m.atm ?? m.spot)})` : " (the spot: the at-the-money pair had no prices)"}, IV from each
      option's bid-ask middle{m.atm_iv ? ` (at the money ${pctIv(m.atm_iv)})` : ""}, {dayWord(m.days)} to the {shortDate(m.expiry)} expiry, rate {+(m.rate * 100).toFixed(2)}%,
      {" "}as of {time} IST.{extra ? ` ${extra}` : ""} Delta and gamma per point of the underlying, theta per calendar day, vega per 1 vol point. Real prices can differ.
    </p>
  );
}

export interface ModelRow { label: string; held: HeldLeg; g: OptionGreeks | null; m: ModelLeg | null }

function Slider({ id, label, value, min, max, step, show, onChange }: {
  id: string; label: string; value: number; min: number; max: number; step: number; show: string; onChange: (v: number) => void;
}) {
  return (
    <label className="whatif-slider">
      <span className="spread"><span className="small">{label}</span><b className="mono small" data-testid={`${id}-value`}>{show}</b></span>
      <input type="range" data-testid={id} aria-label={label} min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} />
    </label>
  );
}

/** Each leg's IV and Greeks per option, and the position's net (× quantity, sold legs negative). */
function GreeksTable({ rows, spot, w, r, net }: { rows: ModelRow[]; spot: number; w: WhatIf; r: number; net: NetGreeks | null }) {
  return (
    <div className="table-wrap" style={{ margin: 0 }}>
      <table className="greeks-t small" data-testid="greeks-table">
        <thead><tr><th>Leg</th><th>IV</th><th>Delta</th><th>Gamma</th><th>Theta / day</th><th>Vega / vol pt</th></tr></thead>
        <tbody>
          {rows.map((row, i) => {
            const g = row.m ? legGreeks(row.m, spot, w, r) : null;
            const s = row.g;
            const v = g ?? (s?.iv ? { iv: s.iv, delta: s.delta!, gamma: s.gamma!, theta: s.theta!, vega: s.vega! } : null);
            return (
              <tr key={i}>
                <td>{row.label}</td>
                {v ? <>
                  <td className="mono">{v.iv > 0 ? pctIv(v.iv) : "expired"}{s?.iv_from === "atm" ? "*" : ""}</td>
                  <td className="mono">{signed(v.delta, 3)}</td><td className="mono">{sig(v.gamma)}</td>
                  <td className="mono">{inr(v.theta, 2)}</td><td className="mono">{inr(v.vega, 2)}</td>
                </> : <td colSpan={5} className="muted">No price, so no IV</td>}
              </tr>
            );
          })}
          {net && (
            <tr className="greeks-net" data-testid="greeks-net">
              <td><b>Net</b> <span className="muted">(× quantity)</span></td><td />
              <td className="mono" data-testid="net-delta"><b>{signed(net.delta, 1)}</b></td>
              <td className="mono" data-testid="net-gamma"><b>{sig(net.gamma)}</b></td>
              <td className="mono" data-testid="net-theta"><b>{inr(net.theta)}</b></td>
              <td className="mono" data-testid="net-vega"><b>{inr(net.vega)}</b></td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** The payoff at expiry and today, the Greeks, and (on Pro) the what-if sliders, all from one model. */
export function ModelPanel({ model, rows, xs, expiry, markers, base = 0, charges, chargesLabel, whatif, plan, name, ariaLabel, testId }: {
  model: GreekModel; rows: ModelRow[]; xs: number[]; expiry: PayoffCurve[]; markers: PayoffMarker[];
  base?: number;                 // profit already booked (legs closed earlier), part of the position's P&L
  charges: number | null;        // charges the after-charges curves take off
  chargesLabel: string;          // what those charges are, for the P&L line
  whatif: boolean; plan: string; name: string; ariaLabel: string; testId?: string;
}) {
  const [raw, setRaw] = useState<WhatIf>(NO_MOVE);
  const w = useSmooth(whatif ? raw : NO_MOVE);
  const r = model.rate;
  const legs = useMemo(() => rows.map((x) => x.m).filter((x): x is ModelLeg => !!x), [rows]);
  const complete = legs.length === rows.length;
  const maxDays = Math.max(model.days, ...legs.map((l) => l.t * 365));
  const dayStep = maxDays > 10 ? 0.5 : maxDays > 2 ? 0.25 : 0.05;
  const days = Math.min(w.days, maxDays);
  const spotW = model.spot * (1 + w.spotPct / 100);
  const todayYs = useMemo(() => (complete ? curve(legs, xs, days, w.ivShift, r).map((y) => y + base) : null), [complete, legs, xs, days, w.ivShift, r, base]);
  const sc = useMemo(() => (legs.length ? scenario(legs, spotW, days, w.ivShift, r) : null), [legs, spotW, days, w.ivShift, r]);
  const moved = w.spotPct !== 0 || w.ivShift !== 0 || days > 0;
  const atExpiry = days >= maxDays - 1e-9;
  const todayLabel = !moved || days === 0 ? "Today" : atExpiry ? "At expiry, with the what-if" : `In ${dayWord(days)}`;
  const curves: PayoffCurve[] = [...expiry];
  if (todayYs) {
    curves.push({ id: "today", label: `${todayLabel} (model)`, tipLabel: `${todayLabel.toLowerCase()}, model estimate`, values: todayYs, color: "var(--series-3)", width: 2, shade: false });
    if (charges != null) curves.push({ id: "today-after", label: `${todayLabel} after charges (model)`, tipLabel: `${todayLabel.toLowerCase()} after charges, model estimate`,
      values: todayYs.map((y) => y - charges), color: "var(--series-3)", dash: "2 3", width: 1.4, shade: false });
  }
  const allMarkers = [...markers, ...(w.spotPct !== 0 ? [{ x: spotW, label: `What-if ${pts(spotW)}`, kind: "other" as const, color: "var(--series-3)" }] : [])];
  const settings = [w.spotPct !== 0 && `${name} ${w.spotPct > 0 ? "+" : MINUS}${Math.abs(w.spotPct)}% at ${pts(spotW)}`,
    w.ivShift !== 0 && `IV ${w.ivShift > 0 ? "+" : MINUS}${Math.abs(w.ivShift)} pts`, days > 0 && (atExpiry ? "at expiry" : `${dayWord(days)} on`)].filter(Boolean).join(", ");
  const missing = rows.filter((x) => !x.m).map((x) => x.label);

  return (
    <div className="stack" style={{ gap: 12 }} data-testid={testId}>
      {whatif ? (
        <div className="whatif card-inset stack" style={{ gap: 10 }} data-testid="whatif">
          <div className="spread"><span className="eyebrow">What if</span>
            <button className="btn quiet sm" data-testid="whatif-reset" disabled={raw === NO_MOVE} onClick={() => setRaw(NO_MOVE)}>Reset</button></div>
          <div className="whatif-grid">
            <Slider id="whatif-spot" label={`${name} moves`} value={raw.spotPct} min={-10} max={10} step={0.25}
              show={`${raw.spotPct > 0 ? "+" : raw.spotPct < 0 ? MINUS : ""}${Math.abs(raw.spotPct)}% · ${pts(model.spot * (1 + raw.spotPct / 100))}`}
              onChange={(v) => setRaw((x) => ({ ...x, spotPct: v }))} />
            <Slider id="whatif-iv" label="IV shifts" value={raw.ivShift} min={-20} max={20} step={0.5}
              show={`${raw.ivShift > 0 ? "+" : raw.ivShift < 0 ? MINUS : ""}${Math.abs(raw.ivShift)} vol pts`} onChange={(v) => setRaw((x) => ({ ...x, ivShift: v }))} />
            <Slider id="whatif-days" label="Days pass" value={raw.days} min={0} max={Math.ceil(maxDays / dayStep) * dayStep} step={dayStep}
              show={raw.days >= maxDays - 1e-9 ? "to expiry" : dayWord(raw.days)} onChange={(v) => setRaw((x) => ({ ...x, days: v }))} />
          </div>
        </div>
      ) : (
        <p className="small muted" data-testid="whatif-locked">What-if sliders (move the underlying, shift IV, pass days) and the roll preview are on the {plan} plan.{" "}
          <Link to="/plans">See plans</Link></p>
      )}
      {sc && complete && (
        <div className="opt-stats" data-testid="whatif-pnl">
          <div><span className="eyebrow">Model P&amp;L{moved ? ", what-if" : " now"}</span><b className={`mono ${sc.pnl + base >= 0 ? "pos" : "neg"}`}>{inr(sc.pnl + base)}</b>
            <span className="small muted">{charges != null ? `${inr(sc.pnl + base - charges)} after ${chargesLabel}` : "before charges"}</span></div>
          <div><span className="eyebrow">Net delta</span><b className="mono">{signed(sc.delta, 1)}</b><span className="small muted">₹ per point</span></div>
          <div><span className="eyebrow">Net theta</span><b className="mono">{inr(sc.theta)}</b><span className="small muted">a day</span></div>
          <div><span className="eyebrow">Net vega</span><b className="mono">{inr(sc.vega)}</b><span className="small muted">per vol point</span></div>
        </div>
      )}
      <PayoffChart ariaLabel={ariaLabel} height={240} xs={xs} testId="payoff-chart" curves={curves} markers={allMarkers}
        format={(v) => inr(v)} axisFormat={(v) => moneyCompact(v, "INR")} xFormat={(x) => pts(x)} />
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Greeks, model estimate{settings ? ` (${settings})` : ""}</span>
        <GreeksTable rows={rows} spot={model.spot} w={{ ...w, days }} r={r} net={complete && sc ? sc : null} />
        {!complete && <p className="small muted">{missing.join(", ")}: no price right now, so the model can't value {missing.length === 1 ? "it" : "them"} and the net Greeks and the today curve wait for one.</p>}
        {rows.some((x) => x.g?.iv_from === "atm") && <p className="small muted">* IV of the at-the-money strike: this option's own price gives none.</p>}
        <ModelInputs m={model} extra={moved ? `What-if: ${settings}; IV floored at 0.5%.` : undefined} />
      </div>
    </div>
  );
}

const SIDE = { buy: "bought", sell: "sold" } as const;
export interface RollLeg { label: string; held: HeldLeg }

/** Close one leg and open another strike or expiry in its place: the premium that changes hands, the charges of the
 * two orders, and the net Greeks before and after (Pro). Strikes and expiries come from the caller, or from the chain. */
export function RollPreview({ legs, exchange, underlying, expiry, strikes, expiries, step, brokerage, freeze }: {
  legs: RollLeg[]; exchange: string; underlying: string; expiry: string; strikes?: number[]; expiries?: string[]; step?: number;
  brokerage: number; freeze: number;
}) {
  const { fail } = useApp();
  const [choices, setChoices] = useState<{ strikes: number[]; expiries: string[]; step: number } | null>(
    strikes && expiries ? { strikes, expiries, step: step ?? 50 } : null);
  const [i, setI] = useState(0);
  const leg = legs[Math.min(i, legs.length - 1)]?.held;
  const [to, setTo] = useState<{ strike: number; expiry: string } | null>(null);
  const [res, setRes] = useState<OptRoll | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (choices) return;
    api<OptChain>(`/options/chain?exchange=${exchange}&underlying=${encodeURIComponent(underlying)}&expiry=${expiry}`)
      .then((c) => setChoices({ strikes: c.rows.map((r) => r.strike), expiries: c.expiries ?? [expiry], step: c.step ?? 50 })).catch(fail);
  }, [choices, exchange, underlying, expiry, fail]);
  // a new leg starts one strike further out of the money, in the same expiry (keyed on the contract, so the session
  // page's refreshed quotes don't wipe a preview)
  const legKey = leg ? `${leg.opt}${leg.strike}` : "";
  useEffect(() => {
    if (!leg || !choices) return;
    const s = choices.strikes, at = s.indexOf(leg.strike);
    const next = at < 0 ? leg.strike : s[Math.min(s.length - 1, Math.max(0, at + (leg.opt === "CE" ? 1 : -1)))];
    setTo({ strike: next, expiry });
    setRes(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [legKey, choices, expiry]);
  if (!leg || !choices || !to) return <p className="small muted">Loading the strikes…</p>;
  const run = async () => {
    setBusy(true);
    try {
      setRes(await api<OptRoll>("/options/roll", { method: "POST", body: {
        exchange, underlying, expiry, brokerage, freeze, leg: Math.min(i, legs.length - 1), strike: to.strike, to_expiry: to.expiry,
        legs: legs.map((l) => ({ side: l.held.side, opt: l.held.opt, strike: l.held.strike, qty: l.held.qty, fill: l.held.fill })) } }));
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const same = to.strike === leg.strike && to.expiry === expiry;
  return (
    <div className="stack" style={{ gap: 12 }} data-testid="roll-preview">
      <div className="opt-grid">
        <label className="field" style={{ minWidth: 170 }}>Leg<select aria-label="Leg to roll" value={i} onChange={(e) => setI(+e.target.value)}>
          {legs.map((l, j) => <option key={j} value={j}>{l.label}</option>)}</select></label>
        <label className="field" style={{ width: 130 }}>New strike<select aria-label="New strike" value={to.strike} onChange={(e) => { setTo({ ...to, strike: +e.target.value }); setRes(null); }}>
          {choices.strikes.map((k) => <option key={k} value={k}>{k.toLocaleString("en-IN")}</option>)}</select></label>
        <label className="field" style={{ width: 150 }}>Expiry<select aria-label="New expiry" value={to.expiry} onChange={(e) => { setTo({ ...to, expiry: e.target.value }); setRes(null); }}>
          {choices.expiries.map((x) => <option key={x} value={x}>{shortDate(x)}{x === expiry ? " (same)" : ""}</option>)}</select></label>
        <button className="btn quiet" disabled={busy || same} onClick={run}>{busy ? "Pricing…" : "Preview the roll"}</button>
      </div>
      {same && <p className="small muted">Pick another strike or expiry for this leg.</p>}
      {res && <RollResult r={res} />}
    </div>
  );
}

function RollResult({ r }: { r: OptRoll }) {
  const rows: [string, keyof NetGreeks, (v: number) => string][] = [["Delta (₹ per point)", "delta", (v) => signed(v, 1)], ["Gamma", "gamma", (v) => sig(v)],
    ["Theta (₹ a day)", "theta", (v) => inr(v)], ["Vega (₹ per vol point)", "vega", (v) => inr(v)]];
  const c = r.close, o = r.open;
  return (
    <div className="stack" style={{ gap: 10 }} data-testid="roll-result">
      <p className="small">Closes the {SIDE[o.side]} {pts(c.strike)} {c.opt} ({shortDate(c.expiry)}) at {inr(c.px, 2)} and opens a {SIDE[o.side]} {pts(o.strike)} {o.opt} ({shortDate(o.expiry)}) at {inr(o.px, 2)}, at today's bid and ask.</p>
      <div className="opt-stats">
        <div><span className="eyebrow">Premium {r.premium >= 0 ? "taken in" : "paid out"}</span><b className={`mono ${r.premium >= 0 ? "pos" : "neg"}`}>{inr(r.premium, 2)}</b></div>
        <div><span className="eyebrow">Charges, two orders</span><b className="mono">{inr(r.charges.total, 2)}</b></div>
        <div data-testid="roll-net"><span className="eyebrow">After charges</span><b className={`mono ${r.net >= 0 ? "pos" : "neg"}`}>{inr(r.net, 2)}</b></div>
        <div><span className="eyebrow">New leg's IV</span><b className="mono">{o.iv ? pctIv(o.iv) : "–"}</b></div>
      </div>
      <div className="table-wrap" style={{ margin: 0 }}>
        <table className="small greeks-t">
          <thead><tr><th>Net Greeks, model estimate</th><th>Before</th><th>After</th><th>Change</th></tr></thead>
          <tbody>{rows.map(([label, k, f]) => (
            <tr key={k} data-testid={`roll-${k}`}><td>{label}</td><td className="mono">{f(r.before[k])}</td><td className="mono">{f(r.after[k])}</td><td className="mono">{f(r.after[k] - r.before[k])}</td></tr>
          ))}</tbody>
        </table>
      </div>
      {!r.complete && <p className="small muted">A leg has no price right now, so the net Greeks leave it out.</p>}
      <ModelInputs m={r.model_to} extra={r.model_to.expiry !== r.model.expiry ? `The other legs: the ${shortDate(r.model.expiry)} expiry, ${dayWord(r.model.days)} left, forward ${pts(r.model.forward)}.` : undefined} />
    </div>
  );
}
