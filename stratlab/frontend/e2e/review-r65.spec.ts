import { expect, test, type Page, type Route } from "@playwright/test";

// Round 65 (19 Oct 2026): a company page left open while the market trades. Helpers as in review-r7t, with a running clock.
// Every answer the page depends on is fixed here (the fake world's background jobs can't change it), and every clock is a
// fixed instant: 09:39 IST on Friday 9 Oct 2026, unless a test says otherwise.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
const OPEN = "2026-10-09T04:09:00Z";                 // 09:39 IST
type Mock = [RegExp, unknown | ((r: Route) => Promise<void>)];

async function open(page: Page, path: string, mocks: Mock[] = [], now: string | null = OPEN) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  if (now) await page.clock.install({ time: new Date(now) });
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


test("a company page left open reads its chart once, not each minute (R65-001)", async ({ page }) => {
  let charts = 0, n = 0;
  page.on("request", (r) => { if (r.url().includes("/research/chart/IN/RELIANCE")) charts++; });
  await open(page, "/research/IN/RELIANCE", [
    [/\/research\/company\/IN\/RELIANCE(\?lean=1)?$/, edited((j) => ({ ...j, market_open: true, phase: "open",
      quote: { ...(j.quote as object), price: 1179, at: new Date(Date.parse(OPEN)).toISOString() } }))],
    [/\/research\/quotes/, async (r: Route) => r.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ RELIANCE: { price: 1180 + ++n, change_pct: 0.1, at: new Date(Date.parse(OPEN) + n * 60_000).toISOString() } }) })],
  ]);
  await expect(page.getByTestId("company-price")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(3000);
  const first = charts;
  for (let i = 0; i < 3; i++) { await page.clock.runFor(61_000); await page.waitForTimeout(1500); }
  expect(n).toBeGreaterThanOrEqual(2);
  expect(charts).toBe(first);
});
