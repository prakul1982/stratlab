// R21 (owner, 7 Nov): a theme's first deck waits for its AI map: the server answers 202 "preparing", the page shows the kit's loading bar and asks
// again until the file comes (at most 3 minutes), and never shows a raw error.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const answer = (status, body) => ({ status, json: async () => body, blob: async () => new Blob([status === 200 ? "PDF" : ""]) });

test("a deck that is being prepared is asked for again until the file comes, with the bar's words", async () => {
  const { deckWhenReady, PREPARING } = await import("../src/lib/deckReady.ts");
  const replies = [answer(202, { preparing: true, retry_after: 10 }), answer(202, { preparing: true, retry_after: 10 }), answer(200)];
  const waits = [], labels = [];
  let t = 0;
  const blob = await deckWhenReady(async () => replies.shift(), { onWait: (l) => labels.push(l), sleep: async (ms) => { waits.push(ms); t += ms; }, now: () => t });
  assert.equal(await blob.text(), "PDF");
  assert.deepEqual(waits, [10000, 10000]);
  assert.deepEqual(labels, [PREPARING, PREPARING]);
  assert.equal(PREPARING, "Preparing the deck: the AI map is being written");
});

test("it stops after three minutes with plain words, never a raw error, and a bad retry hint is bounded", async () => {
  const { deckWhenReady, DeckNotReady } = await import("../src/lib/deckReady.ts");
  let t = 0, asked = 0;
  await assert.rejects(deckWhenReady(async () => { asked++; return answer(202, { retry_after: 9999 }); }, { sleep: async (ms) => { t += ms; }, now: () => t }),
    (e) => e instanceof DeckNotReady && /still being prepared/.test(e.message) && !/202|HTTP|error/i.test(e.message));
  assert.equal(asked, 7);                      // 30 s at most between asks: at 0, 30 ... 180 s, then it stops
});

test("the theme page's deck buttons go through the wait and show the kit's loading bar", () => {
  const src = readFileSync(new URL("../src/components/ThemeDive.tsx", import.meta.url), "utf8");
  assert.match(src, /deckWhenReady\(\(\) => themeApi\.deck\(region, theme, format\), \{ onWait: setPreparing \}\)/);
  assert.match(src, /\{preparing && <Working small label=\{preparing\} \/>\}/);
});
