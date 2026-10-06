/* Timeframes and look-back periods for the Trade pickers (ChipBar + "+ Custom").
 *
 * What the data supports (checked in the backend): candles of 5 minutes, 15 minutes, 1 hour and 1 day only
 * (backend/app/chart_data.py TFS, replay.py TFS, engine/core.py TF_MIN, models.py `tf`); weekly and monthly charts are
 * made from daily candles in the chart itself. The rules engine can also read a higher timeframe of 15 minutes, 1 hour
 * or 1 day. A candle size is not freely typed: any other size has no stored prices behind it. So a custom candle size is
 * accepted only when it is one of those sizes written another way (60 minutes is 1 hour, 24 hours is 1 day), and the
 * (i) says so. A look-back period (how many days of history to test or show) can be any whole number of days up to
 * what the data holds, so those accept real custom values. */
import type { Choice } from "../components/kit/Seg";
import type { CustomCheck, CustomUnit } from "../components/kit/ChipBar";

export const CANDLE_SIZES: Choice[] = [
  { value: "5m", label: "5 min" }, { value: "15m", label: "15 min" }, { value: "1h", label: "1 hour" }, { value: "1d", label: "1 day" },
];
export const CANDLE_UNITS: CustomUnit[] = [
  { value: "min", label: "minute", plural: "minutes" }, { value: "h", label: "hour", plural: "hours" }, { value: "d", label: "day", plural: "days" },
];
export const CANDLE_LIMITS = "StratLab stores candles of 5 minutes, 15 minutes, 1 hour and 1 day. Another size has no prices behind it, so + Custom accepts only those sizes written another way (60 minutes is 1 hour, 24 hours is 1 day). Smaller candles reach back only a few months: 5-minute about four, 15-minute about a year, 1-hour about two years, daily about ten.";

/** A custom candle size, kept only when it equals a stored size. `allowed` narrows the sizes a page can use. */
export function candleCheck(allowed: string[] = CANDLE_SIZES.map((c) => c.value)) {
  return (n: number, unit: string): CustomCheck => {
    const minutes = unit === "min" ? n : unit === "h" ? n * 60 : n * 1440;
    const hit = CANDLE_SIZES.find((c) => minutes === ({ "5m": 5, "15m": 15, "1h": 60, "1d": 1440 } as Record<string, number>)[c.value]);
    if (!hit) return { error: "That size isn't stored. Pick 5 min, 15 min, 1 hour or 1 day." };
    if (!allowed.includes(hit.value)) return { error: `${hit.label} candles aren't available here.` };
    return { value: hit.value, label: hit.label };
  };
}

/** The shared price chart's timeframes: the stored candle sizes plus the weekly and monthly charts made from daily candles. */
export const CHART_TF_UNITS: CustomUnit[] = [
  ...CANDLE_UNITS, { value: "w", label: "week", plural: "weeks" }, { value: "mo", label: "month", plural: "months" },
];
/** A custom timeframe on the price chart: kept only when it is one the chart offers written another way (60 minutes is
 * 1 hour, 24 hours or 1 day is 1 day, 7 days is 1 week). Any other size has no candles behind it. */
export function chartTfCheck(offered: string[]) {
  const NAME: Record<string, string> = { "5m": "5 min", "15m": "15 min", "1h": "1 hour", "1d": "1 day", "1w": "1 week", "1mo": "1 month" };
  return (n: number, unit: string): CustomCheck => {
    const minutes = unit === "min" ? n : unit === "h" ? n * 60 : unit === "d" ? n * 1440 : unit === "w" ? n * 10080 : null;
    const hit = unit === "mo" ? (n === 1 ? "1mo" : null) : ({ 5: "5m", 15: "15m", 60: "1h", 1440: "1d", 10080: "1w" } as Record<number, string>)[minutes ?? -1] ?? null;
    if (!hit) return { error: `That size isn't stored. Pick ${offered.map((o) => NAME[o] ?? o).join(", ").replace(/, ([^,]*)$/, " or $1")}.` };
    if (!offered.includes(hit)) return { error: `${NAME[hit]} candles aren't available on this chart.` };
    return { value: hit, label: NAME[hit] };
  };
}

export const SPAN_UNITS: CustomUnit[] = [
  { value: "days", label: "day", plural: "days" }, { value: "weeks", label: "week", plural: "weeks" },
  { value: "months", label: "month", plural: "months" }, { value: "years", label: "year", plural: "years" },
];
/** Days in "45 days", "6 weeks", "3 months" or "2 years"; null for anything else. */
export function spanDays(v: string): number | null {
  const m = /^(\d{1,3}) (days|weeks|months|years)$/.exec(v);
  if (!m) return null;
  const n = Number(m[1]);
  return n * ({ days: 1, weeks: 7, months: 30, years: 365 } as Record<string, number>)[m[2]];
}
/** A custom look-back period, accepted up to `maxDays` (what the data holds). */
export function spanCheck(maxDays: number, minDays = 1) {
  return (n: number, unit: string): CustomCheck => {
    const days = spanDays(`${n} ${unit}`) ?? 0;
    if (days < minDays) return { error: `Use at least ${minDays} day${minDays === 1 ? "" : "s"}.` };
    if (days > maxDays) return { error: `The data holds about ${maxDays.toLocaleString("en-IN")} days here. Use a shorter period.` };
    return { value: `${n} ${unit}` };
  };
}
