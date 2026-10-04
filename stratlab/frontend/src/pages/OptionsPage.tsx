import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { money, price } from "../lib/format";
import { HELP } from "../lib/help";
import { blankOptions, IMPORTED, payoff, POPULAR_FALLBACK, sessionFor, STRUCTURES } from "../lib/options";
import type { LiveRow, Notebook, OptChain, OptCharges, OptionStrategy, OptLeg, OptPreview, Underlying } from "../lib/types";
import { LineChart } from "../components/Charts";
import { Block, More } from "../components/More";
import { Info, Loading } from "../components/ui";
import { track } from "../lib/analytics";
import { PositioningCard } from "../components/PositioningCard";
import { Earlier } from "../components/Earlier";

const DRAFT = "stratlab.options.draft.v1";

const loadDraft = (): OptionStrategy => {
  try {
    const raw = localStorage.getItem(DRAFT);
    if (raw) return { ...blankOptions(), ...JSON.parse(raw) };
  } catch { /* storage off */ }
  return blankOptions();
};

const inr = (v: number | null | undefined, dp = 0) => money(v, "INR", dp);
const expiryName = (e: string) => new Date(e + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", weekday: "short" });

function Num({ label, value, onChange, min = 0, max, step = 1, width = 110, suffix, help }: {
  label: ReactNode; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; width?: number; suffix?: string; help?: string;
}) {
  const [txt, setTxt] = useState(String(value));
  useEffect(() => setTxt(String(value)), [value]);
  return (
    <label className="field" style={{ width }}>
      <span className="row" style={{ gap: 0 }}>{label}{help && <Info>{help}</Info>}</span>
      <span className="row" style={{ gap: 6 }}>
        <input type="number" inputMode="decimal" value={txt} min={min} max={max} step={step} style={{ minWidth: 0, flex: 1 }}
          onChange={(e) => { setTxt(e.target.value); const n = parseFloat(e.target.value); if (!isNaN(n) && n >= min && (max == null || n <= max)) onChange(n); }} />
        {suffix && <span className="small muted">{suffix}</span>}
      </span>
    </label>
  );
}

function Time({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return <label className="field" style={{ width: 130 }}><span>{label}</span><input type="time" value={value} onChange={(e) => e.target.value && onChange(e.target.value)} /></label>;
}

function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, n]) => <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>{n}</button>)}
    </div>
  );
}

