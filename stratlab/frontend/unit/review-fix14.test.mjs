// fix14 (LIVE11B, 18 Nov 2026): the scored live review of Release 66/67. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem0 = new Map();
globalThis.localStorage ??= { getItem: (k) => mem0.get(k) ?? null, setItem: (k, v) => mem0.set(k, String(v)), removeItem: (k) => mem0.delete(k) };

test("LIVE11B-004: the data status is asked for as the app starts, and the page waits for it (a moment at most) so the offline line is in the first frame", () => {
  assert.match(read("src/entry.tsx"), /if \(account\) import\("\.\/lib\/http"\)\.then\(\(m\) => m\.prefetchPublic\("\/public\/data-online"\)\)/);
  const app = read("src/lib/app.tsx");
  assert.match(app, /publicGet<\{ data_online: boolean; data_note\?: DataNote \}>\("\/public\/data-online"\)/);
  assert.match(app, /export const DATA_STATUS_WAIT_MS = 1500;/);
  const main = read("src/main.tsx");
  assert.match(main, /if \(!dataKnown\) return <><main><h1 className="sr-only">Opening StratLab<\/h1>/);
  assert.match(main, /<DataBanner note=\{me \? me\.data_note \?\? null : dataNote\}/);
});

test("LIVE11B-005: Nearest = Monthly is explained from the expiry calendar, never 'monthly expiries only' for an index with weeklies", async () => {
  const { sameExpiryNote } = await import("../src/lib/options.ts");
  const fmt = (d) => `${+d.slice(8, 10)} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+d.slice(5, 7) - 1]}`;
  // the review's case: Mon 23 Nov (the Tue 24 Nov weekly and monthly, moved for the holiday), then the Tue 1 Dec weekly
  const weekly = sameExpiryNote("NIFTY", ["2026-11-23", "2026-12-01"], ["2026-11-24"], fmt);
  assert.equal(weekly, "This week's expiry, 23 Nov, is also the month's last, so Nearest and Monthly are the same day. It is on Monday 23 Nov, moved from Tuesday 24 Nov, an exchange holiday.");
  assert.doesNotMatch(weekly, /monthly expiries only/);
  assert.equal(sameExpiryNote("NIFTY", ["2026-11-23", "2026-12-01", "2026-12-08", "2026-12-29"], [], fmt),
    "This week's expiry, 23 Nov, is also the month's last, so Nearest and Monthly are the same day.");
  // a monthly-only index: three expiries, each its month's last
  assert.equal(sameExpiryNote("BANKNIFTY", ["2026-11-24", "2026-12-29", "2027-01-26"], [], fmt), "BANKNIFTY has monthly expiries only, so Nearest and Monthly are the same day.");
  // two expiries a month apart: no claim about the calendar beyond what the dates show
  assert.equal(sameExpiryNote("X", ["2026-11-24", "2026-12-29"], [], fmt), "The nearest expiry, 24 Nov, is also the month's last, so Nearest and Monthly are the same day.");
  // Nearest and Monthly differ: no line
  assert.equal(sameExpiryNote("NIFTY", ["2026-11-17", "2026-11-24", "2026-12-01"], [], fmt), null);
  assert.match(read("src/pages/OptionsPage.tsx"), /\{sameExpiry && <span className="k-note" data-testid="opt-expiry-same">\{sameExpiry\}<\/span>\}/);
});

test("LIVE11B-002: the signed-out view of an app page is drawn in /login's frame, and names both ways in when email sign-in is on", () => {
  const gate = read("src/pages/Gate.tsx"), frame = read("src/components/SiteFrame.tsx"), login = read("src/pages/Login.tsx");
  // the same header, ruled band and footer classes as /login
  for (const cls of ['<header className="lp-nav">', 'className="lp-hero ruled"', 'lp-hero-grid lp-hero-solo lp-hero-login', '<footer className="lp-foot">']) {
    assert.ok(frame.includes(cls), cls);
    assert.ok(login.includes(cls.replace("lp-hero-grid lp-hero-solo lp-hero-login", "lp-hero-grid")), `/login has ${cls}`);
  }
  // the footer's disclaimer is /login's, word for word
  const said = frame.match(/SITE_DISCLAIMER = "([^"]+)"/)[1];
  assert.ok(login.includes(said), "the disclaimer is /login's");
  assert.match(gate, /<SignInFrame>/);
  assert.doesNotMatch(gate.slice(gate.indexOf("export function SignInGate"), gate.indexOf("export function NotFound")), /<PublicFrame className="gate">\s*<PageHeader eyebrow="StratLab" title=\{title\}/);
  // the words: both ways in while email sign-in is on, Google alone only while it is the only way
  assert.match(gate, /const how = email \? "sign in with Google or your email" : "sign in with Google";/);
  assert.match(gate, /Signing in only reads your name and email from Google\{email \? ", or only your email address by email" : ""\}\./);
  assert.doesNotMatch(gate, /Sign in with Google to continue|sign in with Google and the page opens/);
});

test("LIVE11B-010: a level kept from yesterday's session (or before a newer close) is drawn faded with its time, never as the day's figure", async () => {
  const M = await import("../src/lib/mine.ts");
  const at = Date.parse("2026-11-17T09:08:00Z");                // 14:38 IST Tue 17 Nov, mid-session in India; 04:08 in New York
  const now = Date.parse("2026-11-18T00:30:00Z");               // 06:00 IST Wed 18 Nov: the first open of the day
  assert.equal(M.keptStale("nifty", { day: "2026-11-17", at }, now), true);          // an intraday level, not 17 Nov's close
  assert.equal(M.keptStale("sp500", { day: "2026-11-16", at }, now), true);          // 16 Nov's close, with 17 Nov's out since
  assert.equal(M.keptStale("gold", { day: "2026-11-17", at }, now), true);           // round the clock: hours old
  const after = Date.parse("2026-11-17T10:30:00Z");             // 16:00 IST: after India's close was final
  assert.equal(M.keptStale("nifty", { day: "2026-11-17", at: after }, now), false);  // 17 Nov's close, still the latest
  assert.equal(M.keptStale("gold", { day: "2026-11-18", at: now - 60_000 }, now), false);
  assert.equal(M.keptStale("nifty", { day: "2026-11-17", at: after }, Date.parse("2026-11-18T10:20:00Z")), true);   // 18 Nov's close is out
  const mem = new Map();
  const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)) };
  M.keepStripTile("nifty", { values: [25291, 25448], last: 25448, prev: 25291, changePct: 0.62, day: "2026-11-17", at }, store);
  assert.equal(M.keptStrip(now, store).nifty.stale, true);
  const page = read("src/pages/MineHome.tsx");
  assert.match(page, /: s\.stale \? \(\s*<span className="mine-mkt-old" data-testid="mine-mkt-old"/);
  assert.match(page, /Faded levels are from your last visit, read \{fmtDateTime\(keptAt, \{ tz: IST, zone: true, year: false \}\)\}: the latest are on their way\./);
});
