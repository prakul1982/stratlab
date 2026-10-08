import { dayIn } from "../../lib/format";
import type { RawCandle } from "./transforms";

/** The page's one reading of the price: what the company's header and tab title show, and when it was read. */
export interface QuoteReading { price: number | null | undefined; asOf: string | null | undefined; tz: string }

/** The calendar day of a candle's time (a date as written, or an instant in the market's zone). */
const candleDay = (t: string, tz: string): string | null => (/^\d{4}-\d{2}-\d{2}$/.test(t) ? t : dayIn(t, tz));

/** The newest candle brought to the price the page already shows. The header, the tab title and the chart's last candle are
 * one reading: when the newest candle is from the day that price was read, its close is that price (its high and low
 * widened to hold it), so the legend's close and change never differ from the header's by the cents a second reading
 * moved. Candles of another day, or a page without a price, are as the source sent them. */
export function settleLast(candles: RawCandle[], r: QuoteReading | null | undefined): RawCandle[] {
  const px = r?.price;
  if (!r || px == null || !Number.isFinite(px) || !candles.length) return candles;
  const last = candles[candles.length - 1];
  const day = dayIn(r.asOf, r.tz);
  if (!day || candleDay(last.t, r.tz) !== day) return candles;
  const hi = last.h == null ? px : Math.max(last.h, px), lo = last.l == null ? px : Math.min(last.l, px);
  return [...candles.slice(0, -1), { ...last, c: px, h: hi, l: lo }];
}
