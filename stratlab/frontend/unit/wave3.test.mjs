// Wave 3: the greeting's first name, the price chart's custom timeframes, and the CSP that lets Admin show an email in a
// sandboxed srcdoc frame. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { firstName } from "../src/lib/format.ts";
import { chartTfCheck } from "../src/lib/intervals.ts";

test("the greeting uses the first name when the profile has one", () => {
  assert.equal(firstName({ full_name: "Asha Rao" }), "Asha");
  assert.equal(firstName({ name: "Vikram Singh Chauhan" }), "Vikram");
  assert.equal(firstName({ given_name: "Meera", full_name: "Rao Meera" }), "Meera");
  assert.equal(firstName({ full_name: "PRIYA SHAH" }), "Priya");
  assert.equal(firstName({ full_name: "rohan" }), "Rohan");
  assert.equal(firstName({ full_name: "McDonald Lee" }), "McDonald");
});

test("no name, an email or digits give no first name, so the greeting has no comma", () => {
  assert.equal(firstName(undefined), "");
  assert.equal(firstName(null), "");
  assert.equal(firstName({}), "");
  assert.equal(firstName({ full_name: "   " }), "");
  assert.equal(firstName({ name: "owner@example.com" }), "");
  assert.equal(firstName({ full_name: "user12345" }), "");
  assert.equal(firstName({ full_name: 42 }), "");
});

test("a custom chart timeframe is kept only when it is a timeframe the chart offers, written another way", () => {
  const offered = ["5m", "15m", "1h", "1d", "1w", "1mo"];
  const ok = chartTfCheck(offered);
  assert.deepEqual(ok(5, "min"), { value: "5m", label: "5 min" });
  assert.deepEqual(ok(60, "min"), { value: "1h", label: "1 hour" });
  assert.deepEqual(ok(24, "h"), { value: "1d", label: "1 day" });
  assert.deepEqual(ok(7, "d"), { value: "1w", label: "1 week" });
  assert.deepEqual(ok(1, "w"), { value: "1w", label: "1 week" });
  assert.deepEqual(ok(1, "mo"), { value: "1mo", label: "1 month" });
  for (const [n, u] of [[7, "min"], [2, "mo"], [3, "w"], [90, "min"]]) assert.ok("error" in ok(n, u), `${n} ${u}`);
  assert.match(ok(7, "min").error, /5 min, 15 min, 1 hour, 1 day, 1 week or 1 month/);
  assert.ok("error" in chartTfCheck(["1d"])(5, "min"), "a size the chart does not offer is refused");
});

test("the app's CSP does not stop a sandboxed srcdoc frame, and nothing in the frame can run scripts", () => {
  const csp = JSON.parse(readFileSync(new URL("../vercel.json", import.meta.url), "utf8")).headers
    .flatMap((h) => h.headers).find((h) => h.key === "Content-Security-Policy").value;
  const dirs = Object.fromEntries(csp.split(";").map((d) => d.trim().split(/\s+/)).filter((d) => d[0]).map(([k, ...v]) => [k, v]));
  // a srcdoc frame is not fetched, so frame-src never sees it; it inherits this policy: scripts stay off, inline styles and https images work
  assert.ok(!dirs["script-src"].includes("'unsafe-inline'") && !dirs["script-src"].includes("'unsafe-eval'"));
  assert.ok(dirs["style-src"].includes("'unsafe-inline'"), "the email's own styles run");
  assert.ok(dirs["img-src"].includes("https:"), "the email's images show");
  assert.ok(!dirs["frame-src"].includes("*") && !dirs["frame-src"].includes("data:"), "no other frames are opened");
  // and the Admin page asks for a frame with no sandbox permissions at all
  const src = readFileSync(new URL("../src/pages/admin/EmailSection.tsx", import.meta.url), "utf8");
  assert.match(src, /sandbox=""/);
  assert.match(src, /srcDoc=/);
  assert.doesNotMatch(src, /allow-scripts|allow-same-origin/);
});

test("Admin is built on the kit: no inline style={{}} and no browser confirm() in its files", () => {
  const dir = new URL("../src/pages/admin/", import.meta.url);
  const files = readdirSync(dir).filter((f) => f.endsWith(".tsx"));
  files.push("../AdminPage.tsx");
  assert.ok(files.length >= 10);
  for (const f of files) {
    const src = readFileSync(new URL(f, dir), "utf8");
    assert.doesNotMatch(src, /style=\{\{/, `${f} has an inline style`);
    assert.doesNotMatch(src, /\bconfirm\(/, `${f} uses a browser confirm()`);
    assert.doesNotMatch(src, /window\.(alert|prompt)\(/, `${f} uses a browser box`);
  }
});
