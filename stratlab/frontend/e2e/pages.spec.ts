import { readFileSync } from "node:fs";
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
  ["/research/scan", "Stage 2"], ["/research/screens", "Filter companies by plain facts"], ["/alerts", "Your stock alerts"], ["/research/watchlist", "Companies you're watching"], ["/research/rotation", "rotation"], ["/research/results", "Results this week and next"], ["/research/corporate-actions", "Dividends, bonuses and splits"], ["/research/investor", "Investor"], ["/holdings", "By sector"], ["/tax-report", "How FY"], ["/news", "News"], ["/plans", "Plans"],
  ["/account", "Account"], ["/admin", "Needs your attention"], ["/admin?tab=services", "Market data"], ["/admin?tab=checks", "Check every feature"],
  ["/admin?tab=users", "Paper trading now"], ["/admin?tab=billing", "Launch offer"],
];

for (const [path, ready] of PAGES) {
  test(`page ${path}`, async ({ page }, info) => {
    await sane(page, await open(page, path, ready));
    if (info.project.name === "phone") await touchable(page);
  });
}

test("results calendar: every company's dates, and the company page links to it", async ({ page }, info) => {
  await sane(page, await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called"));
  await expect(page.getByRole("link", { name: "RELIANCE" }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Financial Results").first()).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await expect(page.getByRole("link", { name: "RELIANCE" }).first()).toHaveAttribute("href", "/research/IN/RELIANCE");
  await page.goto("/research/IN/RELIANCE");
  await expect(page.getByRole("link", { name: /^Results on / })).toBeVisible({ timeout: 30_000 });
});

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

test("the company AI read shows plain numbers, never 0-100 scores", async ({ page }) => {
  // an old stored read can still carry scores: the page must draw the fact rows and none of the scores
  const read = {
    summary: "Runs refineries, a telecom network and retail stores.", valuation_note: "P/E 24 against 20-28 over five years.",
    scores: { moat: 92, growth: 94, momentum: 81, health: 38 }, composite: 77,
    facts: [
      { id: "growth", label: "Growth", items: [{ label: "Sales, 3 years", text: "11.6% a year" }, { label: "Net profit, 5 years", text: "15.3% a year" }] },
      { id: "price", label: "Price trend", items: [{ label: "Price vs 200-day average", text: "1.5% below" }, { label: "Stage (150-day average)", text: "Stage 3 (topping)" }] },
      { id: "debt", label: "Debt and cash", items: [{ label: "Debt to equity", text: "0.44" }, { label: "Interest cover", text: "6.1x" }] },
      { id: "margins", label: "Margins and returns", items: [{ label: "Operating margin, 5 years", text: "17% → 16% → 18% (Mar 2023 to Mar 2025)" }, { label: "ROCE", text: "9.7%" }] },
    ],
    bull: ["Jio has 470 million users."], bear: ["Refining margins move with crude."], segments: [], position: "", watch: [], ideas: [],
    generated_at: Date.now() / 1000,
  };
  await page.route("**/research/company/IN/RELIANCE/ai*", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(read) }));
  const errors = await open(page, "/research/IN/RELIANCE", "The numbers");
  const ai = page.locator(".ai-read");
  for (const t of ["Growth", "Price trend", "Debt and cash", "Margins and returns", "11.6% a year", "1.5% below", "6.1x", "ROCE"])
    await expect(ai.getByText(t, { exact: false }).first()).toBeVisible();
  const text = await ai.innerText();
  expect(text).not.toMatch(/\b(moat|momentum|health|score)\b/i);
  for (const n of ["92", "94", "81", "38", "77"]) expect(text).not.toMatch(new RegExp(`(^|\\s)${n}(\\s|$)`));
  expect(await ai.locator(".score-track").count()).toBe(0);
  // deals: "Bought" and "Sold" in one neutral style, words only
  const sides = page.locator(".deals-table .badge");
  const looks = new Set(await sides.evaluateAll((els) => els.map((e) => `${getComputedStyle(e).backgroundColor}|${getComputedStyle(e).color}`)));
  expect(looks.size).toBeLessThanOrEqual(1);
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

// Public company pages are plain HTML from the API (the site's host forwards /stocks/* there), for search engines.
for (const [path, name, symbol] of [["/stocks/in/RELIANCE", "Reliance Industries", "RELIANCE"], ["/stocks/us/AAPL", "Apple Inc.", "AAPL"]]) {
  test(`public company page ${path}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(API + path);
    await expect(page.locator("h1")).toContainText(name);
    await expect(page.getByRole("link", { name: `Test a strategy on ${symbol}` })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open the full deep dive" })).toBeVisible();
    await expect(page.getByText(/As of \d+ \w+ \d{4}/).first()).toBeVisible();
    expect(errors).toEqual([]);
    const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
    expect(await page.locator("main").innerText()).not.toMatch(/\bNaN\b|\bundefined\b|\bnull\b|Infinity/);
    if (info.project.name === "phone") await touchable(page);
  });
}

test("a company page's test link opens a new test on that company", async ({ page }) => {
  const errors = await open(page, "/new?market=IN&symbol=RELIANCE", "testing a strategy on RELIANCE");
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
    await expect(page.getByText("₹699 / month", { exact: true })).toBeVisible();
    await expect(page.getByText("₹1,999 / month", { exact: true })).toBeVisible();
    await expect(page.getByText("incl. GST", { exact: true })).toHaveCount(2);        // next to each rupee price
    await sane(page, errors);
  });
});

test("plans: short cards, the full comparison, and backtests (not experiments)", async ({ page }, info) => {
  const errors = await open(page, "/plans", "Side by side");
  for (const line of ["Everything in Free, plus:", "Everything in Basic, plus:", "10 backtests a month, each with a full verdict",
    "2 company deep dives and 1 slide deck a month", "Indian F&O and options entered on your own rules' signals"]) {
    await expect(page.locator(".grid4 li", { hasText: line })).toBeVisible();
  }
  for (const card of await page.locator(".grid4 > .card").all()) expect(await card.locator("li").count()).toBeLessThanOrEqual(9);
  expect(await page.locator("main").innerText()).not.toMatch(/experiment/i);
  const table = page.locator("table.plan-compare");
  const row = (label: string) => table.locator("tr", { has: page.getByText(label, { exact: true }) }).locator("td");
  await expect(row("Backtests a month, each with a verdict")).toHaveText(["Backtests a month, each with a verdict", "10", "100", "Unlimited"]);
  await expect(row("Company deep dives a month")).toHaveText(["Company deep dives a month", "2", "15", "Unlimited"]);
  await expect(row("All 20+ indicators")).toHaveText(["All 20+ indicators", "–", "✓", "✓"]);
  await expect(row("Trade notifications")).toHaveText(["Trade notifications", "–", "✓", "✓"]);
  await expect(row("Indian F&O")).toHaveText(["Indian F&O", "–", "–", "✓"]);
  await expect(row("Red flags on every company page")).toHaveText(["Red flags on every company page", "✓", "✓", "✓"]);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
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

const HOLDINGS_FILES = new URL("../../backend/tests/fixtures/holdings/", import.meta.url).pathname;

/** The first-visit questions stay open over the page until answered; these tests click on the page, so answer them. */
async function settle(page: Page) {
  const level = page.getByRole("dialog", { name: /How much .* have you done/ });
  await level.waitFor({ timeout: 4000 }).then(() => level.getByRole("button", { name: /done a bit/ }).click()).catch(() => undefined);
  await expect(level).toHaveCount(0);
}

test("my holdings: positions, sectors and facts per stock, then a broker file added", async ({ page, request }, info) => {
  // start from the owner's Zerodha file again: the other project's run of this test added a Groww file to the shared account
  const zerodha = "zerodha_console_holdings.xlsx";
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: "Bearer admin-token" },
    data: { filename: zerodha, data: readFileSync(HOLDINGS_FILES + zerodha).toString("base64"), mode: "replace" } })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "By sector");
  await settle(page);
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.getByText("RELIANCE", { exact: true })).toBeVisible();
  await expect(table.getByText("TINYCO", { exact: true })).toBeVisible();            // listed only on BSE
  await expect(page.getByText(/your Zerodha Console file/)).toBeVisible();
  await expect(table.getByText(/red flag/).first()).toBeVisible({ timeout: 30_000 });  // the QIP filing, once the facts arrive
  await expect(table.getByText(/Stage \d/).first()).toBeVisible();
  await expect(page.getByText("Recent filings")).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(/\b(buy|sell|accumulate|avoid)\b/i);
  await page.getByRole("radio", { name: "Add to them" }).click();
  await page.locator("input[type=file]").setInputFiles(HOLDINGS_FILES + "groww_holdings_statement.xlsx");
  await expect(page.getByText("Read as a Groww file")).toBeVisible({ timeout: 30_000 });   // matching a first file reads the stock lists
  const missed = page.getByRole("table", { name: "Lines that couldn't be matched" });
  await expect(missed.getByText(/INE000X01000/)).toBeVisible();
  await expect(table.getByText("INFY", { exact: true })).toBeVisible();
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
});

test("my holdings: edit by hand and delete them all", async ({ page }, info) => {
  const errors = await open(page, "/holdings", "By sector");
  await settle(page);
  await page.getByRole("button", { name: "Edit RELIANCE" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit RELIANCE" });
  await expect(dialog.getByRole("button", { name: "Save" })).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Close" }).click();
  // the delete is answered here, so the shared fake account keeps its holdings for the other tests
  const empty = { rows: [], allocation: [], totals: { value: 0, invested: 0, pnl: null, pnl_pct: null, day: null, day_pct: null, count: 0, priced: 0 },
    source: null, updated_at: null, prices: true, limit: 300, facts_max: 40 };
  await page.route("**/holdings", (r) => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify(r.request().method() === "DELETE" ? { deleted: true } : empty) }));
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete my holdings" }).click();
  await expect(page.getByText("No holdings yet")).toBeVisible();
  await expect(page.getByText("Your holdings are deleted.")).toBeVisible();
  await sane(page, errors);
});

test("my holdings: add by hand from suggestions, an Indian stock with the keyboard, then a US one", async ({ page, request }, info) => {
  // each project signs in as its own user with no holdings, so the two runs don't add to the same account
  const n = info.project.name === "phone" ? 152 : 151;
  const [token, id, email] = [`load-${n}`, `u-load-${n}`, `load${n}@example.com`];
  expect((await request.delete(`${API}/holdings`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "No holdings yet", sessionAs(token, id, email));
  await settle(page);
  const box = page.getByRole("combobox", { name: "NSE symbol or BSE code" });
  await box.fill("re");
  const list = page.getByRole("listbox", { name: "Suggestions" });
  const reliance = list.getByRole("option", { name: /Reliance/ }).first();
  await expect(reliance).toBeVisible();
  await expect(box).toHaveAttribute("aria-expanded", "true");
  const options = await list.getByRole("option").allInnerTexts();
  expect(options.length).toBeGreaterThan(0);
  expect(options.length).toBeLessThanOrEqual(8);
  expect(options[0]).toMatch(/\bRE/);                                             // symbols starting with what's typed come first
  const width = page.viewportSize()!.width;
  const b = (await list.boundingBox())!;
  expect(b.x).toBeGreaterThanOrEqual(0);
  expect(b.x + b.width, "the suggestions fit on the screen").toBeLessThanOrEqual(width + 1);
  if (info.project.name === "phone") await touchable(page);
  // the keyboard: down to Reliance, Enter picks it and fills the NSE symbol
  const at = options.findIndex((t) => /Reliance/.test(t));
  for (let i = 0; i <= at; i++) await box.press("ArrowDown");
  await expect(reliance).toHaveAttribute("aria-selected", "true");
  await box.press("Enter");
  await expect(box).toHaveValue("RELIANCE");
  await expect(list).toBeHidden();
  await page.getByLabel("Quantity").fill("5");
  await page.getByLabel(/Average price/).fill("2400");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("RELIANCE added.")).toBeVisible({ timeout: 30_000 });
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.getByText("RELIANCE", { exact: true })).toBeVisible();
  // a US stock: found by its name, valued in dollars
  await page.getByRole("radio", { name: "United States" }).click();
  const us = page.getByRole("combobox", { name: "US ticker" });
  await us.fill("apple");
  const apple = list.getByRole("option", { name: /Apple Inc/ });
  await expect(apple).toBeVisible();
  await expect(apple.getByText("US", { exact: true })).toBeVisible();
  await us.press("ArrowDown");
  await us.press("Enter");
  await expect(us).toHaveValue("AAPL");
  await page.getByLabel("Quantity").fill("3");
  await page.getByLabel("Average price ($, optional)").fill("150");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("AAPL added.")).toBeVisible({ timeout: 30_000 });
  await expect(table.getByText("AAPL", { exact: true })).toBeVisible();
  await expect(table.getByRole("row", { name: /AAPL/ })).toContainText("$");
  const usLine = page.getByLabel("US stocks");
  await expect(usLine).toContainText("$");
  await expect(usLine).toContainText("aren't part of the tax report");
  // an exact symbol typed without picking still works
  await page.getByRole("radio", { name: "India (NSE/BSE)" }).click();
  await box.fill("INFY");
  await page.getByLabel("Quantity").fill("2");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("INFY added.")).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
});

const TRADEBOOKS = new URL("../../backend/tests/fixtures/tradebooks/", import.meta.url).pathname;
const TAXPNL = new URL("../../backend/tests/fixtures/taxpnl/", import.meta.url).pathname;

test("tax report: tradebooks from several brokers, one year's gains, lots below cost, downloads and delete", async ({ page, request }, info) => {
  // each project signs in as its own user and starts with no trades, so the two runs don't share tax data
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  expect((await request.delete(`${API}/tax`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/tax-report", "Capital gains on your shares", sessionAs(token, id, email));
  await settle(page);
  await expect(page.getByText("No trades yet")).toBeVisible();
  await expect(page.getByText(/not tax advice/).first()).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  // three files, two brokers, one pick: what they added up to, with the line left out
  await page.locator("input[type=file]").setInputFiles(["upstox_tradebook.csv", "zerodha_tax_pnl.xlsx", "zerodha_console_tradebook.csv"].map((f) => TRADEBOOKS + f));
  await expect(page.getByText(/Read 3 files: 15 trades added/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("table", { name: "Lines left out" }).getByText(/Futures, options/)).toBeVisible();
  await expect(page.getByText(/15 trades from 3 files/)).toBeVisible();
  await expect(page.getByText("Estimate only.")).toHaveCount(1);                                  // once, at the top

  await page.getByRole("combobox", { name: "Financial year" }).selectOption("2024");
  await expect(page.getByRole("heading", { name: "How FY 2024-25 adds up" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Gains by rate" }).getByText("Long-term, sold from 23 Jul 2024")).toBeVisible();
  await expect(page.getByText("1 same-day round trip", { exact: false })).toBeVisible();          // INFY, kept apart
  const sales = page.getByRole("table", { name: "Realised sales" });
  await expect(sales.getByText("RELIANCE").first()).toBeVisible();
  await expect(sales.getByText("grandfathered")).toBeVisible();                                   // WIPRO, from the tax P&L
  await expect(page.getByRole("table", { name: "Open lots below cost" }).getByText("TCS")).toBeVisible();
  await expect(page.getByText("Shares held on 31 Jan 2018")).toBeVisible();
  await page.getByRole("button", { name: "What is tax-loss harvesting?" }).click();
  await expect(page.getByRole("note").filter({ hasText: "wash-sale" })).toBeVisible();

  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/you should|we suggest|consider selling|sell now|recommend/i);
  expect(text).not.toMatch(/yahoo|finnhub|kite|screener/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await csv).suggestedFilename()).toBe("stratlab-tax-FY-2024-25.csv");
  const pdf = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF summary" }).click();
  expect((await pdf).suggestedFilename()).toBe("stratlab-tax-FY-2024-25.pdf");

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete my tax data" }).click();
  await expect(page.getByText("Your tax data is deleted.")).toBeVisible();
  await expect(page.getByText("No trades yet")).toBeVisible();
});

test("tax report: the tax P&L ZIP as the broker gives it, F&O included, checked against its summary, and the total tax", async ({ page, request }, info) => {
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  expect((await request.delete(`${API}/tax`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/tax-report", "Capital gains on your shares", sessionAs(token, id, email));
  await settle(page);
  await expect(page.locator("input[type=file]")).toHaveAttribute("accept", /\.zip/);
  await page.locator("input[type=file]").setInputFiles(TAXPNL + "zerodha_taxpnl_2024_2025.zip");
  await expect(page.getByText(/Read as a Zerodha tax P&L: 16 trades added/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/7 F&O, commodity and currency lines added up as business income/)).toBeVisible();
  await expect(page.getByText(/From the ZIP: Commodity \(2 lines\), Equity short term \(3 lines\), Equity long term \(2 lines\), Equity intraday \(3 lines\), F&O \(4 lines\), Currency \(1 line\)/)).toBeVisible();
  const check = page.getByRole("list", { name: "Totals checked against your broker's summary" });
  await expect(check.getByText(/the same as your broker's summary sheet/)).toHaveCount(9);
  await expect(check.getByText(/F&O turnover: ₹3,788 netted per contract/)).toBeVisible();
  const left = page.getByRole("list", { name: "Files left out" });
  await expect(left.getByText("Non Equity.csv", { exact: false })).toBeVisible();
  await expect(left.getByText("F&O.csv", { exact: false })).toHaveCount(0);
  // the only year with sales opens by itself
  await expect(page.getByRole("heading", { name: "How FY 2024-25 adds up" })).toBeVisible();
  await expect(page.getByText("2 same-day round trips", { exact: false })).toBeVisible();
  await expect(page.getByText("Estimate only.")).toHaveCount(1);
  await expect(page.getByText(/advance tax and TDS already paid aren't included/)).toBeVisible();

  // the total, at the top of the year, with where it comes from
  const total = page.getByRole("region", { name: "Total tax estimate" });
  await expect(total.getByRole("heading", { name: "Total tax estimate, FY 2024-25" })).toBeVisible();
  const chips = total.getByRole("list", { name: "Where the tax comes from" });
  await expect(chips.getByRole("listitem")).toHaveCount(4);
  for (const c of ["Capital gains", "Intraday", "F&O", "Other income"]) await expect(chips.getByRole("listitem").filter({ hasText: c })).toHaveCount(1);
  await expect(total.getByText(/no other income entered yet/)).toBeVisible();
  await expect(total.getByRole("table", { name: "Total tax breakdown" }).getByText("Estimated total tax")).toBeVisible();
  // F&O by segment, and the return and audit facts
  const segs = page.getByRole("table", { name: "F&O by segment" });
  for (const s of ["F&O", "Commodity", "Currency"]) await expect(segs.getByText(s, { exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "F&O by underlying" }).getByText("BANKNIFTY")).toBeVisible();
  await expect(page.getByRole("list", { name: "Returns and tax audit" }).getByText(/ITR-3/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  // other income and the regime: saved, and the estimate follows
  await total.getByRole("textbox", { name: "Other income", exact: true }).fill("1500000");
  await total.getByRole("textbox", { name: "Of which salary", exact: true }).fill("1200000");
  await total.getByRole("radio", { name: "Old" }).click();
  await expect(total.getByRole("textbox", { name: "Deductions", exact: true })).toBeVisible();
  await total.getByRole("textbox", { name: "Deductions", exact: true }).fill("150000");
  if (info.project.name === "phone") await touchable(page);
  await total.getByRole("button", { name: "Save and update" }).click();
  await expect(page.getByText("Saved. The estimate is updated.")).toBeVisible();
  await expect(total.getByText(/^Old regime/)).toBeVisible();
  await expect(total.getByText(/With the same figures, the new regime works out to/)).toBeVisible();
  await expect(total.getByText(/Deductions you entered \(80C and the like\): ₹1,50,000/)).toBeVisible();
  const amount = await total.getByLabel("Estimated total tax").innerText();
  expect(Number(amount.replace(/[^\d]/g, ""))).toBeGreaterThan(100000);
  await expect(total.getByText(/Covers only the income you enter or import here/)).toBeVisible();
  await expect(total.getByText(/Rules for this year not yet confirmed/)).toHaveCount(0);
  await total.getByRole("link", { name: "Which return and whether a tax audit applies" }).click();
  await expect(page.getByRole("list", { name: "Returns and tax audit" })).toBeInViewport();
  await expect(page.locator("#tax-filing").getByRole("link", { name: "incometax.gov.in" })).toHaveAttribute("href", /incometax\.gov\.in/);

  // age and residency: both with their notes, saved per year, and the estimate follows
  await expect(total.getByRole("radio", { name: "Below 60", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(total.getByRole("radio", { name: "Yes", exact: true })).toHaveAttribute("aria-checked", "true");
  await total.getByRole("button", { name: "About age" }).click();
  await expect(page.getByText(/₹3 lakh from 60 to 79 and ₹5 lakh from 80/)).toBeVisible();
  await page.keyboard.press("Escape");
  await total.getByRole("button", { name: "About residency" }).click();
  await expect(page.getByText(/A non-resident gets no section 87A rebate/)).toBeVisible();
  await page.keyboard.press("Escape");
  await total.getByRole("radio", { name: "60–79", exact: true }).click();
  if (info.project.name === "phone") await touchable(page);
  await total.getByRole("button", { name: "Save and update" }).click();
  await expect(total.getByText(/resident, aged 60 to 79/)).toBeVisible();
  await expect(total.getByText(/the old regime's basic exemption is ₹3,00,000/)).toBeVisible();
  const senior = Number((await total.getByLabel("Estimated total tax").innerText()).replace(/[^\d]/g, ""));
  expect(senior).toBeLessThan(Number(amount.replace(/[^\d]/g, "")));
  await total.getByRole("radio", { name: "No", exact: true }).click();
  await total.getByRole("button", { name: "Save and update" }).click();
  await expect(total.getByText(/non-resident, aged 60 to 79/)).toBeVisible();
  await expect(total.getByText("TDS on NRI sales is deducted by the broker; this estimate does not reconcile TDS.").first()).toBeVisible();
  await expect(total.getByText(/Non-resident: no section 87A rebate/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await page.reload();
  await settle(page);
  await expect(page.getByRole("region", { name: "Total tax estimate" }).getByRole("textbox", { name: "Other income", exact: true })).toHaveValue("1500000");
  await expect(page.getByRole("region", { name: "Total tax estimate" }).getByRole("radio", { name: "60–79", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("region", { name: "Total tax estimate" }).getByRole("radio", { name: "No", exact: true })).toHaveAttribute("aria-checked", "true");

  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/you should|we suggest|recommend|better off|switch to/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await csv).suggestedFilename()).toBe("stratlab-tax-FY-2024-25.csv");
  expect((await request.delete(`${API}/tax`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
});

test("tax report: a file that isn't a tradebook gets a plain answer", async ({ page }) => {
  const errors = await open(page, "/tax-report", "Capital gains on your shares");
  await settle(page);
  await page.locator("input[type=file]").setInputFiles(HOLDINGS_FILES + "upstox_holdings.csv");
  await expect(page.getByText(/looks like a holdings file/)).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);
});

/** The experience question that follows the first one covers the page; answer it before clicking anything. */
async function answerLevel(page: Page) {
  const ask = page.getByText(/How much (trading|investing) have you done\?/);
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("button", { name: /done a bit/ }).click()).catch(() => undefined);
  await expect(ask).toHaveCount(0);
}

test("alerts: set one on a company page, then edit and delete it on the Alerts page", async ({ page }, info) => {
  const tag = `e2e ${info.project.name} ${Date.now()}`;             // both projects share the fake database
  let errors = await open(page, "/research/IN/RELIANCE", "Reliance");
  await answerLevel(page);
  await page.getByRole("button", { name: "Set alert" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Alert on RELIANCE" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Price level (₹)").fill("1");
  await dialog.getByLabel("Note for yourself (optional)").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Set alert" }).click();
  await expect(page.getByText(/already above ₹1/).first()).toBeVisible();   // the price is far above: it waits for a cross
  await sane(page, errors);

  errors = await open(page, "/alerts", "Your stock alerts");
  await answerLevel(page);
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Price crosses above ₹1");
  if (info.project.name === "phone") await touchable(page);
  await row.getByRole("button", { name: /Edit/ }).click();
  const edit = page.getByRole("dialog", { name: "Edit alert on RELIANCE" });
  await edit.getByLabel("Alert me when").selectOption("ma_below");
  await edit.getByLabel("Moving average", { exact: true }).selectOption("200");
  await edit.getByRole("button", { name: "Save alert" }).click();
  await expect(row).toContainText("Price crosses below its 200-day average");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await sane(page, errors);
});

test("alerts: a new one from the Alerts page, for any stock", async ({ page }, info) => {
  const tag = `e2e-new ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/alerts", "Your stock alerts");
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Stock").fill("TCS");
  await page.getByLabel("Alert me when").selectOption("move_either");
  await page.getByLabel("Move in a day (%)").fill("4");
  await page.getByLabel("Note for yourself (optional)").fill(tag);
  await page.getByLabel(/Repeat/).check();
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Moves 4% or more either way in a day");
  await expect(row).toContainText("Repeats");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await sane(page, errors);
});

test("alerts: Set alert on the watchlist offers its stocks", async ({ page }, info) => {
  const tag = `e2e-watch ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/research/watchlist?region=IN", "Companies you're watching");
  await answerLevel(page);
  // a watchlist of one, without changing the shared one other tests read
  await page.route("**/research/watchlist", (r) => r.request().method() === "GET"
    ? r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ region: "IN", symbol: "RELIANCE", name: "Reliance Industries" }] }) })
    : r.fallback());
  await page.reload();
  await page.getByRole("button", { name: "Set alert" }).click();
  const dialog = page.getByRole("dialog", { name: "Set an alert" });
  await expect(dialog.getByLabel("Stock")).toHaveValue("IN:RELIANCE");
  await dialog.getByLabel("Alert me when", { exact: true }).selectOption("high52");
  await dialog.getByLabel("Note for yourself (optional)").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Set alert" }).click();
  await expect(page.getByText("Alert set on RELIANCE.")).toBeVisible();
  await sane(page, errors);
  await open(page, "/alerts", "Your stock alerts");
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Makes a new 52-week high");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
});

test("the tools grid shows one group until asked, and the menu reaches Account without scrolling", async ({ page }, info) => {
  const errors = await open(page, "/new", "What trading idea do you want to test?");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 4000 }).catch(() => undefined);   // the experience question
  await expect(page.getByRole("button", { name: "Paper trade options" })).toHaveCount(0);
  await page.getByRole("button", { name: /Show \d+ more tools/ }).click();
  await expect(page.getByRole("button", { name: "Paper trade options" })).toBeVisible();
  if (info.project.name === "desktop") await expect(page.getByRole("link", { name: /^Account/ })).toBeInViewport();
  await sane(page, errors);
});

// ---------- the sidebar menu ----------
/** On a phone the menu is a drawer: open it. */
async function menu(page: Page, phone: boolean) {
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 1500 }).catch(() => undefined);   // the experience question
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  const side = page.locator("aside.sidebar");
  await expect(side.getByRole("navigation", { name: "Main" })).toBeVisible();
  return side;
}

test("the menu: a few short groups, Scans and Watchlist each one entry with tabs, old links still open", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research", "Companies");
  await page.evaluate(() => { localStorage.removeItem("stratlab.side.shut"); localStorage.removeItem("stratlab.view.scans"); });
  let side = await menu(page, phone);
  const main = side.getByRole("navigation", { name: "Main" });
  for (const g of ["Research", "Portfolio", "Watch", "Notebooks", "Trading"]) await expect(main.getByRole("button", { name: g, exact: true })).toBeVisible();
  // eleven entries in the groups, where there were fifteen flat ones; the old separate entries are gone
  await expect(main.locator(".side-nav a")).toHaveCount(11);
  for (const gone of ["Stage 2 trend scan", "Sector rotation", "Red flags", "Watchlist at a glance", "My Holdings"]) await expect(side.getByRole("link", { name: gone })).toHaveCount(0);
  // Account and Admin sit at the bottom, with the markets folded to one line
  const bottom = side.locator(".side-bottom");
  await expect(bottom.getByRole("link", { name: /^Account/ })).toBeVisible();
  await expect(bottom.getByRole("link", { name: "Admin" })).toBeVisible();
  await expect(bottom.locator(".mkt-box > summary")).toHaveText(/^\d+ of \d+ markets open/);
  await expect(bottom.locator(".mkt-grid")).toBeHidden();
  if (phone) for (const el of await side.locator("a, button, summary").all()) {
    const b = await el.boundingBox();
    if (b && b.height) expect(b.height, `"${(await el.innerText()).slice(0, 30)}" is too small to tap`).toBeGreaterThanOrEqual(32);
  }

  // Scans: one entry, four tabs, each tab its own address
  await main.getByRole("link", { name: "Scans" }).click();
  await expect(page).toHaveURL(/\/research\/scan$/);
  const tabs = page.getByRole("navigation", { name: "Scans" });
  await expect(tabs.getByRole("link")).toHaveText(["Trend scan", "Screener", "Sector rotation", "Red flags"]);
  await tabs.getByRole("link", { name: "Sector rotation" }).click();
  await expect(page).toHaveURL(/\/research\/rotation$/);
  await expect(tabs.getByRole("link", { name: "Sector rotation" })).toHaveAttribute("aria-current", "page");
  // the entry reopens the tab you left, and the old addresses still work
  await page.goto("/research/scans");
  await expect(page).toHaveURL(/\/research\/rotation$/);
  await page.goto("/research/filings");
  await expect(page.getByText("Filings and red flags").first()).toBeVisible({ timeout: 30_000 });
  side = await menu(page, phone);
  await expect(side.getByRole("link", { name: "Scans" })).toHaveClass(/active/);
  await expect(side.getByRole("link", { name: "Companies" })).not.toHaveClass(/active/);    // one entry lit at a time

  // Watchlist: the list and "at a glance" are two tabs of one entry
  await side.getByRole("link", { name: "Watchlist" }).click();
  await expect(page).toHaveURL(/\/research\/watchlist$/);
  const views = page.getByRole("navigation", { name: "Watchlist" });
  await views.getByRole("link", { name: "At a glance" }).click();
  await expect(page).toHaveURL(/\/research\/investor$/);
  await page.goto("/watchlist");
  await expect(page).toHaveURL(/\/research\/watchlist$/);
  await page.goto("/research/scan");
  await expect(page.getByText("Stage 2").first()).toBeVisible({ timeout: 30_000 });

  // a group folds, by mouse or keyboard, and stays folded on this device; so do the markets
  side = await menu(page, phone);
  const trading = side.getByRole("button", { name: "Trading", exact: true });
  await expect(trading).toHaveAttribute("aria-expanded", "true");
  await trading.click();
  await expect(trading).toHaveAttribute("aria-expanded", "false");
  await expect(side.getByRole("link", { name: "Paper trading" })).toBeHidden();
  await side.locator(".mkt-box > summary").click();
  await expect(side.locator(".mkt-grid")).toBeVisible();
  // the open state is saved by the toggle event, which fires a moment after the click: wait for it before reloading
  await expect.poll(() => page.evaluate(() => localStorage.getItem("stratlab.markets.open"))).toBe("1");
  await page.reload();
  side = await menu(page, phone);
  await expect(side.getByRole("button", { name: "Trading", exact: true })).toHaveAttribute("aria-expanded", "false");
  await expect(side.locator(".mkt-grid")).toBeVisible();
  // the keyboard: Tab from the search button lands on the first group, with a visible focus ring, and Enter folds it
  await side.getByRole("button", { name: /Ask or do anything/ }).focus();
  await page.keyboard.press("Tab");
  const first = side.locator(".side-toggle").first();
  await expect(first).toBeFocused();
  expect(await first.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("solid");
  const was = await first.getAttribute("aria-expanded");
  await page.keyboard.press("Enter");
  await expect(first).toHaveAttribute("aria-expanded", was === "true" ? "false" : "true");
  await page.keyboard.press("Enter");
  await page.evaluate(() => { localStorage.removeItem("stratlab.side.shut"); localStorage.removeItem("stratlab.markets.open"); });
  await sane(page, errors);
});

test("the menu shows Admin only to admins", async ({ page }, info) => {
  await open(page, "/research", "Companies", sessionAs("free-token", "u-free", "free@example.com"));
  const side = await menu(page, info.project.name === "phone");
  await expect(side.getByRole("link", { name: /^Account/ })).toBeVisible();
  await expect(side.getByRole("link", { name: "Admin" })).toHaveCount(0);
});

// ---------- sharing: company fact cards and invite links ----------
/** Watch what the page shares: the phone's share sheet (stubbed, as headless browsers have none) and the clipboard. */
async function watchSharing(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __shared: unknown[]; __copied: string[] };
    w.__shared = []; w.__copied = [];
    Object.defineProperty(navigator, "share", { configurable: true, value: async (d: { url?: string; text?: string; files?: File[] }) => {
      w.__shared.push({ url: d.url, text: d.text, files: (d.files ?? []).map((f) => ({ name: f.name, type: f.type, size: f.size })) });
    } });
    Object.defineProperty(navigator, "canShare", { configurable: true, value: () => true });
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (t: string) => { w.__copied.push(t); }, write: async () => undefined } });
  });
}

type SharedCall = { url: string; files: { type: string; size: number }[] };
const shared = (page: Page) => page.evaluate(() => (window as unknown as { __shared: SharedCall[] }).__shared);
const copied = (page: Page) => page.evaluate(() => (window as unknown as { __copied: string[] }).__copied);

/** Phone: the share sheet got the card's link and image. Desktop: the link was copied. Returns the link. */
async function sharedLink(page: Page, phone: boolean): Promise<string> {
  if (phone) {
    await expect.poll(async () => (await shared(page)).length, { timeout: 30_000 }).toBeGreaterThan(0);
    const s = (await shared(page))[0];
    expect(s.files[0]?.type, "the card image goes with the link").toBe("image/png");
    expect(s.files[0].size).toBeGreaterThan(5000);
    expect(await copied(page), "a phone uses its share sheet, not the clipboard").toEqual([]);
    return s.url;
  }
  await expect.poll(async () => (await copied(page)).length, { timeout: 30_000 }).toBeGreaterThan(0);
  await expect(page.getByRole("status")).toContainText("Link copied");
  await expect(page.getByRole("status").getByRole("button", { name: "Save the image" })).toBeVisible();
  expect(await shared(page), "a computer copies the link instead of a share sheet").toEqual([]);
  return (await copied(page))[0];
}

for (const [path, ready] of [["/research/IN/RELIANCE", "Reliance"], ["/research/US/AAPL/deep", "Growth and margins"]]) {
  test(`share a company's fact card from ${path}`, async ({ page, request }, info) => {
    const phone = info.project.name === "phone";
    await watchSharing(page);
    const errors = await open(page, path, ready);
    await answerLevel(page);
    const button = page.getByRole("button", { name: "Share", exact: true });
    await expect(button).toBeVisible();
    if (phone) await touchable(page);
    await button.click();
    const link = await sharedLink(page, phone);
    const token = link.match(/\/c\/([A-Za-z0-9_-]+)$/)?.[1];
    expect(token, `a card link: ${link}`).toBeTruthy();
    // the public link previews as the card the browser drew, and opens the company's public page
    const preview = await (await request.get(`${API}/c/${token}`)).text();
    expect(preview).toContain('property="og:image"');
    expect(preview).toContain(`/c/${token}.png`);
    expect(preview).toMatch(/\/stocks\/(in\/RELIANCE|us\/AAPL)\?ref=[A-Za-z0-9_-]{12}/);
    expect(preview).toContain("Facts, not advice");
    expect(preview).not.toMatch(/kite|zerodha|yahoo|screener|finnhub/i);
    const png = await request.get(`${API}/c/${token}.png`);
    expect(png.status()).toBe(200);
    expect((await png.body()).subarray(0, 4).toString("latin1")).toBe("\x89PNG");
    await sane(page, errors);
  });
}

test("account: your invite link, how many friends joined, and sharing it", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  await watchSharing(page);
  const errors = await open(page, "/account", "Invite friends");
  await expect(page.getByTestId("friends-joined")).toHaveText(/^3 friends joined · 1 free month earned$/);
  await expect(page.getByTestId("invite-reward-line")).toHaveText(/you both get a month of Basic free \(up to 12 months for you\)/);
  await expect(page.getByLabel("Your invite link")).toHaveValue(/\/\?ref=[A-Za-z0-9_-]{12}$/);
  if (phone) await touchable(page);
  await page.getByRole("button", { name: "Share your link" }).click();
  const link = await page.getByLabel("Your invite link").inputValue();
  if (phone) await expect.poll(async () => (await shared(page)).map((s) => s.url)).toEqual([link]);
  else {
    await expect.poll(() => copied(page)).toEqual([link]);
    await expect(page.getByRole("status")).toContainText("Invite link copied");
  }
  await sane(page, errors);
});

test("an invite link is remembered through sign-in, sent once, and taken out of the address", async ({ page }) => {
  const sent: unknown[] = [];
  await page.route("**/me/referral", async (r) => { sent.push(r.request().postDataJSON()); await r.fulfill({ status: 200, contentType: "application/json", body: '{"recorded":false}' }); });
  const errors = await open(page, "/?ref=AbCdEf123_-x", "notebook");
  await expect.poll(() => sent).toEqual([{ code: "AbCdEf123_-x" }]);
  expect(new URL(page.url()).search).toBe("");
  await page.reload();
  await expect(page.getByText("notebook").first()).toBeVisible();
  await page.waitForTimeout(500);
  expect(sent, "sent only once").toHaveLength(1);
  await sane(page, errors);
});

test("admin: invite counts in the Users tab", async ({ page }, info) => {
  const errors = await open(page, "/admin?tab=users", "Paper trading now");
  await expect(page.getByRole("cell", { name: "Invited", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Free months", exact: true })).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("admin: invite rewards waiting for review are approved or rejected", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/admin?tab=users", "Invite rewards");
  const panel = page.getByTestId("invite-rewards");
  await expect(panel.getByText("Waiting for your review")).toBeVisible();
  await expect(panel.locator("tr", { hasText: "load3@example.com" })).toBeVisible();          // given
  if (phone) await touchable(page);
  // each run decides its own row: desktop rejects one, phone approves the other
  const row = panel.locator("tr", { hasText: phone ? "load2@example.com" : "load1@example.com" }).filter({ has: page.getByRole("button") });
  await row.getByRole("button", { name: phone ? "Approve" : "Reject" }).click();
  await expect(page.getByRole("status")).toContainText(phone ? "Approved" : "Rejected");
  await expect(row).toHaveCount(0);
  await sane(page, errors);
});

test("account: free Basic from invites shows on the plan", async ({ page }, info) => {
  const errors = await open(page, "/account", "Invite friends", sessionAs("load-3", "u-load-3", "load3@example.com"));
  await expect(page.getByText("Free Basic from invites")).toBeVisible();
  await expect(page.getByText("Basic (free from invites)")).toBeVisible();
  await expect(page.getByTestId("friends-joined")).toHaveText("0 friends joined · 1 free month earned");
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("screens: filter by plain facts, sort by a column, save one; no provider names", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const tag = `e2e screen ${info.project.name} ${Date.now()}`;          // both projects share the fake database
  const errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Prices as of 1 Oct 2026/)).toBeVisible();
  const table = page.locator(".screens-table");
  await expect(table.locator("tbody tr").first()).toContainText("Axisbank Ltd");          // alphabetical by default
  if (phone) await page.getByRole("button", { name: /Show filters/ }).click();
  await page.getByRole("button", { name: "Energy", exact: true }).click();
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await page.getByRole("button", { name: "What is Debt to equity?" }).click();
  await expect(page.getByRole("note")).toContainText("Borrowings divided by shareholders' equity");
  await page.getByLabel("P/E (price to earnings): at most").fill("abc");
  await expect(page.getByText("Enter a plain number, like 15 or -10.")).toBeVisible();
  await page.getByLabel("P/E (price to earnings): at most").fill("1");
  await expect(page.getByText("No company meets every condition.", { exact: false })).toBeVisible();
  await page.getByLabel("P/E (price to earnings): at most").fill("");
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await table.getByRole("button", { name: "P/E" }).click();                             // sort by a column the user picks
  await expect(table.locator("th[aria-sort=ascending]")).toContainText("P/E");
  await page.getByRole("button", { name: /Low to high/ }).click();
  await expect(table.locator("th[aria-sort=descending]")).toContainText("P/E");
  if (phone) await touchable(page);
  await page.getByLabel("Name").fill(tag);
  await page.getByLabel("Weekly email of new matches").check();
  await page.getByRole("button", { name: "Save screen" }).click();
  const saved = page.getByRole("button", { name: `${tag} · weekly` });
  await expect(saved).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible();
  await saved.click();                                                                  // a saved screen opens its conditions
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await page.getByRole("button", { name: `Delete ${tag}` }).click();
  await expect(page.getByRole("button", { name: `${tag} · weekly` })).toHaveCount(0);
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener\.in|finnhub/i);
  expect(text).not.toMatch(/\b(buy|sell|undervalued|best stocks?|score)\b/i);
  await sane(page, errors);
});

test("as-of lines: the company page, deep dive and holdings say how fresh their numbers are", async ({ page }) => {
  let errors = await open(page, "/research/IN/RELIANCE", "Reliance");
  await expect(page.getByText(/Prices as of \d+ \w+ \d{4}, \d\d:\d\d/).first()).toBeVisible();
  await sane(page, errors);
  errors = await open(page, "/research/IN/RELIANCE/deep", "Growth and margins");
  await expect(page.getByText(/Reported numbers as of \d+ \w+ \d{4}/).first()).toBeVisible();
  await sane(page, errors);
  errors = await open(page, "/holdings", "By sector");
  await expect(page.getByText(/Prices as of \d+ \w+ \d{4}/).first()).toBeVisible();
  await sane(page, errors);
});

test("deals and insider trades: a dated table on the company page and the deep dive, facts only", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  let errors = await open(page, "/research/IN/RELIANCE", "Deals and insider trades");
  const panel = page.locator("#deals");
  const table = panel.locator(".deals-table");
  await expect(table).toContainText("Mukesh Shah Family Trust", { timeout: 30_000 });
  await expect(table).toContainText("Promoter");
  await expect(table).toContainText("25,000");
  await expect(table).toContainText("₹7.3 cr");
  await expect(panel).toContainText("1 person bought 25,000 shares");
  await expect(table.getByRole("link", { name: /Disclosure/ }).first()).toHaveAttribute("href", /^https:\/\//);
  await panel.getByRole("radio", { name: "Bulk and block deals" }).click();
  await expect(table).toContainText("Index Fund One");
  await expect(table).not.toContainText("Mukesh Shah Family Trust");
  const text = await panel.innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener|finnhub|nseindia/i);
  expect(text).not.toMatch(/\b(signal|smart money|buy|sell|accumulate|avoid)\b/i);
  if (phone) await touchable(page);
  await sane(page, errors);

  errors = await open(page, "/research/IN/RELIANCE/deep", "Growth and margins");
  await expect(page.getByText("Promoter and insider buying and selling, 6 months").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".deals-table").first()).toContainText("Pension Plan Two");
  if (phone) await touchable(page);
  await sane(page, errors);
});

