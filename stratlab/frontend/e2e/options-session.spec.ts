import { expect, test, type Page } from "@playwright/test";

// An options paper session's page, from a saved snapshot: the orders sent together sit under one line, contracts read
// as "NIFTY 22450 PE", and the list scrolls inside its card instead of running down the page.
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };

const leg = (side: "buy" | "sell", strike: number, opt: "CE" | "PE", px: number, why: string, t: string, pnl?: number, saved = true) => ({
  t, side, qty: 3380, px, why, sym: `NIFTY26006${strike}${opt}`, slices: 2, ...(saved ? { strike, opt } : {}), ...(pnl != null ? { pnl } : {}),
});

const events = [
  ...Array.from({ length: 20 }, (_, d) => [
    leg("sell", 22450, "CE", 152.55, "Entry", `2026-09-${String(d + 1).padStart(2, "0")}T04:00:00+00:00`),
    leg("sell", 22450, "PE", 113.25, "Entry", `2026-09-${String(d + 1).padStart(2, "0")}T04:00:00+00:00`),
  ]).flat(),
  leg("buy", 22450, "PE", 156.1, "Stop loss", "2026-10-01T07:18:00+00:00", -144833, false),
  leg("buy", 22450, "CE", 119.65, "Stop loss", "2026-10-01T07:18:00+00:00", 111202),
];

const snapshot = {
  id: "s1", name: "Short straddle", kind: "options", status: "stopped", stop_reason: null,
  instrument: { symbol: "NIFTY", exchange: "NFO", underlying: "NIFTY" },
  strategy: { name: "Short straddle", structure: "straddle", exchange: "NFO", underlying: "NIFTY", expiry: "weekly", offsetUnit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 }],
    timing: { entry: "09:30", lastEntry: "14:00", squareoff: "15:15", maxEntries: 1, cooldown: 0 },
    risk: { stopType: "amount", stop: 50000, tgtType: "none", tgt: 0, trailAfter: 0, trailBy: 0, legStopPct: 0, dailyLoss: 0 },
    recenter: { enabled: false, every: 15, threshold: 2, roll: "shorts" }, sizing: { mode: "margin", lots: 1, capital: 2000000, safety: 0.9 },
    costs: { brokerage: 20, slippageTicks: 1, freeze: 1800 }, notes: "" },
  started_at: "2026-09-01T03:45:00+00:00", stopped_at: "2026-10-01T10:00:00+00:00", spot: 22400, fresh: false, feed_connected: false,
  expiry: "2026-10-06", lot: 65, note: "", legs: [], position: null,
  trades: [{ opened: "2026-10-01T04:00:00+00:00", closed: "2026-10-01T07:18:00+00:00", why: "Stop loss", pnl: -56346, gross: -52221, costs: 4125,
    credit: 830635, rolls: 1, units: 52, orders: 8, best: 1000, worst: -60000, expiry: "2026-10-06", legs: [] }],
  equity_curve: [{ t: "2026-09-01T04:00:00+00:00", eq: 2000000 }, { t: "2026-10-01T07:18:00+00:00", eq: 1943654 }],
  account: { capital: 2000000, equity: 1943654, cash: 1943654, realised: -56346, today: 0, halted: false, entries_today: 0, trades: 1, wins: 0, unrealised: 0 },
  events,
};

async function open(page: Page) {
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.pathname.endsWith("/live/sessions/s1")) return r.fulfill({ status: 200, body: JSON.stringify(snapshot), contentType: "application/json" });
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto("/options/s/s1");
}

test("options session: a closed trade's orders open under its row, grouped by moment, with readable contracts", async ({ page }, info) => {
  await open(page);
  await expect(page.getByRole("heading", { name: "Orders" })).toHaveCount(0);          // no separate list of every order
  const trades = page.locator("section", { has: page.getByRole("heading", { name: "Trades" }) });
  await expect(trades.locator(".order-group")).toHaveCount(0);                          // closed trades' orders stay folded
  const toggle = trades.getByRole("button", { name: /Show the orders of the trade opened/ });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(trades.getByRole("button", { name: /Hide the orders/ })).toHaveAttribute("aria-expanded", "true");
  const group = trades.locator(".order-group");
  await expect(group).toHaveCount(1);
  await expect(group.locator(".order-head")).toContainText("Stop loss");
  await expect(group.locator(".order-head .order-num")).toHaveText("−₹33,631");          // the two legs' P&L added up
  await expect(group.locator(".order-sym")).toHaveText(["NIFTY 22450 PE", "NIFTY 22450 CE"]);   // read from the symbol, then saved
  await expect(group.getByRole("img", { name: "Buy" })).toHaveCount(2);
  // nothing spills sideways on a phone
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide).toBeLessThanOrEqual(1);
  await trades.screenshot({ path: `test-results/options-session-${info.project.name}.png` });
  await trades.getByRole("button", { name: /Hide the orders/ }).click();
  await expect(trades.locator(".order-group")).toHaveCount(0);
});
