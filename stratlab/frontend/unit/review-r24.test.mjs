// Round 24, India's open: the pulse's loading states, the breadth card when its newest point is late and how many stocks it
// read, the PCR table's one basis, the two ATM IV figures named apart, the index change rounded, the options session's costs
// over the orders listed, the build shown in Admin, and the wording fixes. Fixed values only: nothing reads the clock.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R24-001: the pulse shows the levels, a skeleton, then 'Still loading…' with Retry, or an error; never a skeleton for ever", async () => {
  const { askAgain, PULSE_PENDING_TRIES, PULSE_SLOW_MS, pulseLoad } = await import("../src/lib/pulseLoad.ts");
  assert.equal(PULSE_SLOW_MS, 15_000);
  assert.equal(pulseLoad({ data: null, error: null, slow: false }), "loading");
  assert.equal(pulseLoad({ data: null, error: null, slow: true }), "slow");
  assert.equal(pulseLoad({ data: null, error: "Can't reach the StratLab server.", slow: true }), "error");
  assert.equal(pulseLoad({ data: { indices: [] }, error: null, slow: true }), "ready");
  // the server's first read is pending: asked again a few times, then the page says it is still loading
  assert.equal(askAgain(true, 0), true);
  assert.equal(askAgain(true, PULSE_PENDING_TRIES), false);
  assert.equal(askAgain(false, 0), false);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /Still loading…/);
  assert.match(page, /onClick=\{p\.retry\}>Retry</);
  assert.match(page, /title="The index levels couldn't be read" action=\{\{ label: "Try again"/);
  assert.match(page, /<PulseLevels p=\{levels\} \/>/);                 // the pulse page uses it
});

test("R24-002: a late newest point is said with its time and age, and the tag stops saying Live", async () => {
  const { liveTag, liveTitle } = await import("../src/lib/breadthLive.ts");
  assert.equal(liveTitle({ as_of: "09:15", late: true, age_minutes: 25 }), "Last updated 09:15, 25 minutes ago");
  assert.equal(liveTitle({ as_of: "09:15", late: true, age_minutes: 1 }), "Last updated 09:15, 1 minute ago");
  assert.equal(liveTitle({ as_of: "09:45", late: false, age_minutes: 4 }), "Today, live as of 09:45");
  assert.equal(liveTitle({ as_of: "09:45" }), "Today, live as of 09:45");            // an older server sends no age
  assert.deepEqual(liveTag({ late: true }), { tone: "warn", text: "Delayed" });
  assert.deepEqual(liveTag({ late: false }), { tone: "live", text: "Live" });
  assert.match(read("src/pages/BreadthPage.tsx"), /<Badge tone=\{tag\.tone\}>\{tag\.text\}<\/Badge>/);
});

test("R24-003: the live card says how many stocks it read and how many have no price yet", async () => {
  const { liveReadLine } = await import("../src/lib/breadthLive.ts");
  assert.equal(liveReadLine({ adv: 808, dec: 1044, unch: 492, of: 2563 }),
    "2,344 of 2,563 stocks read · 219 without a price yet today (not traded yet, suspended or not quoted)");
  assert.equal(liveReadLine({ adv: 80, dec: 165, unch: 5, of: 250 }), "250 of 250 stocks read");
  assert.equal(liveReadLine({ adv: 1, dec: 1, unch: 0 }), null);                     // an older point has no group size
});

test("R24-011, R79-008: the breadth chip names the daily figures above a live card", async () => {
  const { breadthChipLabel } = await import("../src/lib/breadthLive.ts");
  assert.equal(breadthChipLabel({ state: "live" }), "Daily figures to");
  assert.equal(breadthChipLabel(null), "Prices as of");
  assert.match(read("src/pages/BreadthPage.tsx"), /asOfLabel=\{breadthChipLabel\(data\?\.live\)\}/);
});

test("R24-011: the live price feed light doesn't say OK and 'Not needed' as if they disagreed", async () => {
  const { feedTile } = await import("../src/pages/admin/attention.ts");
  const t = feedTile({ feed_connected: false, live_sessions: 2, india_sessions: 0, options_sessions: 2, options_users: 1 });
  assert.equal(t.state, "ok");
  assert.equal(t.detail, "Not connected, and no session needs it: the 2 options paper sessions running read quotes every few seconds instead");
  assert.doesNotMatch(t.detail, /Not needed:/);
});

