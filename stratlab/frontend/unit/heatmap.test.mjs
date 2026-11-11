// The heatmap (L4): the treemap's geometry, the colour steps and the legend, which figure a tile is coloured and sized by, the
// palette's text contrast in both themes, and that the page is a lazy route with a menu entry and a link from a theme.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import { FULL, PERIODS, colorValue, groupName, layout, legend, matches, sizeValue, squarify, step, stepClass, tileWords } from "../src/lib/heatmap.ts";

// the app's own files import each other without ".ts"
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const tile = (s, o = {}) => ({ s, n: `${s} Ltd`, sec: "Energy", ind: "Refineries", cap: 100, px: 50, r: [1, 2, 3, 4, 5, 6], vx: 1.2, tv: 500, ...o });
const area = (r) => r.w * r.h;
const overlap = (a, b) => Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 1e-6 && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 1e-6;

test("squarify gives each value its share of the box, inside it, with no two rectangles overlapping", () => {
  const values = [500, 300, 120, 50, 20, 6, 3, 1];
  const box = { x: 10, y: 20, w: 800, h: 500 };
  const rects = squarify(values, box);
  const total = values.reduce((a, b) => a + b, 0);
  assert.equal(rects.length, values.length);
  rects.forEach((r, i) => {
    assert.ok(Math.abs(area(r) - (values[i] / total) * box.w * box.h) < 1e-6, `area of ${values[i]}`);
    assert.ok(r.x >= box.x - 1e-9 && r.y >= box.y - 1e-9 && r.x + r.w <= box.x + box.w + 1e-6 && r.y + r.h <= box.y + box.h + 1e-6, `inside: ${i}`);
  });
  for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) assert.ok(!overlap(rects[i], rects[j]), `${i} and ${j} overlap`);
  // squarified: the big tiles are close to squares, not slivers
  for (const r of rects.slice(0, 4)) assert.ok(Math.max(r.w / r.h, r.h / r.w) < 3, `ratio ${r.w}x${r.h}`);
});

test("squarify: equal values fill the box evenly; nothing and bad values get empty rectangles", () => {
  const four = squarify([1, 1, 1, 1], { x: 0, y: 0, w: 200, h: 200 });
  for (const r of four) assert.ok(Math.abs(area(r) - 10000) < 1e-6);
  const some = squarify([5, 0, NaN, -2, 5], { x: 0, y: 0, w: 100, h: 50 });
  assert.deepEqual(some.map((r) => Math.round(area(r))), [2500, 0, 0, 0, 2500]);
  assert.deepEqual(squarify([], { x: 0, y: 0, w: 10, h: 10 }), []);
  assert.equal(area(squarify([3], { x: 0, y: 0, w: 0, h: 10 })[0]), 0);
});

test("a tile is coloured by its change, its change less the index's, or its volume against the average", () => {
  const t = tile("A", { r: [1.5, -2, null, 4, 5, 6], vx: 2.4 });
  assert.equal(colorValue(t, "change", "1d", null), 1.5);
  assert.equal(colorValue(t, "change", "1w", null), -2);
  assert.equal(colorValue(t, "change", "1m", null), null);
  assert.equal(colorValue(t, "vs", "1d", [0.4, 1, 1, 1, 1, 1]), 1.1);
  assert.equal(colorValue(t, "vs", "1w", [0.4, 1, 1, 1, 1, 1]), -3);
  assert.equal(colorValue(t, "vs", "1d", null), null);                       // no index figure: nothing to set it against
  assert.equal(colorValue(t, "vs", "1d", [null, 1, 1, 1, 1, 1]), null);
  assert.equal(colorValue(t, "volume", "1y", null), 2.4);
  assert.equal(colorValue(tile("B", { vx: null }), "volume", "1d", null), null);
});

test("a tile is sized by its market value, equally, or by the value traded; one without the figure has no size", () => {
  assert.equal(sizeValue(tile("A", { cap: 250 }), "cap"), 250);
  assert.equal(sizeValue(tile("A", { cap: null }), "cap"), null);
  assert.equal(sizeValue(tile("A", { cap: 0 }), "cap"), null);
  assert.equal(sizeValue(tile("A", { cap: null, tv: null }), "equal"), 1);
  assert.equal(sizeValue(tile("A", { tv: 900 }), "traded"), 900);
});

