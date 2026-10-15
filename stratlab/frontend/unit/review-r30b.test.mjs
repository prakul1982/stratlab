// Live visitor review, round 30 (phone and deploy robustness). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R30-003: a chunk that fails after a deploy reloads the page once; the error card shows only if the reload also fails", async () => {
  const { importWithRetry } = await import("../src/lib/lazyRetry.ts");
  let reloads = 0, shown = 0;
  const store = new Map();
  const win = { addEventListener() {}, location: { reload: () => { reloads += 1; } } };
  win.__stratlabRecover = undefined;
  const root = { querySelector: () => ({}), textContent: "", appendChild: () => { shown += 1; } };
  const el = () => ({ setAttribute() {}, appendChild() {}, addEventListener() {}, className: "", style: {} });
  const sandbox = {
    window: win, document: { getElementById: () => root, createElement: el, documentElement: { dataset: {} } },
    sessionStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    localStorage: { getItem: () => null }, setTimeout: () => 0, Date, Number, String, location: win.location,
  };
  new Function(...Object.keys(sandbox), read("public/boot.js"))(...Object.values(sandbox));
  globalThis.window = win;
  try {
    const gone = () => importWithRetry(async () => { throw new Error("Failed to fetch dynamically imported module: /assets/Old-abc.js"); }, [1], 5);
    await assert.rejects(gone());
    assert.equal(reloads, 1, "the first failure reloads on its own");
    assert.equal(shown, 0);
    await assert.rejects(gone());
    assert.equal(reloads, 1, "the guard in sessionStorage stops a second reload");
    assert.equal(shown, 1, "then the error card shows");
  } finally { delete globalThis.window; }
});

test("R30-003: the app's entry page is never served stale", () => {
  const v = JSON.parse(read("vercel.json"));
  const rule = (src) => v.headers.find((h) => h.source === src);
  const cc = (h) => h.headers.find((x) => x.key === "Cache-Control").value;
  assert.match(cc(rule("/config.js")), /must-revalidate/);
  const pages = v.headers.find((h) => h.source.includes("index.html"));
  assert.equal(cc(pages), "no-cache");
  const re = new RegExp(`^${pages.source}$`);
  for (const path of ["/", "/paper", "/research/US/NVDA", "/index.html"]) assert.ok(re.test(path), path);
  assert.ok(!re.test("/assets/x.js"));
  assert.match(cc(rule("/assets/(.*)")), /immutable/);
});

test("R30-009: on a phone the banner's dismiss is an icon on the text's row, 40 px, labelled Dismiss", () => {
  const main = read("src/main.tsx");
  assert.match(main, /promo-got"[^>]*aria-label="Dismiss"/);
  const css = read("src/styles.css");
  assert.match(css, /\.promo-banner \.promo-got \{[^}]*min-width: 40px; min-height: 40px/);
});

test("R30-010: on a phone the paper session cards stack inside the page", () => {
  assert.match(read("src/pages/trade/paper.css"), /max-width: 640px\) \{\s*\.k-sessions \{ flex-direction: column; overflow-x: visible; \}\s*\.k-sess \{ min-width: 0; width: 100%/);
});

test("R30-013: the scan line names the number of stocks from the first render", async () => {
  const { scanningText } = await import("../src/lib/scanText.ts");
  assert.equal(scanningText(20), "Scanning 20 stocks…");
  assert.equal(scanningText(1), "Scanning 1 stock…");
  assert.equal(scanningText(undefined), "Scanning…");
});
