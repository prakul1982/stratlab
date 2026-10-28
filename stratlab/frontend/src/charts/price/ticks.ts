/* The forming candle, built from live prices (MW-1): each price the broker's feed sends (its last price and the day's traded
 * volume so far) moves the newest candle of the chart's own timeframe: its close, its high and low, and the volume that traded
 * since the last price. A price that falls after the candle's end starts the next one on the same grid, but only inside the
 * market's session, so no candle appears for the closing auction or after the close. Pure: no page, no request, so the unit
 * tests run it directly. */
import { dayOf, periodStart, type Bar } from "./transforms";

/** One live price: `p` the last price, `v` the day's volume so far (null when the source doesn't say), `t` when it traded (ms). */
export interface Tick { p: number; v: number | null; t: number }

/** The volume seen so far today, kept between ticks so each one adds only what traded since the last. */
export interface VolState { cum: number | null }

/** Length of each intraday timeframe, ms. Daily and longer are null: their candle runs to the end of the day, week or month. */
export const TF_MS: Record<string, number | null> = {
  "1m": 60_000, "3m": 180_000, "5m": 300_000, "10m": 600_000, "15m": 900_000, "30m": 1_800_000,
  "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "1d": null, "1w": null, "1mo": null,
};

/** When each market that streams trades, as minutes after midnight on the exchange's clock: [open, close). */
export const SESSION_MIN: Record<string, [number, number]> = { IN: [9 * 60 + 15, 15 * 60 + 30], MCX: [9 * 60, 23 * 60 + 30], CDS: [9 * 60, 17 * 60] };

/** The volume this tick adds: what traded since the previous one. The first tick of a chart only sets the mark (what traded
 * before it is in the candles already); a lower number than before is a new day, so it starts again. */
export function volumeSince(state: VolState, v: number | null): number {
  if (v == null || !Number.isFinite(v)) return 0;
  const add = state.cum != null && v >= state.cum ? v - state.cum : 0;
  state.cum = v;
  return add;
}

/** The newest candle with a tick applied, and whether it is a new candle: null when the tick doesn't belong on the chart (older
 * than the candle, or after the session's end, or of another day on a daily chart). `bars` are the chart's own candles. */
export function applyTick(last: Bar | undefined, tick: Tick, tf: string, vol: VolState, market = "IN"): { bar: Bar; isNew: boolean } | null {
  if (!last || !Number.isFinite(tick.p) || !Number.isFinite(tick.t)) return null;
  const add = volumeSince(vol, tick.v);
  const ms = TF_MS[tf];
  const grow = (b: Bar): Bar => ({ ...b, h: Math.max(b.h, tick.p), l: Math.min(b.l, tick.p), c: tick.p, v: b.v + add });
  if (ms == null) {
    // a daily, weekly or monthly candle takes the tick only while the tick is still in its own day, week or month
    const wall = tick.t + (last.w - last.t);
    const same = tf === "1d" ? dayOf(wall) === last.day : periodStart(wall, tf === "1w" ? "week" : "month") === periodStart(last.w, tf === "1w" ? "week" : "month");
    return same ? { bar: grow(last), isNew: false } : null;
  }
  if (tick.t < last.t) return null;
  if (tick.t < last.t + ms) return { bar: grow(last), isNew: false };
  const start = last.t + Math.floor((tick.t - last.t) / ms) * ms;
  const wall = start + (last.w - last.t);
  const [open, close] = SESSION_MIN[market] ?? [0, 1440];
  const minutes = ((wall % 86_400_000) / 60_000) | 0;
  if (minutes < open || minutes >= close) return null;
  return { bar: { t: start, w: wall, o: tick.p, h: tick.p, l: tick.p, c: tick.p, v: add, day: dayOf(wall) }, isNew: true };
}

/** Seconds left in the forming candle ("closes in 04:32"), or null when none is forming now: the newest candle's window must
 * hold the present moment. Daily and longer candles have no countdown. */
export function closesIn(last: Bar | undefined, tf: string, now: number): number | null {
  const ms = TF_MS[tf];
  if (!last || ms == null || now < last.t || now >= last.t + ms) return null;
  return Math.max(0, Math.ceil((last.t + ms - now) / 1000));
}

/** "4:32", or "1:04:32" from an hour up. */
export function countdown(seconds: number): string {
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  const two = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${two(m)}:${two(s)}` : `${m}:${two(s)}`;
}

/** The timeframe one step along a list (the [ and ] keys), staying at its ends. */
export function stepTf<T extends string>(offered: T[], now: T, by: 1 | -1): T {
  const i = offered.indexOf(now);
  if (i < 0) return offered[0];
  return offered[Math.max(0, Math.min(offered.length - 1, i + by))];
}

/** The number keys' timeframes: 1 to 0 pick 1m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1D and 1W (2h and 1M are on [ and ]). */
export const TF_KEYS: Record<string, string> = { "1": "1m", "2": "3m", "3": "5m", "4": "10m", "5": "15m", "6": "30m", "7": "1h", "8": "4h", "9": "1d", "0": "1w" };

/** Every timeframe the chart workspace offers, shortest first (the sizes the server builds from what a source sends). */
export const WORKSPACE_TFS = ["1m", "3m", "5m", "10m", "15m", "30m", "1h", "2h", "4h", "1d", "1w", "1mo"] as const;
