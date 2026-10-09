// Round 12 review of the live site (9 Oct 2026), the app's side: a /faq that lands with its heading under the sticky header,
// Admin's two words for the exchange holidays, Pulse's opening line, and Admin → System's ISO dates.
// Every value here is fixed; no clock or weekday matters. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R12-008: a section scrolled to starts below the 71 px sticky header, and stays there while the page above it settles", () => {
  const css = read("src/styles.css");
  const margin = Number(/\.lp-sec \{[^}]*scroll-margin-top: (\d+)px/.exec(css)?.[1]);
  assert.ok(margin >= 72, `scroll-margin-top ${margin}px`);
  const login = read("src/pages/Login.tsx");
  const effect = login.slice(login.indexOf("useLayoutEffect(() => {\n    if (!section) return;"), login.indexOf("useEffect(() => {\n    if (error"));
  // drawn at its section before the first paint, then put back there on every change of the layout above it...
  assert.match(effect, /scrollIntoView\(\{ behavior: "instant" \}\)/);
  assert.match(effect, /new ResizeObserver\(/);
  // ...until the visitor scrolls, touches or presses a key, and for a few seconds at most
  for (const ev of ["wheel", "touchstart", "keydown", "pointerdown"]) assert.ok(effect.includes(`"${ev}"`), ev);
  assert.match(effect, /ro\?\.disconnect\(\)/);
  assert.match(effect, /removeEventListener/);
});

const ov = (days_left) => ({ server: { kite_ready: true, kite_token_day: null, feed_connected: true, live_sessions: 0, india_sessions: 0,
  auto_login: { at: null, ok: true, message: "ok" }, auto_login_configured: true, billing_enabled: true, ai: [], research: { finnhub: true },
  recent_errors: [], server_started_at: "2026-10-09T01:00:00+05:30", calendar: { days_left } }, stats: {} });
const holidaysJob = (state, error) => ({ id: "holidays", name: "Exchange holidays", schedule: "Every day", last_run: null, error, state, running: false,
  log: [], run: [] });

test("R12-010: the Exchange holidays light and Needs your attention say the same thing when the exchange's feed is down", async () => {
  const { attention, services, lights } = await import("../src/pages/admin/attention.ts");
  const down = [holidaysJob("bad", "The exchange feed isn't answering right now.")];
  const cal = services(ov(83), down).find((s) => s.key === "cal");
  assert.equal(cal.state, "warn");
  assert.equal(cal.detail, "Holidays on file for 83 more days · live feed down");
  assert.equal(lights(ov(83), down).services.find((s) => s.key === "cal").detail, cal.detail);
  const todo = attention(ov(83), null, down).map((a) => a.text);
  assert.ok(todo.includes("Exchange holidays: holidays on file for 83 more days · live feed down. The exchange feed isn't answering right now."), todo.join("\n"));
  assert.ok(!todo.some((t) => /only known for/.test(t)));          // 83 days on file is not a shortage
  // with the feed answering: the plain "Known for" and OK, as before
  const ok = services(ov(83), [holidaysJob("ok", null)]).find((s) => s.key === "cal");
  assert.deepEqual([ok.state, ok.detail], ["ok", "Known for 83 more days"]);
  assert.equal(services(ov(83)).find((s) => s.key === "cal").state, "ok");     // a caller with no jobs list: unchanged
  // a real shortage still says so
  assert.ok(attention(ov(20), null, []).some((a) => a.text === "Exchange holidays are only known for 20 more days."));
});

test("R12-011: Pulse's opening line names only the sections the page shows", async () => {
  const { pulseLede } = await import("../src/lib/researchFormat.ts");
  assert.equal(pulseLede(null), "Live index levels and headlines, with an AI read of the mood.");
  assert.equal(pulseLede({ hot: [], flows: [], themes: [] }), "Live index levels and headlines, with an AI read of the mood.");
  assert.equal(pulseLede({ hot: [1], flows: [], themes: [1] }),
    "Live index levels and headlines, with an AI read of the mood, the companies in today's headlines and the themes in play.");
  assert.equal(pulseLede({ hot: [1], flows: [1], themes: [1] }),
    "Live index levels and headlines, with an AI read of the mood, the companies in today's headlines, where money is flowing and the themes in play.");
  const page = read("src/pages/Research.tsx");
  assert.match(page, /lede=\{pulseLede\(ai\)\}/);
  assert.doesNotMatch(page, /what's moving and where money is flowing/);
});

test("R12-012: Admin → System's probe lines and the jobs' logs write their days the app's way", async () => {
  const { plainDates } = await import("../src/lib/format.ts");
  assert.equal(plainDates("163 Reliance filings; newest 2026-10-07."), "163 Reliance filings; newest 7 Oct 2026.");
  assert.equal(plainDates("Expiry 2026-10-13, spot 22520.45, 21 strikes"), "Expiry 13 Oct 2026, spot 22520.45, 21 strikes");
  assert.equal(plainDates("NIFTY 50: 21 daily candles, latest 2026-10-09, close 22,520.45."), "NIFTY 50: 21 daily candles, latest 9 Oct 2026, close 22,520.45.");
  assert.equal(plainDates("Holidays known at least 60 days ahead in all 8 markets; India's until 2026-12-31 (83 days)."),
    "Holidays known at least 60 days ahead in all 8 markets; India's until 31 Dec 2026 (83 days).");
  assert.equal(plainDates("2182 schemes read for 2026-10, today"), "2182 schemes read for Oct 2026, today");
  // not a day: an invoice number, a time stamp, a range of years
  assert.equal(plainDates("INVOICE SL/2026-27/0001"), "INVOICE SL/2026-27/0001");
  assert.equal(plainDates("at 2026-10-09T12:00:00+00:00"), "at 2026-10-09T12:00:00+00:00");
  assert.equal(plainDates(null), "");
  assert.match(read("src/pages/admin/PlatformPanel.tsx"), /plainDates\(c\.detail\)/);
  assert.match(read("src/pages/admin/DataSection.tsx"), /plainDates\(l\)/);
});
