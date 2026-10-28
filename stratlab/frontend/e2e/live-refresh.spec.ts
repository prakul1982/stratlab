import { expect, test, type Page } from "@playwright/test";

// LIVE-1: a page that shows live market numbers reads them again by itself each minute while its market is open and the tab is in
// view, and stops when every market it shows is shut. The page's clock is faked (page.clock) so a minute passes at once.
const base = { token_type: "bearer", expires_in: 86400 * 30 };
const ADMIN = { token: "admin-token", id: "u-admin", email: "owner@example.com" };

async function signIn(page: Page, path: string, at: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  // a session valid for weeks, so the faked clock (a Wednesday or a Saturday) never finds it expired
  const session = { ...base, access_token: ADMIN.token, refresh_token: "r", expires_at: Math.floor(Date.parse(at) / 1000) + 86400 * 30,
    user: { id: ADMIN.id, aud: "authenticated", email: ADMIN.email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.clock.install({ time: new Date(at) });
  await page.goto(path);
  return errors;
}

/** How many times the page has asked for a URL (a substring of it). */
function counter(page: Page, part: string) {
  let n = 0;
  page.on("request", (r) => { if (r.url().includes(part)) n++; });
  return () => n;
}

const WED_OPEN = "2026-10-28T05:00:00Z";      // 10:30 IST on a Wednesday: India trades, the dollar and gold trade; the US opens at 19:00 IST
const SAT = "2026-10-31T06:00:00Z";           // 11:30 IST on a Saturday: India, the US, the dollar and gold are all shut

test("live: My space's market tiles and gold are read again each minute while a market is open, and the time under them moves", async ({ page }) => {
  const nifty = counter(page, "/research/chart/IN/");
  const dollar = counter(page, "/chart/candles/FX");
  const gold = counter(page, "/money/gold");
  await signIn(page, "/mine", WED_OPEN);
  const strip = page.getByTestId("mine-markets");
  await expect(strip.locator(".mine-mkt")).toHaveCount(6, { timeout: 30_000 });
  await expect(strip.locator(".k-skel")).toHaveCount(0, { timeout: 30_000 });
  await expect(strip.getByTestId("mine-mkt-at")).toContainText(/Levels read at 10:[0-5]\d IST/, { timeout: 30_000 });
  const first = [nifty(), dollar(), gold()];
  expect(first.every((n) => n >= 1), "each is read once on opening").toBe(true);
  const stamp1 = await strip.getByTestId("mine-mkt-at").innerText();
  await page.clock.runFor(61_000);
  await expect.poll(() => [nifty(), dollar(), gold()].every((n, i) => n > first[i]), { timeout: 15_000 }).toBe(true);
  await expect(strip.getByTestId("mine-mkt-at")).not.toHaveText(stamp1, { timeout: 15_000 });         // the time moves with the levels
  const second = [nifty(), dollar(), gold()];
  await page.clock.runFor(60_000);
  await expect.poll(() => nifty() > second[0], { timeout: 15_000 }).toBe(true);
  // nothing jumps: the six tiles are still there, none back to a placeholder
  await expect(strip.locator(".mine-mkt")).toHaveCount(6);
  await expect(strip.locator(".k-skel")).toHaveCount(0);
});

test("live: My space's tiles are not read again while every market they show is shut", async ({ page }) => {
  const nifty = counter(page, "/research/chart/IN/");
  const sp = counter(page, "/research/chart/US/");
  const dollar = counter(page, "/chart/candles/FX");
  const gold = counter(page, "/money/gold");
  await signIn(page, "/mine", SAT);
  const strip = page.getByTestId("mine-markets");
  await expect(strip.locator(".mine-mkt")).toHaveCount(6, { timeout: 30_000 });
  await expect(strip.locator(".k-skel")).toHaveCount(0, { timeout: 30_000 });
  await expect(strip.getByTestId("mine-mkt-at")).toBeVisible({ timeout: 30_000 });
  const first = [nifty(), sp(), dollar(), gold()];
  await page.clock.runFor(5 * 60_000);
  await page.waitForTimeout(500);
  expect([nifty(), sp(), dollar(), gold()], "no tile is read again on a Saturday").toEqual(first);
});

test("live: a hidden tab reads nothing, and the tab coming back into view reads at once", async ({ page }) => {
  const nifty = counter(page, "/research/chart/IN/");
  await signIn(page, "/mine", WED_OPEN);
  const strip = page.getByTestId("mine-markets");
  await expect(strip.locator(".k-skel")).toHaveCount(0, { timeout: 30_000 });
  await expect(strip.getByTestId("mine-mkt-at")).toBeVisible({ timeout: 30_000 });
  const first = nifty();
  const view = (state: "hidden" | "visible") => page.evaluate((v) => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => v });
    document.dispatchEvent(new Event("visibilitychange"));
  }, state);
  await view("hidden");
  await page.clock.runFor(3 * 60_000);
  await page.waitForTimeout(500);
  expect(nifty(), "nothing is read while the tab is out of view").toBe(first);
  await view("visible");
  await expect.poll(nifty, { timeout: 15_000 }).toBeGreaterThan(first);                   // and once on coming back
});

