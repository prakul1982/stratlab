/* The heatmap's arithmetic, kept apart from the page so it can be tested on its own (unit/heatmap.test.mjs): which figure a tile
 * is coloured and sized by, which of the legend's steps that figure falls in, and where each tile sits (a squarified treemap: every
 * tile's area is its share of the whole, drawn as close to a square as the space allows). Facts and geometry only. */

/** One company as the server sends it: `r` its change in percent over PERIODS, in order; `cap` its market value in the market's
 * unit (₹ crore, $ million); `vx` the last day's volume as a multiple of its 20-day average; `tv` the value traded that day. */
export type Tile = { s: string; n: string; sec: string | null; ind: string | null; cap: number | null; px: number | null;
  r: (number | null)[]; vx: number | null; tv: number | null;
  /** a theme's layer, set by the page when the tiles are a theme's companies */
  layer?: string };
export type HeatView = {
  market: "IN" | "US"; universe: string | null; universe_name: string | null; universes: { id: string; name: string }[];
  periods: string[]; as_of: string | null; cap_unit: string; index: { name: string; r: (number | null)[] | null };
  pending: boolean; min_cap: number | null; tiles: Tile[]; members: number; with_prices: number; matching: number; shown: number;
  /** a theme's companies with no closes drawn grey at their stored last price (LIVE6-005); absent from older answers */
  price_only?: number;
};

/** The note under the map on companies without closes (LIVE6-005): those drawn grey at their last price, and those with neither closes
 *  nor a price, which are left out. null when every company has its closes. */
export function closesNote(v: Pick<HeatView, "members" | "with_prices" | "price_only">, where: string): string | null {
  const n = (x: number) => x.toLocaleString("en-IN");
  const grey = v.price_only ?? 0, gone = Math.max(0, v.members - v.with_prices - grey);
  const parts: string[] = [];
  if (grey) parts.push(`${n(grey)} of the ${n(v.members)} companies ${where} ${grey === 1 ? "has" : "have"} no closes on record yet and ${grey === 1 ? "is" : "are"} shown in grey at the last price.`);
  if (gone) parts.push(`${n(gone)} of the ${n(v.members)} companies ${where} ${gone === 1 ? "has" : "have"} no closes or price on record and ${gone === 1 ? "is" : "are"} not shown.`);
  return parts.length ? parts.join(" ") : null;
}

export const PERIODS = ["1d", "1w", "1m", "3m", "ytd", "1y"] as const;
export type Period = (typeof PERIODS)[number];
export const PERIOD_LABEL: Record<Period, string> = { "1d": "1 day", "1w": "1 week", "1m": "1 month", "3m": "3 months", ytd: "Year to date", "1y": "1 year" };
export const PERIOD_SHORT: Record<Period, string> = { "1d": "1D", "1w": "1W", "1m": "1M", "3m": "3M", ytd: "YTD", "1y": "1Y" };
export type ColorBy = "change" | "vs" | "volume";
export type SizeBy = "cap" | "equal" | "traded";
export type GroupBy = "sector" | "industry" | "layer" | "none";

export const isPeriod = (v: unknown): v is Period => (PERIODS as readonly string[]).includes(v as string);
const fin = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);

/** The figure a tile is coloured by: its change over the period, that change less the index's (percentage points), or the last
 * day's volume as a multiple of its average. null when the tile (or the index) has no figure. */
export function colorValue(t: Tile, by: ColorBy, period: Period, index: (number | null)[] | null | undefined): number | null {
  if (by === "volume") return fin(t.vx) ? t.vx : null;
  const i = PERIODS.indexOf(period), v = t.r[i];
  if (!fin(v)) return null;
  if (by === "change") return v;
  const base = index?.[i];
  return fin(base) ? Math.round((v - base) * 100) / 100 : null;
}

/** The figure a tile is sized by: market value, one each, or the value traded on the last day. */
export function sizeValue(t: Tile, by: SizeBy): number | null {
  if (by === "equal") return 1;
  const v = by === "cap" ? t.cap : t.tv;
  return fin(v) && v > 0 ? v : null;
}

/** The change at which a period's colour is at its strongest, in percent: a day's 3%, a year's 36%. Each divides by six, so the
 * legend's steps are round figures. */
