import { expect, test, type Page } from "@playwright/test";

// The theme deep dive on the fake world (tests/fake_theme.py: a made-up "India steel and mining" map; the companies are the demo world's, with
// their own stored pages). Desktop and phone, each as its own fake Basic user. Checks what is drawn: every block of figures is a table, a company
// shows only where its own description puts it, a stale claim is gone, nothing sideways, no advice wording, no data provider named.
const ADVICE = /\b(strong buy|buy (the|this|it)|sell (the|this|it)|accumulate|avoid (the|this)|undervalued|overvalued|target price|we recommend)\b/i;      // advice, not the word "sell" in "generators sell electricity"
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|trendlyne|nseindia/i;
const SHOTS = process.env.E2E_SHOTS;
const THEME_URL = "/research/themes?region=IN&q=" + encodeURIComponent("India steel and mining");

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, n: number, scheme: "light" | "dark" = "light", url = THEME_URL) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.emulateMedia({ colorScheme: scheme });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(url);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => { await welcome.getByRole("button", { name: /^All of it/ }).click(); return true; }).catch(() => false);
  if (answered) await page.goto(url);
  if (url === THEME_URL) await expect(page.getByRole("heading", { name: "The whole chain in one table" })).toBeVisible({ timeout: 90_000 });
  return errors;
}

test("the theme page is a deep dive made of tables, with each company only where it belongs", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, phone ? 280 : 277);
  const main = page.locator("main").first();
  // THEMES: every company of the theme's official industries (Iron & Steel, the mining industries) is in it, by layer, whatever the AI
  // said; the AI's additions from other industries are marked (NTPC kept in its own words, ONGC left out by its own); Vedanta, which the
  // map doesn't name, is listed under its own industry
  const members = page.locator("#theme-members");
  await expect(members.getByTestId("theme-counts")).toHaveText(/^6 companies: 5 from the official industry list, 1 added \(1 confirmed from its own description\)\.$/);
  await expect(members).toContainText("Official industries: Iron & Steel");
  // R21: Vedanta, which the map doesn't name, is placed in the map's own layer that fits it (mining), never in an exchange-industry layer
  // beside the map's
  await expect(members.getByRole("heading", { name: /official industry/ })).toHaveCount(0);
  await expect(members.getByRole("table", { name: /Coal and metal mining: companies in the theme/ })).toContainText("Vedanta");
  await expect(members.getByRole("table", { name: /Power generation: companies in the theme/ })).toContainText("Added");
  // the whole chain in one table, with the basis said
  const chain = page.getByRole("table", { name: /value chain by layer/i });
  await expect(chain.locator("thead th")).toHaveText([/^Layer$/, /^Companies$/, /^i?Revenue$/, /^i?EBITDA margin$/, /^Net margin$/, /^i?ROCE$/]);
  await expect(chain.locator("tbody tr")).toHaveCount(3);          // the map's three layers (R21: Vedanta placed in one of them)
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
  await expect(claims.getByText(/no dated headline was found/)).toHaveCount(1);         // said once under the table (LIVE3-017)
  // the theme in numbers: sections that are tables
  for (const id of ["numbers-size", "numbers-growth", "numbers-valuation", "numbers-quarter", "numbers-balance", "numbers-price", "numbers-ownership", "numbers-events", "numbers-management", "numbers-leaders"]) {
    await expect(page.locator(`#${id}`)).toBeVisible();
    expect(await page.locator(`#${id} table`).count(), `${id} has a table`).toBeGreaterThan(0);
  }
  const val = page.locator("#numbers-valuation");
  for (const m of ["P/E", "P/B", "EV/EBITDA"]) await expect(val.getByRole("rowheader", { name: m, exact: true })).toBeVisible();
  await expect(page.locator("#numbers-listings")).toBeVisible();
  const leaders = page.locator("#numbers-leaders table");
  if (phone) await page.locator("#numbers-leaders").getByLabel("Sort by").selectOption({ label: "Market value" });          // a phone's cards have no header row: the Sort by box does it
  else await leaders.getByRole("button", { name: /Market value/ }).click();
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

test("a theme whose AI read is slow shows its official companies within seconds, and the AI's map fills in after", async ({ page }, info) => {
  // LIVE3-001: live, every theme failed at 30 s with "Can't reach the StratLab server" while the AI took longer. The fake AI maps a theme
  // with "slowly" in it after 35 s (tests/fake_theme.py); each project asks its own theme, so neither finds the other's map already written
  test.setTimeout(150_000);
  const phone = info.project.name === "phone";
  const errors = await open(page, phone ? 280 : 277, "light", "/research/themes?region=IN&q=" + encodeURIComponent(`India steel and mining slowly ${info.project.name}`));
  const started = Date.now();
  const members = page.locator("#theme-members");
  await expect(members).toContainText("Tata Steel", { timeout: 10_000 });          // the exchange's own classification, no AI needed
  await expect(members).toContainText("Vedanta");
  expect(Date.now() - started, "the base list waited on the AI").toBeLessThan(15_000);
  // a moving bar with one line while the map is written (owner, 5 Nov), not a warning box
  const working = page.getByRole("status").filter({ hasText: "Mapping the theme: sorting its companies into layers" });
  await expect(working).toBeVisible();
  await expect(working.locator(".k-working-bar")).toBeVisible();
  await expect(page.getByText("The theme couldn't be mapped")).toHaveCount(0);
  // R15 (owner, 7 Nov: "it was vanishing all the data for a sec and then bringing it all back"): once the base's figures are shown, they
  // stay on the page while the map arrives and the figures are read again; watched every 50 ms in the page
  await expect(page.getByRole("heading", { name: "The whole chain in one table" })).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => {
    const w = window as unknown as { __blanked: number };
    w.__blanked = 0;
    setInterval(() => { if (!document.getElementById("theme-chain")) w.__blanked++; }, 50);
  });
  // the AI's map arrives behind the page, with no reload and no error on the way
  await expect(page.getByText("Steel makers depend on ore and coal from miners")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("The theme couldn't be mapped")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "The whole chain in one table" })).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(3000);                                             // the figures' second read is in
  expect(await page.evaluate(() => (window as unknown as { __blanked: number }).__blanked), "the figures vanished while read again").toBe(0);
  // and when the reads are done, no loading bar is left on the page (R15: "after finishing it's still loading")
  await expect(page.locator(".k-working-bar")).toHaveCount(0, { timeout: 60_000 });
  expect(errors).toEqual([]);
});
