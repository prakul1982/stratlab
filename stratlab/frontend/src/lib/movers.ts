/* Market movers, kept apart from the page so it can be tested on its own (unit/movers.test.mjs): what the server sends, each list's name
 * and the figure it is sorted by, and a row's figures in words. Facts only: a list is sorted by a figure, nothing more. */

/** One stock in a list: `cap` its market value in the market's unit (₹ crore, $ million); `chg` the day's change in percent; `vol` the
 * day's volume and `avg` its average over the 20 sessions before; `vx` the one over the other; `tv` the value traded (close × volume, in
 * rupees or dollars); `hi` and `lo` the 52-week high and low. */
export type MoverRow = { s: string; n: string; cap: number | null; px: number | null; chg: number | null; vol: number | null; avg: number | null;
  vx: number | null; tv: number | null; hi: number | null; lo: number | null };

export const LISTS = ["gainers", "losers", "traded", "spikes", "highs", "lows"] as const;
export type ListId = (typeof LISTS)[number];

export type MoversView = {
  market: "IN" | "US"; universe: string; universe_name: string; universes: { id: string; name: string }[]; as_of: string | null;
  cap_unit: string; pending: boolean; marks: boolean; min_cap: number | null; top: number; members: number; with_prices: number; matching: number;
  lists: Record<ListId, { total: number; rows: MoverRow[] }>;
  /** Free: the top rows of the default index only; `plan` names the plan with the rest */
  locked: boolean; plan?: string;
};

/** Each list's tab name, what it is sorted by (one line under the table), and its own figure's column. */
export const LIST_META: Record<ListId, { label: string; what: string; figure: string }> = {
  gainers: { label: "Gainers", what: "The largest rises at the close, from the close before.", figure: "Volume vs average" },
  losers: { label: "Losers", what: "The largest falls at the close, from the close before.", figure: "Volume vs average" },
  traded: { label: "Most traded", what: "The most value traded: the closing price times the day's volume.", figure: "Value traded" },
  spikes: { label: "Volume spikes", what: "The day's volume as a multiple of its average over the 20 sessions before, among stocks above their average.", figure: "Volume vs average" },
  highs: { label: "52-week highs", what: "Stocks whose day's high was above every high of the 52 weeks before.", figure: "52-week high" },
  lows: { label: "52-week lows", what: "Stocks whose day's low was below every low of the 52 weeks before.", figure: "52-week low" },
};

export const isList = (v: string | null): v is ListId => !!v && (LISTS as readonly string[]).includes(v);

/** "4.1×" of the average volume, or "–". */
export const times = (v: number | null): string => (v == null ? "–" : `${v.toFixed(1)}×`);

/** The figure a list adds to every row, as a number for the CSV: the multiple, the value traded, or the 52-week high or low. */
export function figureOf(list: ListId, r: MoverRow): number | null {
  return list === "traded" ? r.tv : list === "highs" ? r.hi : list === "lows" ? r.lo : r.vx;
}

/** "The top 5 of 312" when a list is cut (Free's teaser, or a long list), else "All 12"; "" for none. */
export function countLine(shown: number, total: number): string {
  if (!total) return "";
  return shown < total ? `The top ${shown} of ${total.toLocaleString("en-IN")}` : `All ${total.toLocaleString("en-IN")}`;
}