test("alerts: one on bulk or block deals, India only", async ({ page }, info) => {
  const tag = `e2e-deal ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/alerts", "Your stock alerts");
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Stock").fill("RELIANCE");
  await page.getByLabel("Alert me when").selectOption("deal");
  await expect(page.getByText("Checked once each evening against that day's exchange disclosures.", { exact: false })).toBeVisible();
  await page.getByLabel("Note for yourself (optional)").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("A bulk or block deal is reported");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Market").selectOption("US");
  await expect(page.getByLabel("Alert me when").locator("option", { hasText: "bulk or block deal" })).toHaveCount(0);
  await sane(page, errors);
});

test("screens: promoter or insider bought in the last N days", async ({ page }, info) => {
  const errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  if (info.project.name === "phone") await page.getByRole("button", { name: /Show filters/ }).click();
  const group = page.getByRole("radiogroup", { name: "Promoter or insider bought" });
  await group.getByRole("radio", { name: "Yes" }).click();
  await expect(page.getByText(/5 of 20 companies match/)).toBeVisible();
  await page.getByLabel("Promoter or insider bought: in the last").selectOption("365");
  await expect(page.getByText(/10 of 20 companies match/)).toBeVisible();
  await group.getByRole("radio", { name: "No" }).click();
  await expect(page.getByText(/10 of 20 companies match/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "What is Promoter or insider bought?" }).click();
  await expect(page.getByRole("note")).toContainText("insider-trading disclosures");
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener\.in|finnhub/i);
  expect(text).not.toMatch(/\b(buy|sell|signal|score)\b/i);
  await sane(page, errors);
});

test("surveillance flags: badges with what each measure is on the company page, holdings and screens; facts only", async ({ page, request }, info) => {
  // the fake exchange: RELIANCE on long-term ASM Stage II, TATASTEEL short-term ASM Stage I, ITC GSM Stage II and T2T, INFY in the F&O ban
  let errors = await open(page, "/research/IN/RELIANCE", "Sales and profit, by year");
  await answerLevel(page);
  const flags = page.locator("[data-surveillance=RELIANCE]").first();
  await expect(flags.getByText("LT-ASM 2")).toBeVisible({ timeout: 30_000 });
  await flags.getByRole("button", { name: "What RELIANCE's exchange surveillance flags mean" }).click();
  const note = page.getByRole("note");
  await expect(note).toContainText("Stage 2: 100% margin");
  await expect(note).toContainText("List as of");
  const said = await note.innerText();
  expect(said).not.toMatch(/\b(buy|sell|avoid|risky|danger|warning)\b/i);
  expect(said).not.toMatch(/nseindia|kite|zerodha|yahoo|screener|finnhub/i);
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  errors = await open(page, "/holdings", "By sector");
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.locator("[data-surveillance=RELIANCE]").getByText("LT-ASM 2")).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);

  errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  if (info.project.name === "phone") await page.getByRole("button", { name: /Show filters/ }).click();
  await page.getByRole("radiogroup", { name: "Exchange surveillance" }).getByRole("radio", { name: "On a list" }).click();
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await page.getByRole("button", { name: "ASM (long or short term)", exact: true }).click();
  await expect(page.getByText(/2 of 20 companies match/)).toBeVisible();
  const rows = page.locator(".screens-table");
  await expect(rows.getByText("ST-ASM 1")).toBeVisible();
  await page.getByRole("radiogroup", { name: "Exchange surveillance" }).getByRole("radio", { name: "On none" }).click();
  await expect(page.getByText(/18 of 20 companies match/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  const pub = await (await request.get(`${API}/stocks/in/RELIANCE`)).text();
  expect(pub).toContain("Exchange surveillance");
  expect(pub).toContain("LT-ASM 2");
});

test("alerts: one on a stock entering or leaving a surveillance list, India only", async ({ page }, info) => {
  const tag = `e2e-surv ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/alerts", "Your stock alerts");
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Stock").fill("INFY");
  await page.getByLabel("Alert me when").selectOption("surveillance");
  await expect(page.getByText("Checked twice each trading day against the exchange's surveillance lists", { exact: false })).toBeVisible();
  await page.getByLabel("Note for yourself (optional)").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Enters or leaves an exchange surveillance list");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Market").selectOption("US");
  await expect(page.getByLabel("Alert me when").locator("option", { hasText: "surveillance list" })).toHaveCount(0);
  await sane(page, errors);
});