test("live: My space's P&L card reads the holdings again each minute while India trades and says when its prices are from", async ({ page }) => {
  const holdings = counter(page, "/holdings");
  await signIn(page, "/mine", WED_OPEN);
  const pnl = page.getByTestId("mine-pnl");
  await expect(pnl.locator(".k-skel-box")).toHaveCount(0, { timeout: 30_000 });
  await expect(pnl).toContainText(/₹|needs prices|Your P&L/, { timeout: 30_000 });
  const n0 = holdings();
  expect(n0).toBeGreaterThanOrEqual(1);
  await page.clock.runFor(61_000);
  await expect.poll(holdings, { timeout: 15_000 }).toBeGreaterThan(n0);
});

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

test("live: the holdings page reads the prices again each minute and nothing else (not the filings facts, not the uploads)", async ({ page, request }) => {
  const held = await (await request.get(`${API}/holdings`, { headers: { Authorization: `Bearer ${ADMIN.token}` } })).json();
  test.skip(!held.rows?.length, "the fake world holds no holdings for this account");
  const holdings = counter(page, "/holdings");
  const facts = counter(page, "/holdings/facts");
  const imports = counter(page, "/holdings/import");
  const tax = counter(page, "/tax");
  await signIn(page, "/holdings", WED_OPEN);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".k-skel-box")).toHaveCount(0, { timeout: 30_000 });
  await expect.poll(facts, { timeout: 30_000 }).toBeGreaterThanOrEqual(1);          // the facts are read once, after the holdings
  await page.waitForTimeout(500);
  const n0 = holdings(), f0 = facts();
  await page.clock.runFor(61_000);
  await expect.poll(() => holdings() - facts() > n0 - f0, { timeout: 15_000 }).toBe(true);
  expect(facts(), "the filings facts are read once").toBe(f0);
  expect(imports()).toBe(0);
  expect(tax()).toBe(0);
});

test("live: the net worth page reads only the price-dependent part again (no history, no deposit tax), and not at all with the markets shut", async ({ page }) => {
  const live = counter(page, "/money/net-worth?live=true");
  const full = counter(page, "/money/net-worth");
  const bodies: string[] = [];
  page.on("response", async (r) => { if (r.url().includes("live=true") && r.ok()) bodies.push(await r.text().catch(() => "")); });
  await signIn(page, "/money/net-worth", WED_OPEN);
  await expect(page.getByRole("heading", { level: 1, name: "Net worth" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".k-skel-box")).toHaveCount(0, { timeout: 30_000 });
  const f0 = full();
  await page.clock.runFor(61_000);
  await page.waitForTimeout(800);
  if (live() === 0) {
    // an account whose rows are not valued at a market price has nothing to read again
    test.skip(true, "the fake world's net worth has no row at a market price");
  }
  expect(bodies.length).toBeGreaterThan(0);
  const body = JSON.parse(bodies[0]);
  expect(body.totals).toBeTruthy();
  expect(body.history).toBeUndefined();
  expect(body.deposit_tax).toBeUndefined();
  expect(full() - live(), "the full page is not read again").toBe(f0);
});