export const FULL: Record<Period, number> = { "1d": 3, "1w": 6, "1m": 12, "3m": 18, ytd: 30, "1y": 36 };
/** Where the volume colour steps up, as multiples of the 20-day average. */
export const VOLUME_STEPS = [0.5, 1, 1.5, 2, 3];

/** The colour step of a figure: for a change, −3 to 3 (0 within a sixth of the period's full change either side of nothing, then
 * ±1 to half of it, ±2 to all of it, ±3 beyond); for volume, 0 to 5 by VOLUME_STEPS. null for no figure. */
export function step(v: number | null, by: ColorBy, period: Period): number | null {
  if (!fin(v)) return null;
  if (by === "volume") return VOLUME_STEPS.filter((s) => v >= s).length;
  const full = FULL[period], a = Math.abs(v);
  const n = a < full / 6 ? 0 : a < full / 2 ? 1 : a < full ? 2 : 3;
  return n === 0 ? 0 : v < 0 ? -n : n;
}

/** A step's CSS class: hm-d3 … hm-d1, hm-z, hm-u1 … hm-u3 for a change, hm-v0 … hm-v5 for volume, hm-na without a figure. */
export function stepClass(s: number | null, by: ColorBy): string {
  if (s == null) return "hm-na";
  if (by === "volume") return `hm-v${s}`;
  return s === 0 ? "hm-z" : s > 0 ? `hm-u${s}` : `hm-d${-s}`;
}

const trim = (n: number) => String(Math.round(n * 100) / 100);

/** The legend: each step with the words under it, weakest change in the middle. */
export function legend(by: ColorBy, period: Period): { cls: string; label: string }[] {
  if (by === "volume") {
    return [{ cls: "hm-v0", label: `under ${VOLUME_STEPS[0]}×` }, ...VOLUME_STEPS.map((s, i) => ({ cls: `hm-v${i + 1}`, label: `${s}×${i === VOLUME_STEPS.length - 1 ? " and up" : ""}` }))];
  }
  const full = FULL[period], unit = by === "vs" ? " pts" : "%";
  const edge = [full, full / 2, full / 6];
  return [
    ...edge.map((e, i) => ({ cls: `hm-d${3 - i}`, label: `−${trim(e)}${unit}` })),
    { cls: "hm-z", label: `0${unit}` },
    ...[...edge].reverse().map((e, i) => ({ cls: `hm-u${i + 1}`, label: `+${trim(e)}${unit}` })),
  ];
}

/** Whether a tile matches what was typed in the search box: the start of its symbol, or any part of its name. */
export function matches(t: Tile, q: string): boolean {
  const want = q.trim().toLowerCase();
  if (!want) return true;
  return t.s.toLowerCase().startsWith(want) || t.n.toLowerCase().includes(want);
}

export type Rect = { x: number; y: number; w: number; h: number };

/** A squarified treemap of `values` (largest first works best) inside `box`: one rectangle per value, each with an area in
 * proportion to its value, laid out in rows along the shorter side so the rectangles stay close to squares. A value that is not
 * above zero gets an empty rectangle. */
export function squarify(values: number[], box: Rect): Rect[] {
  const out: Rect[] = values.map(() => ({ x: box.x, y: box.y, w: 0, h: 0 }));
  const live = values.map((v, i) => ({ v, i })).filter((p) => Number.isFinite(p.v) && p.v > 0);
  const total = live.reduce((n, p) => n + p.v, 0);
  if (!live.length || box.w <= 0 || box.h <= 0) return out;
  const k = (box.w * box.h) / total;
  const area = live.map((p) => p.v * k);
  let { x, y, w, h } = box, at = 0;
  // the worst width-to-height ratio in a row of areas (smallest lo, largest hi, sum) laid along a side of length `side`
  const worst = (lo: number, hi: number, sum: number, side: number) => Math.max((side * side * hi) / (sum * sum), (sum * sum) / (side * side * lo));
  while (at < area.length) {
    const side = Math.min(w, h);
    let end = at + 1, sum = area[at], lo = area[at], hi = area[at];
    while (end < area.length) {
      const a = area[end], lo2 = Math.min(lo, a), hi2 = Math.max(hi, a);
      if (worst(lo2, hi2, sum + a, side) > worst(lo, hi, sum, side)) break;
      sum += a; lo = lo2; hi = hi2; end++;
    }
    const last = end === area.length;
    if (w >= h) {                       // a column down the left of what is left
      const cw = last ? w : sum / h;
      let cy = y;
      for (let j = at; j < end; j++) { const ch = j === end - 1 ? y + h - cy : area[j] / cw; out[live[j].i] = { x, y: cy, w: cw, h: ch }; cy += ch; }
      x += cw; w -= cw;
    } else {                            // a row across the top of what is left
      const rh = last ? h : sum / w;
      let cx = x;
      for (let j = at; j < end; j++) { const rw = j === end - 1 ? x + w - cx : area[j] / rh; out[live[j].i] = { x: cx, y, w: rw, h: rh }; cx += rw; }
      y += rh; h -= rh;
    }
    at = end;
  }
  return out;
}

