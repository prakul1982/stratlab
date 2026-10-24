// Round 80 (22 Oct 2026): the launch check as a signed-out visitor — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R80-001: the Pro card and the FAQ say the same about backtesting options", async () => {
  const { FAQ } = await import("../src/content/faq.ts");
  const opt = FAQ.find((f) => f.q === "Can I backtest options?");
  assert.match(opt.a[0], /^One contract at a time\. On Pro, a notebook can backtest a single listed futures or options contract/);
  assert.doesNotMatch(opt.a[0], /^No\./);
  const plans = read("src/lib/plans.ts");
  assert.match(plans, /in notebooks, each backtested on its own past prices/);
  assert.match(plans, /Options paper trading on your own rules' signals, strikes picked by delta or premium/);        // reworded in DK-003
});

test("R80-005: a losing strategy's line says its checks ran", async () => {
  const { LOST_CHECKS } = await import("../src/lib/tradeUi.ts");
  assert.equal(LOST_CHECKS, "Lost money after costs · its checks are shown for reference");
});

test("R80-010, R80-011: Terms has no pre-launch line and names the paper-trading limit as the plans do", () => {
  const legal = read("src/content/legal.ts");
  assert.doesNotMatch(legal, /billed only once they are on sale/);
  assert.match(legal, /Plan limits \(backtests, AI builds, strategies paper traded at a time\)/);
  assert.doesNotMatch(read("src/content/seo.ts"), /AI builds and paper sessions/);
});

test("R80-012: the library's filter says what all its strategies share", () => {
  assert.match(read("src/components/LibraryBits.tsx"), /v === "edge" \? "No check failed" : l/);
});

test("R80-003: a cold /faq shows the splash, not a one-line page the landing then jumps over", () => {
  assert.match(read("src/visitor/VisitorApp.tsx"), /const words = view\.kind === "landing" && view\.section === "faq" \? "" : heldStartup\(\);/);
});

test("R80-007: the first screen's fonts are asked for by index.html", () => {
  const plugin = read("scripts/publicFonts.mjs");
  assert.match(plugin, /transformIndexHtml/);
  assert.match(plugin, /rel: "preload", href: `\/\$\{f\}`, as: "font", type: "font\/woff2", crossorigin: ""/);
});

test("R80-017, R80-014: public pages' header has the site links on wider screens; the page keeps inside an iPhone's notch", () => {
  assert.match(read("src/components/PublicFrame.tsx"), /<nav className="pub-links" aria-label="Site">/);
  const css = read("src/styles.css");
  assert.match(css, /\.pub-links \{ display: flex;/);
  assert.match(css, /padding-left: env\(safe-area-inset-left, 0px\); padding-right: env\(safe-area-inset-right, 0px\);/);
});