function LegsEditor({ s, set, preview }: { s: OptionStrategy; set: (legs: OptLeg[]) => void; preview: OptPreview | null }) {
  const upd = (i: number, p: Partial<OptLeg>) => set(s.legs.map((l, j) => (j === i ? { ...l, ...p } : l)));
  const unit = s.offsetUnit === "points" ? "points" : "strikes";
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="table-wrap" style={{ margin: 0 }}>
        <table className="legs">
          <thead><tr><th>Buy or sell</th><th>Type</th><th>{unit === "points" ? "Points" : "Strikes"} from ATM<Info>{HELP.optOffset}</Info></th><th>Lots</th>
            {preview && <><th>Strike</th><th>Fill now</th></>}<th /></tr></thead>
          <tbody>{s.legs.map((l, i) => {
            const p = preview?.legs[i];
            return (
              <tr key={i}>
                <td><select aria-label={`Leg ${i + 1} buy or sell`} value={l.side} onChange={(e) => upd(i, { side: e.target.value as OptLeg["side"] })}>
                  <option value="sell">Sell</option><option value="buy">Buy</option></select></td>
                <td><select aria-label={`Leg ${i + 1} call or put`} value={l.opt} onChange={(e) => upd(i, { opt: e.target.value as OptLeg["opt"] })}>
                  <option value="CE">Call (CE)</option><option value="PE">Put (PE)</option></select></td>
                <td><input aria-label={`Leg ${i + 1} distance from the money`} type="number" value={l.offset} step={unit === "points" ? 50 : 1}
                  onChange={(e) => { const n = parseFloat(e.target.value); if (!isNaN(n)) upd(i, { offset: n }); }} /></td>
                <td><input aria-label={`Leg ${i + 1} lots`} type="number" min={1} max={50} value={l.lots}
                  onChange={(e) => { const n = parseInt(e.target.value, 10); if (n >= 1 && n <= 50) upd(i, { lots: n }); }} /></td>
                {preview && <><td className="mono">{p?.strike ?? "not listed"}</td><td className="mono">{p?.fill != null ? price(p.fill, "INR") : "no quote"}</td></>}
                <td>{s.legs.length > 1 && <button className="chip-x" aria-label={`Remove leg ${i + 1}`} onClick={() => set(s.legs.filter((_, j) => j !== i))}>×</button>}</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      {s.legs.length < 8 && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }}
        onClick={() => set([...s.legs, { side: "buy", opt: "CE", offset: s.offsetUnit === "points" ? 500 : 6, lots: 1 }])}>Add a leg</button>}
    </div>
  );
}

const points = (xs: number[]) => xs.map((b) => Math.round(b).toLocaleString("en-IN")).join(" and ");
const share = (v: number | null) => (v == null ? "–" : `${v.toFixed(2)}%`);
const asOf = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** What opening and closing the structure once costs, line by line, and what that does to its numbers. */
function Charges({ c }: { c: OptCharges }) {
  return (
    <div className="stack opt-charges" style={{ gap: 10 }} data-testid="opt-charges">
      <div className="opt-stats">
        <div><span className="eyebrow">Charges to open and close</span><b className="mono">{inr(c.total, 2)}</b></div>
        <div><span className="eyebrow">Share of the premium</span><b className="mono">{share(c.pct_of_premium)}</b></div>
        <div><span className="eyebrow">Share of the most it can make</span><b className="mono">{c.max_profit == null ? "No ceiling" : share(c.pct_of_max_profit)}</b></div>
        {c.credit
          ? <div><span className="eyebrow">Premium kept after charges</span><b className="mono">{inr(c.premium_after, 2)}</b></div>
          : <div><span className="eyebrow">Most it can make after charges</span><b className="mono">{c.max_profit_after == null ? "Unlimited" : inr(c.max_profit_after, 2)}</b></div>}
      </div>
      <details className="opt-charge-lines">
        <summary className="small">Charges line by line</summary>
        <table className="small">
          <tbody>
            {c.items.map((i) => <tr key={i.key}><td>{i.label}</td><td className="mono num">{inr(i.amount, 2)}</td></tr>)}
            <tr><td><b>Total</b></td><td className="mono num"><b>{inr(c.total, 2)}</b></td></tr>
          </tbody>
        </table>
        <p className="small muted">
          {c.orders} orders at {inr(c.brokerage_per_order)} brokerage each{c.freeze ? `; orders above ${c.freeze.toLocaleString("en-IN")} units go in slices, each one an order` : ""}.
          Every leg opened and closed once at the fill shown. Rates as of {asOf(c.rates_as_of)}.
        </p>
      </details>
    </div>
  );
}

function Payoff({ p }: { p: OptPreview }) {
  const f = useMemo(() => payoff(p), [p]);
  const c = p.charges;
  const before = c ? c.breakevens : f.breakevens;
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="opt-stats">
        <div><span className="eyebrow">{f.credit >= 0 ? "Premium collected" : "Premium paid"}</span><b className="mono">{inr(Math.abs(f.credit))}</b></div>
        <div><span className="eyebrow">Most it can make</span><b className="mono pos">{f.maxProfit == null ? "Unlimited" : inr(f.maxProfit)}</b></div>
        <div><span className="eyebrow">Most it can lose</span><b className="mono neg">{f.maxLoss == null ? "Unlimited" : inr(f.maxLoss)}</b></div>
        <div><span className="eyebrow">Margin needed</span><b className="mono">{p.margin != null ? inr(p.margin) : "Not available"}</b></div>
      </div>
      <LineChart ariaLabel="Profit or loss at expiry across prices" height={200} labels={f.xs.map((x) => `${p.legs.length ? "At " : ""}${Math.round(x).toLocaleString("en-IN")}`)}
        format={(v) => inr(v)} axisFormat={(v) => inr(v)} baseline={0}
        lines={[{ label: "At expiry", values: f.ys, color: "var(--blue)", width: 1.8 },
          ...(c ? [{ label: "After charges", values: f.ys.map((y) => y - c.total), color: "var(--blue)", width: 1.2, dash: "4 4" }] : [])]} />
      <p className="small muted" data-testid="opt-breakevens">
        At expiry, if held to the end{c ? "; the dashed line is after charges" : ", before costs"}.{" "}
        {before.length > 0 && <>Breaks even at {points(before)}{c ? " before charges" : ""}. </>}
        {c && (c.breakevens_after.length > 0 ? <>After charges: {points(c.breakevens_after)}. </> : <>After charges it doesn't break even at any price. </>)}
        Paper trades close at your square-off time, usually well before expiry, so they rarely reach these extremes.
      </p>
      {c && <Charges c={c} />}
    </div>
  );
}

function Chain({ s }: { s: OptionStrategy }) {
  const { fail } = useApp();
  const [chain, setChain] = useState<OptChain | null>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try { setChain(await api<OptChain>(`/options/chain?exchange=${s.exchange}&underlying=${encodeURIComponent(s.underlying)}&expiry=${s.expiry}`)); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  const q = (x: { bid: number | null; ask: number | null; ltp: number | null } | null) => x ? `${x.bid ?? "–"} / ${x.ask ?? "–"}` : "–";
  return (
    <details className="card chain" onToggle={(e) => (e.target as HTMLDetailsElement).open && !chain && load()}>
      <summary className="h3">Option chain<span className="small muted" style={{ fontWeight: 400, marginLeft: 8 }}>bid / ask, live</span></summary>
      {busy && <Loading label="Loading the chain" />}
      {chain && (
        <div className="stack" style={{ gap: 8, marginTop: 12 }}>
          <div className="spread small"><span>{s.underlying} {chain.spot != null ? (s.exchange === "CDS" ? money(chain.spot, "INR", 4) : price(chain.spot, "INR")) : ""} · expiry {chain.expiry && expiryName(chain.expiry)} · lot {chain.lot}</span>
            <button className="btn quiet sm" onClick={load}>Refresh</button></div>
          <div className="table-wrap" style={{ margin: 0 }}>
            <table className="chain-t">
              <thead><tr><th>Call bid / ask</th><th>Call OI</th><th>Strike</th><th>Put bid / ask</th><th>Put OI</th></tr></thead>
              <tbody>{chain.rows.map((r) => (
                <tr key={r.strike} className={r.strike === chain.atm ? "atm" : ""}>
                  <td className="mono">{q(r.ce)}</td><td className="mono muted">{r.ce?.oi?.toLocaleString("en-IN") ?? "–"}</td>
                  <td className="mono"><b>{r.strike}</b></td>
                  <td className="mono">{q(r.pe)}</td><td className="mono muted">{r.pe?.oi?.toLocaleString("en-IN") ?? "–"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
    </details>
  );
}

export function OptionsPage() {
  const { fail, notify, refreshMe, notebooks } = useApp();
  const nav = useNavigate();
  const [s, setS] = useState<OptionStrategy>(loadDraft);
  const [unds, setUnds] = useState<Underlying[] | null>(null);
  const [offline, setOffline] = useState<string | null>(null);
  const [preview, setPreview] = useState<OptPreview | null>(null);
  const [pricing, setPricing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [rows, setRows] = useState<LiveRow[] | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const live = (rows ?? []).filter((x) => x.status === "running" || x.status === "paused");     // the stopped ones fold away

  useEffect(() => {
    api<Underlying[]>("/options/underlyings").then(setUnds).catch((e: ApiError) => { setUnds([]); setOffline(e.message); });
    api<LiveRow[]>("/live/sessions").then((r) => setRows(r.filter((x) => x.instrument?.type === "OPTIONS"))).catch(() => setRows([]));
    try {
      const imp = sessionStorage.getItem(IMPORTED);
      if (imp) {
        sessionStorage.removeItem(IMPORTED);
        const d = JSON.parse(imp) as { strategy: OptionStrategy; notes: string[] };
        setS({ ...blankOptions(), ...d.strategy }); setNotes(d.notes || []);
      }
    } catch { /* nothing imported */ }
  }, []);
  useEffect(() => { try { localStorage.setItem(DRAFT, JSON.stringify(s)); } catch { /* storage off */ } }, [s]);

  const patch = useCallback((p: Partial<OptionStrategy>) => { setS((x) => ({ ...x, ...p })); setPreview(null); }, []);
  const und = unds?.find((u) => u.exchange === s.exchange && u.name === s.underlying);
  const popular = unds?.length ? unds.filter((u) => u.popular) : POPULAR_FALLBACK.map((u) => ({ ...u, venue: u.exchange === "BFO" ? "BSE" : u.exchange === "MCX" ? "MCX" : u.exchange === "CDS" ? "NSE currency" : "NSE" }));
  const pickUnderlying = (exchange: OptionStrategy["exchange"], name: string) => {
    const t = s.exchange !== exchange ? sessionFor(exchange) : null;
    const st = STRUCTURES.find((x) => x.id === s.structure);
    patch({ exchange, underlying: name, expiry: "current", ...(t ? { timing: { ...s.timing, ...t } } : {}),
      name: `${name} ${st ? st.name.toLowerCase() : "options"}` });
  };
  const pickStructure = (id: string) => {
    const st = STRUCTURES.find((x) => x.id === id)!;
    patch({ structure: id, offsetUnit: st.unit, legs: st.legs.map((l) => ({ ...l })), name: `${s.underlying} ${st.name.toLowerCase()}` });
  };
  const hasShort = s.legs.some((l) => l.side === "sell");

  const price_ = async () => {
    setPricing(true);
    try { setPreview(await api<OptPreview>("/options/preview", { method: "POST", body: { strategy: s } })); }
    catch (e) { fail(e); } finally { setPricing(false); }
  };
  const start = async () => {
    const when = s.signal ? `whenever "${s.signal.name}" signals a trade (from ${s.timing.entry})` : `at ${s.timing.entry}`;
    if (!confirm(`Start paper trading "${s.name}"? It enters ${when} on market days with fake money, on live ${s.underlying} option prices.`)) return;
    setStarting(true);
    try {
      const snap = await api<{ id: string }>("/options/sessions", { method: "POST", body: { strategy: s } });
      track("paper trading started", { kind: "options" });
      refreshMe();
      nav(`/options/s/${snap.id}`);
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "live_limit" || err.code === "trial_ended") notify(err.message, { label: "See plans", run: () => nav("/plans") });
      else fail(e);
    } finally { setStarting(false); }
  };
  const exportIt = () => {
    const blob = new Blob([JSON.stringify({ stratlab: "options", version: 1, strategy: s }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `${s.name.replace(/[^\w-]+/g, "-").toLowerCase()}.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  const [sigBusy, setSigBusy] = useState(false);
  const [ruleMode, setRuleMode] = useState(() => !!s.signal || new URLSearchParams(location.search).get("enter") === "rules");
  const pickRules = async (id: string) => {
    if (!id) return;
    setSigBusy(true);
    try {
      const nb = await api<Notebook>(`/notebooks/${id}`);
      if (!["5m", "15m", "1h"].includes(nb.strategy.tf)) {
        notify(`"${nb.name}" uses daily candles. Option trades close every day, so pick rules on 5-minute, 15-minute or hourly candles.`);
        return;
      }
      const signal = { rules: nb.strategy, notebook: nb.id, name: nb.name, short: s.signal?.short ?? (nb.strategy.side === "long" ? "none" : "mirror") as "none" | "mirror" };
      // a directional signal usually buys an option; swap out the default short straddle
      const bc = STRUCTURES.find((x) => x.id === "buy_call")!;
      if (s.structure === "short_straddle") {
        patch({ signal, structure: "buy_call", offsetUnit: bc.unit, legs: bc.legs.map((l) => ({ ...l })), name: `${s.underlying} options on ${nb.name}` });
        notify("Switched the structure to Buy a call. Change it above if you want something else.");
      } else patch({ signal, name: `${s.underlying} options on ${nb.name}` });
    } catch (e) { fail(e); } finally { setSigBusy(false); }
  };
  useEffect(() => {   // "Trade it with options" on a verdict hands over its notebook
    const id = new URLSearchParams(location.search).get("nb");
    if (id && id !== s.signal?.notebook) pickRules(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const sigTf = s.signal ? ({ "5m": "5-minute", "15m": "15-minute", "1h": "hourly" } as Record<string, string>)[s.signal.rules.tf] : "";
  const r = s.risk, t = s.timing, rc = s.recenter, z = s.sizing, c = s.costs;
  const setRisk = (p: Partial<OptionStrategy["risk"]>) => patch({ risk: { ...r, ...p } });
  const setTiming = (p: Partial<OptionStrategy["timing"]>) => patch({ timing: { ...t, ...p } });
  const setRc = (p: Partial<OptionStrategy["recenter"]>) => patch({ recenter: { ...rc, ...p } });
  const setZ = (p: Partial<OptionStrategy["sizing"]>) => patch({ sizing: { ...z, ...p } });
  const setC = (p: Partial<OptionStrategy["costs"]>) => patch({ costs: { ...c, ...p } });
  const lossOpts: [OptionStrategy["risk"]["stopType"], string][] = [["none", "Off"], ["amount", "₹"], ["credit_pct", "% of premium"]];
  const MAIN = ["short_straddle", "short_strangle", "iron_fly", "iron_condor"];
  const inMain = MAIN.includes(s.structure);
  const legsText = s.legs.map((l) => `${l.side === "sell" ? "Sell" : "Buy"} ${l.lots > 1 ? l.lots + "× " : ""}${l.offset === 0 ? "ATM" : `${Math.abs(l.offset)}${s.offsetUnit === "points" ? " pts" : ""} ${l.offset > 0 ? "OTM" : "ITM"}`} ${l.opt}`).join(" · ");

  return (
    <div className="stack opt-page" style={{ gap: 20 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h1 className="page-title">Options<Info>{HELP.options}</Info></h1>
        <p className="muted" style={{ maxWidth: "62ch" }}>Paper trade option structures on live NSE, BSE, MCX and NSE currency (USDINR) prices. Fills use the real bid and ask.</p>
        <p className="small muted row wrap" style={{ gap: 6 }}><span className="pill soon-pill">Backtesting coming soon</span><Info>{HELP.optBacktest}</Info></p>
      </div>

      {offline && <div className="banner">{offline}</div>}
      {notes.length > 0 && (
        <div className="banner stack" style={{ gap: 6 }}>
          <b>Imported. Check these before you start:</b>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setNotes([])}>Got it</button>
        </div>
      )}

      <section className="card stack opt-form" style={{ gap: 18 }} aria-label="Set up the structure">
        <Block title="1. What to trade">
        <div className="opt-row">
          <span className="opt-label">Trade</span>
          <div className="row wrap" style={{ gap: 8 }}>
            {popular.slice(0, 5).map((u) => {
              const on = u.exchange === s.exchange && u.name === s.underlying;
              return <button key={u.exchange + u.name} className={`chip${on ? " on" : ""}`} aria-pressed={on} onClick={() => pickUnderlying(u.exchange, u.name)}>{u.name}</button>;
            })}
            {!!unds?.length && (
              <span className={`chip-select${popular.slice(0, 5).some((u) => u.exchange === s.exchange && u.name === s.underlying) ? "" : " on"}`}><select aria-label="Other underlyings" value={popular.slice(0, 5).some((u) => u.exchange === s.exchange && u.name === s.underlying) ? "" : `${s.exchange}:${s.underlying}`}
                onChange={(e) => { if (e.target.value) { const [ex, n] = e.target.value.split(":"); pickUnderlying(ex as OptionStrategy["exchange"], n); } }}>
                <option value="">More…</option>
                {unds.map((u) => <option key={u.exchange + u.name} value={`${u.exchange}:${u.name}`}>{u.name} ({u.venue})</option>)}
              </select></span>
            )}
          </div>
        </div>

        <div className="opt-row">
          <span className="opt-label">Expiry</span>
          <div className="row wrap" style={{ gap: 8 }}>
            <Seg label="Expiry" value={["current", "next", "month"].includes(s.expiry) ? s.expiry : "date"}
              options={[["current", "Nearest"], ["next", "Next"], ["month", "Monthly"]]} onChange={(v) => patch({ expiry: v })} />
            {und && <span className="small muted">lot {und.lot}</span>}
          </div>
        </div>
        </Block>

        <Block title="2. Structure">

        <div className="opt-row">
          <span className="opt-label">Structure</span>
          <div className="row wrap" style={{ gap: 8 }}>
            {MAIN.map((id) => { const x = STRUCTURES.find((y) => y.id === id)!; return (
              <button key={id} title={x.hint} className={`chip${s.structure === id ? " on" : ""}`} aria-pressed={s.structure === id} onClick={() => pickStructure(id)}>{x.name}</button>); })}
            <span className={`chip-select${inMain ? "" : " on"}`}><select aria-label="Other structures" value={inMain ? "" : s.structure}
              onChange={(e) => { const v = e.target.value; if (v === "custom") patch({ structure: "custom" }); else if (v) pickStructure(v); }}>
              <option value="">More…</option>
              {STRUCTURES.filter((x) => !MAIN.includes(x.id)).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              <option value="custom">Custom legs</option>
            </select></span>
          </div>
        </div>

        <details className="legs-box" open={s.structure === "custom" || undefined}>
          <summary><span className="small">{legsText}</span><span className="small link-ish">Edit legs</span></summary>
          <div className="stack" style={{ gap: 10, marginTop: 12 }}>
            <div className="row" style={{ gap: 8, alignItems: "center" }}>
              <span className="small muted">Distance in</span>
              <Seg label="Distance unit" value={s.offsetUnit} options={[["strikes", "Strikes"], ["points", "Points"]]}
                onChange={(v) => patch({ offsetUnit: v, legs: s.legs.map((l) => ({ ...l, offset: v === "points" ? l.offset * (preview?.step ?? 50) : Math.round(l.offset / (preview?.step ?? 50)) })) })} />
            </div>
            <LegsEditor s={s} preview={preview} set={(legs) => patch({ legs, structure: "custom" })} />
          </div>
        </details>
        </Block>

        <Block title="3. When and how much risk">

        <div className="opt-row">
          <span className="opt-label">Enter</span>
          <div className="stack" style={{ gap: 10 }}>
            <Seg label="When to enter" value={ruleMode ? "rules" : "time"}
              options={[["time", "At a set time"], ["rules", "When a notebook's rules say so"]]}
              onChange={(v) => { setRuleMode(v === "rules"); if (v === "time") patch({ signal: null }); }} />
            {ruleMode && <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
              <span className="chip-select">
                <select aria-label="Notebook with the rules" value={s.signal?.notebook ?? ""} disabled={sigBusy} onChange={(e) => pickRules(e.target.value)}>
                  <option value="">{s.signal ? s.signal.name : "Use a notebook's rules…"}</option>
                  {(notebooks ?? []).filter((n) => n.id !== s.signal?.notebook).map((n) => (
                    <option key={n.id} value={n.id}>{n.name}{n.tf ? ` (${n.tf})` : ""}</option>))}
                </select>
              </span>
              {s.signal && <Seg label="Short signals" value={s.signal.short}
                options={[["mirror", "Short signals: swap calls and puts"], ["none", "Long signals only"]]}
                onChange={(v) => patch({ signal: { ...s.signal!, short: v } })} />}
            </div>}
            {ruleMode && !s.signal && <p className="small muted">Pick a notebook with rules on 5-minute, 15-minute or hourly candles, for example a 7 EMA crossover on NIFTY 50.</p>}
            {s.signal && <p className="small muted" style={{ maxWidth: "70ch" }}>
              The rules of <b>{s.signal.name}</b> run on {s.underlying}'s own {sigTf} candles. When they go long, this enters the legs above
              {s.signal.short === "mirror" ? "; when they go short, it enters the same legs with calls and puts swapped" : ""}. When they exit, the options are closed.
              Your stop, target and square-off below still apply, and one signal is traded once.
            </p>}
          </div>
        </div>

        <div className="opt-grid">
          <Time label={s.signal ? "Earliest entry" : "Enter at"} value={t.entry} onChange={(v) => setTiming({ entry: v })} />
          <Time label="Last entry" value={t.lastEntry} onChange={(v) => setTiming({ lastEntry: v })} />
          <Time label="Square off" value={t.squareoff} onChange={(v) => setTiming({ squareoff: v })} />
          <Num label="Units" value={z.lots} min={1} max={1000} width={120} onChange={(v) => setZ({ lots: Math.round(v) })} />
        </div>

        <div className="opt-grid two">
          <div className="stack" style={{ gap: 6 }}>
            <span className="opt-lbl">Stop loss<Info>{HELP.optRisk}</Info></span>
            <div className="row wrap" style={{ gap: 8 }}>
              <Seg label="Stop type" value={r.stopType} options={lossOpts} onChange={(v) => setRisk({ stopType: v })} />
              {r.stopType !== "none" && <input className="input" style={{ width: 110 }} type="number" aria-label="Stop value" value={r.stop} onChange={(e) => setRisk({ stop: +e.target.value || 0 })} />}
            </div>
          </div>
          <div className="stack" style={{ gap: 6 }}>
            <span className="opt-lbl">Target</span>
            <div className="row wrap" style={{ gap: 8 }}>
              <Seg label="Target type" value={r.tgtType} options={lossOpts} onChange={(v) => setRisk({ tgtType: v })} />
              {r.tgtType !== "none" && <input className="input" style={{ width: 110 }} type="number" aria-label="Target value" value={r.tgt} onChange={(e) => setRisk({ tgt: +e.target.value || 0 })} />}
            </div>
          </div>
        </div>
        </Block>

        <More id="options" what="entries a day, daily loss cap, trailing, re-centring, sizing, costs"
          on={[t.maxEntries > 1, t.cooldown > 0, r.dailyLoss > 0, hasShort && r.legStopPct > 0, r.trailAfter > 0, hasShort && rc.enabled, z.mode === "margin", c.brokerage > 0 && c.brokerage !== 20].filter(Boolean).length}>
          <div className="stack" style={{ gap: 18 }}>
            <div className="opt-grid">
              <Num label="Entries a day" value={t.maxEntries} min={1} max={20} width={120} onChange={(v) => setTiming({ maxEntries: Math.round(v) })} />
              <Num label="Wait after a trade" value={t.cooldown} max={600} suffix="min" width={140} onChange={(v) => setTiming({ cooldown: Math.round(v) })} />
              <Num label="Daily loss cap (₹)" value={r.dailyLoss} step={1000} width={150} onChange={(v) => setRisk({ dailyLoss: v })} />
              {hasShort && <Num label="Sold-leg stop +%" value={r.legStopPct} step={5} width={140} help={HELP.optLegStop} onChange={(v) => setRisk({ legStopPct: v })} />}
            </div>
            <div className="opt-grid">
              <Num label="Trail once up (₹)" value={r.trailAfter} step={500} width={150} help={HELP.optTrail} onChange={(v) => setRisk({ trailAfter: v })} />
              <Num label="…giving back (₹)" value={r.trailBy} step={500} width={150} onChange={(v) => setRisk({ trailBy: v })} />
            </div>
            {hasShort && (
              <div className="stack" style={{ gap: 10 }}>
                <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={rc.enabled} onChange={(e) => setRc({ enabled: e.target.checked })} />
                  Re-centre when the market moves<Info>{HELP.optRecenter}</Info></label>
                {rc.enabled && (
                  <div className="opt-grid">
                    <Num label="Check every" value={rc.every} min={5} max={240} suffix="min" width={130} onChange={(v) => setRc({ every: Math.round(v) })} />
                    <Num label="After moving" value={rc.threshold} min={0.5} max={50} step={0.5} suffix="strikes" width={150} onChange={(v) => setRc({ threshold: v })} />
                    <div className="stack" style={{ gap: 6 }}><span className="opt-lbl">Roll</span>
                      <Seg label="What rolls" value={rc.roll} options={[["shorts", "Sold legs"], ["all", "All legs"]]} onChange={(v) => setRc({ roll: v })} /></div>
                  </div>
                )}
              </div>
            )}
            <div className="opt-grid">
              <div className="stack" style={{ gap: 6 }}><span className="opt-lbl">Size<Info>{HELP.optSize}</Info></span>
                <Seg label="Sizing" value={z.mode} options={[["lots", "Fixed units"], ["margin", "Fit to margin"]]} onChange={(v) => setZ({ mode: v })} /></div>
              <Num label="Paper capital (₹)" value={z.capital} min={1000} step={50000} width={160} onChange={(v) => setZ({ capital: v })} />
            </div>
            <div className="opt-grid">
              <Num label="Brokerage / order (₹)" value={c.brokerage} max={1000} width={150} onChange={(v) => setC({ brokerage: v })} />
              <Num label="Extra slippage" value={c.slippageTicks} max={100} suffix="ticks" width={140} onChange={(v) => setC({ slippageTicks: Math.round(v) })} />
              <Num label="Freeze limit" value={c.freeze} max={100000} width={130} help={HELP.optFreeze} onChange={(v) => setC({ freeze: Math.round(v) })} />
            </div>
            {!c.freeze && und?.freeze ? <span className="hint">Freeze limit 0 uses the exchange's: {und.freeze.toLocaleString("en-IN")} for {und.name}.</span> : null}
          </div>
        </More>
      </section>

      <section className="card stack" style={{ gap: 14 }} aria-label="Price and start">
        <div className="row wrap" style={{ gap: 10, alignItems: "flex-end" }}>
          <label className="field" style={{ flex: "1 1 220px" }}>Name<input value={s.name} maxLength={80} onChange={(e) => patch({ name: e.target.value })} /></label>
          <button className="btn quiet" disabled={pricing || !!offline} onClick={price_}>{pricing ? "Pricing…" : preview ? "Price again" : "Price it now"}</button>
          <button className="btn blue" disabled={starting || !!offline || (ruleMode && !s.signal)} onClick={start}>{starting ? "Starting…" : "Start paper trading"}</button>
        </div>
        {preview && (
          <div className="stack" style={{ gap: 10 }}>
            <span className="small muted">{s.underlying} {price(preview.spot, "INR")} · ATM {preview.atm} · expiry {expiryName(preview.expiry)} · lot {preview.lot} · {preview.units} unit{preview.units === 1 ? "" : "s"}{s.sizing.mode === "margin" && preview.margin_one ? ` (${inr(preview.margin_one)} margin each)` : ""}</span>
            {preview.units === 0 ? <p className="neg small">Not enough capital for one unit at today's margin.</p> : <Payoff p={preview} />}
          </div>
        )}
      </section>

      <div className="opt-extras one">
        <Chain key={`${s.exchange}${s.underlying}${s.expiry}`} s={s} />
      </div>
      <div className="row" style={{ gap: 8 }}>
        <button className="btn quiet sm" onClick={exportIt}>Export</button>
        <button className="btn quiet sm" onClick={() => { if (confirm("Start over with a fresh short straddle?")) { setS(blankOptions()); setPreview(null); } }}>Start over</button>
        <Link to="/import" className="btn quiet sm">Import a structure</Link>
      </div>

      <PositioningCard />

      {rows && rows.length > 0 && (
        <section className="stack" style={{ gap: 10 }} aria-labelledby="o-sess">
          <h2 id="o-sess" className="h3">Your options sessions</h2>
          {live.length ? <OptSessionCards rows={live} /> : <p className="small muted">None running.</p>}
          <Earlier label="Stopped sessions" count={rows.length - live.length}>
            <OptSessionCards rows={rows.filter((x) => !live.includes(x))} />
          </Earlier>
        </section>
      )}
    </div>
  );
}

/** Options sessions as a row of cards, each opening its page. */
function OptSessionCards({ rows }: { rows: LiveRow[] }) {
  return (
    <div className="row" style={{ gap: 10, overflowX: "auto", paddingBottom: 4 }}>
      {rows.map((x) => (
        <Link key={x.id} to={`/options/s/${x.id}`} className="card" style={{ flex: "none", minWidth: 200, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 4 }}>
          <b>{x.name}</b>
          <span className="small muted">{new Date(x.started_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}</span>
          <span className={`badge ${x.status}`} style={{ alignSelf: "flex-start" }}>{x.status}</span>
        </Link>
      ))}
    </div>
  );
}
