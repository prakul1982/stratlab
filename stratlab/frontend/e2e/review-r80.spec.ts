import { expect, test, type Page, type Route } from "@playwright/test";

// Round 80 fixes (22 Oct 2026): leftovers from rounds 73 and 79. The clock is a fixed instant.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
const NOW = "2026-10-22T06:00:00Z";
type Mock = [RegExp, unknown | ((r: Route) => Promise<void>)];

async function open(page: Page, path: string, mocks: Mock[] = [], who = { token: "admin-token", id: "u-admin", email: "owner@example.com" }) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.clock.setFixedTime(new Date(NOW));
  await page.route("**/*", async (r) => {
    const u = new URL(r.request().url());
    const call = ["fetch", "xhr"].includes(r.request().resourceType());
    for (const [re, body] of call ? mocks : []) {
      if (re.test(u.pathname + u.search)) {
        if (typeof body === "function") return (body as (r: Route) => Promise<void>)(r);
        return r.fulfill({ status: 200, body: JSON.stringify(body), contentType: "application/json" });
      }
    }
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: who.token, user: { id: who.id, aud: "authenticated", email: who.email, role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(path);
  return errors;
}

// ---------- R73-003: a busy market-data answer is read once more before the chart shows an error ----------
test("the price chart reads its candles again after a busy answer instead of showing an error (R73-003)", async ({ page }) => {
  let calls = 0;
  const busyOnce = async (r: Route) => {
    calls += 1;
    if (calls === 1) return r.fulfill({ status: 503, body: JSON.stringify({ detail: "The market data source is busy." }), contentType: "application/json" });
    return r.fallback();
  };
  const errors = await open(page, "/research/IN/RELIANCE", [[/\/research\/chart\/IN\/RELIANCE\?tf=1d/, busyOnce]]);
  const chart = page.getByTestId("price-chart").first();
  await expect(chart).toHaveAttribute("data-loaded", "1d", { timeout: 30_000 });
  await expect(chart.getByText("Couldn't load prices")).toHaveCount(0);
  expect(calls).toBeGreaterThanOrEqual(2);
  expect(errors).toEqual([]);
});

// ---------- R79-007: the PCR table is a card per index on a phone, so no column sits past the edge ----------
test("the put-call ratio table fits a phone without a sideways swipe (R79-007)", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "a phone layout");
  const row = (name: string) => ({ name, exchange: "NFO", expiry: "2026-10-27", cycle: "weekly", pcr_oi: 0.84, pcr_vol: 0.91, pcr_near: 0.84, pcr_all: 0.9,
    strikes_read: 31, near_strikes: 15, spot: 25520.45, source: "live", at_close: false, as_of: "2026-10-22T11:29:00+05:30" });
  const errors = await open(page, "/trade/positioning", [[/\/trade\/positioning\/pcr$/, { pcr: ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"].map(row) }]]);
  const table = page.getByTestId("pcr-table");
  await expect(table.locator('tr[data-pcr="SENSEX"]')).toBeVisible({ timeout: 30_000 });
  const over = await table.evaluate((t) => { const w = t.querySelector(".k-tbl-wrap")!; return w.scrollWidth - w.clientWidth; });
  expect(over, "the table scrolls sideways").toBeLessThanOrEqual(1);
  await expect(table.locator('tr[data-pcr="NIFTY"] td[data-label="Strikes in the PCR"]')).toBeVisible();
  expect(errors).toEqual([]);
});