test("corporate actions: the calendar, a company's actions, and a bonus applied (and undone) in My Holdings", async ({ page, request }, info) => {
  // each project signs in as its own user, so the two runs don't adjust the same holdings at once
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  const csv = Buffer.from("Symbol,Quantity,Average price\nTCS,12,3520\nRELIANCE,50,2400\n").toString("base64");
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: `Bearer ${token}` },
    data: { filename: "holdings.csv", data: csv, mode: "replace" } })).ok()).toBeTruthy();
  const who = sessionAs(token, id, email);

  let errors = await open(page, "/research/corporate-actions?region=IN&scope=all", "Dividends, bonuses and splits", who);
  await settle(page);
  await expect(page.getByRole("link", { name: "TCS" }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Bonus 1:1 (1 new share for every 1 held)")).toBeVisible();
  await expect(page.getByText(/Interim dividend ₹11 a share/).first()).toBeVisible();
  await expect(page.getByText("Annual General Meeting")).toHaveCount(0);           // a meeting isn't an action
  await page.getByRole("combobox", { name: "Kind of action" }).selectOption("bonus");
  await expect(page.getByText(/Dividend - Rs|₹5.50 a share/)).toHaveCount(0);
  await expect(page.getByText("Bonus 1:1 (1 new share for every 1 held)")).toBeVisible();
  await page.getByRole("radio", { name: "My stocks" }).click();
  await expect(page.getByText("Bonus 1:1 (1 new share for every 1 held)")).toBeVisible();      // TCS is in the holdings
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
  expect(await page.locator("main").innerText()).not.toMatch(/yahoo|finnhub|kite|screener/i);

  await page.goto("/research/IN/TCS");
  const panel = page.locator("#corporate-actions");
  await expect(panel.getByText(/Interim dividend ₹11 a share/)).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByText(/Final dividend ₹30 a share/)).toBeVisible();
  await expect(panel.getByText(/Dividends with an ex-date in the last 12 months/)).toBeVisible();

  errors = await open(page, "/holdings", "By sector", who);
  await settle(page);
  const notice = page.getByText(/TCS had a 1:1 bonus on .*: your quantity is now 24, average price ₹1,760/);
  await expect(notice).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Dividends" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Dividends ahead" }).getByText("TCS")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("TCS: quantity 24, average price ₹1,760.00.")).toBeVisible();
  const positions = page.getByRole("table", { name: "Positions" });
  await expect(positions.getByRole("row").filter({ hasText: "TCS" }).getByText("24", { exact: true })).toBeVisible();
  await expect(notice).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("TCS is back to 12 shares.")).toBeVisible();
  await expect(notice).toBeVisible();
  await sane(page, errors);
});