test("R24-004: every PCR row counts the same window and says so", async () => {
  const { pcrStrikes } = await import("../src/lib/positioning.ts");
  assert.equal(pcrStrikes({ strikes_read: 81, strikes_counted: 31, strikes_window: 31, partial: false }), "31 of 31");
  assert.equal(pcrStrikes({ strikes_read: 31, strikes_counted: 31, strikes_window: 31, partial: false }), "31 of 31");
  assert.equal(pcrStrikes({ strikes_read: 31, strikes_counted: 27, strikes_window: 31, partial: true }), "27 of 31, partial");
  assert.equal(pcrStrikes({ strikes_read: 61 }), "61");                               // an older server's row
  assert.match(read("src/pages/PositioningPage.tsx"), /header: "Strikes in the PCR", numeric: true, cell: \(r\) => pcrStrikes\(r\)/);
});

test("R24-005: the two NIFTY ATM IV figures are named apart, each with its strike, both to two decimals", async () => {
  const { atmIvLabel, strike, VIX_IV_LABEL, vixIvNote } = await import("../src/lib/positioning.ts");
  assert.equal(atmIvLabel(22750, strike), "ATM IV at the 22,750 strike");
  assert.equal(atmIvLabel(null, strike), "ATM implied volatility");
  assert.equal(VIX_IV_LABEL, "NIFTY ATM IV, StratLab model");
  // R52-014: the note also says the nearest expiry's IV and VIX's 30 days differ by design
  assert.match(vixIvNote(22750, "Live chain, 09:40 IST", strike), /^At the 22,750 strike · Live chain, 09:40 IST\. The IV of the nearest expiry's options\. India VIX measures the next 30 days/);
  assert.match(read("src/pages/PositioningPage.tsx"), /value=\{c\.atm_iv == null \? "–" : `\$\{c\.atm_iv\.toFixed\(2\)\}%`\}/);
  assert.match(read("src/components/VixPanel.tsx"), /label=\{VIX_IV_LABEL\}/);
});

test("R24-006: an index change shows the server's figure rounded, never cut", async () => {
  const { pct } = await import("../src/lib/format.ts");
  assert.equal(pct(0.476, 2), "+0.48%");
  assert.equal(pct(0.48, 2), "+0.48%");                  // the server now sends it rounded half up to two places
  assert.equal(pct(-0.476, 2), "−0.48%");
});

test("R24-007: the session's costs are over the orders the list shows", async () => {
  const { costsLine } = await import("../src/lib/options.ts");
  const four = [{ slices: 2 }, { slices: 2 }, { slices: 2 }, { slices: 2 }];
  assert.equal(costsLine("₹1,860", four), "Costs so far ₹1,860 over the 4 orders in this trade (sent as 8 exchange orders, split at the exchange's limit per order).");
  assert.equal(costsLine("₹930", [{ slices: 1 }, {}]), "Costs so far ₹930 over the 2 orders in this trade.");
  assert.equal(costsLine("₹0", [{ slices: 0 }]), "Costs so far ₹0 over the 0 orders in this trade.");    // a settlement isn't an order
  const page = read("src/pages/OptionsSession.tsx");
  assert.match(page, /costsLine\(inr\(p\.costs\), openOrders\)/);
  assert.match(page, /count=\{openOrders\.length\}/);
});

test("R24-009: the builds are written plainly, and the bundle's stamp reads only the host's commit names", async () => {
  const { buildLine } = await import("../src/lib/buildInfo.ts");
  const fmt = (iso) => iso.slice(0, 16).replace("T", " ");
  assert.equal(buildLine({ sha: "4610d78abc", short: "4610d78", branch: "main", built_at: "2026-10-15T03:54:10+00:00", started_at: "2026-10-15T03:56:00+00:00" }, fmt),
    "4610d78 on main, built 2026-10-15 03:54, running since 2026-10-15 03:56.");
  assert.equal(buildLine({ sha: null, started_at: "2026-10-15T03:56:00+00:00" }, fmt), "Commit not set by the host, running since 2026-10-15 03:56.");
  assert.equal(buildLine(undefined, fmt), "Not reported (an older server).");
  const { buildStamp } = await import("../scripts/buildStamp.mjs");
  const s = buildStamp({ VERCEL_GIT_COMMIT_SHA: "ABCDEF1234567", VERCEL_GIT_COMMIT_REF: "main", VERCEL_ENV: "production", SUPABASE_SERVICE_KEY: "k3y" },
    new Date("2026-10-15T03:50:00Z"));
  assert.deepEqual(s, { sha: "abcdef1234567", ref: "main", env: "production", built_at: "2026-10-15T03:50:00.000Z" });
  assert.equal(buildStamp({ VERCEL_GIT_COMMIT_SHA: "nope; rm" }, new Date(0)).sha, null);
  assert.match(read("vite.config.ts"), /__APP_BUILD__: JSON\.stringify\(buildStamp\(\)\)/);
  assert.match(read("src/pages/admin/SystemSection.tsx"), /label="Server" detail=\{sv \? buildLine\(sv\.build/);
  assert.match(read("src/pages/admin/PlatformPanel.tsx"), /on build \$\{r\.build\}/);
});
