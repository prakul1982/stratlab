// SECMEM lane (Wed 4 Nov): HSTS on the site, sign-in by PKCE (no session token in the address), the emailed links' trade.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("SECMEM 1a: every page is sent with HSTS (a year, subdomains, no preload yet) beside the unchanged CSP", () => {
  const all = JSON.parse(read("vercel.json")).headers.find((h) => h.source === "/(.*)").headers;
  const v = (k) => all.find((h) => h.key === k)?.value;
  assert.equal(v("Strict-Transport-Security"), "max-age=31536000; includeSubDomains");
  assert.match(v("Content-Security-Policy"), /^default-src 'self'; script-src 'self' /);
});

test("SECMEM 1b: the sign-in client uses PKCE, never the implicit flow", () => {
  const api = read("src/lib/api.ts");
  assert.match(api, /flowType: "pkce"/);
  assert.doesNotMatch(api, /flowType: "implicit"/);
});

test("SECMEM 1b: an emailed link's hashed token is read, and the address is cleaned of it", async () => {
  const { emailLinkIn, withoutEmailLink, hasAuthInUrl, wantsAccount } = await import("../src/lib/entry.ts");
  assert.deepEqual(emailLinkIn("?token_hash=0123456789abcdef&type=magiclink"), { token_hash: "0123456789abcdef", type: "magiclink" });
  assert.equal(emailLinkIn("?token_hash=0123456789abcdef&type=signup"), null);       // only the sign-in links Admin sends
  assert.equal(emailLinkIn("?token_hash=<x>&type=magiclink"), null);
  assert.equal(emailLinkIn("?tab=deals"), null);
  assert.equal(withoutEmailLink("https://stratlab.studio/?token_hash=abcdefgh12&type=magiclink"), "/");
  assert.equal(withoutEmailLink("https://stratlab.studio/mine?tab=a&token_hash=abcdefgh12&type=magiclink#x"), "/mine?tab=a#x");
  assert.equal(hasAuthInUrl("?code=abc", ""), true);                                   // Google's PKCE return
  assert.equal(wantsAccount({ search: "?token_hash=abcdefgh12&type=magiclink", storage: { getItem: () => null } }), true);
});

test("SECMEM 6: a finished whole-market check refreshes every 5 min, not every 30 s, and a source's error isn't 'not checked yet'", () => {
  const src = read("src/pages/admin/AuditPanel.tsx");
  assert.match(src, /const moving = !!\(m\?\.due \|\| m\?\.full\?\.running \|\| m\?\.current\);/);
  assert.match(src, /window\.setInterval\(load, moving \? 30000 : 300000\)/);
  assert.match(src, /m\.pending === \(sum\?\.pending \?\? 0\) \? "not checked yet" : "a source turned away"/);
});