test("admin: the whole-market audit tells facts and companies not checked yet apart, and re-checks those", async ({ page }, info) => {
  const sent: object[] = [];
  const row = (symbol: string, name: string, level: string, area: string, detail: string) => ({ symbol, name, seconds: 1, issues: [{ level, area, detail }] });
  const refused = "Not checked yet: the exchange feed refused the request (403). It is checked again later.";
  const rows = [row("BSE:543210", "Tiny Co Ltd", "pending", "Documents", refused), row("BSE:543211", "Small Co Ltd", "pending", "Documents", refused),
    row("NEWCO", "New Co Ltd", "fact", "Numbers", "Only 2 years of annual results so far: listed, demerged or first reporting recently")];
  const summary = { companies: 3, clean: 1, mismatches: 0, gaps: 0, errors: 0, facts: 1, pending: 2, avg_seconds: 1, slowest: [],
    by_area: { Documents: { mismatch: 0, gap: 0, error: 0, fact: 0, pending: 2 }, Numbers: { mismatch: 0, gap: 0, error: 0, fact: 1, pending: 0 } } };
  const state = (retrying: boolean, india: boolean) => ({ enabled: true, listed: 3, checked: 3, due: retrying ? 2 : 0, current: null, eta_hours: null,
    list_at: null, list_error: null, new_listings: [], pending: india ? 2 : 0, rows: india ? rows : [], summary: india ? summary : { ...summary, companies: 0 },
    full: { running: retrying, since: retrying ? new Date().toISOString() : null, done_at: null, left: retrying ? 2 : 0, checked: null, pending_only: retrying } });
  let retrying = false;
  await page.route((u) => u.pathname === "/admin/audit/market", async (r) => {
    const req = r.request();
    const body = req.method() === "POST" ? req.postDataJSON() : null;
    if (body) { sent.push(body); retrying = true; }
    const india = body ? (body.region ?? "IN") === "IN" : new URL(req.url()).searchParams.get("region") !== "US";
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state(retrying && india, india)) });
  });
  const errors = await open(page, "/admin?tab=checks", "Whole market: India");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 3000 }).catch(() => undefined);   // asked once, if not yet
  const india = page.locator("section", { hasText: "Whole market: India" });
  await expect(india.getByText("0 gaps · 0 errors · 1 fact · 2 not checked yet")).toBeVisible();
  await india.getByRole("radio", { name: "Facts" }).click();
  await expect(india.getByText("Only 2 years of annual results so far")).toBeVisible();
  await india.getByRole("radio", { name: "Not checked yet" }).click();
  await expect(india.getByText("Tiny Co Ltd")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await india.getByRole("button", { name: "Re-check the 2 not checked yet" }).click();
  await expect.poll(() => sent).toEqual([{ region: "IN", retry: true }]);
  await expect(india.getByText("Re-checking companies not checked yet:")).toBeVisible();
  await sane(page, errors);
});

