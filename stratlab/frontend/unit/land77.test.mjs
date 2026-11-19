// Lane land77: LIVE14A-014 / LIVE14B-003, the landing's LCP and the phone's layout shift. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

/** boot.js run on a page at `path`, with a font loading API that answers `answer(descriptor)` (the faces it found, or a rejection). */
function boot(path, answer) {
  const attrs = new Map(), on = { doc: {}, win: {} };
  const html = { dataset: {}, hasAttribute: (k) => attrs.has(k), setAttribute: (k, v) => attrs.set(k, String(v)), getAttribute: (k) => attrs.get(k) ?? null };
  const asked = [];
  const fonts = answer && { load: (f) => { asked.push(f); return answer(f); } };
  const fire = (to) => (e) => (to ?? []).forEach((f) => f(e));
  const win = { addEventListener: (t, f) => { (on.win[t] ??= []).push(f); }, location: { pathname: path, search: "", reload() {} } };
  const sandbox = {
    window: win, location: win.location, setTimeout: () => 0, Date, Number, String, Object, Promise,
    document: { documentElement: html, fonts, getElementById: () => null, querySelector: () => null, addEventListener: (t, f) => { (on.doc[t] ??= []).push(f); } },
    sessionStorage: { getItem: () => null, setItem() {} }, localStorage: { length: 0, key: () => null, getItem: () => null },
  };
  new Function(...Object.keys(sandbox), read("public/boot.js"))(...Object.values(sandbox));
  return { faces: () => attrs.has("data-faces"), asked, docLoad: (e) => fire(on.doc.load)(e), winLoad: () => fire(on.win.load)({}) };
}
const tick = () => new Promise((ok) => setTimeout(ok, 0));

test("LIVE14A-014 / LIVE14B-003: the landing's hero words wait, hidden, for their own faces, at most 3 s, and only on the home page", async () => {
  const css = read("index.html");
  assert.match(css, /@media \(scripting: enabled\) \{ html\[data-home\]:not\(\[data-faces\]\) \.lp-hero-copy \{ visibility: hidden; animation: boot-faces 0s 3s forwards; \} \}/);
  assert.match(css, /@keyframes boot-faces \{ to \{ visibility: visible; \} \}/);
  // no stand-in metrics anywhere: the frame is drawn with the app's own classes and nothing sized for a fallback face (site76's reverted try)
  assert.ok(!/size-adjust|Fraunces Boot|7\.78em/.test(css + read("scripts/seoPages.mjs")));

  // the faces are here: shown
  let b = boot("/", () => Promise.resolve([{}]));
  await tick();
  assert.equal(b.faces(), true);
  // (updated on purpose, site78: the eyebrow's IBM Plex Mono too, whose late arrival re-wrapped it on CI's phone)
  assert.deepEqual(b.asked, ["400 1em Fraunces", "italic 400 1em Fraunces", '400 1em "IBM Plex Sans"', '600 1em "IBM Plex Sans"', '400 1em "IBM Plex Mono"']);
  assert.match(read("scripts/publicFonts.mjs"), /\|ibm-plex-mono-latin-400-normal\)-/);

  // the stylesheet (and its @font-face rules) not here yet: still hidden, looked for again when a stylesheet arrives
  let ready = false;
  b = boot("/", () => Promise.resolve(ready ? [{}] : []));
  await tick();
  assert.equal(b.faces(), false, "no faces known yet: the words stay hidden");
  b.docLoad({ target: { tagName: "SCRIPT" } });
  ready = true;
  await tick();
  assert.equal(b.faces(), false, "only a stylesheet's arrival looks again");
  b.docLoad({ target: { tagName: "LINK" } });
  await tick();
  assert.equal(b.faces(), true, "the stylesheet came with the faces, and they loaded");

  // the page loaded with no such faces (a dev server), or one failed to download: shown at once in whatever the browser has
  b = boot("/", () => Promise.resolve([]));
  await tick();
  b.winLoad();
  await tick();
  assert.equal(b.faces(), true);
  b = boot("/", () => Promise.reject(new Error("NetworkError")));
  await tick();
  assert.equal(b.faces(), true);
  b = boot("/", null);
  assert.equal(b.faces(), true, "no font loading API: shown at once");

  // another address: nothing asked, nothing held (its page has no landing hero)
  b = boot("/pricing", () => Promise.resolve([{}]));
  await tick();
  assert.equal(b.asked.length, 0);
});

test("LIVE14A-014 / LIVE14B-003: the app's hero drawn over the start-up frame on the home page waits for the same faces (at most 1.5 s more)", () => {
  const e = read("src/entry.tsx");
  assert.match(e, /\.map\(\(f\) => document\.fonts\.load\(f\)\)\)\]\)\.then\(heroFaces\)\.catch\(\(\) => undefined\);/);
  const fn = e.match(/function heroFaces\(\): Promise<void> \{([^]*?)\n\}/)[1];
  assert.match(fn, /if \(!html\.hasAttribute\("data-home"\) \|\| html\.hasAttribute\("data-faces"\)\) return Promise\.resolve\(\);/);
  assert.match(fn, /seen\.observe\(html, \{ attributes: true, attributeFilter: \["data-faces"\] \}\);\s*window\.setTimeout\(done, 1500\);/);
});
