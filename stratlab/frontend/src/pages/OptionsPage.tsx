import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { axisInrFor, money, price, fmtDate, IST, tzLabel } from "../lib/format";
import { HELP } from "../lib/help";
import { blankOptions, IMPORTED, isAutoName, legName, legRule, levelText, optMoney, payoff, PICKS, POPULAR_FALLBACK, sessionFor, staleQuoteLine, STRUCTURES } from "../lib/options";
import type { LiveRow, Notebook, OptChain, OptCharges, OptionStrategy, OptLeg, OptPreview, StrikePick, Underlying } from "../lib/types";
import { PayoffChart, type PayoffCurve, type PayoffMarker } from "../components/Charts";
import { ModelInputs, ModelPanel, RollPreview, type ModelRow } from "../components/OptionModel";
import type { OptionGreeks } from "../lib/greeks";
import { More } from "../components/More";
import { Info } from "../components/ui";
import { track } from "../lib/analytics";
import { Earlier } from "../components/Earlier";
import { FoBadges } from "../components/FoBadges";
import { foSymbol } from "../lib/foChanges";
import {
  Badge, Card, CardHead, CheckField, ChipBar, ConfirmDialog, DataTable, Disclosure, Field, FieldGroup, FormActions, FormGrid, Notice, PageHeader, Seg, Select, Skeleton,
  TimeInput,
  Stat, StatRow, TilePicker, type Column, type TileGroup,
} from "../components/kit";
import "./trade/trade.css";
import "./trade/options.css";
import "./trade/paper.css";
import { usePlansToast } from "../components/PlanInterest";

/* /options: build an option structure (straddle, strangle, condor, any legs), see its numbers at the live bid and ask, and
 * paper trade it. Built from the kit (components/kit): a picker for what to trade, settings written as sentences, a
 * summary of the most it can make and lose, and the advanced settings folded away. */

const DRAFT = "stratlab.options.draft.v1";

const loadDraft = (): OptionStrategy => {
  try {
    const raw = localStorage.getItem(DRAFT);
    if (raw) return { ...blankOptions(), ...JSON.parse(raw) };
  } catch { /* storage off */ }
  return blankOptions();
};

const inr = (v: number | null | undefined, dp = 0) => money(v, "INR", dp);
const expiryName = (e: string) => fmtDate(e, { weekday: true, year: false });

/** A number box that keeps what is typed until it is a number in range. */
function NumField({ label, value, onChange, min = 0, max, step = 1, unit, info }: {
  label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; unit?: string; info?: ReactNode;
}) {
  const [txt, setTxt] = useState(String(value));
  useEffect(() => setTxt(String(value)), [value]);
  return (
    <Field label={label} info={info} unit={unit} type="number" inputMode="decimal" value={txt} min={min} max={max} step={step}
      onChange={(e) => { setTxt(e.target.value); const n = parseFloat(e.target.value); if (!isNaN(n) && n >= min && (max == null || n <= max)) onChange(n); }} />
  );
}

/** A small number box inside a sentence. */
function InNum({ label, value, onChange, min = 0, max, step = 1 }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number }) {
  const [txt, setTxt] = useState(String(value));
  useEffect(() => setTxt(String(value)), [value]);
  return (
    <input className="k-input k-in num" aria-label={label} type="number" inputMode="decimal" value={txt} min={min} max={max} step={step}
      onChange={(e) => { setTxt(e.target.value); const n = parseFloat(e.target.value); if (!isNaN(n) && n >= min && (max == null || n <= max)) onChange(n); }} />
  );
}

/** Every exchange the builder trades on (NSE, BSE, MCX, NSE currency) keeps India's time: its times are IST. */
const ZONE = tzLabel(IST);

