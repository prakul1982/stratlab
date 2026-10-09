import { expect, test, type Page, type Route } from "@playwright/test";

// Round 7 time review of the live site during India's open (9 Oct 2026): what the app draws, on the reviewer's examples.
// Every answer the page depends on is fixed here (the fake world's background jobs can't change it), and every clock is a
// fixed instant: 09:39 IST on Friday 9 Oct 2026, unless a test says otherwise.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
const OPEN = "2026-10-09T04:09:00Z";                 // 09:39 IST
type Mock = [RegExp, unknown | ((r: Route) => Promise<void>)];

async function open(page: Page, path: string, mocks: Mock[] = [], now: string | null = OPEN) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  if (now) await page.clock.setFixedTime(new Date(now));
  await page.route("**/*", async (r) => {
    const u = new URL(r.request().url());
    const call = ["fetch", "xhr"].includes(r.request().resourceType());       // the page's own address is never an answer
    for (const [re, body] of call ? mocks : []) {
      if (re.test(u.pathname + u.search)) {
        if (typeof body === "function") return (body as (r: Route) => Promise<void>)(r);
        return r.fulfill({ status: 200, body: JSON.stringify(body), contentType: "application/json" });
      }
    }
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(path);
  return errors;
}

/** The fake world's own answer for a request, changed by `edit`. */
const edited = (edit: (j: Record<string, unknown>) => Record<string, unknown>) => async (r: Route) => {
  const res = await r.fetch();
  return r.fulfill({ response: res, json: edit(await res.json()) });
};

// ---------- R7T-003: a previous session's index level is never "today", and no mood is written on it ----------
test("SENSEX at the 8 Oct close after the open says so, and the mood waits (R7T-003)", async ({ page }) => {
  const indices = [
    { name: "NIFTY 50", price: 22430.1, change_pct: 0.9, high52: 26277, from_high_pct: -14.6, at: "2026-10-09T09:39:00+05:30", day: "2026-10-09", live: true, stale: false },
    { name: "SENSEX", price: 71593.24, change_pct: -1.44, high52: 85978, from_high_pct: -16.7, at: "2026-10-08T15:30:00+05:30", day: "2026-10-08", live: false, stale: true },
  ];
  const errors = await open(page, "/research/pulse?region=IN", [
    [/\/research\/pulse\/ai\?/, { unavailable: true, code: "stale", message: "SENSEX hasn't updated for today's session yet, so no mood is written on a previous session's numbers. Ask again in a minute." }],
    [/\/research\/pulse\?/, { indices, headlines: [] }],
  ]);
  const sensex = page.locator(".k-stat", { hasText: "SENSEX" }).first();
  await expect(sensex.getByTestId("index-when")).toHaveText(/^8 Oct close · not updated today yet/, { timeout: 30_000 });
  await expect(sensex).not.toContainText("today ·");
  await expect(page.locator(".k-stat", { hasText: "NIFTY 50" }).first().getByTestId("index-when")).toHaveText(/^today/);
  await expect(page.locator("main")).toContainText("SENSEX hasn't updated for today's session yet");
  await expect(page.locator("main")).not.toContainText("Written");
  expect(errors).toEqual([]);
});

test("Mine's SENSEX tile names the day of a move that isn't today's (R7T-003)", async ({ page }) => {
  const candles = ["2026-10-06", "2026-10-07", "2026-10-08"].map((d, i) => ({ t: `${d}T00:00:00+05:30`, o: 72000, h: 72500, l: 71400, c: [72100, 72640, 71593.24][i], v: 0 }));
  const errors = await open(page, "/mine", [[/\/research\/chart\/IN\/(%5E|\^)BSESN/, { currency: "INR", source: "x", tf: "1d", more: false, candles }]]);
  const tile = page.locator('[data-market="sensex"]');
  await expect(tile.getByTestId("mine-mkt-when")).toHaveText(/on 8 Oct/, { timeout: 30_000 });
  expect(errors).toEqual([]);
});

// ---------- R7T-002: the chain counts contracts ----------
test("the option chain's open interest is in contracts, as the exchange counts it (R7T-002)", async ({ page }) => {
  const rows = [22900, 22950, 23000, 23050].map((k) => ({ strike: k, call_oi: k === 23000 ? 216713 : 50000, put_oi: 40000, call_vol: 9000, put_vol: 8000,
    call_chg: k === 23000 ? 16713 : 100, put_chg: -50 }));
  const chain = { name: "NIFTY", exchange: "NFO", choice: "current", source: "live", at_close: false, as_of: "2026-10-09T09:41:00+05:30", expiry: "2026-10-13",
    expiries: ["2026-10-13"], spot: 22950, rows, change_from: "2026-10-08T15:25+05:30", strikes_counted: 81, lot: 65, unit: "lots", near_strikes: 15,
    pcr: { oi: 0.736, vol: 0.9, call_oi: 366713, put_oi: 160000, call_vol: 36000, put_vol: 32000 }, pcr_all: 0.6, pcr_near: 0.736, pcr_near_vol: 0.9,
    max_pain: 22950, atm_iv: 13.51, atm: 22950, top: { call: { strike: 23000, oi: 216713 }, put: { strike: 22900, oi: 40000 } }, iv: null,
    note: "Facts from the option chain.", plan_needed: "Basic", recorded: { days: 20, first: "2026-09-10", last: "2026-10-08" } };
  const errors = await open(page, "/trade/positioning", [[/\/trade\/positioning\/chain\?/, chain]]);
  const facts = page.getByTestId("chain-facts");
  await expect(facts).toContainText("2,16,713 contracts", { timeout: 30_000 });
  await expect(page.getByTestId("chain-unit")).toContainText("contracts (lots of 65 shares)");
  await expect(facts).toContainText("PCR (open interest)");
  await expect(facts).toContainText("0.74");
  await expect(facts).toContainText("all strikes read 0.60");
  await expect(facts).toContainText(/longest bar is \S+ contracts/);
  expect(errors).toEqual([]);
});

// ---------- R7T-004: the pre-open price is never the last close ----------
test("a company page at 09:13 IST calls its price the pre-open's (R7T-004)", async ({ page }) => {
  const errors = await open(page, "/research/IN/RELIANCE", [
    [/\/research\/company\/IN\/RELIANCE$/, edited((j) => ({ ...j, market_open: false, phase: "pre_open",
      quote: { ...(j.quote as object), price: 1179, change: 1, change_pct: 0.0849, prev_close: 1178, at: "2026-10-09T09:09:49+05:30" } }))],
  ], "2026-10-09T03:43:00Z");
  const price = page.getByTestId("company-price");
  await expect(price).toContainText("Pre-open (indicative)", { timeout: 30_000 });
  await expect(price).toContainText("against the last close");
  await expect(price).not.toContainText("Last close");
  await expect(price).not.toContainText("on the day");
  expect(errors).toEqual([]);
});

// ---------- R7T-001: a range from another class of shares isn't drawn ----------
test("a 52-week range that can't be the share's is not shown under its price (R7T-001)", async ({ page }) => {
  const errors = await open(page, "/research/IN/RELIANCE", [
    [/\/research\/company\/IN\/RELIANCE$/, edited((j) => ({ ...j, range52: { low: 698000, high: 806102.8 } }))],
  ]);
  await expect(page.getByTestId("company-price")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main")).not.toContainText("52-wk low");
  expect(errors).toEqual([]);
});

// ---------- R7T-010: the home breadth card is live during the session ----------
test("the Invest home's breadth card shows the live count after the open (R7T-010)", async ({ page }) => {
  const fig = (v: number) => ({ value: v, prev: null, change: null });
  const today = { day: "2026-10-08", prev_day: "2026-10-07", adv: fig(18), dec: fig(232), unch: fig(0), ad_ratio: fig(0.08), pct20: fig(10), pct50: fig(20),
    pct200: fig(30), highs: fig(1), lows: fig(30), up4: fig(0), down4: fig(5) };
  const group = { id: "nifty500", name: "NIFTY 500", region: "IN", index_name: "NIFTY 500" };
  const view = { group, groups: [group], today, as_of: "2026-10-08", since: "2025-10-08", range: "1y", help: {}, status: null, locked: false, plan_needed: "Basic",
    history: null, sectors: null, thrusts: null,
    live: { state: "live", day: "2026-10-09", fields: [], points: [], as_of: "09:30", message: null, every_minutes: 15,
      latest: { adv: 317, dec: 176, unch: 1, a20: 250, n20: 500, a50: 240, n50: 500, a200: 260, n200: 500, idx: 23010, pct20: 50, pct50: 48, pct200: 52 } } };
  const errors = await open(page, "/invest", [[/\/invest\/breadth\?.*brief=true/, view]]);
  const card = page.getByTestId("breadth-card");
  await expect(card).toHaveAttribute("data-live", "1", { timeout: 30_000 });
  await expect(card.getByTestId("breadth-card-when")).toHaveText("Live as of 09:30 IST");
  await expect(card).toContainText("317 / 176");
  await expect(card).toContainText("Last close, 8 Oct");            // the year's highs and lows stay the close's, said so
  expect(errors).toEqual([]);
});

// ---------- R7T-011: an options session at /paper/<id>, and a page that crashes ----------
const strategy = { name: "Iron fly", structure: "ironfly", exchange: "NFO", underlying: "NIFTY", expiry: "weekly", offsetUnit: "points",
  legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 }],
  timing: { entry: "09:30", lastEntry: "14:45", squareoff: "15:15", maxEntries: 3, cooldown: 120 },
  risk: { stopType: "amount", stop: 50000, tgtType: "none", tgt: 0, trailAfter: 0, trailBy: 0, legStopPct: 0, dailyLoss: 0 },
  recenter: { enabled: false, every: 15, threshold: 2, roll: "shorts" }, sizing: { mode: "margin", lots: 50, capital: 5000000, safety: 0.9 },
  costs: { brokerage: 20, slippageTicks: 1, freeze: 1800 }, notes: "" };
