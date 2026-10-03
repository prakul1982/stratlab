import { expect, test, type Page } from "@playwright/test";

// Signed in as the site owner (the fake database's admin-token), with the tour already seen.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

/** Signed in as another of the fake database's users instead (free-token, basic-token, ...). */
function sessionAs(token: string, id: string, email: string) {
  return { ...session, access_token: token, user: { ...session.user, id, email } };
}

async function open(page: Page, path: string, ready: string, who: typeof session = session) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    // fallback: a test's own route for a backend call (registered before this) still gets its turn
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(path);
  // a first visit asks what the person came for; answer it like a new user would
  const ask = page.getByText("What brings you to StratLab?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /Both/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);
  return errors;
}

/** What every page must get right: no crash, nothing wider than the screen, no broken numbers. */
async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  await expect(page.getByText(/couldn't load your account|can't reach the StratLab server/i), "the page couldn't reach the server").toHaveCount(0);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\b0k\b/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
}

/** On a phone: every button, menu and stand-alone link is big enough for a finger (small icons that carry a larger
 * invisible touch area are left out). */
async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || (el as HTMLInputElement).placeholder || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

/** Bars for gains end at the zero line from above; bars for losses start at it and hang below. */
async function barsAroundZero(page: Page) {
  const charts = page.locator(".tbars");
  expect(await charts.count()).toBeGreaterThan(0);
  let losses = 0;
  for (const chart of await charts.all()) {
    if (!(await chart.locator(".tbar-zero").count())) continue;        // no losses in this chart: no zero line drawn
    const zero = await chart.locator(".tbar-zero").first().boundingBox();
    for (const bar of await chart.locator(".tbar-bar").all()) {
      const v = Number(await bar.getAttribute("data-v"));
      const b = await bar.boundingBox();
      if (!b || !zero) continue;
      if (v < 0) { losses++; expect(Math.abs(b.y - zero.y), "a loss bar starts at the zero line").toBeLessThan(2); }
      else expect(Math.abs(b.y + b.height - zero.y), "a gain bar ends at the zero line").toBeLessThan(2);
    }
  }
  expect(losses, "loss years are drawn").toBeGreaterThan(0);
}

const PAGES: [string, string][] = [
  ["/", "notebook"], ["/notebooks", "notebook"], ["/library", "librar"], ["/options", "Options"], ["/paper", "Paper"],
  ["/research", "Companies"], ["/research/IN/RELIANCE", "Reliance"], ["/research/US/AAPL", "AAPL"], ["/research/IN/RELIANCE/deep", "Growth and margins"],
  ["/research/scan", "Stage 2"], ["/research/rotation", "rotation"], ["/research/investor", "Investor"], ["/news", "News"], ["/plans", "Plans"],
  ["/account", "Account"], ["/admin", "Needs your attention"], ["/admin?tab=services", "Market data"], ["/admin?tab=checks", "Check every feature"],
  ["/admin?tab=users", "Paper trading now"], ["/admin?tab=billing", "Launch offer"],
];

for (const [path, ready] of PAGES) {
  test(`page ${path}`, async ({ page }, info) => {
    await sane(page, await open(page, path, ready));
    if (info.project.name === "phone") await touchable(page);
  });
}

test("losses hang below the zero line, with exact labels (company page)", async ({ page }) => {
  const errors = await open(page, "/research/IN/TCS", "Sales and profit, by year");
  await barsAroundZero(page);
  await expect(page.getByText("-133").first()).toBeVisible();
  await expect(page.getByText("loss years in between, so no yearly rate").first()).toBeVisible();
  await sane(page, errors);
});

test("losses hang below the zero line (deep dive)", async ({ page }) => {
  const errors = await open(page, "/research/IN/TCS/deep", "Growth and margins");
  await barsAroundZero(page);
  await expect(page.getByText("A loss year in the period, so no yearly rate").first()).toBeVisible();
  await sane(page, errors);
});

