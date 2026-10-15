/** Which candle the legend reads: the one under the pointer, else the newest. Read from the engine's own bars at render
 *  time, so a candle added by chart replay's "Next candle" shows in the same render, not after the next pointer move (R29D-003). */
export function legendIndex(hoverIndex: number, bars: number): number {
  if (bars <= 0) return -1;
  return hoverIndex >= 0 && hoverIndex < bars ? hoverIndex : bars - 1;
}
