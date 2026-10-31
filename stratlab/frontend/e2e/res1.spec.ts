import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// RES-1: the results calendar as a table a day, narrowed by size, sector, index, F&O and the meeting's purpose. The fake world has twenty
// companies reporting over this week and next (four today), each with earlier results days and a made-up price history, so the
// "Past results-day moves" column fills in; the options-implied move comes from made-up option prices for the F&O stocks.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
// each project signs in as its own Pro account of the fake world, set up here with RELIANCE as its one stock: the calendar puts a user's own stocks first,
// and admin's list is changed by other specs (a holding or a starred ITC left there put ITC first in "by name" when the files ran side by side)
const USERS: Record<string, number> = { desktop: 104, phone: 107 };
let session = sessionFor(104);
function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
    refresh_token: "r", user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}
test.beforeEach(async ({ request }, info) => {
  const n = USERS[info.project.name] ?? 104;
  session = sessionFor(n);
  const headers = { Authorization: `Bearer load-${n}` };
  await request.put(`${API}/me/prefs`, { headers, data: { level: "some", focus: "both" } });
  await request.put(`${API}/research/watchlist`, { headers, data: { items: [{ region: "IN", symbol: "RELIANCE" }] } });
});
const SHOTS = process.env.E2E_SHOTS;

// the day the calendar opens on, from the API: today on a trading day; on a weekend or a holiday the exchange is shut, the world's
// "today" companies report on the next session and no day is marked today (these tests failed every Saturday while they assumed one)
async function firstDay(request: APIRequestContext) {
  const n = Number(session.access_token.slice(5));
  const r = await request.get(`${API}/research/results?region=IN&scope=all`, { headers: { Authorization: `Bearer load-${n}` } });
  expect(r.ok()).toBeTruthy();
  const j = await r.json() as { today: string; weeks: { days?: { date: string }[] }[] };
  const first = j.weeks.flatMap((w) => w.days ?? []).map((d) => d.date.slice(0, 10)).filter((d) => d >= j.today).sort()[0];
  return { today: j.today, first, open: first === j.today };
}

async function open(page: Page, path: string, ready: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /finnhub|yahoo|kite connect|screener\.in/i]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(/\b(you should|buy|accumulate|avoid|sell to|trade this)\b/i);
}

async function shot(page: Page, name: string, info: { project: { name: string } }) {
  if (!SHOTS) return;
  const phone = info.project.name === "phone";
  await page.screenshot({ path: `${SHOTS}/${name}-${phone ? "390" : "1440"}.png`, fullPage: true });
}

test("results calendar: a table a day with live prices, the latest quarter, earlier results-day moves and the options' implied move", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const cal = await firstDay(request);
  const errors = await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called");
  await expect(page.getByTestId("results-count")).toHaveText("20 companies", { timeout: 30_000 });
  const today = page.getByRole("table", { name: /^Results on .*/ }).first();
  await expect(today).toBeVisible();
  const days = page.getByTestId("results-day");
  // the first day has the world's four: marked today on a trading day; on a shut day it is the next session, after today
  if (cal.open) await expect(days.first().locator(".k-eyebrow")).toContainText("today · 4 companies");
  else {
    expect(cal.first > cal.today, "a shut day's calendar opens on a later session").toBeTruthy();
    await expect(days.first().locator(".k-eyebrow")).toHaveText(/^[A-Z][a-z]{2},? \d{1,2} [A-Z][a-z]{2} · 4 companies$/);
  }
  if (!phone) {
    for (const h of ["Company", "Market value", "Price now", "Day", "Revenue YoY", "Profit YoY", "Past results-day moves", "Options imply"])
      await expect(today.getByRole("columnheader").filter({ hasText: h }).first()).toBeVisible();
  }
  await expect(today.getByRole("row")).toHaveCount(5);                      // the header and four companies
  // the figures: a market value, the latest quarter against a year before with its sign, a usual move that was read in
  const reliance = today.getByRole("row", { name: /RELIANCE/ });
  await expect(reliance).toContainText(/₹1\d\.\d\d lakh cr/);
  await expect(reliance).toContainText(/[+−]\d/);
  await expect(reliance).toContainText("F&O");
  await expect(reliance.getByText(/^±\d+\.\d%$/).first()).toBeVisible({ timeout: 30_000 });      // the usual move, once the prices were read
    await expect(reliance.getByText(/^[▲▼]\d+\.\d%$/).first()).toBeVisible();
  await expect(reliance.getByText(/^±\d+\.\d%$/)).toHaveCount(2, { timeout: 30_000 });             // ...and the move the options price in
  // the price column says when it was read, or that it is the last close
  await expect(page.getByTestId("results-prices")).toContainText(/Prices as of \d|last close/);
  await sane(page, errors);
  await shot(page, "res1-india", info);
});

