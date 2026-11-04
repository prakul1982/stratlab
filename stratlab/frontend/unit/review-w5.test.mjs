// The REVIEW lane (Wed 4 Nov): Instinct's UI items (the tour's address, dialogs over every layer, Market Watch's corner panel
// clear of the page's buttons) and the review rounds' fixes. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("/tour is the app's address for the tour: routed, sent to the app by the site and the offline worker, named for a visitor", async () => {
  const { isAppPath, describePath } = await import("../src/lib/deepLinks.ts");
  assert.ok(isAppPath("/tour"));
  assert.equal(describePath("/tour").what, "the tour");
  assert.match(read("src/main.tsx"), /<Route path="\/tour" element=\{<TourRoute \/>\} \/>/);
  assert.match(read("src/main.tsx"), /nav\("\/", \{ replace: true \}\)[\s\S]{0,200}openTour/);
  const v = JSON.parse(read("vercel.json"));
  const app = v.rewrites.find((r) => r.destination === "/index.html");
  assert.ok(new RegExp(`^${app.source}$`).test("/tour"));
  // the app's pages: never kept stale, and not for search engines
  const pages = v.headers.filter((x) => x.source.includes("|help|"));
  assert.equal(pages.length, 2);
  for (const h of pages)
    assert.ok(new RegExp(`^${h.source}$`).test("/tour"), h.source.slice(0, 30));
  assert.match(read("public/sw.js"), /\|tour\|/);
});

test("Instinct #11: a dialog is drawn at the end of the page and above Market Watch's panel and the cookie question", () => {
  const d = read("src/components/kit/Dialog.tsx");
  assert.match(d, /return createPortal\(\s*<div className="modal-back"/);
  assert.match(d, /<\/div>,\s*document\.body,\s*\);/);
  const css = read("src/styles.css");
  const z = (sel) => Number(css.match(new RegExp(`\\n${sel.replace(".", "\\.")} \\{[^}]*z-index: (\\d+)`))[1]);
  const mw = Number(read("src/components/watch/watch.css").match(/\.mw \{[^}]*z-index: (\d+)/)[1]);
  assert.ok(z(".modal-back") > mw && z(".modal-back") > z(".consent") && z(".modal-back") < z(".toast"));
});

test("Instinct #11: a docked panel floating on a laptop is at most half the window high, and the page's end clears it", async () => {
  const { drawnHeight, cornerCover, DEFAULT_LAYOUT, MIN_H } = await import("../src/lib/watchLayout.ts");
  const open = { ...DEFAULT_LAYOUT, open: true };
  assert.equal(drawnHeight(open, 1280, 720), 360);
  assert.equal(drawnHeight(open, 1280, 560), MIN_H);
  assert.equal(drawnHeight(open, 1700, 720), 560);                                // docked: the window's height, as before
  assert.equal(drawnHeight({ ...open, mode: "float", x: 10, y: 10 }, 1280, 720), 560);   // floated on purpose: the person's own height
  assert.equal(cornerCover(open, 1280, 720), 376);
  assert.equal(cornerCover({ ...open, open: false }, 1280, 720), 0);
  assert.equal(cornerCover(open, 1700, 720), 0);
  assert.equal(cornerCover(open, 390, 800), 0);                                   // a phone's sheet
  assert.equal(cornerCover({ ...open, mode: "float", x: 10, y: 10 }, 1280, 720), 0);   // moved off the corner
  assert.match(read("src/components/watch/launcher.css"), /body\.mw-cover \.shell > \.main \{ padding-bottom: calc\(var\(--mw-cover, 0px\) \+ 24px\); \}/);
});
