import { expect, test, type Browser, type Page } from "@playwright/test";
import { resolve } from "node:path";

// The README's screenshots, light and dark, 1280px wide: the landing page (top, its Money section, plans), the three space
// homes, Positioning, an options paper session, a company page's price chart, ETF vs NAV and F&O changes. Run with scripts/docs-shots.config.ts (see there); files land in
// docs/screenshots. The fake world's data is synthetic, so nothing here is real market data.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const OUT = resolve(process.env.DOCS_SHOTS_DIR ?? "../../docs/screenshots");
const THEMES = ["light", "dark"] as const;
type Theme = (typeof THEMES)[number];
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r",
  user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

/** A browser window at 1280px in one theme, signed in as the owner (or signed out), showing `space`'s menu. */
async function open(browser: Browser, theme: Theme, opts: { signedIn: boolean; space?: string; height?: number }) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: opts.height ?? 860 }, colorScheme: theme, reducedMotion: "reduce",
    timezoneId: "Asia/Kolkata", locale: "en-IN" });
  await ctx.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await ctx.addInitScript(([s, signedIn, theme, space]) => {
    if (signedIn) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab-theme", theme as string);
    if (space) localStorage.setItem("stratlab.space", space as string);
  }, [session, opts.signedIn, theme, opts.space ?? ""] as const);
  return { ctx, page: await ctx.newPage() };
}