test("the colour steps: a day's 3% is the strongest, a year's 36%; volume steps at half, one, one and a half, two and three times", () => {
  assert.deepEqual(PERIODS, ["1d", "1w", "1m", "3m", "ytd", "1y"]);
  assert.equal(FULL["1d"], 3);
  assert.equal(FULL["1y"], 36);
  const day = (v) => step(v, "change", "1d");
  assert.deepEqual([0, 0.49, -0.49, 0.5, 1.49, 1.5, 2.99, 3, 12].map(day), [0, 0, 0, 1, 1, 2, 2, 3, 3]);
  assert.deepEqual([-0.5, -1.5, -3, -40].map(day), [-1, -2, -3, -3]);
  assert.equal(step(3, "change", "1y"), 0);                                  // 3% over a year is within a sixth of 36%
  assert.equal(step(-25, "vs", "1y"), -2);
  assert.equal(step(null, "change", "1d"), null);
  assert.deepEqual([0.2, 0.5, 0.99, 1, 1.6, 2, 2.9, 3, 9].map((v) => step(v, "volume", "1d")), [0, 1, 1, 2, 3, 4, 4, 5, 5]);
  assert.deepEqual([-3, -1, 0, 2, 3].map((s) => stepClass(s, "change")), ["hm-d3", "hm-d1", "hm-z", "hm-u2", "hm-u3"]);
  assert.equal(stepClass(4, "volume"), "hm-v4");
  assert.equal(stepClass(null, "change"), "hm-na");
});

test("the legend names every step, the weakest in the middle, in percent, points or multiples", () => {
  const l = legend("change", "1d");
  assert.deepEqual(l.map((x) => x.cls), ["hm-d3", "hm-d2", "hm-d1", "hm-z", "hm-u1", "hm-u2", "hm-u3"]);
  assert.deepEqual(l.map((x) => x.label), ["−3%", "−1.5%", "−0.5%", "0%", "+0.5%", "+1.5%", "+3%"]);
  assert.deepEqual(legend("vs", "1m").map((x) => x.label), ["−12 pts", "−6 pts", "−2 pts", "0 pts", "+2 pts", "+6 pts", "+12 pts"]);
  const v = legend("volume", "1d");
  assert.deepEqual(v.map((x) => x.cls), ["hm-v0", "hm-v1", "hm-v2", "hm-v3", "hm-v4", "hm-v5"]);
  assert.deepEqual(v.map((x) => x.label), ["under 0.5×", "0.5×", "1×", "1.5×", "2×", "3× and up"]);
  // every legend step falls in its own step
  for (const p of PERIODS) for (const x of legend("change", p)) {
    const n = Number(x.label.replace("−", "-").replace("%", ""));
    assert.equal(stepClass(step(n, "change", p), "change"), x.cls, `${p} ${x.label}`);
  }
});

test("search matches the start of a symbol or any part of a name", () => {
  const t = tile("HDFCBANK", { n: "HDFC Bank Limited" });
  for (const q of ["", "  ", "hdfc", "HDFCB", "bank lim", " Bank "]) assert.ok(matches(t, q), q);
  for (const q of ["fcbank", "icici", "x"]) assert.ok(!matches(t, q), q);
});

