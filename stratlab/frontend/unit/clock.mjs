// One fixed moment for every unit test (CLOCK follow-up, owner 4 Nov: "fix things globally"): loaded before each test
// file (package.json test:unit, node --import), so a test that reads the clock (new Date(), Date.now()) gets the browser
// tests' moment, Wed 28 Oct 2026 11:00 IST (e2e/fixtures.ts E2E_NOW), running on from there; and the machine's time zone
// is UTC (as on CI) unless a test names its own. Tests passed in October and failed in November: a fixed end date that
// had passed (review-5d B6), a reader's zone that left summer time on 1 Nov (zones), a check just past India's midnight.
// UNIT_NOW=<ISO with zone> picks another moment, UNIT_NOW=real the machine's clock.
import { readFileSync } from "node:fs";

process.env.TZ ||= "UTC";
const named = readFileSync(new URL("../e2e/fixtures.ts", import.meta.url), "utf8").match(/export const E2E_NOW = "([^"]+)"/)?.[1];
const want = process.env.UNIT_NOW || named;
if (!want) throw new Error("unit/clock.mjs: E2E_NOW not found in e2e/fixtures.ts");
if (want !== "real") {
  const Real = Date, started = Real.now(), at = Real.parse(want);
  if (Number.isNaN(at)) throw new Error(`unit/clock.mjs: ${want} is not a moment`);
  const now = () => at + (Real.now() - started);
  class FixedDate extends Real {
    constructor(...a) { if (a.length === 0) super(now()); else super(...a); }
    static now() { return now(); }
  }
  // Date() called without new gives now's text, as the real one does
  globalThis.Date = new Proxy(FixedDate, { apply: () => new FixedDate().toString() });
}