test("admin: the whole-market audit starts, pauses, resets, re-checks one company and shows BSE waiting", async ({ page }, info) => {
  const sent: Record<string, unknown>[] = [];
  const err = { symbol: "ACME", name: "Acme Ltd", seconds: 2, issues: [{ level: "error", area: "Numbers", detail: "Revenue or profit missing for Mar 2024" }] };
  const summary = (n: number) => ({ companies: n, clean: 0, mismatches: 1, gaps: 1, errors: n ? 1 : 0, facts: 0, pending: 0, avg_seconds: 2, slowest: [],
    by_area: n ? { Numbers: { mismatch: 1, gap: 1, error: 1, fact: 0, pending: 0 } } : {} });
  let s = { enabled: false, paused: "off", listed: 5058, checked: 3844, due: 0, current: null, eta_hours: null, rate_per_hour: 0, list_at: null, list_error: null,
    full: { running: true, since: new Date(Date.now() - 7 * 3600e3).toISOString(), done_at: null, left: 1214, checked: 3844, everything: true, pending_only: false },
    monthly: { on: true, last: "2026-10", next: "2026-11-01" }, retry: { waiting: 1868, due: 0, next: new Date(Date.now() + 40 * 60e3).toISOString(), gap_hours: 1, batch: 20 },
    bse: { refusing: true, waiting: 1868 }, pending: 1911, new_listings: [], rows: [err], summary: summary(1) } as Record<string, unknown>;
  await page.route((u) => u.pathname === "/admin/audit/market", async (r) => {
    const req = r.request();
    const body = req.method() === "POST" ? req.postDataJSON() : null;
    const us = body ? body.region === "US" : new URL(req.url()).searchParams.get("region") === "US";
    if (body && !us) {
      sent.push(body);
      if ("on" in body) s = { ...s, enabled: body.on, paused: body.on ? null : "off" };
      if (body.reset) s = { ...s, enabled: true, paused: null, checked: 0, due: 5058, rate_per_hour: 0, rows: [], summary: summary(0),
        full: { running: true, since: new Date().toISOString(), done_at: null, left: 5058, checked: 0, everything: true, pending_only: false } };
      if ("monthly" in body) s = { ...s, monthly: { on: body.monthly, last: "2026-10", next: body.monthly ? "2026-11-01" : null } };
    }
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(us ? { ...s, bse: undefined, rows: [], summary: summary(0), full: { ...(s.full as object), running: false } } : s) });
  });
  const errors = await open(page, "/admin?tab=checks", "Whole market: India");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 3000 }).catch(() => undefined);
  const india = page.locator("section", { hasText: "Whole market: India" });
  // paused, and why; a clear Start button
  await expect(india.getByText("Paused: switched off. Press Start to check companies.")).toBeVisible();
  await expect(india.getByText(/Full check: 3,844 of 5,058 done/)).toBeVisible();
  await expect(india.getByRole("progressbar", { name: "Full check India" })).toBeVisible();
  await expect(india.getByText("1 mismatch", { exact: true })).toBeVisible();
  await expect(india.getByText("1 gap · 1 error")).toBeVisible();
  await expect(india.getByText(/BSE is refusing requests from this server; 1,868 companies waiting/)).toBeVisible();
  await expect(india.getByText("Next full check: 1 Nov")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await india.getByRole("button", { name: "Start the India check" }).click();
  await expect(india.getByRole("button", { name: "Pause the India check" })).toBeVisible();
  await expect.poll(() => sent).toEqual([{ region: "IN", on: true }]);
  // an error row: its reason, and a re-check of that one company
  await india.getByRole("radio", { name: "Errors" }).click();
  await expect(india.getByText("Revenue or profit missing for Mar 2024")).toBeVisible();
  await india.getByRole("button", { name: "Re-check Acme Ltd" }).click();
  await expect.poll(() => sent.at(-1)).toEqual({ region: "IN", recheck: "ACME" });
  // the monthly check can be switched off
  await india.getByRole("checkbox", { name: "Full re-check on the 1st of each month" }).click();
  await expect(india.getByText("Only new listings, until you reset")).toBeVisible();
  // reset asks first: dismissed does nothing, accepted clears and starts from 0
  page.once("dialog", (d) => d.dismiss());
  await india.getByRole("button", { name: "Reset and check everything again" }).click();
  expect(sent.some((b) => b.reset)).toBe(false);
  page.once("dialog", (d) => { expect(d.message()).toContain("Clear every stored result for India"); d.accept(); });
  await india.getByRole("button", { name: "Reset and check everything again" }).click();
  await expect.poll(() => sent.at(-1)).toEqual({ region: "IN", reset: true });
  await expect(india.getByText(/Full check: 0 of 5,058 done/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});
