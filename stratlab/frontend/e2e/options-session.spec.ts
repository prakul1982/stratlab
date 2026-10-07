import { expect, test, type Page } from "@playwright/test";

// An options paper session's page, from a saved snapshot, at a fixed moment: today's activity first (the open trade with
// its orders folded under it, the trades closed today), the earlier trades folded under one line with their total, and
// each closed trade's orders opening under its row, sent-together orders under one line with readable contracts.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
const MONDAY = "2026-10-05";
const at = (day: string, utc: string) => `${day}T${utc}:00+00:00`;   // IST is UTC + 5:30

const leg = (side: "buy" | "sell", strike: number, opt: "CE" | "PE", px: number, why: string, t: string, pnl?: number, saved = true) => ({
  t, side, qty: 3380, px, why, sym: `NIFTY26006${strike}${opt}`, slices: 2, ...(saved ? { strike, opt } : {}), ...(pnl != null ? { pnl } : {}),
});

// twenty September days, each an entry at 09:30 and a square-off at 15:15 (IST)
const days = Array.from({ length: 20 }, (_, d) => `2026-09-${String(d + 1).padStart(2, "0")}`);
const pastEvents = days.flatMap((d) => [
  leg("sell", 22450, "CE", 152.55, "Entry", at(d, "04:00")), leg("sell", 22450, "PE", 113.25, "Entry", at(d, "04:00")),
  leg("buy", 22450, "CE", 140.1, "Square-off", at(d, "09:45"), 1000), leg("buy", 22450, "PE", 110.0, "Square-off", at(d, "09:45"), 500),
]);
const pastTrades = days.map((d, i) => ({ opened: at(d, "04:00"), closed: at(d, "09:45"), why: "Square-off", pnl: i === 3 ? -4000 : 1500, gross: 2000, costs: 500,
  credit: 830635, rolls: 0, units: 52, orders: 4, best: 3000, worst: -1000, expiry: "2026-10-06", legs: [] }));

const strategy = { name: "Short straddle", structure: "straddle", exchange: "NFO", underlying: "NIFTY", expiry: "weekly", offsetUnit: "strikes",
  legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 }],
  timing: { entry: "09:30", lastEntry: "14:00", squareoff: "15:15", maxEntries: 2, cooldown: 0 },
  risk: { stopType: "amount", stop: 50000, tgtType: "none", tgt: 0, trailAfter: 0, trailBy: 0, legStopPct: 0, dailyLoss: 0 },
  recenter: { enabled: false, every: 15, threshold: 2, roll: "shorts" }, sizing: { mode: "margin", lots: 1, capital: 2000000, safety: 0.9 },
  costs: { brokerage: 20, slippageTicks: 1, freeze: 1800 }, notes: "" };

const snap = (over: Record<string, unknown>) => ({
  id: "s1", name: "Short straddle", kind: "options", status: "running", stop_reason: null,
  instrument: { symbol: "NIFTY", exchange: "NFO", underlying: "NIFTY" }, strategy,
  started_at: at("2026-09-01", "03:45"), stopped_at: null, spot: 22400, fresh: false, feed_connected: true,
  expiry: "2026-10-06", lot: 65, note: "", legs: [], position: null, signal: null,
  trades: pastTrades, events: pastEvents,
  equity_curve: pastTrades.map((x, i) => ({ t: x.closed, eq: 2000000 + pastTrades.slice(0, i + 1).reduce((n, y) => n + y.pnl, 0) })),
  account: { capital: 2000000, equity: 2024500, cash: 2024500, realised: 24500, today: 0, halted: false, entries_today: 0, trades: 20, wins: 19, unrealised: 0 },
  ...over,
});

async function open(page: Page, body: unknown, now: string) {
  await page.clock.setFixedTime(new Date(now));
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.pathname.endsWith("/live/sessions/s1")) return r.fulfill({ status: 200, body: JSON.stringify(body), contentType: "application/json" });
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto("/options/s/s1");
  // a first visit asks what the person came for; answer it like a new user would
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByRole("heading", { name: "Today" })).toBeVisible();
}

async function noSideScroll(page: Page) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide, "the page scrolls sideways").toBeLessThanOrEqual(1);
}

test("options session, flat before the open: one line for today, the earlier trades folded with their total", async ({ page }, info) => {
  await open(page, snap({}), at(MONDAY, "03:10"));                       // 08:40 IST on a Monday
  const today = page.locator("section", { has: page.getByRole("heading", { name: "Today" }) });
  await expect(today).toContainText("No trades today. Next entry 09:30.");
  await expect(today.locator("table")).toHaveCount(0);                   // no empty table, nothing that looks open
  await expect(page.getByRole("heading", { name: "Orders" })).toHaveCount(0);   // no separate list of every order
  const fold = page.locator("details.earlier", { hasText: "Earlier trades" });
  await expect(fold.locator("summary")).toContainText("Earlier trades (20)");
  await expect(fold.locator("summary")).toContainText("₹24,500 after costs · 19 won");
  await expect(fold).toHaveAttribute("open", "");                        // open by default: the earlier trades are the history people look for
  await expect(fold.locator("table")).toHaveCount(0);                    // each trade is one line; its orders open on a tap
  await noSideScroll(page);
  await page.screenshot({ path: `test-results/stale-options-flat-${info.project.name}.png`, fullPage: true });
  await expect(fold.locator(".trade-line")).toHaveCount(20);
  await expect(fold.locator(".trade-line").first()).toContainText(/20 Sep/);   // newest first
  await noSideScroll(page);
});