test("a US deep dive is in dollars, from the SEC's filings", async ({ page }) => {
  const errors = await open(page, "/research/US/AAPL/deep", "Growth and margins");
  await expect(page.getByText("$ billion").first()).toBeVisible();          // a company this size reads in billions
  expect(await page.locator("main").innerText()).not.toMatch(/\d{3},\d{3} million/);
  await expect(page.getByText("Read the annual report and releases")).toBeVisible();
  await expect(page.getByText("Check past releases")).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(/₹|crore/);
  await sane(page, errors);
});

test.describe("a visitor from the UK", () => {
  test.use({ locale: "en-GB", timezoneId: "Europe/London" });
  test("sees prices in pounds", async ({ page }) => {
    const errors = await open(page, "/plans", "Plans");
    await expect(page.getByText(/£\d+/).first()).toBeVisible();
    await sane(page, errors);
  });
});

test.describe("a visitor in India", () => {
  test.use({ locale: "en-US", timezoneId: "Asia/Kolkata" });
  test("sees prices in rupees", async ({ page }) => {
    const errors = await open(page, "/plans", "Plans");
    await expect(page.getByText("₹999").first()).toBeVisible();
    await sane(page, errors);
  });
});

test("invoices: in Account for the customer, with the GST setup in Admin", async ({ page }) => {
  let errors = await open(page, "/account", "Invoices");
  await expect(page.getByText("Details on your invoices")).toBeVisible();
  await sane(page, errors);
  errors = await open(page, "/admin?tab=billing", "LUT ARN");
  await expect(page.getByText(/Financial year \d{4}-\d{2}/)).toBeVisible();
  await sane(page, errors);
});

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";     // the fake backend (tests/visual_server.py)

test("first steps on Home tick themselves from real data, and hide for good", async ({ page, request }, info) => {
  // each project signs in as its own brand-new user, so hiding the list on one doesn't hide it on the other
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["free-token", "u-free", "free@example.com"];
  const auth = { Authorization: `Bearer ${token}` };
  await request.put(`${API}/me/prefs`, { headers: auth, data: { level: "some", focus: "both" } });     // skip the welcome questions
  expect((await request.put(`${API}/me/first-steps`, { headers: auth, data: { dismissed: false } })).ok()).toBeTruthy();
  expect((await request.put(`${API}/research/watchlist`, { headers: auth, data: { items: [{ region: "IN", symbol: "TCS" }] } })).ok()).toBeTruthy();
  const errors = await open(page, "/", "Your first steps", sessionAs(token, id, email));
  const list = page.locator(".first-steps");
  await expect(list.locator("li")).toHaveCount(5);
  await expect(list.locator('[data-step="watchlist"]')).toHaveClass(/done/);
  await expect(list.locator('[data-step="backtest"] a')).toHaveAttribute("href", "/new");
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  expect((await request.get(`${API}/research/deep/RELIANCE?region=IN`, { headers: auth })).ok()).toBeTruthy();
  await page.reload();
  await expect(list.locator('[data-step="deepdive"]')).toHaveClass(/done/, { timeout: 30_000 });
  await expect(page.getByText(/\d of 5 done/)).toBeVisible();

  await list.getByRole("button", { name: "Hide this" }).click();
  await expect(page.getByText("Your first steps")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("notebook", { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  await expect(page.getByText("Your first steps")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("the launch offer counts down on Home and Plans", async ({ page }, info) => {
  const until = new Date(Date.now() + (2 * 24 + 5) * 3600_000 + 10 * 60_000).toISOString();
  await page.route(`${API}/me`, async (r) => {
    const res = await r.fetch();
    await r.fulfill({ response: res, json: { ...(await res.json()), promo: { until } } });
  });
  let errors = await open(page, "/", "Launch offer:");
  await expect(page.locator(".promo-countdown")).toContainText("2 days 5 hours");
  await expect(page.getByText("Launch offer:")).toHaveCount(1);              // the countdown replaces the site-wide note here
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
  errors = await open(page, "/plans", "Launch offer:");
  await expect(page.locator(".promo-countdown")).toContainText("2 days 5 hours");
  await sane(page, errors);
});
