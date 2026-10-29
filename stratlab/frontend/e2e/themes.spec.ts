import { expect, test, type Page } from "@playwright/test";

// The theme deep dive on the fake world (tests/fake_theme.py: a made-up "India steel and mining" map; the companies are the demo world's, with
// their own stored pages). Desktop and phone, each as its own fake Basic user. Checks what is drawn: every block of figures is a table, a company
// shows only where its own description puts it, a stale claim is gone, nothing sideways, no advice wording, no data provider named.
const ADVICE = /\b(buy|sell|accumulate|avoid|cheap|expensive|undervalued|overvalued|target price)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|trendlyne|nseindia/i;
const SHOTS = process.env.E2E_SHOTS;
const THEME_URL = "/research/themes?region=IN&q=" + encodeURIComponent("India steel and mining");

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, n: number, scheme: "light" | "dark" = "light") {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.emulateMedia({ colorScheme: scheme });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(THEME_URL);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => { await welcome.getByRole("button", { name: /^All of it/ }).click(); return true; }).catch(() => false);
  if (answered) await page.goto(THEME_URL);
  await expect(page.getByRole("heading", { name: "The whole chain in one table" })).toBeVisible({ timeout: 90_000 });
  return errors;
}

test("the theme page is a deep dive made of tables, with each company only where it belongs", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, phone ? 280 : 277);
  const main = page.locator("main").first();
  // the whole chain in one table, with the basis said
  const chain = page.getByRole("table", { name: /value chain by layer/i });
  await expect(chain.locator("thead th")).toHaveText(["Layer", "Companies", "Revenue", "EBITDA margin", "Net margin", "ROCE"]);
  await expect(chain.locator("tbody tr")).toHaveCount(3);
  await expect(main).toContainText("Consolidated accounts where the company files them");
  // a layer: its companies in their own words, the median and the range as rows; the wrong placement (ONGC under steel) isn't there
  const steel = page.locator("#layer-1");
  await expect(steel).toContainText("Steel making");
  await expect(steel.getByRole("table").first().locator("tbody tr")).toHaveCount(5);        // Tata Steel, JSW Steel, SAIL, Median, Range
  await expect(steel).toContainText("In its own words");
  await expect(steel.locator('tr[data-kind="median"]')).toContainText("Median");
  await expect(steel.locator('tr[data-kind="range"]')).toContainText("Range");
  await expect(main).not.toContainText("Oil and Natural Gas");
  // a sub-theme with no listed company says so
  await expect(page.locator("#theme-subs")).toContainText("No listed company is shown for this sub-theme");
  // claims: the one an old scheme rests on is gone, the rest is marked general background
  const claims = page.locator("#theme-claims");
  await expect(claims).toContainText("General background");
  await expect(claims).not.toContainText("old steel scheme");
  // the theme in numbers: sections that are tables
  for (const id of ["numbers-size", "numbers-growth", "numbers-valuation", "numbers-quarter", "numbers-balance", "numbers-price", "numbers-ownership", "numbers-events", "numbers-management", "numbers-leaders"]) {
    await expect(page.locator(`#${id}`)).toBeVisible();
    expect(await page.locator(`#${id} table`).count(), `${id} has a table`).toBeGreaterThan(0);
  }
  const val = page.locator("#numbers-valuation");
  for (const m of ["P/E", "P/B", "EV/EBITDA"]) await expect(val.getByRole("rowheader", { name: m, exact: true })).toBeVisible();
  await expect(page.locator("#numbers-listings")).toBeVisible();
  const leaders = page.locator("#numbers-leaders table");
  await leaders.getByRole("button", { name: /Market value/ }).click();
  await expect(leaders.locator("th[aria-sort]").filter({ hasText: "Market value" })).toHaveAttribute("aria-sort", /ascending|descending/);
  // no stat tiles: figures are in tables
  expect(await page.locator(".k-stat").count()).toBe(0);
  // sane
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await main.innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/themes-${info.project.name}.png`, fullPage: true });
});

test("the theme page in the dark theme", async ({ page }, info) => {
  const errors = await open(page, info.project.name === "phone" ? 280 : 277, "dark");
  expect(errors).toEqual([]);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/themes-dark-${info.project.name}.png`, fullPage: true });
});