export type Placed = { tile: Tile; size: number; value: number | null; box: Rect };
export type Group = { name: string; total: number;
  /** the group's own figure: its tiles' colour figures averaged, each weighted by its size */
  value: number | null; box: Rect; head: number; tiles: Placed[] };
export type Layout = { groups: Group[]; left_out: number };

export const HEAD = 20;          // a group's name strip, in px
const HEAD_MIN_W = 56, HEAD_MIN_H = 44;

export function groupName(t: Tile, by: GroupBy): string {
  if (by === "none") return "";
  const v = by === "sector" ? t.sec : by === "industry" ? t.ind ?? t.sec : t.layer;
  return v || "Other";
}

/** Every tile's place in a `w` × `h` box: the groups squarified by their totals, then each group's tiles squarified inside it under
 * the group's name. Tiles without a size figure are left out and counted (`left_out`). */
export function layout(tiles: Tile[], o: { size: SizeBy; color: ColorBy; period: Period; group: GroupBy; index?: (number | null)[] | null },
  w: number, h: number): Layout {
  const by = new Map<string, Placed[]>();
  let left_out = 0;
  for (const t of tiles) {
    const size = sizeValue(t, o.size);
    if (size == null) { left_out++; continue; }
    const name = groupName(t, o.group);
    if (!by.has(name)) by.set(name, []);
    by.get(name)!.push({ tile: t, size, value: colorValue(t, o.color, o.period, o.index), box: { x: 0, y: 0, w: 0, h: 0 } });
  }
  const groups: Group[] = [...by.entries()].map(([name, list]) => {
    list.sort((a, b) => b.size - a.size || a.tile.s.localeCompare(b.tile.s));
    const total = list.reduce((n, p) => n + p.size, 0);
    const have = list.filter((p) => p.value != null);
    const weight = have.reduce((n, p) => n + p.size, 0);
    const value = weight > 0 ? Math.round((have.reduce((n, p) => n + p.size * (p.value as number), 0) / weight) * 100) / 100 : null;
    return { name, total, value, box: { x: 0, y: 0, w: 0, h: 0 }, head: 0, tiles: list };
  });
  groups.sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
  const boxes = squarify(groups.map((g) => g.total), { x: 0, y: 0, w, h });
  groups.forEach((g, i) => {
    g.box = boxes[i];
    g.head = o.group !== "none" && g.box.w >= HEAD_MIN_W && g.box.h >= HEAD_MIN_H ? HEAD : 0;
    const inner = squarify(g.tiles.map((p) => p.size), { x: g.box.x, y: g.box.y + g.head, w: g.box.w, h: g.box.h - g.head });
    g.tiles.forEach((p, j) => { p.box = inner[j]; });
  });
  return { groups, left_out };
}

/** The words a tile of `w` × `h` px has room for: the font size (15, 12 or 10px; 0 for none) and whether the figure goes under the
 * symbol. `width(text, weight)` is the text's width at 10px in the page's font; a width grows with the size. Nothing is shown
 * that its tile would cut. */
export function tileWords(symbol: string, figure: string, w: number, h: number, width: (text: string, weight: number) => number): { px: number; fig: boolean } {
  const room = w - 7;                                                    // the tile's padding and a pixel to spare
  const fits = (px: number) => (width(symbol, 600) * px) / 10 + symbol.length * 0.01 * px <= room;
  const px = w >= 120 && h >= 72 && fits(15) ? 15 : w >= 56 && h >= 28 && fits(12) ? 12 : h >= 15 && fits(10) ? 10 : 0;
  const fig = px > 0 && h >= (px === 15 ? 46 : px === 12 ? 34 : 28) && (width(figure, 400) * px * 0.92) / 10 <= room;
  return { px, fig };
}
