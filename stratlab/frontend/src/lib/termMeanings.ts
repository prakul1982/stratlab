/* fix12 (CX2 #7, jargon): what the trading terms in a strategy's name or a column mean, in plain words, for an (i) beside them the first
 * time a page shows them. Facts about how each is worked out, never a call. No imports, so the unit tests load it alone. */

const TERMS: [RegExp, string][] = [
  [/\bsupertrend\b/i, "Supertrend (N, M): a line that trails the price at M times its average daily range over the last N candles, below the price while it rises and above it while it falls."],
  [/\bstage\s*[1-4]?\b/i, "Stage 1 to 4: where the price sits against its 150-day average and which way that average slopes: 1 flattening after a fall, 2 above a rising average, 3 flattening after a rise, 4 below a falling average."],
  [/\b(?:sma|simple moving average|\d+[- ]day (?:moving )?averages?)\b/i, "A moving average (SMA): the plain average of the last N closing prices."],
  [/\bema\b/i, "EMA: an average of the last N closes that leans on the newest ones, so it turns sooner than a plain average."],
  [/\b(?:golden|death) cross\b/i, "A golden cross is the 50-day average crossing above the 200-day average; a death cross is the same crossing downwards."],
  [/\brsi\b/i, "RSI: momentum from 0 to 100, high after a run of gains and low after a run of losses."],
  [/\bmacd\b/i, "MACD: the gap between a fast and a slow average; it crossing its own smoothed line is the usual signal."],
  [/\bbollinger\b/i, "Bollinger bands: lines a few standard deviations above and below an average, wider when prices swing more."],
  [/\badx\b/i, "ADX: how strong a trend is, from 0 to 100, whichever way it runs."],
  [/\batr\b/i, "ATR: the average range of a candle (high to low) over the last N candles."],
  [/\bvwap\b/i, "VWAP: the average price weighted by how much traded at each price."],
  [/\b(?:donchian|breakout|\d+-(?:day|week) high)\b/i, "A breakout: the price closing above the highest high of the previous N candles."],
];

/** The plain-words meaning of each trading term `text` names, once each, in the order above. */
export function termMeanings(text: string | null | undefined): string[] {
  const t = String(text ?? "");
  return TERMS.filter(([re]) => re.test(t)).map(([, say]) => say);
}

/** What the library table's "vs hold (pts)" column is, said once under the list (CX2 #7: shorthand; an (i) in its header pushed the
 * table's last column past a 1280 screen's edge, ui-lint R27). */
export const VS_HOLD_SAID = "vs hold (pts): the return after costs minus buying and holding's over the same dates, in percentage points (30% against 20% is +10).";