test("results calendar: size, sector, index, F&O and purpose narrow the table, the count says how many, and the choice is kept", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const cal = await firstDay(request);
  const errors = await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called");
  const count = page.getByTestId("results-count");
  await expect(count).toHaveText("20 companies", { timeout: 30_000 });
  if (phone) await page.getByRole("button", { name: /^Filters/ }).click();
  const filters = page.getByRole("region", { name: "Filters" });
  await filters.getByLabel("Sector", { exact: true }).selectOption("Information Technology");
  await expect(count).toHaveText("20 companies · 4 shown");
  await expect(page.getByRole("button", { name: "Clear filters" })).toBeVisible();
  const links = page.getByTestId("results-day").locator("tbody th a");
  await expect(links.first()).toBeVisible();
  for (const sym of await links.allInnerTexts()) expect(["TCS", "INFY", "WIPRO", "HCLTECH"]).toContain(sym);
  // F&O only, on top of the sector
  await filters.getByLabel(/^F&O stocks only/).check();
  await expect(count).toHaveText("20 companies · 1 shown");               // INFY: the one of the four with futures and options
  await expect(page.getByRole("table", { name: /^Results on/ })).toHaveCount(1);
  await shot(page, "res1-filtered", info);
  // a size none of them is: nothing matches, in words, with the way out
  await filters.getByRole("button", { name: /^Micro/ }).click();
  await expect(page.getByText("No company matches these filters")).toBeVisible();
  await expect(count).toHaveText("20 companies · 0 shown");
  // kept for the next visit on this device
  await page.reload();
  await expect(page.getByTestId("results-count")).toHaveText("20 companies · 0 shown", { timeout: 30_000 });
  await page.getByRole("button", { name: "Clear filters" }).first().click();
  await expect(page.getByTestId("results-count")).toHaveText("20 companies", { timeout: 30_000 });
  // the day and the meeting's purpose
  if (phone && (await page.getByRole("button", { name: /^Filters/ }).getAttribute("aria-expanded")) !== "true") await page.getByRole("button", { name: /^Filters/ }).click();
  await filters.getByLabel("Day", { exact: true }).selectOption(cal.open ? "today" : cal.first);        // the first session's four
  await expect(count).toHaveText("20 companies · 4 shown");
  await filters.getByLabel("Meeting", { exact: true }).selectOption("more");
  await expect(page.getByTestId("results-count")).toContainText("20 companies ·");
  await filters.getByLabel("Meeting", { exact: true }).selectOption("any");
  await filters.getByLabel("Sort by").selectOption("name");
  // by name: the owner's own stock first (RELIANCE), then ICICI Bank, ITC and Oil and Natural Gas
  await expect(page.getByTestId("results-day").first().locator("tbody th a")).toHaveText(["RELIANCE", "ICICIBANK", "ITC", "ONGC"]);
  await sane(page, errors);
});

test("results calendar: the US has its own table without the options column", async ({ page }, info) => {
  const errors = await open(page, "/research/results?region=US&scope=all", "dates US companies have set");
  await expect(page.getByTestId("results-count")).toContainText("compan", { timeout: 30_000 });
  await expect(page.getByRole("columnheader", { name: /^Options imply/ })).toHaveCount(0);
  await sane(page, errors);
  await shot(page, "res1-us", info);
});

test("corporate actions: a table a day with the price now, the payment's yield and the market value, narrowed like the results", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const cal = await firstDay(request);
  const errors = await open(page, "/research/corporate-actions?region=IN&scope=all", "Dividends, bonuses and splits");
  const count = page.getByTestId("actions-count");
  await expect(count).toContainText(/\d+ actions?/, { timeout: 30_000 });
  const day = page.getByTestId("actions-day").first();
  await expect(day.locator(".k-eyebrow")).toContainText("Ex-date");
  const table = day.getByRole("table");
  if (!phone) for (const h of ["Company", "Action", "Amount or ratio", "Record date", "Price now", "Yield of this payment", "Market value"])
    await expect(table.getByRole("columnheader").filter({ hasText: h }).first()).toBeVisible();
  // today: TCS's bonus 1:1 (the world's own row) and the dividends the world adds
  await expect(page.getByRole("table", { name: /^Corporate actions going ex on/ }).first()).toBeVisible();
  // on a shut day the actions "going ex today" went ex on the last session (an ex-date is a trading day), so they are under the
  // earlier weeks, folded until opened
  if (!cal.open) await page.locator("details.earlier summary").filter({ hasText: /^Last (two|four) weeks/ }).first().click();
  const tcs = page.getByRole("row", { name: /TCS/ }).filter({ hasText: "Bonus 1:1" }).first();
  await expect(tcs).toContainText("Bonus 1:1");
  await expect(tcs).toContainText("1:1");
  const icici = page.getByRole("row", { name: /ICICIBANK/ }).filter({ hasText: "₹11" }).first();
  await expect(icici).toContainText("₹11");
  await expect(icici).toContainText(/\d\.\d\d%/);              // the payment's yield: ₹11 over the price
  await expect(icici).toContainText(/₹\d/);                    // the price now (or the last close)
  await expect(icici).toContainText("lakh cr");                // the market value
  await expect(page.getByTestId("actions-prices")).toContainText(/Prices as of \d|last close/);
  // narrowed by the kind of action, by sector, and the count says how many
  if (phone) await page.getByRole("button", { name: /^Filters/ }).click();
  const filters = page.getByRole("region", { name: "Filters" });
  await filters.getByLabel("Kind of action").selectOption("split");
  await expect(page.getByRole("row", { name: /VEDL/ }).first()).toBeVisible();
  await expect(page.getByRole("row", { name: /ICICIBANK/ })).toHaveCount(0);
  await expect(count).toContainText("shown");
  await filters.getByLabel("Kind of action").selectOption("");
  await filters.getByRole("button", { name: /^Micro/ }).click();
  await expect(page.getByText("No action matches these filters")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).first().click();
  await expect(page.getByTestId("actions-day").first()).toBeVisible();
  await sane(page, errors);
  await shot(page, "res1-corp-india", info);
});
