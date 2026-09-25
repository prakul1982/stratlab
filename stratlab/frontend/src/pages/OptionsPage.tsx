import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { money, price } from "../lib/format";
import { HELP } from "../lib/help";
import { blankOptions, payoff, POPULAR_FALLBACK, sessionFor, STRUCTURES } from "../lib/options";
import type { LiveRow, OptChain, OptionStrategy, OptLeg, OptPreview, Underlying } from "../lib/types";
import { LineChart } from "../components/Charts";
import { Info, Loading } from "../components/ui";

const DRAFT = "stratlab.options.draft.v1";
export const IMPORTED = "stratlab.options.import";

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
  return <label className="field" style={{ width: 130 }}>{label}<input type="time" value={value} onChange={(e) => e.target.value && onChange(e.target.value)} /></label>;
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

function Payoff({ p }: { p: OptPreview }) {
  const f = useMemo(() => payoff(p), [p]);
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="opt-stats two">
        <div><span className="eyebrow">{f.credit >= 0 ? "Premium collected" : "Premium paid"}</span><b className="mono">{inr(Math.abs(f.credit))}</b></div>
        <div><span className="eyebrow">Most it can make</span><b className="mono pos">{f.maxProfit == null ? "Unlimited" : inr(f.maxProfit)}</b></div>
        <div><span className="eyebrow">Most it can lose</span><b className="mono neg">{f.maxLoss == null ? "Unlimited" : inr(f.maxLoss)}</b></div>
        <div><span className="eyebrow">Margin needed</span><b className="mono">{p.margin != null ? inr(p.margin) : "Not available"}</b></div>
      </div>
      <LineChart ariaLabel="Profit or loss at expiry across prices" height={200} labels={f.xs.map((x) => `${p.legs.length ? "At " : ""}${Math.round(x).toLocaleString("en-IN")}`)}
        format={(v) => inr(v)} axisFormat={(v) => inr(v)} baseline={0}
        lines={[{ label: "At expiry", values: f.ys, color: "var(--blue)", width: 1.8 }]} />
      <p className="small muted">
        At expiry, before costs, if held to the end. {f.breakevens.length > 0 && <>Breaks even at {f.breakevens.map((b) => Math.round(b).toLocaleString("en-IN")).join(" and ")}. </>}
        Paper trades close at your square-off time, usually well before expiry, so they rarely reach these extremes.
      </p>
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
          <div className="spread small"><span>{s.underlying} {chain.spot != null ? price(chain.spot, "INR") : ""} · expiry {chain.expiry && expiryName(chain.expiry)} · lot {chain.lot}</span>
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

function ImportBox({ onLoaded }: { onLoaded: (s: OptionStrategy, notes: string[]) => void }) {
  const { refreshMe } = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const go = async () => {
    if (text.trim().length < 10) { setNote("Paste or choose your options strategy first."); return; }
    setBusy(true); setNote(null);
    try {
      const out = await api<{ strategy: OptionStrategy; notes: string[]; used_ai: boolean }>("/options/import", { method: "POST", body: { text } });
      if (out.used_ai) refreshMe();
      onLoaded(out.strategy, out.notes);
      setText("");
    } catch (e) { setNote((e as ApiError).message); } finally { setBusy(false); }
  };
  return (
    <details className="card">
      <summary className="h3">Import an options strategy</summary>
      <div className="stack" style={{ gap: 10, marginTop: 12 }}>
        <p className="small muted">A config file, code or a description of a straddle, strangle, condor or any multi-leg structure. A StratLab options export loads exactly; anything else is translated by the AI, and whatever it can't carry over is listed.</p>
        <textarea className="input" rows={5} value={text} placeholder="Paste it here, or choose a file" onChange={(e) => setText(e.target.value)} aria-label="Options strategy to import" />
        <div className="row wrap" style={{ gap: 8 }}>
          <input ref={file} type="file" accept=".json,.txt,.py,.md" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f) setText((await f.text()).slice(0, 60000)); }} />
          <button className="btn quiet sm" onClick={() => file.current?.click()}>Choose a file</button>
          <button className="btn sm" disabled={busy} onClick={go}>{busy ? "Reading…" : "Import"}</button>
        </div>
        {note && <p className="small neg">{note}</p>}
      </div>
    </details>
  );
}

