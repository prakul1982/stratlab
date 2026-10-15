// Review round 29A: public pages promise no Telegram, the Privacy page quotes the Account buttons, the meta description's
// options are paper trading's, the /library phone menu opens under its button, and one AI providers count.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R29A-002: the landing page, All features and the alerts help say phone or email, not Telegram", () => {
  assert.match(read("src/pages/Login.tsx"), /On your phone or by email, including every paper trade\./);
  assert.doesNotMatch(read("src/pages/Login.tsx"), /Telegram/);
  assert.match(read("src/lib/features.ts"), /what: "On your phone or by email for each trade/);
  assert.doesNotMatch(read("src/lib/help.ts"), /alerts: "Get a Telegram/);
  const legal = read("src/pages/LegalPage.tsx");
  assert.match(legal, /a Telegram chat ID if Telegram is offered in Settings and you connect it/);
  assert.match(legal, /Telegram delivers them if it is offered in Settings and you connect it/);
});

test("R29A-005: Privacy quotes the Account buttons as they read, with one updated date", () => {
  const legal = read("src/pages/LegalPage.tsx"), account = read("src/pages/AccountPage.tsx");
  for (const label of ["Download all my data", "Delete all my data"]) {
    assert.match(legal, new RegExp(`"${label}"`));
    assert.ok(account.includes(label), label);
  }
  assert.doesNotMatch(legal, /"Download everything"/);
  assert.match(legal, /"\/privacy": "15 October 2026"/);
  assert.match(read("../backend/app/site_pages.py"), /\("\/privacy", "2026-10-15"\)/);
});

test("R29A-008: the description's options are paper trading's", () => {
  for (const f of ["src/content/seo.ts", "index.html"]) {
    const s = read(f);
    assert.match(s, /paper trade them, options too\./, f);
    assert.doesNotMatch(s, /options included/, f);
  }
});

test("R29A-009: beside a page's own wide button the phone Menu's list opens under the button", () => {
  assert.match(read("src/components/PublicFrame.tsx"), /lp-menu pub-menu\$\{action \? " pub-menu-start" : ""\}/);
  assert.match(read("src/styles.css"), /\.pub-nav \.pub-menu-start nav \{ left: 0; right: auto; \}/);
});

test("R29A-014: System counts the AI providers as Overview does", () => {
  const panel = read("src/pages/admin/AIPanel.tsx");
  assert.match(panel, /aiCountText\(on\.filter\(\(p\) => p\.result === "working"\)\.length, on\.length, v\.providers\.length\)/);
  assert.doesNotMatch(panel, /providers set up\. Each/);
});
