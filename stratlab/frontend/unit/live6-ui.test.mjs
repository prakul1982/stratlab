// LIVE6 (11 Nov review), lane p2-ui: the app UI and privacy fixes that can be checked without a browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// a source file's own imports name no extension ("./api"): try ".ts" (as unit/live5.test.mjs does)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("LIVE6-012: the search box's theme list is the shared library, never worded as this account's reading", async () => {
  const { libraryLabel, LIBRARY_HEAD } = await import("../src/lib/themeFormat.ts");
  const day = (iso) => ({ "2026-11-11": "11 Nov" })[iso] ?? iso;
  assert.equal(LIBRARY_HEAD, "Ready to open:");
  assert.equal(libraryLabel({ name: "Cybersecurity", region: "US", at: "2026-11-11T09:12:00Z" }, day), "Cybersecurity · US, updated 11 Nov");
  assert.equal(libraryLabel({ name: "Automotive", region: "IN", at: null }, day), "Automotive · India");
  const page = src("pages/ThemesPage.tsx");
  assert.doesNotMatch(page, /Already read:|, read \$\{/);
  assert.match(page, /\{LIBRARY_HEAD\}/);
});

test("LIVE6-005: the heatmap's note says which theme companies are grey at their last price and which have nothing", async () => {
  const { closesNote } = await import("../src/lib/heatmap.ts");
  assert.equal(closesNote({ members: 16, with_prices: 16, price_only: 0 }, "in the theme"), null);
  assert.equal(closesNote({ members: 16, with_prices: 14, price_only: 2 }, "in the theme"),
    "2 of the 16 companies in the theme have no closes on record yet and are shown in grey at the last price.");
  assert.equal(closesNote({ members: 16, with_prices: 14, price_only: 1 }, "in the theme"),
    "1 of the 16 companies in the theme has no closes on record yet and is shown in grey at the last price. 1 of the 16 companies in the theme has no closes or price on record and is not shown.");
  assert.equal(closesNote({ members: 500, with_prices: 498 }, "in this group"), "2 of the 500 companies in this group have no closes or price on record and are not shown.");
  assert.doesNotMatch(src("pages/HeatmapPage.tsx"), /have no stored closes and are not shown/);
});

test("LIVE6-013: a docked panel takes its column at 1440 and goes with every page; a floating one stays on the page it was opened on", async () => {
  const L = await import("../src/lib/watchLayout.ts");
  const dock = { ...L.DEFAULT_LAYOUT, open: true, mode: "dock", w: 380, at: "/breadth" };
  assert.equal(L.shapeOf(dock, 1440), "dock");
  assert.equal(L.dockWidth(dock, 1440), 380);                         // the page reflows beside it: 1060px left for the page
  assert.ok(1440 - L.dockWidth({ ...dock, w: 720 }, 1440) >= L.PAGE_MIN);
  assert.equal(L.showsOn(dock, 1440, "/research/rotation"), true);    // docked: on every page
  const float = { ...dock, mode: "float" };
  assert.equal(L.showsOn(float, 1440, "/breadth"), true);
  assert.equal(L.showsOn(float, 1440, "/research/rotation"), false);  // reached by a link or by its address alike: not over the next page
  assert.equal(L.showsOn({ ...dock, mode: "dock" }, 1280, "/research/rotation"), false);   // too narrow to dock: floats, so the same rule
  assert.equal(L.showsOn({ ...float, at: null }, 1440, "/x"), true);  // kept before pages were kept: shown as it was
  assert.equal(L.showsOn({ ...float, open: false }, 1440, "/breadth"), false);
  assert.equal(L.clampLayout({ ...float }, 1440, 900).at, "/breadth");
  assert.equal(L.clampLayout({ ...float, at: "javascript:x" }, 1440, 900).at, undefined);
  const launcher = src("components/watch/Launcher.tsx");
  assert.match(launcher, /showsOn\(layout, vw, pathname\)/);
  assert.match(launcher, /at: window\.location\.pathname/);
});