test("options session, mid-day: the open trade with its orders folded under it, then the trade closed today", async ({ page }, info) => {
  const opened = at(MONDAY, "06:30"), closed = { opened: at(MONDAY, "04:00"), closed: at(MONDAY, "06:00") };
  const body = snap({
    position: { opened, center: 22450, spot_in: 22441, credit: 830635, mtm: 12000, costs: 2000, net: 10000, best: 15000, worst: -2000, rolls: 0, units: 52, orders: 2, expiry: "2026-10-06" },
    legs: [{ sym: "NIFTY2600622450CE", side: "sell", qty: 3380, entry: 152.55, mark: 150, pnl: 8619, open: true },
      { sym: "NIFTY2600622450PE", side: "sell", qty: 3380, entry: 113.25, mark: 112.8, pnl: 1521, open: true }],
    trades: [...pastTrades, { ...pastTrades[0], ...closed, pnl: -56346, gross: -52221, costs: 4125, why: "Stop loss" }],
    events: [...pastEvents,
      leg("sell", 22450, "CE", 152.55, "Entry", closed.opened), leg("sell", 22450, "PE", 113.25, "Entry", closed.opened),
      leg("buy", 22450, "PE", 156.1, "Stop loss", closed.closed, -144833, false), leg("buy", 22450, "CE", 119.65, "Stop loss", closed.closed, 111202),
      leg("sell", 22450, "CE", 152.55, "Entry", opened), leg("sell", 22450, "PE", 113.25, "Entry", opened)],
    account: { capital: 2000000, equity: 1968154, cash: 1968154, realised: -31846, today: -56346, halted: false, entries_today: 2, trades: 21, wins: 19, unrealised: 10000 },
  });
  await open(page, body, at(MONDAY, "07:30"));                           // 13:00 IST
  const today = page.locator("section", { has: page.getByRole("heading", { name: "Today" }) });
  await expect(today).toContainText("Open since 5 Oct, 12:00");
  const own = today.locator("details.earlier", { hasText: "Orders in this trade" });
  await expect(own.locator("summary")).toContainText("Orders in this trade (2)");
  await expect(own.locator(".order-group")).toHaveCount(0);             // folded until asked
  await own.locator("summary").click();
  await expect(own.locator(".order-sym")).toHaveText(["NIFTY 22450 CE", "NIFTY 22450 PE"]);
  // the trade closed today, its orders under its row
  await expect(today.getByText("Closed today")).toBeVisible();
  await expect(today.locator(".trade-line")).toHaveCount(1);
  const toggle = today.getByRole("button", { name: /Show the orders of the trade opened 5 Oct, 09:30/ });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(today.getByRole("button", { name: /Hide the orders/ })).toHaveAttribute("aria-expanded", "true");
  const groups = today.locator(".trade-orders .order-group");
  await expect(groups).toHaveCount(2);
  const stop = groups.nth(1);
  await expect(stop.locator(".order-head")).toContainText("Stop loss");
  await expect(stop.locator(".order-head .order-num")).toHaveText("−₹33,631");     // the two legs' P&L added up
  await expect(stop.locator(".order-sym")).toHaveText(["NIFTY 22450 PE", "NIFTY 22450 CE"]);   // read from the symbol, then saved
  await expect(stop.getByRole("img", { name: "Buy" })).toHaveCount(2);
  await expect(page.locator("details.earlier", { hasText: "Earlier trades" }).locator("summary")).toContainText("Earlier trades (20)");
  await noSideScroll(page);
  await page.screenshot({ path: `test-results/stale-options-midday-${info.project.name}.png`, fullPage: true });
  await today.getByRole("button", { name: /Hide the orders/ }).click();
  await expect(groups).toHaveCount(0);
});

test("options session, stopped: nothing today, every trade under Earlier", async ({ page }) => {
  await open(page, snap({ status: "stopped", stopped_at: at("2026-10-02", "10:00") }), at(MONDAY, "07:30"));
  const today = page.locator("section", { has: page.getByRole("heading", { name: "Today" }) });
  await expect(today).toContainText("No trades today.");
  await expect(today).not.toContainText("Next entry");
  await expect(page.locator("details.earlier summary", { hasText: "Earlier trades" })).toContainText("(20)");
});
