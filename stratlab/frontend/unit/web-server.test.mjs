// The Railway web server (Caddyfile) keeps vercel.json's rules while the site moves off Vercel: every path vercel.json forwards to the API
// is forwarded, the app's routes fall back to index.html, and every header vercel.json sets is set with the same value.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const vercel = JSON.parse(fs.readFileSync(new URL("../vercel.json", import.meta.url), "utf8"));
const caddy = fs.readFileSync(new URL("../Caddyfile", import.meta.url), "utf8");
const API = "https://stratlab-production-ca25.up.railway.app";

test("every path vercel.json forwards to the API is forwarded by the Caddyfile", () => {
  const apiLine = caddy.split("\n").find((l) => l.trim().startsWith("@api path"));
  assert.ok(apiLine, "the @api matcher");
  const paths = apiLine.trim().split(/\s+/).slice(2);
  for (const r of vercel.rewrites.filter((x) => x.destination.startsWith(API))) {
    const src = r.source.replace(/\/:[a-z]+\*$/, "").replace(/\/:[a-z]+/g, "");
    const covered = paths.some((p) => p === r.source || p === `${src}/*` || (p.endsWith("/*") && src.startsWith(p.slice(0, -2))));
    assert.ok(covered, `${r.source} is forwarded`);
    if (/:path\*$/.test(r.source)) assert.ok(paths.includes(src), `${src} itself is forwarded, as :path* matches it`);
  }
  assert.ok(caddy.includes(API), "to the API host");
});

test("the app's routes are answered by index.html as vercel.json's rewrite does", () => {
  const spa = vercel.rewrites.find((x) => x.destination === "/index.html");
  const inner = spa.source.slice(2, -1);                 // /(... ) -> ...
  const words = inner.match(/[a-z-]+/g);
  const appRe = caddy.match(/path_regexp app \^\/\((.+)\)\$/)[1];
  for (const w of new Set(words)) assert.ok(new RegExp(`(^|[|(])${w}([|)]|$)`).test(appRe), `route ${w}`);
});

test("every header vercel.json sets is set by the Caddyfile with the same value", () => {
  for (const block of vercel.headers) {
    for (const { key, value } of block.headers) {
      if (key.startsWith("x-vercel")) continue;            // Vercel's own edge cache switch: nothing to carry
      assert.ok(caddy.includes(`${key} "${value}"`), `${block.source}: ${key}`);
    }
  }
});
