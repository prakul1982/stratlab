import { fmtDateTime, inr, IST } from "./format";
import { marketState } from "./marketHours";
import type { Market, OptLeg, OptionSnapshot, OptionStrategy, OptPreview, StrikePick } from "./types";

/** What the costs leave out, said on the builder and the session page. */
export const STT_NOTE = "STT on options exercised at expiry is not included.";

/** A premium, a profit or a loss in the options builder: whole rupees, the same everywhere (the premium collected, the
 * most it can make, and what is left after charges); paise only for a figure under ₹100, where they are the answer
 * (a spread that keeps -₹92.68 after charges). The charges themselves are small and keep their paise. */
export function optMoney(v: number | null | undefined): string {
  if (v == null) return inr(v);
  return inr(v, Math.abs(v) < 100 ? 2 : 0);
}

/** A price level (a breakeven, the spot) at the contract's own precision: whole points for an index, and a currency
 * option's quarter paise, "95.1625" (R11C-007: USDINR's breakevens of 95.16 and 97.10 read "95 and 97"). */
export function levelText(x: number, tick?: number | null): string {
  if (tick && tick < 0.01) {
    const v = Math.round(x / tick) * tick;
    return v.toLocaleString("en-IN", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  }
  return Math.round(x).toLocaleString("en-IN");
}

/** The expiry a pick names among an underlying's listed ones (the server's pick_expiry): Nearest, Next (the one after, else
 * the only one), Monthly (the last of the nearest month) or a date. undefined when it names none. */
export function pickedExpiry(expiries: string[] | undefined, choice: string): string | undefined {
  const ex = expiries ?? [];
  if (!ex.length) return undefined;
  if (choice === "current") return ex[0];
  if (choice === "next") return ex[1] ?? ex[0];
  if (choice === "month") return ex.filter((e) => e.slice(0, 7) === ex[0].slice(0, 7)).pop();
  return ex.includes(choice) ? choice : undefined;
}

/** Shares in one lot of the expiry picked: that expiry's own (a later series can have another lot), else the underlying's
 * (the nearest expiry's) when the nearest is the one picked. undefined when it can't be told. */
export function lotOf(u: { lot: number; expiries?: string[]; lots?: Record<string, number> } | undefined, choice: string): number | undefined {
  const e = u && pickedExpiry(u.expiries, choice);
  if (!u || !e) return undefined;
  return u.lots?.[e] ?? (e === u.expiries?.[0] ? u.lot : undefined);
}

/** The underlying's price in the line under the form, at the contract's precision, saying when it is the spot rate
 * (R13-002: "USDINR ₹96.14" from a future frozen at 96.135 for a month, with the dollar at 96.76). */
export function spotText(name: string, spot: number, tick?: number | null, from?: string | null): string {
  const px = tick && tick < 0.01 ? `₹${levelText(spot, tick)}` : `₹${spot.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return `${name} ${px}${from === "spot" ? " (the spot rate: the future has no live quote)" : ""}`;
}

/** The banner over a structure some of whose legs had no bid or ask to fill on (R11C-007: USDINR priced from last trades
 * hours old, under "Fills use the real bid and ask"). Empty when every leg had one. */
export function staleQuoteLine(fromLast: number, legs: number): string {
  if (!fromLast) return "";
  const lead = fromLast >= legs
    ? (legs === 1 ? "No live bid or ask: the leg is priced from its last traded price" : "No live bid or ask: every leg is priced from its last traded price")
    : `No live bid or ask for ${fromLast} of the ${legs} legs: ${fromLast === 1 ? "it is priced from its last traded price" : "they are priced from their last traded prices"}`;
  return `${lead}, which may be hours old. The numbers below can be far from what an order would fill at now.`;
}

/** The ways a leg's strike can be picked (strike rules beyond the distance are Pro). */
export const PICKS: [StrikePick, string][] = [["offset", "Distance from ATM"], ["delta", "Closest delta"], ["delta_range", "Delta range"],
  ["premium", "Premium"], ["straddle_pct", "% of ATM straddle"]];

/** A leg's strike rule in a few words: "ATM", "2 OTM", "Δ 0.20", "Δ 0.15–0.25", "₹50", "≥ ₹40", "20% of straddle". */
export function legRule(l: OptLeg, unit: "strikes" | "points"): string {
  switch (l.pick ?? "offset") {
    case "delta": return `Δ ${(l.delta ?? 0.2).toFixed(2)}`;
    case "delta_range": return `Δ ${(l.delta ?? 0.2).toFixed(2)}–${(l.deltaTo ?? 0.3).toFixed(2)}`;
    case "premium": return `${{ near: "≈", gte: "≥", lte: "≤" }[l.premiumOp ?? "near"]} ₹${l.premium ?? 50}`;
    case "straddle_pct": return `${l.pct ?? 20}% of straddle`;
    // the unit named either way (DB-006: "4 OTM" read the same in strikes and in points)
    default: return l.offset === 0 ? "ATM" : `${Math.abs(l.offset)}${unit === "points" ? " pts" : Math.abs(l.offset) === 1 ? " strike" : " strikes"} ${l.offset > 0 ? "OTM" : "ITM"}`;
  }
}

export const STRUCTURES: { id: string; name: string; hint: string; unit: "strikes" | "points"; legs: OptLeg[] }[] = [
  { id: "short_straddle", name: "Short straddle", hint: "Sell the at-the-money call and put", unit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 }] },
  { id: "short_strangle", name: "Short strangle", hint: "Sell a call and a put either side of the money", unit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 4, lots: 1 }, { side: "sell", opt: "PE", offset: 4, lots: 1 }] },
  { id: "iron_fly", name: "Iron fly", hint: "A short straddle with bought wings that cap the loss", unit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 },
      { side: "buy", opt: "CE", offset: 8, lots: 1 }, { side: "buy", opt: "PE", offset: 8, lots: 1 }] },
  { id: "iron_condor", name: "Iron condor", hint: "A short strangle with bought wings", unit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 4, lots: 1 }, { side: "sell", opt: "PE", offset: 4, lots: 1 },
      { side: "buy", opt: "CE", offset: 8, lots: 1 }, { side: "buy", opt: "PE", offset: 8, lots: 1 }] },
  { id: "long_straddle", name: "Long straddle", hint: "Buy the at-the-money call and put for a big move", unit: "strikes",
    legs: [{ side: "buy", opt: "CE", offset: 0, lots: 1 }, { side: "buy", opt: "PE", offset: 0, lots: 1 }] },
  { id: "bull_call_spread", name: "Bull call spread", hint: "Buy a call, sell a higher one", unit: "strikes",
    legs: [{ side: "buy", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "CE", offset: 4, lots: 1 }] },
  { id: "bear_put_spread", name: "Bear put spread", hint: "Buy a put, sell a lower one", unit: "strikes",
    legs: [{ side: "buy", opt: "PE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 4, lots: 1 }] },
  { id: "sell_call", name: "Sell a call", hint: "One sold call", unit: "strikes", legs: [{ side: "sell", opt: "CE", offset: 2, lots: 1 }] },
  { id: "sell_put", name: "Sell a put", hint: "One sold put", unit: "strikes", legs: [{ side: "sell", opt: "PE", offset: 2, lots: 1 }] },
  { id: "buy_call", name: "Buy a call", hint: "One bought call", unit: "strikes", legs: [{ side: "buy", opt: "CE", offset: 0, lots: 1 }] },
  { id: "buy_put", name: "Buy a put", hint: "One bought put", unit: "strikes", legs: [{ side: "buy", opt: "PE", offset: 0, lots: 1 }] },
];

/** The chips before the list of underlyings has come: the server's first five (options/data.py POPULAR), so MIDCPNIFTY is
 * one of them, as the backtesting note says it is recorded (DB-008: a fixed CRUDEOIL chip stood in its place). */
export const POPULAR_FALLBACK = [
  { exchange: "NFO", name: "NIFTY" }, { exchange: "NFO", name: "BANKNIFTY" }, { exchange: "BFO", name: "SENSEX" },
  { exchange: "NFO", name: "FINNIFTY" }, { exchange: "NFO", name: "MIDCPNIFTY" }, { exchange: "MCX", name: "CRUDEOIL" }, { exchange: "CDS", name: "USDINR" },
] as const;

/** Whether a structure's name is one the builder made up ("NIFTY iron condor", "NIFTY options on 7 EMA cross") rather
 * than one the person typed: only a made-up one follows a change of strategy, underlying or rules. */
export function isAutoName(name: string, underlying: string): boolean {
  const n = name.trim();
  if (!n) return true;
  const rest = n.startsWith(`${underlying} `) ? n.slice(underlying.length + 1) : null;
  if (rest == null) return false;
  return rest === "options" || rest.startsWith("options on ") || STRUCTURES.some((s) => s.name.toLowerCase() === rest);
}

export function blankOptions(): OptionStrategy {
  const s = STRUCTURES[0];
  return {
    name: "NIFTY short straddle", structure: s.id, exchange: "NFO", underlying: "NIFTY", expiry: "current", offsetUnit: s.unit,
    legs: s.legs.map((l) => ({ ...l })),
    timing: { entry: "09:30", lastEntry: "14:45", squareoff: "15:15", maxEntries: 1, cooldown: 0 },
    risk: { stopType: "credit_pct", stop: 30, tgtType: "none", tgt: 0, trailAfter: 0, trailBy: 0, legStopPct: 0, dailyLoss: 0 },
    recenter: { enabled: false, every: 30, threshold: 2, roll: "shorts" },
    sizing: { mode: "lots", lots: 1, capital: 500000, safety: 0.98 },
    costs: { brokerage: 20, slippageTicks: 0, freeze: 0 },
    notes: "",
  };
}

/** A saved draft over today's defaults, nested settings (risk, sizing, re-centring, timing, costs) field by field: a draft
 * saved before a field existed keeps the default for it rather than showing "undefined". Arrays (the legs) are taken
 * whole. */
export function mergeDraft<T>(base: T, saved: unknown): T {
  const plain = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
  if (!plain(base) || !plain(saved)) return (saved === undefined || saved === null ? base : saved) as T;
  const out: Record<string, unknown> = { ...base };
  for (const [k, v] of Object.entries(saved)) out[k] = plain(out[k]) ? mergeDraft(out[k], v) : v === undefined ? out[k] : v;
  return out as T;
}

/** What a flat session is waiting for, in one line: "No trades today. Next entry 09:30." `market` is the session's
 * exchange's market (its holidays): on an exchange holiday it says the market is closed for it. */
export function flatLine(snap: OptionSnapshot, closedToday: number, market: Market | null | undefined, now = new Date()): string {
  const s = snap.strategy, a = snap.account;
  const none = closedToday ? "Nothing open." : "No trades today.";
  if (snap.status !== "running") return none;
  if (a.halted || a.entries_today >= s.timing.maxEntries) return `${none} Done for today; next entry ${s.timing.entry} on the next market day.`;
  if (market && marketState(market, now).closedFor === "holiday") return `${none} The market is closed today for a holiday; next entry ${s.timing.entry} on the next market day.`;
  if (s.signal) return `${none} Enters when ${s.signal.name} signals, from ${s.timing.entry}.`;
  const hm = now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: IST });
  const wd = now.toLocaleDateString("en-GB", { weekday: "short", timeZone: IST });
  if (wd === "Sat" || wd === "Sun" || hm > s.timing.lastEntry) return `${none} Next entry ${s.timing.entry} on the next market day.`;
  // the gap the rules keep between trades, still running after a trade closed (R7T-013)
  const gap = gapLine(a, s.timing.cooldown, s.timing.lastEntry, s.timing.entry, now);
  if (gap) return `${none} ${gap}`;
  return hm < s.timing.entry ? `${none} Next entry ${s.timing.entry}.` : `${none} Entries open until ${s.timing.lastEntry}.`;
}

/** MCX trades into the evening and currency options until 17:00; everything else follows equity hours. */
export const sessionFor = (exchange: string) =>
  exchange === "MCX" ? { entry: "09:15", lastEntry: "22:30", squareoff: "23:15" }
    : exchange === "CDS" ? { entry: "09:15", lastEntry: "16:15", squareoff: "16:45" }
      : { entry: "09:30", lastEntry: "14:45", squareoff: "15:15" };

/** A held or priced leg: its contract, units of the underlying and the price it filled at. */
export interface HeldLeg { side: "buy" | "sell"; opt: "CE" | "PE"; strike: number; qty: number; fill: number }

/** Profit at expiry with the underlying at x, before costs. */
export function atExpiry(legs: HeldLeg[], x: number): number {
  return legs.reduce((sum, l) => {
    const intrinsic = l.opt === "CE" ? Math.max(0, x - l.strike) : Math.max(0, l.strike - x);
    return sum + (l.side === "sell" ? l.fill - intrinsic : intrinsic - l.fill) * l.qty;
  }, 0);
}

/** A leg in a few words: "Sold 25,000 CE". */
export const legName = (side: "buy" | "sell", strike: number, opt: "CE" | "PE") =>
  `${side === "sell" ? "Sold" : "Bought"} ${strike.toLocaleString("en-IN")} ${opt}`;

/** Prices 10% either side of the spot: an even grid plus every strike inside it, where the payoff bends. */
export function priceGrid(spot: number, strikes: number[], n = 121): number[] {
  const lo = spot * 0.9, hi = spot * 1.1;
  return [...Array.from({ length: n }, (_, i) => lo + ((hi - lo) * i) / (n - 1)), ...strikes.filter((k) => k > lo && k < hi)]
    .sort((a, b) => a - b).filter((x, i, arr) => i === 0 || x !== arr[i - 1]);
}

/** A priced structure's legs, sized: each leg's lots × units × the lot size. */
export function heldLegs(p: OptPreview): HeldLeg[] {
  return p.legs.filter((l) => l.strike != null && l.fill != null)
    .map((l) => ({ side: l.side, opt: l.opt, strike: l.strike!, fill: l.fill!, qty: l.lots * p.units * p.lot }));
}

/** Profit or loss at expiry across a range of prices, for a priced structure. */
export function payoff(p: OptPreview) {
  const legs = heldLegs(p);
  const at = (x: number) => atExpiry(legs, x);
  const xs = priceGrid(p.spot, legs.map((l) => l.strike));
  const ys = xs.map(at);
  // exact bounds, as options/charges.py works them out: the payoff is straight between strikes and the price stops at
  // zero, so the extremes are at zero or a strike; only above the top strike can it run on, by the calls' net slope
  const at0 = [0, ...legs.map((l) => l.strike)], corners = at0.map(at);
  const slopeAbove = legs.reduce((n, l) => n + (l.opt === "CE" ? (l.side === "buy" ? 1 : -1) * l.qty : 0), 0);
  const maxP = Math.max(...corners), maxL = Math.min(...corners);
  // every crossing, as options/charges.py finds them: on each segment between 0 and the strikes, then past the top strike
  const bx = [0, ...[...new Set(legs.map((l) => l.strike))].sort((a, b) => a - b)], by = bx.map(at);
  const breakevens: number[] = [];
  for (let i = 1; i < bx.length; i++) if ((by[i - 1] < 0) !== (by[i] < 0)) breakevens.push(bx[i - 1] + ((bx[i] - bx[i - 1]) * -by[i - 1]) / (by[i] - by[i - 1]));
  if (slopeAbove && (by[by.length - 1] < 0) !== (slopeAbove < 0)) breakevens.push(bx[bx.length - 1] - by[by.length - 1] / slopeAbove);
  const credit = legs.reduce((s, l) => s + (l.side === "sell" ? 1 : -1) * l.fill * l.qty, 0);
  // the price where each bound is reached: a flat stretch (an iron condor beyond its wings) reaches it at every price
  // there, so take the one nearest today's price; "outside the chart" is then said only when no price on it reaches it
  const nearest = (v: number) => at0.filter((_, i) => Math.abs(corners[i] - v) <= 1e-6 * Math.max(1, Math.abs(v)))
    .reduce((a, b) => (Math.abs(b - p.spot) < Math.abs(a - p.spot) ? b : a));
  return { xs, ys, maxProfit: slopeAbove > 1e-9 ? null : maxP, maxLoss: slopeAbove < -1e-9 ? null : maxL, breakevens, credit,
    bestAt: nearest(maxP), worstAt: nearest(maxL) };
}

/** sessionStorage key: an imported options strategy handed from the import dialog to the Options page. */
export const IMPORTED = "stratlab.options.import";

/** The line a flat options session shows after a trade closed while the rules' gap between trades still runs (R7T-013: after
 * a 09:41 stop-out with entries 120 minutes apart, "Entries open until 14:45" instead of the next entry's time). Null when
 * no gap is running at `now`; `lastEntry` is the day's last entry and `entry` the first. */
export function gapLine(a: { cool_until?: string | null; next_entry?: string | null }, cooldown: number | null | undefined, lastEntry: string, entry: string,
  now: Date): string | null {
  if (!a.cool_until) return null;
  const until = new Date(a.cool_until);
  if (Number.isNaN(until.getTime()) || until.getTime() <= now.getTime()) return null;
  const gap = cooldown ? `entries are ${cooldown} min apart` : "the rules keep a gap between entries";
  return a.next_entry ? `Next entry from ${a.next_entry}: ${gap}.` : `Next entry ${entry} on the next market day: ${gap}, past the last entry at ${lastEntry}.`;
}

/* ---------- Trade space fixes (review 5b) ---------- */

/** The legs' distances in the other unit: strikes × the underlying's own strike step = points, and back. The step is the
 * chain's or the priced preview's (50 for NIFTY, 100 for BANKNIFTY, 0.25 for USDINR); never assumed. */
export function offsetsIn(legs: OptLeg[], to: "strikes" | "points", step: number): OptLeg[] {
  const tidy = (v: number) => Math.round(v * 1e6) / 1e6;
  return legs.map((l) => ({ ...l, offset: to === "points" ? tidy(l.offset * step) : Math.round(l.offset / step) }));
}

/** A stop or target switched between rupees and % of the premium: converted at the priced premium when there is one (a
 * whole-rupee figure, or a percent to one decimal), else cleared to 0 with a line saying so. `premium` is the premium in
 * rupees for the units priced (collected or paid), null when nothing is priced. */
export function convertOptLimit(value: number, from: OptionStrategy["risk"]["stopType"], to: OptionStrategy["risk"]["stopType"],
  premium: number | null, what: "stop" | "target"): { value: number; note: string | null } {
  if (from === to || to === "none" || from === "none" || !value) return { value, note: null };
  const p = premium != null ? Math.abs(premium) : 0;
  if (p > 0) {
    const v = to === "amount" ? Math.round((value / 100) * p) : Math.round((value / p) * 1000) / 10;
    return { value: v, note: `The ${what} of ${from === "amount" ? `₹${value.toLocaleString("en-IN")}` : `${value}% of the premium`} is ${to === "amount" ? `₹${v.toLocaleString("en-IN")}` : `${v}% of the premium`} at the premium priced now.` };
  }
  return { value: 0, note: `The ${what} was ${from === "amount" ? `₹${value.toLocaleString("en-IN")}` : `${value}% of the premium`}; with nothing priced yet it can't be turned into ${to === "amount" ? "rupees" : "a percent"}, so it was cleared. Enter it again, or price the structure first.` };
}

/** The notebook signal an options session enters on, read from the notebook now (`asOf`, an instant). */
export type OptSignal = NonNullable<OptionStrategy["signal"]>;
export function signalFrom(nb: { id: string; name: string; strategy: OptSignal["rules"] }, prev: OptSignal | null | undefined, asOf: string): OptSignal {
  return { rules: nb.strategy, notebook: nb.id, name: nb.name, short: prev?.short ?? (nb.strategy.side === "long" ? "none" : "mirror"), asOf };
}

/** "Rules from RSI dips, as of 15 Oct, 10:20 IST": which notebook's rules the session will run, and when they were read
 * (they are read again right before Start). */
export function signalLine(sig: Pick<OptSignal, "name" | "asOf">): string {
  return `Rules from ${sig.name}${sig.asOf ? `, as of ${fmtDateTime(sig.asOf, { tz: IST, year: false, zone: true })}` : ", as of when they were picked"}`;
}

/** The open trade's costs line, counting the orders the list under it shows (R24-007: "Costs so far ₹1,860 over 8 orders"
 * above "Orders in this trade (4)": the 8 were the exchange orders after each was split at the freeze limit). `orders` are
 * the trade's orders as listed; a split order says how many exchange orders it was sent as. */
export function costsLine(costs: string, orders: { slices?: number }[]): string {
  const sent = orders.filter((o) => (o.slices ?? 1) > 0);
  const n = sent.length, slices = sent.reduce((a, o) => a + (o.slices ?? 1), 0);
  return `Costs so far ${costs} over the ${n} order${n === 1 ? "" : "s"} in this trade`
    + (slices > n ? ` (sent as ${slices} exchange orders, split at the exchange's limit per order)` : "") + ".";
}

/* ---------- review DB (24 Oct 2026) ---------- */

/** What is wrong with a structure's times, in plain words (DB-004: 16:00 entry, 08:00 last entry and 09:00 square-off were
 * written back as a plan with no warning). `open`/`close` are the exchange's hours ("09:15", "15:40"), when known. Empty
 * when the times work. */
export function timingIssues(t: { entry: string; lastEntry: string; squareoff: string }, open?: string | null, close?: string | null): string[] {
  const out: string[] = [];
  const inHours = (x: string) => !open || !close || (x >= open && x <= close);
  if (open && close) {
    for (const [v, what] of [[t.entry, "The entry time"], [t.lastEntry, "The last entry"], [t.squareoff, "The square-off"]] as const)
      if (!inHours(v)) out.push(`${what}, ${v}, is outside the market's hours (${open} to ${close}).`);
  }
  if (t.lastEntry < t.entry) out.push(`The last entry (${t.lastEntry}) is before the first (${t.entry}), so it would never enter.`);
  if (t.squareoff <= t.entry || t.squareoff < t.lastEntry) out.push(`The square-off (${t.squareoff}) has to come after the entries.`);
  return out;
}

/** A number box's range in words, for the line under it: "1 to 50", "a whole number from −100 to 100". */
export function rangeText(min: number, max: number | undefined, whole: boolean): string {
  const n = (v: number) => `${v < 0 ? "−" : ""}${Math.abs(v).toLocaleString("en-IN")}`;
  const span = max == null ? `${n(min)} or more` : `${n(min)} to ${n(max)}`;
  return whole ? `A whole number, ${span}.` : `From ${span}.`;
}

/** A typed number held to a box's range (DB-007: 999 lots went back to 1; now it is 50, and said): the value it becomes on
 * leaving the box, or null when the text isn't a number. */
export function clampTyped(text: string, min: number, max: number | undefined, whole: boolean): number | null {
  const t = text.replace(/,/g, "").trim();
  if (!/^[−-]?\d*\.?\d+$/.test(t)) return null;
  let v = Number(t.replace("−", "-"));
  if (whole) v = Math.round(v);
  return Math.min(max ?? Infinity, Math.max(min, v));
}

/** The expiry a choice names, for its button: "Nearest · 27 Oct" (DB-008: the choices never named a date). */
export function expiryChoiceLabel(name: string, date: string | undefined, fmt: (d: string) => string): string {
  return date ? `${name} · ${fmt(date)}` : name;
}

/** The line over a structure priced on a recording, not live quotes (DB-001). `at` is the recording's time, written. */
export function recordedLine(at: string): string {
  return `Priced on the last recorded option chain, as of ${at} (the last close), because live quotes are offline: bids and asks as recorded then, else last trades. Not a live price; the broker's margin and paper trading need the live feed.`;
}