/** Wait until the page has stopped loading: no spinners or "Loading…" lines, fonts in. */
async function settle(page: Page) {
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await expect(page.locator(".spinner")).toHaveCount(0, { timeout: 30_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
}

/** A moving-average cross, the same rules the e2e suite tests with. */
const cross = (name: string, fast: number, slow: number) => ({ name, tf: "1d", entry: [{ l: { t: "ema", p: fast }, op: "xa", r: { t: "ema", p: slow } }],
  exit: [{ l: { t: "ema", p: fast }, op: "xb", r: { t: "ema", p: slow } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } });

test.beforeAll(async ({ request }) => {
  const post = async (path: string, data: object) => {
    const r = await request.post(API + path, { headers: admin, data });
    expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy();
    return r.json();
  };
  // no welcome question, a watchlist so the Invest home has prices to show, and two notebooks and a paper session for Trade
  await request.put(`${API}/me/prefs`, { headers: admin, data: { level: "some", focus: "both" } });
  const items = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "LT"].map((symbol) => ({ region: "IN", symbol }));
  await request.put(`${API}/research/watchlist`, { headers: admin, data: { items } });
  for (const [name, inst, fast, slow] of [["Trend follower on Bitcoin", "CRYPTO:BTC-USD", 10, 30], ["EMA 20/50 on Ethereum", "CRYPTO:ETH-USD", 20, 50]] as const) {
    const nb = await post("/notebooks", { name, question: "Does the cross hold up after costs?", strategy: cross(name, fast, slow), instrument: inst });
    await post(`/notebooks/${nb.id}/experiments`, { days: 1500 });
  }
  await post("/live/sessions", { strategy: cross("Trend follower on Bitcoin", 10, 30), instrument: "CRYPTO:BTC-USD" });
});

for (const theme of THEMES) {
  test(`landing, ${theme}`, async ({ browser }) => {
    const { ctx, page } = await open(browser, theme, { signedIn: false, height: 760 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Test it, research it, track it/ })).toBeVisible({ timeout: 30_000 });
    await settle(page);
    await page.screenshot({ path: `${OUT}/landing-${theme}.png` });
    const noNav = ".lp-nav { visibility: hidden; }";     // the sticky menu would sit over a section scrolled to the top
    await page.locator("section#money").screenshot({ path: `${OUT}/landing-money-${theme}.png`, style: noNav });
    await page.locator("section#pricing").screenshot({ path: `${OUT}/pricing-${theme}.png`, style: noNav });
    await ctx.close();
  });

  for (const [space, path, ready] of [["trade", "/trade", "Straddles, strangles"], ["invest", "/invest", "Which company do you want to look into?"],
    ["money", "/money", "Your money"]] as const) {
    test(`${space} home, ${theme}`, async ({ browser }) => {
      const { ctx, page } = await open(browser, theme, { signedIn: true, space });
      await page.goto(path);
      await expect(page.getByText(ready).first()).toBeVisible({ timeout: 30_000 });
      await settle(page);
      await page.screenshot({ path: `${OUT}/${space}-home-${theme}.png` });
      await ctx.close();
    });
  }

  test(`positioning, ${theme}`, async ({ browser }) => {
    const { ctx, page } = await open(browser, theme, { signedIn: true, space: "trade", height: 1000 });
    await page.goto("/trade/positioning");
    await expect(page.getByText("Participant-wise open interest").first()).toBeVisible({ timeout: 30_000 });
    await settle(page);
    await page.screenshot({ path: `${OUT}/positioning-${theme}.png` });
    await ctx.close();
  });

  test(`price chart, ${theme}`, async ({ browser }) => {
    const { ctx, page } = await open(browser, theme, { signedIn: true, space: "invest", height: 900 });
    await page.goto("/research/IN/RELIANCE");
    const chart = page.getByTestId("price-chart").first();
    await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
    await settle(page);
    await chart.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await chart.screenshot({ path: `${OUT}/price-chart-${theme}.png` });
    await ctx.close();
  });

  for (const [name, path, ready, space] of [["etf-gaps", "/invest/etf-gaps", "ETF price against NAV", "invest"],
    ["fo-changes", "/trade/fo-changes", "Every change", "trade"]] as const) {
    test(`${name}, ${theme}`, async ({ browser }) => {
      const { ctx, page } = await open(browser, theme, { signedIn: true, space, height: 900 });
      await page.goto(path);
      await expect(page.getByText(ready).first()).toBeVisible({ timeout: 30_000 });
      await settle(page);
      await page.screenshot({ path: `${OUT}/${name}-${theme}.png` });
      await ctx.close();
    });
  }

  test(`options session, ${theme}`, async ({ browser }) => {
    const { ctx, page } = await open(browser, theme, { signedIn: true, space: "trade", height: 1120 });
    await page.clock.setFixedTime(new Date(at(MONDAY, "07:30")));          // 13:00 India time
    await page.route("**/live/sessions/s1", (r) => r.fulfill({ status: 200, body: JSON.stringify(midday()), contentType: "application/json" }));
    await page.goto("/options/s/s1");
    const today = page.locator("section", { has: page.getByRole("heading", { name: "Today" }) });
    await expect(today).toBeVisible({ timeout: 30_000 });
    await today.getByRole("button", { name: /Show the orders of the trade opened/ }).click();
    await settle(page);
    await page.screenshot({ path: `${OUT}/options-session-${theme}.png` });
    await ctx.close();
  });
}

/* ---------- an options paper session at mid-day: one trade open, one closed today, twenty earlier (as e2e/options-session.spec.ts) ---------- */
const MONDAY = "2026-10-05";
const at = (day: string, utc: string) => `${day}T${utc}:00+00:00`;
const leg = (side: "buy" | "sell", strike: number, opt: "CE" | "PE", px: number, why: string, t: string, pnl?: number) => ({
  t, side, qty: 3380, px, why, sym: `NIFTY26006${strike}${opt}`, slices: 2, strike, opt, ...(pnl != null ? { pnl } : {}),
});

function midday() {
  const days = Array.from({ length: 20 }, (_, d) => `2026-09-${String(d + 1).padStart(2, "0")}`);
  const pastEvents = days.flatMap((d) => [
    leg("sell", 22450, "CE", 152.55, "Entry", at(d, "04:00")), leg("sell", 22450, "PE", 113.25, "Entry", at(d, "04:00")),
    leg("buy", 22450, "CE", 140.1, "Square-off", at(d, "09:45"), 1000), leg("buy", 22450, "PE", 110.0, "Square-off", at(d, "09:45"), 500),
  ]);
  const pastTrades = days.map((d, i) => ({ opened: at(d, "04:00"), closed: at(d, "09:45"), why: "Square-off", pnl: i % 6 === 3 ? -4000 : 1500, gross: 2000,
    costs: 500, credit: 830635, rolls: 0, units: 52, orders: 4, best: 3000, worst: -1000, expiry: "2026-10-06", legs: [] }));
  const opened = at(MONDAY, "06:30"), closed = { opened: at(MONDAY, "04:00"), closed: at(MONDAY, "06:00") };
  const strategy = { name: "Short straddle", structure: "straddle", exchange: "NFO", underlying: "NIFTY", expiry: "weekly", offsetUnit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 }],
    timing: { entry: "09:30", lastEntry: "14:00", squareoff: "15:15", maxEntries: 2, cooldown: 0 },
    risk: { stopType: "amount", stop: 50000, tgtType: "none", tgt: 0, trailAfter: 0, trailBy: 0, legStopPct: 0, dailyLoss: 0 },
    recenter: { enabled: false, every: 15, threshold: 2, roll: "shorts" }, sizing: { mode: "margin", lots: 1, capital: 2000000, safety: 0.9 },
    costs: { brokerage: 20, slippageTicks: 1, freeze: 1800 }, notes: "" };
  const trades = [...pastTrades, { ...pastTrades[0], ...closed, pnl: -56346, gross: -52221, costs: 4125, why: "Stop loss" }];
  return {
    id: "s1", name: "NIFTY short straddle", kind: "options", status: "running", stop_reason: null,
    instrument: { symbol: "NIFTY", exchange: "NFO", underlying: "NIFTY" }, strategy,
    started_at: at("2026-09-01", "03:45"), stopped_at: null, spot: 22441, fresh: true, feed_connected: true,
    expiry: "2026-10-06", lot: 65, note: "", signal: null,
    position: { opened, center: 22450, spot_in: 22441, credit: 830635, mtm: 12000, costs: 2000, net: 10000, best: 15000, worst: -2000, rolls: 0, units: 52,
      orders: 2, expiry: "2026-10-06" },
    legs: [{ sym: "NIFTY2600622450CE", side: "sell", qty: 3380, entry: 152.55, mark: 150, pnl: 8619, open: true },
      { sym: "NIFTY2600622450PE", side: "sell", qty: 3380, entry: 113.25, mark: 112.8, pnl: 1521, open: true }],
    trades,
    events: [...pastEvents,
      leg("sell", 22450, "CE", 152.55, "Entry", closed.opened), leg("sell", 22450, "PE", 113.25, "Entry", closed.opened),
      leg("buy", 22450, "PE", 156.1, "Stop loss", closed.closed, -144833), leg("buy", 22450, "CE", 119.65, "Stop loss", closed.closed, 111202),
      leg("sell", 22450, "CE", 152.55, "Entry", opened), leg("sell", 22450, "PE", 113.25, "Entry", opened)],
    equity_curve: trades.map((x, i) => ({ t: x.closed, eq: 2000000 + trades.slice(0, i + 1).reduce((n, y) => n + y.pnl, 0) })),
    account: { capital: 2000000, equity: 1957154, cash: 1957154, realised: -42846, today: -56346, halted: false, entries_today: 2, trades: 21, wins: 17,
      unrealised: 10000 },
  };
}