const stopOut = { opened: "2026-10-09T09:30:01+05:30", closed: "2026-10-09T09:41:00+05:30", why: "Stop loss", pnl: -270494, gross: -250000, costs: 20494,
  credit: 900000, rolls: 0, units: 50, orders: 8, best: 1000, worst: -270494, expiry: "2026-10-13", legs: [] };
const optionsSnap = { id: "610500be", name: "Iron fly", kind: "options", status: "running", stop_reason: null,
  instrument: { symbol: "NIFTY options", exchange: "NFO", underlying: "NIFTY", type: "OPTIONS", market: "IN" }, strategy,
  started_at: "2026-10-01T09:00:00+05:30", stopped_at: null, spot: 22400, fresh: true, feed_connected: true, expiry: "2026-10-13", lot: 65,
  note: "Next entry from 11:41: entries are 120 minutes apart.", legs: [], position: null, signal: null, trades: [stopOut], events: [], equity_curve: [],
  account: { capital: 5000000, equity: 4729506, cash: 4729506, realised: -270494, today: -270494, halted: false, entries_today: 1, trades: 1, wins: 0,
    unrealised: 0, cool_until: "2026-10-09T11:41:00+05:30", next_entry: "11:41" } };

test("an options session opened at /paper/<id> goes to its own page (R7T-011)", async ({ page }) => {
  const row = { id: "610500be", name: "Iron fly", status: "running", instrument: optionsSnap.instrument, started_at: optionsSnap.started_at };
  const errors = await open(page, "/paper/610500be", [[/\/live\/sessions\/610500be$/, optionsSnap], [/\/live\/sessions$/, [row]]], "2026-10-09T04:15:00Z");
  await expect(page).toHaveURL(/\/options\/s\/610500be$/, { timeout: 30_000 });
  await expect(page.locator("body")).not.toContainText("Couldn't load StratLab");
  expect(errors).toEqual([]);
});

test("after a stop-out the options session says when it may enter again (R7T-013)", async ({ page }) => {
  const errors = await open(page, "/options/s/610500be", [[/\/live\/sessions\/610500be$/, optionsSnap]], "2026-10-09T04:15:00Z");   // 09:45 IST
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.locator("main")).toContainText("Nothing open. Next entry from 11:41: entries are 120 min apart.", { timeout: 30_000 });
  await expect(page.locator("main")).not.toContainText("Entries open until 14:45");
  expect(errors).toEqual([]);
});

test("a page that fails while it runs says so honestly, not that a file didn't download (R7T-011)", async ({ page }) => {
  const errors = await open(page, "/paper/zz", [[/\/live\/sessions\/zz$/, { id: "zz", status: "running" }], [/\/live\/sessions$/, []]]);
  await expect(page.getByTestId("page-failed")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("page-failed")).toContainText("This page ran into a problem");
  await expect(page.locator("body")).not.toContainText("A file didn't download");
  await expect(page.getByRole("navigation").first()).toBeVisible();      // the rest of the app still works
  expect(errors).toEqual([]);
});