export function OptionsPage() {
  const { fail, notify, refreshMe } = useApp();
  const nav = useNavigate();
  const [s, setS] = useState<OptionStrategy>(loadDraft);
  const [unds, setUnds] = useState<Underlying[] | null>(null);
  const [offline, setOffline] = useState<string | null>(null);
  const [preview, setPreview] = useState<OptPreview | null>(null);
  const [pricing, setPricing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [rows, setRows] = useState<LiveRow[] | null>(null);
  const [notes, setNotes] = useState<string[]>([]);

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
  const popular = unds?.length ? unds.filter((u) => u.popular) : POPULAR_FALLBACK.map((u) => ({ ...u, venue: u.exchange === "BFO" ? "BSE" : u.exchange === "MCX" ? "MCX" : "NSE" }));
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
    if (!confirm(`Start paper trading "${s.name}"? It enters at ${s.timing.entry} on market days with fake money, on live ${s.underlying} option prices.`)) return;
    setStarting(true);
    try {
      const snap = await api<{ id: string }>("/options/sessions", { method: "POST", body: { strategy: s } });
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

  const r = s.risk, t = s.timing, rc = s.recenter, z = s.sizing, c = s.costs;
  const setRisk = (p: Partial<OptionStrategy["risk"]>) => patch({ risk: { ...r, ...p } });
  const setTiming = (p: Partial<OptionStrategy["timing"]>) => patch({ timing: { ...t, ...p } });
  const setRc = (p: Partial<OptionStrategy["recenter"]>) => patch({ recenter: { ...rc, ...p } });
  const setZ = (p: Partial<OptionStrategy["sizing"]>) => patch({ sizing: { ...z, ...p } });
  const setC = (p: Partial<OptionStrategy["costs"]>) => patch({ costs: { ...c, ...p } });
  const lossWord = () => [["none", "None"], ["amount", "₹ amount"], ["credit_pct", hasShort ? "% of premium" : "% of cost"]] as [OptionStrategy["risk"]["stopType"], string][];

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">NSE · BSE · MCX</span>
        <h1 className="serif row" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", gap: 0 }}>Options<Info>{HELP.options}</Info></h1>
        <p className="muted" style={{ fontSize: 17, maxWidth: "72ch" }}>
          Build a straddle, strangle, iron fly, condor or any structure up to eight legs, and paper trade it on <b>live option prices</b>. Every fill is the real bid or ask at that moment. Nothing is modelled.
        </p>
      </div>

      <div className="row wrap" style={{ gap: 12 }}>
        <div className="mode-card on"><b>Live paper trading</b><span className="small muted">Runs every market day on live quotes</span></div>
        <div className="mode-card soon" aria-disabled="true"><b>Backtesting <span className="pill">Coming soon</span></b><span className="small muted">{HELP.optBacktest}</span></div>
      </div>

      {offline && <div className="banner">{offline} You can still build and save a structure; pricing and starting need live quotes.</div>}
      {notes.length > 0 && (
        <div className="banner stack" style={{ gap: 6 }}>
          <b>Imported. Check these before you start:</b>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setNotes([])}>Got it</button>
        </div>
      )}

      <div className="nb-grid" style={{ gap: 16 }}>
        <div className="stack" style={{ gap: 16, minWidth: 0 }}>
          <section className="card stack" style={{ gap: 14 }} aria-labelledby="o-und">
            <h2 id="o-und" className="h2">1. What to trade</h2>
            <div className="row wrap" style={{ gap: 8 }}>
              {popular.map((u) => (
                <button key={u.exchange + u.name} className={`btn sm ${u.exchange === s.exchange && u.name === s.underlying ? "" : "quiet"}`}
                  aria-pressed={u.exchange === s.exchange && u.name === s.underlying} onClick={() => pickUnderlying(u.exchange, u.name)}>
                  {u.name}<span className="small" style={{ opacity: 0.6, marginLeft: 6 }}>{u.venue}</span></button>
              ))}
            </div>
            {!!unds?.length && (
              <label className="field" style={{ maxWidth: 360 }}>Or any other underlying, including stock options
                <select value={`${s.exchange}:${s.underlying}`} onChange={(e) => { const [ex, n] = e.target.value.split(":"); pickUnderlying(ex as OptionStrategy["exchange"], n); }}>
                  {!und && <option value={`${s.exchange}:${s.underlying}`}>{s.underlying}</option>}
                  {unds.map((u) => <option key={u.exchange + u.name} value={`${u.exchange}:${u.name}`}>{u.name} ({u.venue})</option>)}
                </select></label>
            )}
            <div className="stack" style={{ gap: 6 }}>
              <span className="field">Expiry</span>
              <div className="row wrap" style={{ gap: 8 }}>
                <Seg label="Expiry" value={["current", "next", "month"].includes(s.expiry) ? s.expiry : "date"}
                  options={[["current", "Nearest"], ["next", "Next"], ["month", "Monthly"], ...(und?.expiries.length ? [["date", "Pick a date"] as [string, string]] : [])]}
                  onChange={(v) => patch({ expiry: v === "date" ? (und?.expiries[0] ?? "current") : v })} />
                {und && /\d/.test(s.expiry) && (
                  <select aria-label="Expiry date" value={s.expiry} onChange={(e) => patch({ expiry: e.target.value })}>
                    {und.expiries.map((e) => <option key={e} value={e}>{expiryName(e)}</option>)}
                  </select>)}
              </div>
              <span className="hint">Nearest rolls to the next expiry each day, so the session keeps trading week after week.{und ? ` Lot size ${und.lot}.` : ""}</span>
            </div>
          </section>

          <section className="card stack" style={{ gap: 14 }} aria-labelledby="o-str">
            <h2 id="o-str" className="h2">2. The structure</h2>
            <div className="row wrap" style={{ gap: 8 }}>
              {STRUCTURES.map((x) => <button key={x.id} title={x.hint} className={`btn sm ${s.structure === x.id ? "" : "quiet"}`} aria-pressed={s.structure === x.id}
                onClick={() => pickStructure(x.id)}>{x.name}</button>)}
              <button className={`btn sm ${s.structure === "custom" ? "" : "quiet"}`} aria-pressed={s.structure === "custom"} onClick={() => patch({ structure: "custom" })}>Custom</button>
            </div>
            <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
              <span className="small muted">Measure distance in</span>
              <Seg label="Distance unit" value={s.offsetUnit} options={[["strikes", "Strikes"], ["points", "Points"]]}
                onChange={(v) => patch({ offsetUnit: v, legs: s.legs.map((l) => ({ ...l, offset: v === "points" ? l.offset * (preview?.step ?? 50) : Math.round(l.offset / (preview?.step ?? 50)) })) })} />
            </div>
            <LegsEditor s={s} preview={preview} set={(legs) => patch({ legs, structure: "custom" })} />
          </section>

          <section className="card stack" style={{ gap: 14 }} aria-labelledby="o-time">
            <h2 id="o-time" className="h2 row" style={{ gap: 0 }}>3. When<Info>{HELP.optTiming}</Info></h2>
            <div className="row wrap" style={{ gap: 12 }}>
              <Time label="Enter at" value={t.entry} onChange={(v) => setTiming({ entry: v })} />
              <Time label="No new entries after" value={t.lastEntry} onChange={(v) => setTiming({ lastEntry: v })} />
              <Time label="Square off at" value={t.squareoff} onChange={(v) => setTiming({ squareoff: v })} />
              <Num label="Entries a day" value={t.maxEntries} min={1} max={20} onChange={(v) => setTiming({ maxEntries: Math.round(v) })} />
              <Num label="Wait after a trade" value={t.cooldown} max={600} suffix="min" width={130} onChange={(v) => setTiming({ cooldown: Math.round(v) })} />
            </div>
          </section>

          <section className="card stack" style={{ gap: 14 }} aria-labelledby="o-risk">
            <h2 id="o-risk" className="h2 row" style={{ gap: 0 }}>4. Exits and risk<Info>{HELP.optRisk}</Info></h2>
            <div className="row wrap" style={{ gap: 14, alignItems: "flex-end" }}>
              <div className="stack" style={{ gap: 6 }}><span className="field">Stop loss on the whole trade</span>
                <Seg label="Stop type" value={r.stopType} options={lossWord()} onChange={(v) => setRisk({ stopType: v })} /></div>
              {r.stopType !== "none" && <Num label={r.stopType === "amount" ? "Lose (₹)" : "Lose (%)"} value={r.stop} step={r.stopType === "amount" ? 500 : 5} width={130} onChange={(v) => setRisk({ stop: v })} />}
            </div>
            <div className="row wrap" style={{ gap: 14, alignItems: "flex-end" }}>
              <div className="stack" style={{ gap: 6 }}><span className="field">Target</span>
                <Seg label="Target type" value={r.tgtType} options={lossWord()} onChange={(v) => setRisk({ tgtType: v })} /></div>
              {r.tgtType !== "none" && <Num label={r.tgtType === "amount" ? "Make (₹)" : "Make (%)"} value={r.tgt} step={r.tgtType === "amount" ? 500 : 5} width={130} onChange={(v) => setRisk({ tgt: v })} />}
            </div>
            <div className="row wrap" style={{ gap: 12 }}>
              <Num label="Trail once up (₹)" value={r.trailAfter} step={500} width={150} help={HELP.optTrail} onChange={(v) => setRisk({ trailAfter: v })} />
              <Num label="…by giving back (₹)" value={r.trailBy} step={500} width={150} onChange={(v) => setRisk({ trailBy: v })} />
              {hasShort && <Num label="Stop a sold leg at +%" value={r.legStopPct} step={5} width={150} help={HELP.optLegStop} onChange={(v) => setRisk({ legStopPct: v })} />}
              <Num label="Daily loss cap (₹)" value={r.dailyLoss} step={1000} width={150} onChange={(v) => setRisk({ dailyLoss: v })} />
            </div>
            <span className="hint">0 turns a setting off.</span>
          </section>

          {hasShort && (
            <section className="card stack" style={{ gap: 14 }} aria-labelledby="o-rc">
              <div className="spread">
                <h2 id="o-rc" className="h2 row" style={{ gap: 0 }}>5. Re-centre<Info>{HELP.optRecenter}</Info></h2>
                <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={rc.enabled} onChange={(e) => setRc({ enabled: e.target.checked })} />Roll when the market moves</label>
              </div>
              {rc.enabled && (
                <div className="row wrap" style={{ gap: 12, alignItems: "flex-end" }}>
                  <Num label="Check every" value={rc.every} min={5} max={240} suffix="min" width={130} onChange={(v) => setRc({ every: Math.round(v) })} />
                  <Num label="Roll after moving" value={rc.threshold} min={0.5} max={50} step={0.5} suffix="strikes" width={160} onChange={(v) => setRc({ threshold: v })} />
                  <div className="stack" style={{ gap: 6 }}><span className="field">What moves</span>
                    <Seg label="What rolls" value={rc.roll} options={[["shorts", "Sold legs"], ["all", "Every leg"]]} onChange={(v) => setRc({ roll: v })} /></div>
                </div>
              )}
            </section>
          )}

          <section className="card stack" style={{ gap: 14 }} aria-labelledby="o-size">
            <h2 id="o-size" className="h2 row" style={{ gap: 0 }}>{hasShort ? 6 : 5}. Size and costs<Info>{HELP.optSize}</Info></h2>
            <div className="row wrap" style={{ gap: 12, alignItems: "flex-end" }}>
              <div className="stack" style={{ gap: 6 }}><span className="field">Size</span>
                <Seg label="Sizing" value={z.mode} options={[["lots", "Fixed lots"], ["margin", "As much as margin allows"]]} onChange={(v) => setZ({ mode: v })} /></div>
              {z.mode === "lots" && <Num label="Units of the structure" value={z.lots} min={1} max={1000} width={170} onChange={(v) => setZ({ lots: Math.round(v) })} />}
              <Num label="Paper capital (₹)" value={z.capital} min={1000} step={50000} width={170} onChange={(v) => setZ({ capital: v })} />
              {z.mode === "margin" && <Num label="Use up to" value={Math.round(z.safety * 100)} min={50} max={100} suffix="%" width={110} onChange={(v) => setZ({ safety: v / 100 })} />}
            </div>
            <div className="row wrap" style={{ gap: 12 }}>
              <Num label="Brokerage per order (₹)" value={c.brokerage} max={1000} width={170} onChange={(v) => setC({ brokerage: v })} />
              <Num label="Extra slippage" value={c.slippageTicks} max={100} suffix="ticks" width={140} onChange={(v) => setC({ slippageTicks: Math.round(v) })} />
              <Num label="Freeze limit (units)" value={c.freeze} max={100000} width={160} help={HELP.optFreeze} onChange={(v) => setC({ freeze: Math.round(v) })} />
            </div>
            <span className="hint">Freeze limit 0 uses the exchange's{und?.freeze ? ` (${und.freeze.toLocaleString("en-IN")} for ${und.name})` : ""}. Bigger orders are split, and each slice pays brokerage.</span>
          </section>
        </div>

        <div className="stack" style={{ gap: 16, minWidth: 0 }}>
          <section className="card stack sticky-col" style={{ gap: 14 }} aria-labelledby="o-go">
            <h2 id="o-go" className="h2">Price it and start</h2>
            <label className="field">Name<input value={s.name} maxLength={80} onChange={(e) => patch({ name: e.target.value })} /></label>
            <p className="small muted">
              {s.legs.map((l) => `${l.side === "sell" ? "Sell" : "Buy"} ${l.lots > 1 ? l.lots + " × " : ""}${l.offset === 0 ? "ATM" : `${Math.abs(l.offset)} ${s.offsetUnit === "points" ? "pts" : l.offset === 1 || l.offset === -1 ? "strike" : "strikes"} ${l.offset > 0 ? "OTM" : "ITM"}`} ${l.opt}`).join(", ")}
              {" "}on {s.underlying}, entering at {t.entry}, squaring off at {t.squareoff}.
            </p>
            <div className="row wrap" style={{ gap: 8 }}>
              <button className="btn quiet" disabled={pricing || !!offline} onClick={price_}>{pricing ? "Pricing…" : preview ? "Price again" : "Price it now"}</button>
              <button className="btn blue" disabled={starting || !!offline} onClick={start}>{starting ? "Starting…" : "Start paper trading"}</button>
            </div>
            {preview && (
              <div className="stack" style={{ gap: 10 }}>
                <span className="small">{s.underlying} {price(preview.spot, "INR")} · ATM {preview.atm} · expiry {expiryName(preview.expiry)} · lot {preview.lot}
                  {" "}· {preview.units} unit{preview.units === 1 ? "" : "s"}{s.sizing.mode === "margin" && preview.margin_one ? ` (${inr(preview.margin_one)} margin each)` : ""}</span>
                {preview.units === 0 ? <p className="neg small">Not enough capital for one unit at today's margin.</p> : <Payoff p={preview} />}
              </div>
            )}
            <div className="row wrap" style={{ gap: 8, borderTop: "1px dashed var(--line)", paddingTop: 12 }}>
              <button className="btn quiet sm" onClick={exportIt}>Export</button>
              <button className="btn quiet sm" onClick={() => { if (confirm("Start over with a fresh short straddle?")) { setS(blankOptions()); setPreview(null); } }}>Start over</button>
            </div>
          </section>
          <Chain key={`${s.exchange}${s.underlying}${s.expiry}`} s={s} />
          <ImportBox onLoaded={(x, n) => { setS({ ...blankOptions(), ...x }); setNotes(n); setPreview(null); }} />
        </div>
      </div>

      <section className="stack" style={{ gap: 10 }} aria-labelledby="o-sess">
        <h2 id="o-sess" className="h2">Your options sessions</h2>
        {rows === null ? <Loading /> : rows.length === 0 ? <p className="muted">Sessions you start show up here, and under Paper trading.</p> : (
          <div className="row" style={{ gap: 10, overflowX: "auto", paddingBottom: 4 }}>
            {rows.map((x) => (
              <Link key={x.id} to={`/options/s/${x.id}`} className="card" style={{ flex: "none", minWidth: 210, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 4 }}>
                <b>{x.name}</b>
                <span className="small muted">{x.instrument.symbol} · {new Date(x.started_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}</span>
                <span className={`badge ${x.status}`} style={{ alignSelf: "flex-start" }}>{x.status}</span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