/** A time box inside a sentence: 24-hour, in the exchange's time, with the zone beside it. */
function InTime({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return <TimeInput small label={label} zone={ZONE} value={value} onChange={onChange} />;
}

/** How a leg's strike is picked, and the number(s) the rule needs. */
function PickCell({ l, i, unit, upd, rules }: { l: OptLeg; i: number; unit: "points" | "strikes"; upd: (i: number, p: Partial<OptLeg>) => void; rules: boolean }) {
  const pick = l.pick ?? "offset";
  const n = (k: keyof OptLeg, d: number) => (l[k] as number | undefined) ?? d;
  return (
    <div className="k-leg-pick">
      <Select small label={`Leg ${i + 1} strike by`} value={pick} onChange={(v) => upd(i, { pick: v as StrikePick })}
        options={PICKS.map(([v, name]) => ({ value: v, label: `${name}${v !== "offset" && !rules ? " (Pro)" : ""}`, disabled: v !== "offset" && !rules && v !== pick }))} />
      {pick === "offset" && <InNum label={`Leg ${i + 1} distance from the money`} value={l.offset} min={-5000} max={5000} step={unit === "points" ? 50 : 1} onChange={(v) => upd(i, { offset: v })} />}
      {pick === "offset" && <span className="k-note">{unit}</span>}
      {(pick === "delta" || pick === "delta_range") && <InNum label={`Leg ${i + 1} delta`} value={n("delta", 0.2)} min={0.01} max={0.99} step={0.05} onChange={(v) => upd(i, { delta: v })} />}
      {pick === "delta_range" && <><span className="k-note">to</span><InNum label={`Leg ${i + 1} delta, high end`} value={n("deltaTo", 0.3)} min={0.01} max={0.99} step={0.05} onChange={(v) => upd(i, { deltaTo: v })} /></>}
      {pick === "premium" && <>
        <Select small label={`Leg ${i + 1} premium match`} value={l.premiumOp ?? "near"} onChange={(v) => upd(i, { premiumOp: v as OptLeg["premiumOp"] })}
          options={[{ value: "near", label: "nearest" }, { value: "gte", label: "at or above" }, { value: "lte", label: "at or below" }]} />
        <span className="k-note">₹</span><InNum label={`Leg ${i + 1} premium`} value={n("premium", 50)} min={0.05} max={1000000} step={5} onChange={(v) => upd(i, { premium: v })} /></>}
      {pick === "straddle_pct" && <><InNum label={`Leg ${i + 1} share of the straddle`} value={n("pct", 20)} min={1} max={200} step={5} onChange={(v) => upd(i, { pct: v })} /><span className="k-note">% of ATM straddle</span></>}
    </div>
  );
}

type LegRow = { l: OptLeg; i: number };

function LegsEditor({ s, set, preview, rules }: { s: OptionStrategy; set: (legs: OptLeg[]) => void; preview: OptPreview | null; rules: boolean }) {
  const upd = (i: number, p: Partial<OptLeg>) => set(s.legs.map((l, j) => (j === i ? { ...l, ...p } : l)));
  const unit = s.offsetUnit === "points" ? "points" : "strikes";
  const picks = preview ? preview.legs.map((p, i) => [i, p.pick] as const).filter(([, w]) => !!w) : [];
  const usesRules = s.legs.some((l) => (l.pick ?? "offset") !== "offset");
  const rows: LegRow[] = s.legs.map((l, i) => ({ l, i }));
  const cols: Column<LegRow>[] = [
    { key: "side", header: "Buy or sell", cell: ({ l, i }) => <Select small label={`Leg ${i + 1} buy or sell`} value={l.side} onChange={(v) => upd(i, { side: v as OptLeg["side"] })} options={[{ value: "sell", label: "Sell" }, { value: "buy", label: "Buy" }]} /> },
    { key: "opt", header: "Type", cell: ({ l, i }) => <Select small label={`Leg ${i + 1} call or put`} value={l.opt} onChange={(v) => upd(i, { opt: v as OptLeg["opt"] })} options={[{ value: "CE", label: "Call (CE)" }, { value: "PE", label: "Put (PE)" }]} /> },
    { key: "by", header: "Strike by", info: HELP.optStrikeRule, cell: ({ l, i }) => <PickCell l={l} i={i} unit={unit} upd={upd} rules={rules} /> },
    { key: "lots", header: "Lots", cell: ({ l, i }) => <input className="k-input sm k-in num" aria-label={`Leg ${i + 1} lots`} type="number" min={1} max={50} value={l.lots}
      onChange={(e) => { const n = parseInt(e.target.value, 10); if (n >= 1 && n <= 50) upd(i, { lots: n }); }} /> },
    ...(preview ? [
      { key: "strike", header: "Strike", numeric: true, cell: ({ i }: LegRow) => { const p = preview.legs[i]; return p?.strike ?? (p?.pick ? "none fits" : "not listed"); } },
      { key: "fill", header: "Fill now", numeric: true, cell: ({ i }: LegRow) => { const p = preview.legs[i]; return p?.fill != null ? `${price(p.fill, "INR", preview.tick && preview.tick < 0.01 ? 4 : undefined)}${p.from_last ? " (last trade)" : ""}` : "no quote"; } },
    ] : []),
    { key: "x", header: <span className="sr-only">Remove</span>, action: true, cell: ({ i }) => (s.legs.length > 1 ? <button type="button" className="chip-x" aria-label={`Remove leg ${i + 1}`} onClick={() => set(s.legs.filter((_, j) => j !== i))}>×</button> : null) },
  ];
  return (
    <div className="k-stack">
      <DataTable label="Legs" columns={cols} rows={rows} rowKey={({ i }) => String(i)} />
      {picks.length > 0 && (
        <ul className="k-list muted" data-testid="leg-picks">
          {picks.map(([i, w]) => <li key={i}>Leg {i + 1}: {w}</li>)}
        </ul>
      )}
      {usesRules && <p className="k-note">
        A rule picks its strike from the live quotes when the session enters (and at each re-centre), so the strike can differ from the one shown now.
        Deltas are the pricing model's estimates.{!rules && " Picking strikes by delta or premium is on the Pro plan; Price it now shows what a rule would pick."}
      </p>}
      {s.legs.length < 8 && <button type="button" className="btn quiet sm k-btn-end"
        onClick={() => set([...s.legs, { side: "buy", opt: "CE", offset: s.offsetUnit === "points" ? 500 : 6, lots: 1 }])}>Add a leg</button>}
    </div>
  );
}

const points = (xs: number[], tick?: number | null) => xs.map((b) => levelText(b, tick)).join(" and ");
const share = (v: number | null) => (v == null ? "–" : v > 0 && v < 0.005 ? "under 0.01%" : `${v.toFixed(2)}%`);
const asOf = (d: string) => fmtDate(d);

/** What opening and closing the structure once costs, line by line, and what that does to its numbers. */
function Charges({ c }: { c: OptCharges }) {
  type Line = { key: string; label: string; amount: number };
  const cols: Column<Line>[] = [
    { key: "label", header: "Charge", rowHeader: true, cell: (r) => r.label },
    { key: "amount", header: "Amount", numeric: true, cell: (r) => inr(r.amount, 2) },
  ];
  // a sold structure whose most it can make is the premium it takes in: one figure, not the same one twice
  const sameAsPremium = c.credit && c.max_profit != null && Math.abs(c.max_profit - c.premium) < 0.5;
  return (
    <div className="k-stack" data-testid="opt-charges">
      <StatRow label="Charges">
        <Stat label="Charges to open and close" value={inr(c.total, 2)} />
        {sameAsPremium
          ? <Stat label="Share of the premium (also the most it can make)" value={share(c.pct_of_premium)} />
          : <>
            <Stat label="Share of the premium" value={share(c.pct_of_premium)} />
            <Stat label="Share of the most it can make" value={c.max_profit == null ? "No ceiling" : share(c.pct_of_max_profit)} />
          </>}
        {c.credit
          ? <Stat label="Premium kept after charges" value={optMoney(c.premium_after)} />
          : <Stat label="Most it can make after charges" value={c.max_profit_after == null ? "Unlimited" : optMoney(c.max_profit_after)} />}
      </StatRow>
      <Disclosure className="opt-charge-lines" summary="Charges line by line">
        <DataTable label="Charges line by line" columns={cols} rows={c.items} rowKey={(r) => r.key} foot={{ label: "Total", amount: inr(c.total, 2) }} />
        <p className="k-note">
          {c.orders} orders at {inr(c.brokerage_per_order)} brokerage each{c.freeze ? `; orders above ${c.freeze.toLocaleString("en-IN")} units go in slices, each one an order` : ""}.
          Every leg opened and closed once at the fill shown. Rates as of {asOf(c.rates_as_of)}.
        </p>
      </Disclosure>
    </div>
  );
}

/** The priced structure: a summary card (most it can make and lose, breakevens, margin), then the payoff and the charges. */
function Payoff({ p, s }: { p: OptPreview; s: OptionStrategy }) {
  const { me } = useApp();
  const f = useMemo(() => payoff(p), [p]);
  const c = p.charges;
  const whatif = !!me?.plan_info?.features?.options_whatif;
  const [rollOpen, setRollOpen] = useState(false);
  const g = p.greeks;
  // each priced leg with its model inputs, for the Greeks, the today curve and the what-if
  const rows: ModelRow[] = useMemo(() => {
    if (!g) return [];
    let m = 0;
    return p.legs.flatMap((l, i) => {
      if (l.strike == null || l.fill == null) return [];
      const gi = g.legs[i];
      const ml = gi?.iv ? g.model_legs[m++] ?? null : null;
      const qty = l.lots * p.units * p.lot;
      return [{ label: legName(l.side, l.strike, l.opt), held: { side: l.side, opt: l.opt, strike: l.strike, qty, fill: l.fill }, g: gi, m: ml }];
    });
  }, [p, g]);
  const before = c ? c.breakevens : f.breakevens;
  // exact bounds at expiry (the price can fall to zero; only calls can run on above the top strike), from the server
  // when it has priced the charges, else the same sums here
  const best = c ? c.max_profit : f.maxProfit, worst = c ? c.max_loss : f.maxLoss;
  // the chart spans 10% either side of today's price; say where a bound lies when it's outside that
  const lo = f.xs[0], hi = f.xs[f.xs.length - 1];
  const outside = (v: number | null, x: number) => v != null && (x < lo || x > hi) ? Math.round(x).toLocaleString("en-IN") : null;
  const bestOut = outside(best, f.bestAt), worstOut = outside(worst, f.worstAt);
  const curves: PayoffCurve[] = [{ id: "expiry", label: "At expiry", values: f.ys },
    ...(c ? [{ id: "after", label: "After charges", values: f.ys.map((y) => y - c.total), dash: "4 4", width: 1.4 }] : [])];
  const markers: PayoffMarker[] = [{ x: p.spot, label: `Spot ${levelText(p.spot, p.tick)}`, kind: "spot" as const },
    // each breakeven's label sits on the side away from the spot, so both read beside the spot's
    ...before.map((x) => ({ x, label: `Breakeven ${levelText(x, p.tick)}`, kind: "breakeven" as const, side: x < p.spot ? "left" as const : "right" as const })),
    // after charges they sit a few points inside: lines only, the numbers are in the note under the chart
    ...(c ? c.breakevens_after.map((x) => ({ x, label: "", kind: "other" as const })) : [])];
  const stale = staleQuoteLine(p.from_last ?? p.legs.filter((l) => l.from_last).length, p.legs.length);
  return (
    <>
      {stale && <Notice tone="warn" role="status" className="opt-stale">{stale}</Notice>}
      {p.impossible && <Notice tone="warn" role="status" className="opt-impossible">{p.impossible}</Notice>}
      <Card label="Summary">
        <CardHead title="Summary" info="Worked out at expiry from the fills shown, with the legs held to the end. Paper trades close at your square-off time, usually well before expiry, so they rarely reach these extremes." />
        <StatRow label="Priced structure">
          <Stat label={f.credit >= 0 ? "Premium collected" : "Premium paid"} value={optMoney(Math.abs(f.credit))} />
          <Stat testId="opt-max-profit" label="Most it can make" value={best == null ? "Unlimited" : optMoney(best)} tone={best == null ? undefined : "up"}
            note={c && c.max_profit_after != null ? `${optMoney(c.max_profit_after)} after charges` : undefined} />
          <Stat testId="opt-max-loss" label="Most it can lose" value={worst == null ? "Unlimited" : optMoney(worst)} tone={worst == null ? undefined : "down"}
            note={c && c.max_loss_after != null ? `${optMoney(c.max_loss_after)} after charges` : undefined} />
          <Stat testId="opt-be-stat" label="Breakevens" value={before.length ? points(before, p.tick) : "None"}
            note={c ? (c.breakevens_after.length ? `${points(c.breakevens_after, p.tick)} after charges` : "none after charges") : undefined} />
          <Stat testId="opt-margin" label="Margin needed" value={p.margin != null ? inr(p.margin) : "Not available"}
            note={p.margin != null ? "the broker's figure for these legs, asked when priced" : "the broker didn't give one; price it again"} />
        </StatRow>
      </Card>
      <Card label="Payoff">
        <CardHead title="Profit or loss across prices" />
        {p.model && rows.length > 0 ? (
          <ModelPanel model={p.model} rows={rows} xs={f.xs} expiry={curves} markers={markers} charges={c ? c.total : null}
            chargesLabel="the round trip's charges" whatif={whatif} plan="Pro" name={s.underlying} testId="opt-model"
            ariaLabel="Profit or loss at expiry and today across prices" />
        ) : (
          <PayoffChart ariaLabel="Profit or loss at expiry across prices" height={220} xs={f.xs} testId="payoff-chart"
            format={(v) => inr(v)} axisFormat={axisInrFor(Math.max(0, ...curves.flatMap((x) => x.values.map((v) => Math.abs(v ?? 0)))))} xFormat={(x) => levelText(x, p.tick)}
            curves={curves} markers={markers} />
        )}
        <p className="k-note" data-testid="opt-breakevens">
          At expiry, if held to the end{c ? "; the dashed line is after charges" : ", before costs"}.{" "}
          {before.length > 0 && <>Breaks even at {points(before, p.tick)}{c ? " before charges" : ""}. </>}
          {c && (c.breakevens_after.length > 0 ? <>After charges: {points(c.breakevens_after, p.tick)}. </> : <>After charges it doesn't break even at any price. </>)}
          {bestOut != null && <>The most it can make is reached at {bestOut}, outside the chart. </>}
          {worstOut != null && <>The most it can lose is reached at {worstOut}, outside the chart. </>}
          Paper trades close at your square-off time, usually well before expiry, so they rarely reach these extremes.
          {p.model && rows.length > 0 && " The today line is the pricing model's value of the position now, at each option's current IV; it is an estimate, not a quote."}
        </p>
        {c && <Charges c={c} />}
        {whatif && p.model && rows.length > 0 && (
          <Disclosure className="opt-charge-lines" testId="roll-fold" summary="Roll a leg: preview" onToggle={setRollOpen}>
            {rollOpen && <RollPreview legs={rows.map(({ label, held }) => ({ label, held }))} exchange={s.exchange} underlying={s.underlying}
              expiry={p.expiry} strikes={p.strikes} expiries={p.expiries ?? [p.expiry]} step={p.step} brokerage={s.costs.brokerage} freeze={p.freeze} />}
          </Disclosure>
        )}
      </Card>
    </>
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
  const [view, setView] = useState<"quotes" | "greeks">("quotes");
  type CRow = OptChain["rows"][number];
  const q = (x: { bid: number | null; ask: number | null; ltp: number | null } | null) => x ? `${x.bid ?? "–"} / ${x.ask ?? "–"}` : "–";
  const greeks = view === "greeks" && !!chain?.model;
  const g = (side: "ce_g" | "pe_g", f: (g: OptionGreeks) => string, key: string, header: string): Column<CRow> => ({
    key: `${side}${key}`, header, numeric: true, cell: (r) => { const x = r[side]; return x?.iv ? f(x) : "–"; } });
  const n = (v: number, dp: number) => (v < 0 ? "−" : "") + Math.abs(v).toFixed(dp);
  const greekCols: Column<CRow>[] = [
    g("ce_g", (x) => `${(x.iv! * 100).toFixed(1)}%${x.iv_from === "atm" ? "*" : ""}`, "iv", "Call IV"), g("ce_g", (x) => n(x.delta!, 2), "d", "Call delta"),
    g("ce_g", (x) => String(+x.gamma!.toPrecision(2)), "g", "Call gamma"), g("ce_g", (x) => n(x.theta!, 2), "t", "Call theta"), g("ce_g", (x) => n(x.vega!, 2), "v", "Call vega"),
    { key: "k", header: "Strike", numeric: true, cell: (r) => <b>{r.strike}</b> },
    g("pe_g", (x) => `${(x.iv! * 100).toFixed(1)}%${x.iv_from === "atm" ? "*" : ""}`, "iv", "Put IV"), g("pe_g", (x) => n(x.delta!, 2), "d", "Put delta"),
    g("pe_g", (x) => String(+x.gamma!.toPrecision(2)), "g", "Put gamma"), g("pe_g", (x) => n(x.theta!, 2), "t", "Put theta"), g("pe_g", (x) => n(x.vega!, 2), "v", "Put vega"),
  ];
  const quoteCols: Column<CRow>[] = [
    { key: "cq", header: "Call bid / ask", numeric: true, cell: (r) => q(r.ce) }, { key: "co", header: "Call OI", numeric: true, cell: (r) => r.ce?.oi?.toLocaleString("en-IN") ?? "–" },
    { key: "k", header: "Strike", numeric: true, cell: (r) => <b>{r.strike}</b> },
    { key: "pq", header: "Put bid / ask", numeric: true, cell: (r) => q(r.pe) }, { key: "po", header: "Put OI", numeric: true, cell: (r) => r.pe?.oi?.toLocaleString("en-IN") ?? "–" },
  ];
  const atm = (r: CRow): Record<string, string> => (r.strike === chain?.atm ? { "data-atm": "1", className: "atm" } : {});
  return (
    <Card label="Option chain" testId="chain-card">
      <Disclosure className="chain" summary={<><b>Option chain</b><span className="k-note">bid / ask, IV and Greeks, live</span></>} onToggle={(o) => { if (o && !chain) void load(); }}>
        {busy && <Skeleton label="Loading the chain" />}
        {chain && (
          <div className="k-stack">
            <div className="k-spread k-small">
              <span>{s.underlying} {chain.spot != null ? (s.exchange === "CDS" ? money(chain.spot, "INR", 4) : price(chain.spot, "INR")) : ""} · expiry {chain.expiry && expiryName(chain.expiry)} · lot {chain.lot}</span>
              <span className="k-row">
                {chain.model && <Seg label="Chain columns" value={view} options={[{ value: "quotes", label: "Bid / ask" }, { value: "greeks", label: "IV and Greeks" }]} onChange={(v) => setView(v as "quotes" | "greeks")} />}
                <button type="button" className="btn quiet sm" onClick={load}>Refresh</button>
              </span>
            </div>
            <div data-testid={greeks ? "chain-greeks" : "chain-quotes"}>
              <DataTable label={greeks ? "Option chain, IV and Greeks" : "Option chain, bid and ask"} columns={greeks ? greekCols : quoteCols} rows={chain.rows} rowKey={(r) => String(r.strike)} rowAttrs={atm} />
            </div>
            {greeks && chain.model && <ModelInputs m={chain.model} extra="Per option; an asterisk marks an IV taken from the at-the-money strike." />}
          </div>
        )}
      </Disclosure>
    </Card>
  );
}

/** The structures as tiles, in the groups people look for them in. */
const TILE_GROUPS: { title: string; ids: string[] }[] = [
  { title: "Sell premium", ids: ["short_straddle", "short_strangle", "iron_fly", "iron_condor"] },
  { title: "Buy a move, or a spread", ids: ["long_straddle", "bull_call_spread", "bear_put_spread", "buy_call", "buy_put", "sell_call", "sell_put"] },
];

export function OptionsPage() {
  const { fail, notify, refreshMe, notebooks, me } = useApp();
  const feats = me?.plan_info?.features;
  const rulesOk = feats ? !!feats.strike_rules : true, vixOk = feats ? !!feats.vix_filter : true, canStart = feats ? feats.options !== false : true;
  const nav = useNavigate();
  const plansToast = usePlansToast();
  const [s, setS] = useState<OptionStrategy>(loadDraft);
  const [unds, setUnds] = useState<Underlying[] | null>(null);
  const [offline, setOffline] = useState<string | null>(null);
  const [preview, setPreview] = useState<OptPreview | null>(null);
  const [pricing, setPricing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [confirmStart, setConfirmStart] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
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
  const popular = (unds?.length ? unds.filter((u) => u.popular) : POPULAR_FALLBACK.map((u) => ({ ...u, venue: u.exchange === "BFO" ? "BSE" : u.exchange === "MCX" ? "MCX" : u.exchange === "CDS" ? "NSE currency" : "NSE" }))).slice(0, 5);
  const onPopular = popular.some((u) => u.exchange === s.exchange && u.name === s.underlying);
  // a name the person typed stays; one the builder made up follows the strategy, underlying and rules
  const named = (next: string) => (isAutoName(s.name, s.underlying) ? { name: next } : {});
  const pickUnderlying = (exchange: OptionStrategy["exchange"], name: string) => {
    const t = s.exchange !== exchange ? sessionFor(exchange) : null;
    const st = STRUCTURES.find((x) => x.id === s.structure);
    patch({ exchange, underlying: name, expiry: "current", ...(t ? { timing: { ...s.timing, ...t } } : {}),
      ...named(`${name} ${st ? st.name.toLowerCase() : "options"}`) });
  };
  const pickStructure = (id: string) => {
    if (id === "custom") { patch({ structure: "custom" }); return; }
    const st = STRUCTURES.find((x) => x.id === id)!;
    patch({ structure: id, offsetUnit: st.unit, legs: st.legs.map((l) => ({ ...l })), ...named(`${s.underlying} ${st.name.toLowerCase()}`) });
  };
  const hasShort = s.legs.some((l) => l.side === "sell");

  const price_ = async () => {
    setPricing(true);
    try { setPreview(await api<OptPreview>("/options/preview", { method: "POST", body: { strategy: s } })); }
    catch (e) { fail(e); } finally { setPricing(false); }
  };
  const startWhen = s.signal ? `whenever "${s.signal.name}" signals a trade (from ${s.timing.entry})` : `at ${s.timing.entry}`;
  const start = async () => {
    setConfirmStart(false);
    setStarting(true);
    try {
      const snap = await api<{ id: string }>("/options/sessions", { method: "POST", body: { strategy: s } });
      track("paper trading started", { kind: "options" });
      refreshMe();
      nav(`/options/s/${snap.id}`);
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "live_limit" || err.code === "trial_ended") plansToast(err.message);
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
        patch({ signal, structure: "buy_call", offsetUnit: bc.unit, legs: bc.legs.map((l) => ({ ...l })), ...named(`${s.underlying} options on ${nb.name}`) });
        notify("Switched the structure to Buy a call. Change it above if you want something else.");
      } else patch({ signal, ...named(`${s.underlying} options on ${nb.name}`) });
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
  const lossOpts = [{ value: "none", label: "Off" }, { value: "amount", label: "₹" }, { value: "credit_pct", label: "% of premium" }];
  const legsText = s.legs.map((l) => `${l.side === "sell" ? "Sell" : "Buy"} ${l.lots > 1 ? l.lots + "× " : ""}${legRule(l, s.offsetUnit)} ${l.opt}`).join(" · ");
  const vf = s.vix;
  const expiryNames: Record<string, string> = { current: "the nearest expiry", next: "the next expiry", month: "the monthly expiry" };
  const exp = und?.expiries?.[s.expiry === "next" ? 1 : 0];
  const stopWord = r.stopType === "none" ? "" : `, stopping out if the loss reaches ${r.stopType === "amount" ? inr(r.stop) : `${r.stop}% of the premium`}`;
  const tgtWord = r.tgtType === "none" ? "" : ` and taking profit at ${r.tgtType === "amount" ? inr(r.tgt) : `${r.tgt}% of the premium`}`;
  const words = `${s.name}: ${legsText}, on ${expiryNames[s.expiry] ?? `the ${s.expiry} expiry`}. ${s.signal ? `Enters whenever "${s.signal.name}" signals a trade, from ${t.entry} to ${t.lastEntry} ${ZONE}` : `Enters at ${t.entry} ${ZONE}, no later than ${t.lastEntry} ${ZONE}`}, and exits by ${t.squareoff} ${ZONE}${stopWord}${tgtWord}.`;
  const tileGroups: TileGroup[] = [
    ...TILE_GROUPS.map((g) => ({ title: g.title, tiles: g.ids.map((id) => { const x = STRUCTURES.find((y) => y.id === id)!; return { value: id, title: x.name, sub: x.hint }; }) })),
    { title: "Your own", tiles: [{ value: "custom", title: "Custom legs", sub: "Choose each leg yourself" }] },
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Practise" title="Options builder" info={HELP.options} infoLabel="About options"
        lede="Paper trade option structures on live NSE, BSE, MCX and NSE currency (USDINR) prices. Fills use the real bid and ask; a contract with none is priced from its last trade, and the page says so."
        actions={<><Badge tone="plain" dot={false}>Backtesting coming soon</Badge><Info label="About options backtesting">{HELP.optBacktest}</Info></>} />

      {offline && <Notice tone="warn">{offline}</Notice>}
      {notes.length > 0 && (
        <Notice actions={<button type="button" className="btn quiet sm" onClick={() => setNotes([])}>Got it</button>}>
          <b>Imported. Check these before you start:</b>
          <ul className="k-list">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </Notice>
      )}

      <Card label="Set up the structure">
        <CardHead title="What to trade" actions={<>
          <button type="button" className="btn quiet sm" onClick={exportIt}>Export</button>
          <button type="button" className="btn quiet sm" onClick={() => setConfirmReset(true)}>Start over</button>
          <Link to="/import" className="btn quiet sm">Import a structure</Link>
        </>} />
        <div className="k-struct">
          <FieldGroup label="Underlying" wide>
            <div className="k-row">
              <ChipBar wrap label="Underlying" value={onPopular ? `${s.exchange}:${s.underlying}` : ""} onChange={(v) => { const [ex, n] = v.split(":"); pickUnderlying(ex as OptionStrategy["exchange"], n); }}
                options={popular.map((u) => ({ value: `${u.exchange}:${u.name}`, label: u.name }))} />
              {!!unds?.length && (
                <Select small label="Other underlyings" value={onPopular ? "" : `${s.exchange}:${s.underlying}`}
                  onChange={(v) => { if (v) { const [ex, n] = v.split(":"); pickUnderlying(ex as OptionStrategy["exchange"], n); } }}
                  options={[{ value: "", label: `Other underlyings (${Math.max(0, unds.length - popular.length)})…` }, ...unds.filter((u) => !popular.some((p) => p.exchange === u.exchange && p.name === u.name)).map((u) => ({ value: `${u.exchange}:${u.name}`, label: `${u.name} (${u.venue})` }))]} />
              )}
            </div>
          </FieldGroup>
          <FieldGroup label="Expiry" info="Nearest is the first expiry still to come; Next is the one after; Monthly is the last expiry of the month.">
            <div className="k-expiry">
              <Seg label="Expiry" value={["current", "next", "month"].includes(s.expiry) ? s.expiry : "date"}
                options={[{ value: "current", label: "Nearest" }, { value: "next", label: "Next" }, { value: "month", label: "Monthly" }]} onChange={(v) => patch({ expiry: v })} />
              {/* the expiry priced, once there is a price: the one the pill names is the one the numbers use (R11C-007) */}
              {und && <span className="k-note" data-testid="opt-expiry-note">{preview ? `${expiryName(preview.expiry)} · ` : exp && s.expiry !== "month" ? `${expiryName(exp)} · ` : ""}lot {und.lot}</span>}
            </div>
          </FieldGroup>
          <FieldGroup label="Strategy" wide>
            <TilePicker label="Strategy" groups={tileGroups} value={s.structure} onChange={pickStructure} />
          </FieldGroup>
          <Disclosure className="legs-box" open={s.structure === "custom" || undefined}
            summary={<><span className="k-small">{legsText}</span><span className="k-small link-ish">Edit legs</span></>}>
            <div className="k-stack">
              <div className="k-row">
                <span className="k-small k-muted">Distance in</span>
                <Seg label="Distance unit" value={s.offsetUnit} options={[{ value: "strikes", label: "Strikes" }, { value: "points", label: "Points" }]}
                  onChange={(v) => patch({ offsetUnit: v as "strikes" | "points", legs: s.legs.map((l) => ({ ...l, offset: v === "points" ? l.offset * (preview?.step ?? 50) : Math.round(l.offset / (preview?.step ?? 50)) })) })} />
              </div>
              <LegsEditor s={s} preview={preview} rules={rulesOk} set={(legs) => patch({ legs, structure: "custom" })} />
            </div>
          </Disclosure>
        </div>
      </Card>

      <Card label="When it trades">
        <CardHead title="When it trades" info={HELP.optRisk} infoLabel="About stops and targets" />
        <p className="k-plain" data-testid="opt-words">{words}</p>
        <div className="k-stack">
          <p className="k-sentence">
            <b>Enter</b>
            <Seg label="When to enter" value={ruleMode ? "rules" : "time"}
              options={[{ value: "time", label: "At a set time" }, { value: "rules", label: "When a notebook's rules say so" }]}
              onChange={(v) => { setRuleMode(v === "rules"); if (v === "time") patch({ signal: null }); }} />
          </p>
          {ruleMode ? (
            <>
              <p className="k-sentence">
                <b>Enter when</b>{" "}
                <Select small label="Notebook with the rules" value={s.signal?.notebook ?? ""} disabled={sigBusy} onChange={pickRules}
                  options={[{ value: "", label: s.signal ? s.signal.name : "Use a notebook's rules…" },
                    ...(notebooks ?? []).filter((n) => n.id !== s.signal?.notebook).map((n) => ({ value: n.id, label: `${n.name}${n.tf ? ` (${n.tf})` : ""}` }))]} />{" "}
                signals a trade, from <InTime label="Earliest entry" value={t.entry} onChange={(v) => setTiming({ entry: v })} /> to <InTime label="Last entry" value={t.lastEntry} onChange={(v) => setTiming({ lastEntry: v })} />.
              </p>
              {s.signal && <Seg label="Short signals" value={s.signal.short}
                options={[{ value: "mirror", label: "Short signals: swap calls and puts" }, { value: "none", label: "Long signals only" }]}
                onChange={(v) => patch({ signal: { ...s.signal!, short: v as "mirror" | "none" } })} />}
              {!s.signal && <p className="k-note">Pick a notebook with rules on 5-minute, 15-minute or hourly candles, for example a 7 EMA crossover on NIFTY 50.</p>}
              {s.signal && <p className="k-note">
                The rules of <b>{s.signal.name}</b> run on {s.underlying}'s own {sigTf} candles. When they go long, this enters the legs above
                {s.signal.short === "mirror" ? "; when they go short, it enters the same legs with calls and puts swapped" : ""}. When they exit, the options are closed.
                Your stop, target and square-off below still apply, and one signal is traded once.
              </p>}
            </>
          ) : (
            <p className="k-sentence"><b>Enter at</b> <InTime label="Enter at" value={t.entry} onChange={(v) => setTiming({ entry: v })} /> on market days, no later than <InTime label="Last entry" value={t.lastEntry} onChange={(v) => setTiming({ lastEntry: v })} />.</p>
          )}
          <p className="k-sentence"><b>Exit at</b> <InTime label="Square off" value={t.squareoff} onChange={(v) => setTiming({ squareoff: v })} /> at the latest.</p>
          <div className="k-form two" role="group" aria-label="Stop and target">
            <div className="k-field">
              <div className="k-label-row"><span className="k-lbl">Exit sooner at a loss of</span></div>
              <div className="k-row">
                <Seg label="Stop type" value={r.stopType} options={lossOpts} onChange={(v) => setRisk({ stopType: v as OptionStrategy["risk"]["stopType"] })} />
                {r.stopType !== "none" && <input className="k-input k-in num" type="number" aria-label="Stop value" value={r.stop} onChange={(e) => setRisk({ stop: +e.target.value || 0 })} />}
              </div>
            </div>
            <div className="k-field">
              <div className="k-label-row"><span className="k-lbl">Or at a gain of</span></div>
              <div className="k-row">
                <Seg label="Target type" value={r.tgtType} options={lossOpts} onChange={(v) => setRisk({ tgtType: v as OptionStrategy["risk"]["tgtType"] })} />
                {r.tgtType !== "none" && <input className="k-input k-in num" type="number" aria-label="Target value" value={r.tgt} onChange={(e) => setRisk({ tgt: +e.target.value || 0 })} />}
              </div>
            </div>
          </div>
          <p className="k-sentence"><b>Trade</b> <InNum label="Units" value={z.lots} min={1} max={1000} onChange={(v) => setZ({ lots: Math.round(v) })} /> unit{z.lots === 1 ? "" : "s"} of the structure.{und ? ` A lot is ${und.lot} ${s.underlying}.` : ""}</p>
          <div className="k-sentence" data-testid="vix-filter">
            <CheckField label={<>Enter only while India VIX is between{!vixOk && " (Basic)"}</>} checked={!!vf} disabled={!vixOk && !vf} onChange={(on) => patch({ vix: on ? { min: 11, max: 18 } : null })} />
            {vf && <> <InNum label="Lowest (0 = none)" value={vf.min} max={100} step={0.5} onChange={(v) => patch({ vix: { ...vf, min: v } })} /> and
              <InNum label="Highest (0 = none)" value={vf.max} max={100} step={0.5} onChange={(v) => patch({ vix: { ...vf, max: v } })} />.</>}
            <Info>{HELP.optVix}</Info>
            {vf && !vf.min && !vf.max && <span className="k-note"> Set a lowest or a highest value, or turn the filter off.</span>}
            {vf && vf.min > 0 && vf.max > 0 && vf.min >= vf.max && <span className="k-note"> The lowest value has to be below the highest.</span>}
          </div>
        </div>
        <More id="options" what="entries a day, daily loss cap, trailing, re-centring, sizing, costs"
          on={[t.maxEntries > 1, t.cooldown > 0, r.dailyLoss > 0, hasShort && r.legStopPct > 0, r.trailAfter > 0, hasShort && rc.enabled, z.mode === "margin", c.brokerage > 0 && c.brokerage !== 20].filter(Boolean).length}>
          <FormGrid label="More settings">
            <NumField label="Entries a day" value={t.maxEntries} min={1} max={20} onChange={(v) => setTiming({ maxEntries: Math.round(v) })} />
            <NumField label="Wait after a trade" value={t.cooldown} max={600} unit="min" onChange={(v) => setTiming({ cooldown: Math.round(v) })} />
            <NumField label="Daily loss cap" value={r.dailyLoss} step={1000} unit="₹" onChange={(v) => setRisk({ dailyLoss: v })} />
            {hasShort && <NumField label="Sold-leg stop" value={r.legStopPct} step={5} unit="+ %" info={HELP.optLegStop} onChange={(v) => setRisk({ legStopPct: v })} />}
            <NumField label="Trail once up" value={r.trailAfter} step={500} unit="₹" info={HELP.optTrail} onChange={(v) => setRisk({ trailAfter: v })} />
            <NumField label="…giving back" value={r.trailBy} step={500} unit="₹" onChange={(v) => setRisk({ trailBy: v })} />
            <FieldGroup label="Size" info={HELP.optSize}>
              <Seg label="Sizing" value={z.mode} options={[{ value: "lots", label: "Fixed units" }, { value: "margin", label: "Fit to margin" }]} onChange={(v) => setZ({ mode: v as "lots" | "margin" })} />
            </FieldGroup>
            <NumField label="Paper capital" value={z.capital} min={1000} step={50000} unit="₹" onChange={(v) => setZ({ capital: v })} />
            <NumField label="Brokerage per order" value={c.brokerage} max={1000} unit="₹" onChange={(v) => setC({ brokerage: v })} />
            <NumField label="Extra slippage" value={c.slippageTicks} max={100} unit="ticks" onChange={(v) => setC({ slippageTicks: Math.round(v) })} />
            <NumField label="Freeze limit" value={c.freeze} max={100000} info={HELP.optFreeze} onChange={(v) => setC({ freeze: Math.round(v) })} />
            {hasShort && (
              <div className="k-field wide"><CheckField label={<>Re-centre when the market moves<Info>{HELP.optRecenter}</Info></>} checked={rc.enabled} onChange={(on) => setRc({ enabled: on })} /></div>
            )}
            {hasShort && rc.enabled && <>
              <NumField label="Check every" value={rc.every} min={5} max={240} unit="min" onChange={(v) => setRc({ every: Math.round(v) })} />
              <NumField label="After moving" value={rc.threshold} min={0.5} max={50} step={0.5} unit="strikes" onChange={(v) => setRc({ threshold: v })} />
              <FieldGroup label="Roll"><Seg label="What rolls" value={rc.roll} options={[{ value: "shorts", label: "Sold legs" }, { value: "all", label: "All legs" }]} onChange={(v) => setRc({ roll: v as "shorts" | "all" })} /></FieldGroup>
            </>}
          </FormGrid>
          {!c.freeze && und?.freeze ? <span className="k-note">Freeze limit 0 uses the exchange's: {und.freeze.toLocaleString("en-IN")} for {und.name}.</span> : null}
        </More>
      </Card>

      <Card label="Price and start">
        <CardHead title="Price it, then start" />
        <FormGrid label="Price and start" onSubmit={(e) => { e.preventDefault(); void price_(); }}>
          <Field label="Name" wide maxLength={80} value={s.name} onChange={(e) => patch({ name: e.target.value })} />
          <FormActions>
            <button type="submit" className="btn quiet" disabled={pricing || !!offline}>{pricing ? "Pricing…" : preview ? "Price again" : "Price it now"}</button>
            <button type="button" className="btn" disabled={starting || !!offline || !canStart || (ruleMode && !s.signal)} onClick={() => setConfirmStart(true)}>{starting ? "Starting…" : canStart ? "Start paper trading" : "🔒 Start paper trading (Basic)"}</button>
            {!canStart && <span className="k-note">Paper trading at set times is on the Basic plan. Price it now works on every plan.</span>}
            {canStart && ruleMode && !s.signal && <span className="k-note">Pick the notebook whose rules give the signal first.</span>}
          </FormActions>
        </FormGrid>
        {preview && (
          <p className="k-note">{s.underlying} {price(preview.spot, "INR")} · ATM {preview.atm} · expiry {expiryName(preview.expiry)} · lot {preview.lot} · {preview.units} unit{preview.units === 1 ? "" : "s"}{s.sizing.mode === "margin" && preview.margin_one ? ` (${inr(preview.margin_one)} margin each)` : ""}</p>
        )}
        {preview && preview.units === 0 && <Notice tone="warn">Not enough capital for one unit at today's margin.</Notice>}
      </Card>
      {preview && preview.units !== 0 && <Payoff p={preview} s={s} />}

      <Chain key={`${s.exchange}${s.underlying}${s.expiry}`} s={s} />

      <p className="k-link-line">Where the market is positioned, by participant and strike: <Link className="link" to="/trade/positioning">open Positioning</Link>.</p>

      {rows && rows.length > 0 && (
        <Card label="Your options sessions">
          <CardHead title="Your options sessions" />
          {live.length ? <OptSessionCards rows={live} /> : <p className="k-small k-muted">None running.</p>}
          <Earlier label="Stopped sessions" count={rows.length - live.length}>
            <OptSessionCards rows={rows.filter((x) => !live.includes(x))} />
          </Earlier>
        </Card>
      )}

      {confirmStart && (
        <ConfirmDialog title={`Start paper trading "${s.name}"?`} confirmLabel="Start paper trading" danger={false} onConfirm={start} onClose={() => setConfirmStart(false)}>
          It enters {startWhen} on market days with fake money, on live {s.underlying} option prices.{s.vix ? " Entries wait while India VIX is outside your band." : ""}
        </ConfirmDialog>
      )}
      {confirmReset && (
        <ConfirmDialog title="Start over?" confirmLabel="Start over" onConfirm={() => { setS(blankOptions()); setPreview(null); setConfirmReset(false); }} onClose={() => setConfirmReset(false)}>
          This replaces what you have set up with a fresh short straddle.
        </ConfirmDialog>
      )}
    </div>
  );
}

/** Options sessions as a row of cards, each opening its page. */
function OptSessionCards({ rows }: { rows: LiveRow[] }) {
  return (
    <div className="k-sessions">
      {rows.map((x) => (
        <Link key={x.id} to={`/options/s/${x.id}`} className="k-sess-link">
          <b>{x.name}</b>
          <span className="k-note">{fmtDate(x.started_at, { year: false })}</span>
          <FoBadges region="IN" symbol={foSymbol(x.instrument)} plain />
          <Badge tone={x.status === "running" ? "ok" : x.status === "paused" ? "warn" : "plain"}>{x.status}</Badge>
        </Link>
      ))}
    </div>
  );
}