test("LIVE6-013: the panel opens on the prices last seen on this device, per person, and reads replace them", async () => {
  const Q = await import("../src/lib/watchQuotes.ts");
  const mem = new Map();
  const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  const q = (price, at = "2026-11-11T10:00:00Z") => ({ price, change: 1, change_pct: 0.5, prev_close: price - 1, at, currency: "INR", stale: false });
  const now = Date.parse("2026-11-11T10:00:00Z");
  assert.deepEqual(Q.keptQuotes("u1", now, store), {});
  Q.keepQuotes("u1", { "IN:INFY": q(1500), "IN:TCS": null, "US:AAPL": { ...q(null) } }, now, store);
  assert.deepEqual(Object.keys(Q.keptQuotes("u1", now, store)), ["IN:INFY"]);       // a quote without a price is not kept
  assert.equal(Q.keptQuotes("u1", now, store)["IN:INFY"].price, 1500);
  assert.equal(Q.keptQuotes("u1", now, store)["IN:INFY"].seen, undefined);
  assert.deepEqual(Q.keptQuotes("u2", now, store), {});                              // another person on the device sees none of it
  Q.keepQuotes("u1", { "IN:INFY": q(null) }, now + 1, store);
  assert.equal(Q.keptQuotes("u1", now + 1, store)["IN:INFY"].price, 1500);           // never replaced by a quote without a price
  assert.deepEqual(Q.keptQuotes("u1", now + 8 * 24 * 3600 * 1000, store), {});      // older than a week: not shown
  assert.deepEqual(Q.keptQuotes("u1", now, { getItem: () => { throw new Error("denied"); } }), {});
  mem.set(`${Q.QUOTES_KEY}.u1`, "not json");
  assert.deepEqual(Q.keptQuotes("u1", now, store), {});
  const panel = src("components/watch/WatchPanel.tsx");
  assert.match(panel, /useState<Record<string, WatchQuote \| null>>\(\(\) => keptQuotes\(/);
});

test("LIVE6-014: signed in, the analytics question is an overlay along the foot that never moves the app", () => {
  const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /body:has\(\.shell\) \.consent \{ position: fixed; \}/);
  assert.doesNotMatch(css, /\.consent \{ position: relative/);
  assert.doesNotMatch(css, /body:has\(\.shell\) \.mw-launch \{ bottom: calc\(16px \+ env/);   // the Markets button rises above the bar again
});

test("LIVE6-016: on the Themes page only the menu's Themes entry is highlighted; the pill is a plain link there", () => {
  const shell = src("components/Shell.tsx"), css = src("styles.css");
  assert.match(shell, /className=\{`side-feature\$\{path\.startsWith\(THEMES\) \? " here" : ""\}`\}/);
  const here = css.match(/\.side-list a\.side-feature\.here \{([^}]*)\}/)?.[1] ?? "";
  assert.match(here, /background: none/);
  assert.match(here, /border-color: var\(--line-2\)/);                 // no orange edge: it doesn't read as selected
  assert.doesNotMatch(here, /orange/);
});

test("LIVE6-019: on a phone the heatmap's settings fold into one row with Options; the period stays out", () => {
  const page = src("pages/HeatmapPage.tsx"), css = src("components/chart/treemap.css");
  assert.match(page, /className=\{`hm-controls\$\{opts \? "" : " folded"\}`\}/);
  assert.match(page, /aria-expanded=\{opts\} aria-controls="hm-controls"/);
  assert.match(css, /\.hm-fold \{ display: none; \}/);                                          // wider screens: as before
  const phone = css.slice(css.indexOf("LIVE6-019"), css.indexOf("/* the search box in the map card's header row"));
  assert.match(phone, /@media \(max-width: 640px\)/);
  assert.match(phone, /\.hm-controls\.folded > \.k-field:not\(:has\(\.k-chipwrap\)\) \{ display: none; \}/);
});
