import { money, periodName, TF_NAME } from "./format";
import { opSay, refName } from "./rules";
import type { Cond, Risk, Strategy } from "./types";

/* What differs between two experiments' setups, in plain words (the compare page's "What changed"). */

export interface CompareRun { strategy: Strategy; instrument?: { symbol?: string; currency?: string | null } | null; days: number }

const condText = (c: Cond) => `${refName(c.l)} ${opSay(c.op)} ${refName(c.r)}`;
/** A strategy's direction as the notebook says it: "both ways" is its own, not "long". */
const SIDE: Record<string, string> = { long: "long only", short: "short only", both: "both ways" };
const PRODUCT: Record<string, string> = { auto: "automatic", delivery: "delivery (CNC)", intraday: "intraday (MIS)" };
const JOIN: Record<string, string> = { all: "all of the rules", any: "any one rule", score: "a score" };

/** A stop in its own unit: "2%", "150 points", "1.5 × ATR", "the 5-candle swing"; "off" at 0. */
export function stopIn(v: number | undefined, unit: Risk["stopType"]): string {
  if (!v) return "off";
  if (unit === "points") return `${v} points`;
  if (unit === "atr") return `${v} × ATR`;
  if (unit === "swing") return `the ${v}-candle swing`;
  return `${v}%`;
}

/** A target in its own unit: "6%", "300 points", "2R"; "off" at 0. */
export function targetIn(v: number | undefined, unit: Risk["tgtType"]): string {
  if (!v) return "off";
  if (unit === "points") return `${v} points`;
  if (unit === "r") return `${v}R (× the stop distance)`;
  return `${v}%`;
}

/** A test period as the period chips say it: whole years as years ("5 years"), anything else in days. */
export function spanIn(days: number): string {
  return days >= 365 && days % 365 === 0 ? periodName(days) : `${days.toLocaleString("en-IN")} day${days === 1 ? "" : "s"}`;
}

/** What bold means in the compare page's table of numbers: the higher figure on a line, and the lower one for costs. It said "the
 * larger", which the bold costs of the cheaper run contradicted (RC3T-005). */
export const BOLD_NOTE = "Bold marks the higher figure on a line, and for costs the lower one. A higher backtest figure is not proof: the verdict's honesty checks are what test for luck.";

/** How a run sizes its trades, in words, with its own currency. Leverage is said for either way of sizing: it widens the most a
 * trade can take on a risk-sized run too, so a change in it changes the result (RC3T-004: it was left out when sizing by risk). */
export function sizing(r: Risk, cur: string | null | undefined): string {
  const lev = (r.leverage ?? 1) > 1 ? ` × ${r.leverage} leverage` : "";
  if ((r.sizing ?? "risk") === "risk") return `by risk${lev}`;
  return r.perTrade ? `fixed ${money(r.perTrade, cur)} a trade${lev}` : `fixed capital per trade${lev}`;
}

/** Plain-English list of what differs between two experiments' setups. Stops and targets are said in their own units,
 * money in each run's own currency, and the app's codes never show. */