test("the layout groups the tiles, the largest group and tile first, under each group's name, and leaves out tiles with no size", () => {
  const tiles = [tile("A", { cap: 600, sec: "Energy" }), tile("B", { cap: 300, sec: "Banks", r: [4, 0, 0, 0, 0, 0] }), tile("C", { cap: 100, sec: "Banks", r: [-2, 0, 0, 0, 0, 0] }),
    tile("D", { cap: null, sec: "Banks" }), tile("E", { cap: 50, sec: null })];
  const l = layout(tiles, { size: "cap", color: "change", period: "1d", group: "sector" }, 1000, 600);
  assert.equal(l.left_out, 1);
  assert.deepEqual(l.groups.map((g) => g.name), ["Energy", "Banks", "Other"]);
  assert.deepEqual(l.groups[1].tiles.map((p) => p.tile.s), ["B", "C"]);
  assert.equal(l.groups[1].value, 2.5);                                      // (300 × 4 + 100 × −2) / 400
  const whole = l.groups.reduce((n, g) => n + area(g.box), 0);
  assert.ok(Math.abs(whole - 600000) < 1e-3);
  for (const g of l.groups) {
    assert.equal(g.head, 20);
    for (const p of g.tiles) {
      assert.ok(p.box.y >= g.box.y + g.head - 1e-6 && p.box.y + p.box.h <= g.box.y + g.box.h + 1e-6 && p.box.x >= g.box.x - 1e-6 && p.box.x + p.box.w <= g.box.x + g.box.w + 1e-6, p.tile.s);
    }
  }
  // B is three times C inside Banks
  const [b, c] = l.groups[1].tiles;
  assert.ok(Math.abs(area(b.box) / area(c.box) - 3) < 1e-6);
  // no grouping: one group with no name strip; equal sizes keep every tile, the one without a market value too
  const flat = layout(tiles, { size: "equal", color: "volume", period: "1d", group: "none" }, 500, 500);
  assert.equal(flat.groups.length, 1);
  assert.equal(flat.groups[0].head, 0);
  assert.equal(flat.groups[0].tiles.length, 5);
  assert.equal(flat.left_out, 0);
  // a theme's tiles by layer; a group too small for a name strip has none
  assert.equal(groupName(tile("A", { layer: "Makers" }), "layer"), "Makers");
  assert.equal(groupName(tile("A", { ind: null, sec: "Energy" }), "industry"), "Energy");
  const small = layout(tiles, { size: "cap", color: "change", period: "1d", group: "sector" }, 90, 60);
  assert.ok(small.groups.every((g) => g.head === 0));
});

test("a tile shows its symbol and figure only at a size they fit at, so no word is cut by its tile", () => {
  const width = (text) => text.length * 6.5;                                 // every letter 6.5px wide at 10px
  assert.deepEqual(tileWords("TCS", "+1.2%", 200, 120, width), { px: 15, fig: true });
  assert.deepEqual(tileWords("TCS", "+1.2%", 80, 40, width), { px: 12, fig: true });
  assert.deepEqual(tileWords("TCS", "+1.2%", 80, 30, width), { px: 12, fig: false });       // room for one line only
  assert.deepEqual(tileWords("TCS", "+1.2%", 40, 40, width), { px: 10, fig: true });
  assert.deepEqual(tileWords("HINDUNILVR", "+1.2%", 60, 40, width), { px: 0, fig: false }); // ten letters need 66px at the smallest size
  assert.deepEqual(tileWords("HINDUNILVR", "+1.2%", 75, 40, width), { px: 10, fig: true });
  assert.deepEqual(tileWords("MAHINDRAHOLIDAYS", "+1.2%", 140, 80, width), { px: 12, fig: true }); // too long for the largest size here
  assert.deepEqual(tileWords("TCS", "+1.2%", 40, 12, width), { px: 0, fig: false });         // too short for a line
  // whatever is shown fits its tile's width
  for (const sym of ["A", "ITC", "RELIANCE", "BAJAJ-AUTO", "MAHINDRAHOLIDAYS"]) for (let w = 10; w <= 260; w += 7) {
    const { px, fig } = tileWords(sym, "−12.5 pts", w, 90, width);
    if (px) assert.ok((width(sym, 600) * px) / 10 <= w - 6, `${sym} at ${px}px in ${w}px`);
    if (fig) assert.ok((width("−12.5 pts", 400) * px * 0.92) / 10 <= w - 6, `figure at ${px}px in ${w}px`);
  }
});

