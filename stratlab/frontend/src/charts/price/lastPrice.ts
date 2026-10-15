/** Where the last price's dashed line and its axis tag may draw without covering the legend or an axis label (R29B-017: at
 * 400 px the line ran through the "1mo candle" legend and the "350" label sat behind the price tag). Pure, so a unit test
 * can read it. */
export interface Box { w: number; h: number }

const LEGEND_LEFT = 8, LEGEND_TOP = 6, PAD = 6;

/** The x ranges of a dashed line at height `y` across a plot `pw` wide, with the legend's box left clear. */
export function lineSpans(y: number, pw: number, legend: Box | null): [number, number][] {
  if (!legend || legend.w <= 0 || legend.h <= 0) return [[0, pw]];
  const inBand = y >= LEGEND_TOP - PAD && y <= LEGEND_TOP + legend.h + PAD;
  if (!inBand) return [[0, pw]];
  const from = Math.min(pw, LEGEND_LEFT + legend.w + PAD);
  return from >= pw ? [] : [[from, pw]];
}

/** Whether an axis label at `y` can be drawn: not under a price tag (a tag is 20 px tall). */
export function labelClear(y: number, tagYs: number[], gap = 12): boolean {
  return tagYs.every((t) => Math.abs(t - y) >= gap);
}
