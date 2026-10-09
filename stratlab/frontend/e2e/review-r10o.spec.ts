import { expect, test, type Page, type Route } from "@playwright/test";

// Round 10 review of the owner's pages (9 Oct 2026): what the app draws, on the reviewer's examples. Every answer a test depends
// on is fixed here (the fake world's background jobs can't change it), and the clock is a fixed instant.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
const NOW = "2026-10-09T09:05:00Z";
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

/** The fake world's own answer for a request, changed by `edit`. */
const edited = (edit: (j: Record<string, any>) => Record<string, any>) => async (r: Route) => {
  const res = await r.fetch();
  return r.fulfill({ response: res, json: edit(await res.json()) });
};

// ---------- R10O-001: a provider's long error with an unbreakable link doesn't push Admin sideways ----------
test("a provider's long error with an unbreakable link keeps Admin Overview inside a phone's width (R10O-001)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const long = "403: AI Gateway requires a valid credit card on file to service requests. Visit https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai%3Fmodal%3Dadd-credit-card"
    + "%26source%3Dai-gateway-free-credit-exhausted-please-add-a-card-to-continue-using-the-gateway to add one.";
  const errors = await open(page, "/admin", [[/\/admin\/overview$/, edited((j) => ({
    ...j, server: { ...j.server, ai: [{ label: "Vercel AI Gateway", configured: true, in_use: true, model: null, last_error: long, answering: false, state_text: long }] },
  }))]]);
  const row = page.locator(".adm-todo-t", { hasText: "AI, Vercel AI Gateway" });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText("AI, Vercel AI Gateway: 403: AI Gateway requires a valid credit card on file to service requests.");
  await expect(row).not.toContainText("vercel.com/d?to=");                      // one line; the whole text is in the tooltip
  await expect(row.locator("span").last()).toHaveAttribute("title", /vercel\.com\/d\?to=/);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

// ---------- R10O-008: the PCR table, with the market shut ----------
test("the PCR table says its rows are the last close's recording while the market is shut (R10O-008)", async ({ page }) => {
  const row = (name: string) => ({ name, exchange: "NFO", expiry: "2026-10-13", cycle: "weekly", pcr_oi: 0.84, pcr_vol: 0.91, pcr_near: 0.84, pcr_all: 0.9,
    strikes_read: 31, near_strikes: 15, spot: 22520.45, source: "recorded", at_close: true, as_of: "2026-10-09T15:39:00+05:30" });
  const errors = await open(page, "/trade/positioning", [[/\/trade\/positioning\/pcr$/, { pcr: ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"].map(row) }]]);
  const table = page.getByTestId("pcr-table");
  await expect(table).toBeVisible({ timeout: 30_000 });
  await expect(table.getByRole("row")).toHaveCount(6);
  await expect(page.getByTestId("pcr-note")).toContainText("The market is shut, so each index shows StratLab's recording of its last close.");
  expect(errors).toEqual([]);
});

// ---------- R10O-009: a company page's header and tables don't wait on its news or its AI read ----------
test("the company page shows its header, price and tables while the news and the AI read are still coming (R10O-009)", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const held = (r: Route) => gate.then(async () => { const res = await r.fetch(); await r.fulfill({ response: res }); });
  const asked: string[] = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (u.pathname.startsWith("/research/company/")) asked.push(u.pathname + u.search); });
  const errors = await open(page, "/research/IN/TCS", [[/\/research\/company\/IN\/TCS\/more$/, held], [/\/research\/company\/IN\/TCS\/ai(\?|$)/, held]]);
  await expect(page.getByRole("heading", { name: /Tata Consultancy/ }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Prices as of")).toBeVisible();
  await expect(page.locator("#co-numbers")).toBeVisible();
  await expect(page.locator("#co-news")).toContainText("Loading the latest news");           // only the news card waits
  await expect(page.locator("#co-news .inv-news-row")).toHaveCount(0);
  expect(asked).toContain("/research/company/IN/TCS?lean=1");
  release();
  await expect(page.locator("#co-news .inv-news-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#co-news")).not.toContainText("Loading the latest news");
  expect(errors).toEqual([]);
});

// ---------- R10O-011: a bank's financing margin, when none can be shown ----------
test("a bank's quarters table leaves the financing margin out when none of it can be shown, and keeps it when it can (R10O-011)", async ({ page }) => {
  const bank = (opm: (number | null)[]) => edited((j) => ({ ...j, bank: true, quarters: { cols: ["Dec 2025", "Mar 2026", "Jun 2026"], sales: [50000, 51000, 52241], profit: [15000, 15500, 16276], opm } }));
  const errors = await open(page, "/research/IN/TCS", [[/\/research\/company\/IN\/TCS(\?lean=1)?$/, bank([null, null, null])]]);
  const quarters = page.getByRole("region", { name: /The last quarters/ });
  await expect(quarters).toBeVisible({ timeout: 30_000 });
  await expect(quarters).toContainText("Net profit");
  await expect(quarters).not.toContainText("Financing margin");
  await page.unroute("**/*");
  expect(errors).toEqual([]);
  const again = await open(page, "/research/IN/TCS", [[/\/research\/company\/IN\/TCS(\?lean=1)?$/, bank([31, 30, 33])]]);
  await expect(page.getByRole("region", { name: /The last quarters/ })).toContainText("Financing margin", { timeout: 30_000 });
  await expect(page.getByRole("region", { name: /The last quarters/ })).toContainText("33%");
  expect(again).toEqual([]);
});

// ---------- R10O-012: the screener names a stock whose close is old ----------
test("the US screener names the one stock whose close is older, instead of calling the list oldest-close 2 Oct (R10O-012)", async ({ page }) => {
  await page.route(/\/research\/screens\/run$/, edited((j) => ({
    ...j, as_of: "2026-10-08", as_of_newest: "2026-10-08", stale: [{ symbol: "XYZ", name: "Xyz Corp", price_at: "2026-10-02" }],
  })));
  const errors = await open(page, "/research/screens?region=US");
  await expect(page.getByTestId("screens-stale")).toHaveText("One stock's close is from 2 Oct: XYZ.", { timeout: 30_000 });
  await expect(page.getByText("Oldest close")).toHaveCount(0);
  expect(errors).toEqual([]);
});