export function changes(a: CompareRun, b: CompareRun): string[] {
  const out: string[] = [];
  const sa: Strategy = a.strategy, sb: Strategy = b.strategy;
  const ca = a.instrument?.currency, cb = b.instrument?.currency;
  if (a.instrument?.symbol !== b.instrument?.symbol) out.push(`Instrument: ${a.instrument?.symbol} → ${b.instrument?.symbol}`);
  if ((sa.side ?? "long") !== (sb.side ?? "long")) out.push(`Direction: ${SIDE[sa.side ?? "long"]} → ${SIDE[sb.side ?? "long"]}`);
  if (sa.tf !== sb.tf) out.push(`Candles: ${TF_NAME[sa.tf]} → ${TF_NAME[sb.tf]}`);
  if (a.days !== b.days) out.push(`Test period: ${spanIn(a.days)} → ${spanIn(b.days)}`);
  const rules = (s: Strategy, k: "entry" | "exit" | "shortEntry" | "shortExit") => (s[k] ?? []).map(condText).join(" · ") || "none";
  if (rules(sa, "entry") !== rules(sb, "entry") || sa.entryJoin !== sb.entryJoin) out.push(`Entry: ${rules(sa, "entry")} → ${rules(sb, "entry")}`);
  if (rules(sa, "exit") !== rules(sb, "exit")) out.push(`Exit: ${rules(sa, "exit")} → ${rules(sb, "exit")}`);
  const ra = sa.risk, rb = sb.risk;
  const stopA = stopIn(ra.sl, ra.stopType ?? "pct"), stopB = stopIn(rb.sl, rb.stopType ?? "pct");
  if (stopA !== stopB) out.push(`Stop loss: ${stopA} → ${stopB}`);
  const tgtA = targetIn(ra.tgt, ra.tgtType ?? "pct"), tgtB = targetIn(rb.tgt, rb.tgtType ?? "pct");
  if (tgtA !== tgtB) out.push(`Target: ${tgtA} → ${tgtB}`);
  const plain: [keyof Risk, string, (v: number, cur: string | null | undefined) => string][] = [
    ["trail", "Trailing stop", (v) => `${v}%`], ["maxBars", "Time limit", (v) => `${v} candles`], ["riskPct", "Risk per trade", (v) => `${v}%`],
    ["maxAlloc", "Most in one trade", (v) => `${v}%`], ["capital", "Capital", (v, cur) => money(v, cur)],
    ["brokerage", "Brokerage", (v, cur) => money(v, cur, 2)], ["slippage", "Slippage", (v) => `${v}%`],
  ];
  for (const [k, label, say] of plain) {
    const x = (ra[k] as number | undefined) ?? 0, y = (rb[k] as number | undefined) ?? 0;
    const tx = x ? say(x, ca) : "off", ty = y ? say(y, cb) : "off";
    if (x !== y || tx !== ty) out.push(`${label}: ${tx} → ${ty}`);
  }
  const za = sizing(ra, ca), zb = sizing(rb, cb);
  if (za !== zb) out.push(`Position size: ${za} → ${zb}`);
  if (rules(sa, "shortEntry") !== rules(sb, "shortEntry")) out.push(`Short entry: ${rules(sa, "shortEntry")} → ${rules(sb, "shortEntry")}`);
  if (rules(sa, "shortExit") !== rules(sb, "shortExit")) out.push(`Short exit: ${rules(sa, "shortExit")} → ${rules(sb, "shortExit")}`);
  if ((sa.product ?? "auto") !== (sb.product ?? "auto")) out.push(`Indian stock costs: ${PRODUCT[sa.product ?? "auto"]} → ${PRODUCT[sb.product ?? "auto"]}`);
  const join = (s: Strategy) => s.entryJoin === "score" ? `a score of at least ${s.minScore ?? 0}` : JOIN[s.entryJoin] ?? s.entryJoin;
  if (sa.entryJoin !== sb.entryJoin || (sa.minScore ?? 0) !== (sb.minScore ?? 0)) out.push(`Entry needs: ${join(sa)} → ${join(sb)}`);
  const say = (v: unknown) => (v === "" || v == null || v === 0 ? "off" : String(v));
  const labels: [keyof NonNullable<Strategy["session"]>, string][] = [["start", "First entry"], ["end", "Last entry"], ["squareoff", "Square-off"],
    ["maxTradesDay", "Trades a day"], ["cooldown", "Cooldown (candles)"], ["dailyLossPct", "Daily loss cap %"]];
  for (const [k, label] of labels) {
    const x = sa.session?.[k] ?? "", y = sb.session?.[k] ?? "";
    if (say(x) !== say(y)) out.push(`${label}: ${say(x)} → ${say(y)}`);
  }
  return out;
}

/** One run's values on the dates of both runs' charts: its own points as they are, a date between two of them read off
 * the straight line joining them, and nothing before its first point or after its last. Each run keeps a thinned set of
 * points (240 over its own window), so the two runs' dates rarely match: a value only on its own dates broke both lines
 * into pieces, and one stopped part way (DA-031). `dates` are sorted "YYYY-MM-DD" days. */
export function onDates(points: Map<string, number>, dates: string[]): (number | null)[] {
  const own = [...points.keys()].sort();
  if (!own.length) return dates.map(() => null);
  const ms = (d: string) => Date.parse(`${d.slice(0, 10)}T00:00:00Z`);
  let k = 0;
  return dates.map((d) => {
    if (d < own[0] || d > own[own.length - 1]) return null;
    const exact = points.get(d);
    if (exact != null) return exact;
    while (k < own.length - 1 && own[k + 1] < d) k++;
    const a = own[k], b = own[Math.min(own.length - 1, k + 1)];
    const va = points.get(a)!, vb = points.get(b)!;
    const span = ms(b) - ms(a);
    return span > 0 ? va + ((vb - va) * (ms(d) - ms(a))) / span : va;
  });
}