test("the palette: every step's text reads on it at 4.5:1 in light and dark, each arm gets stronger step by step, and the two dark copies match", () => {
  const css = read("src/components/chart/treemap.css");
  const block = (re) => { const m = css.match(re); assert.ok(m, String(re)); return Object.fromEntries([...m[1].matchAll(/(--heat-[\w]+):\s*(#[0-9A-Fa-f]{6})/g)].map((x) => [x[1], x[2]])); };
  const light = block(/\n\.hm-page \{([^}]*)\}/), dark = block(/:root\[data-theme="dark"\] \.hm-page \{([^}]*)\}/), system = block(/:root:not\(\[data-theme\]\) \.hm-page \{([^}]*)\}/);
  assert.deepEqual(dark, system);
  assert.equal(Object.keys(light).length, 16);
  assert.deepEqual(Object.keys(light).sort(), Object.keys(dark).sort());
  const lum = (hex) => { const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const text = Object.fromEntries([...css.matchAll(/\.hm-(\w+) \{ background: var\(--heat-(\w+)\); color: var\(--heat-(ink|on)\); \}/g)].map((m) => { assert.equal(m[1], m[2]); return [m[1], m[3]]; }));
  assert.equal(Object.keys(text).length, 14);
  for (const [name, t] of [["light", light], ["dark", dark]]) {
    for (const [stepName, on] of Object.entries(text)) {
      const r = ratio(t[`--heat-${stepName}`], t[`--heat-${on}`]);
      assert.ok(r >= 4.5, `${name} ${stepName}: ${r.toFixed(2)}`);
    }
    // away from the surface, step by step: each arm of the change scale, and the volume scale
    const away = (keys) => keys.map((k) => ratio(t[`--heat-${k}`], t["--heat-on"]));
    for (const arm of [["z", "u1", "u2", "u3"], ["z", "d1", "d2", "d3"], ["v0", "v1", "v2", "v3", "v4", "v5"]]) {
      const c = away(arm);
      for (let i = 1; i < c.length; i++) assert.ok(c[i] > c[i - 1] - (arm[0] === "z" && i === 1 ? 0.2 : 0), `${name} ${arm[i - 1]} -> ${arm[i]}: ${c[i - 1].toFixed(2)} -> ${c[i].toFixed(2)}`);
    }
  }
});

test("the page is a lazy route with a menu entry, a deep link and a feature card, and a theme links to its own heatmap", async () => {
  const main = read("src/main.tsx");
  assert.match(main, /const HeatmapPage = page\(\(\) => import\("\.\/pages\/HeatmapPage"\), "HeatmapPage"\);/);
  assert.match(main, /<Route path="\/invest\/heatmap" element=\{<HeatmapPage \/>\} \/>/);
  assert.ok(!/^import .*HeatmapPage/m.test(main), "the page is loaded when opened, not with the first download");
  const { locate } = await import("../src/lib/nav.ts");
  const { isAppPath } = await import("../src/lib/deepLinks.ts");
  const at = locate("/invest/heatmap");
  assert.equal(at.group.id, "market-today");
  assert.equal(at.page.label, "Heatmap");
  assert.ok(isAppPath("/invest/heatmap"));
  assert.match(read("src/lib/features.ts"), /id: "heatmap", title: "Heatmap",[^\n]*to: "\/invest\/heatmap"/);
  // only the page (and so its own chunk) draws the treemap and loads its CSS
  const page = read("src/pages/HeatmapPage.tsx");
  assert.match(page, /import \{ Treemap, TreemapLegend \} from "\.\.\/components\/chart\/Treemap";/);
  assert.match(read("src/components/chart/Treemap.tsx"), /import "\.\/treemap\.css";/);
  assert.ok(!read("src/styles.css").includes(".hm-"), "the heatmap's CSS stays out of the first download's stylesheet");
  assert.match(page, /<Working /);                                           // loading is the kit's moving bar
  assert.match(page, /params.get\("view"\) === "table"/);                                    // every company is also a table row
  assert.match(read("src/pages/ThemesPage.tsx"), /to=\{`\/invest\/heatmap\?theme=\$\{encodeURIComponent\(q\)\}&region=\$\{region\}`\}/);
});

test("facts only: no advice words and no data source's name on the page", () => {
  const text = read("src/pages/HeatmapPage.tsx") + read("src/components/chart/Treemap.tsx");
  const quoted = [...text.matchAll(/"([^"\n]{12,})"|`([^`\n]{12,})`|>([^<>{}\n]{12,})</g)].map((m) => m[1] ?? m[2] ?? m[3]).join("\n");
  assert.ok(!/\b(buy|sell|hold|accumulate|avoid|cheap|expensive|bullish|bearish|should|recommend)\b/i.test(quoted), quoted.match(/\b(buy|sell|hold|accumulate|avoid|cheap|expensive|bullish|bearish|should|recommend)\b/i)?.[0]);
  assert.ok(!/kite|zerodha|yahoo|screener\.in|finnhub|edgar|nseindia/i.test(text));
});
