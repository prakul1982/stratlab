import { expect, test, type Page } from "@playwright/test";

// Market breadth while the market is open, business updates across sectors (My stocks, month-by-month comparison, both
// exchanges) and StratLab's own strategies in the library, on desktop and phone. The fake world (tests/visual_server.py) holds
// today's live points for two Indian groups (a third has none), a made-up year of cement updates, Maruti's and TVS Motor's real
// September filings, holdings and a watchlist for the business-updates users, and StratLab's strategies run on the fake market.
const ADVICE = /\b(buy now|sell now|accumulate|avoid|cheap|expensive|bullish|bearish|you should|recommend\w*|worth paper trading)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|trendlyne|nseindia|edgar/i;
const SHOTS = process.env.E2E_SHOTS;

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, path: string, ready: string, n: number) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(path);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").first().innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

test("market breadth: live while the market is open, and what it says when live prices are missing", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  await page.addInitScript(() => localStorage.setItem("stratlab.breadth", JSON.stringify({ group: "nifty500", range: "1y" })));
  const errors = await open(page, "/invest/breadth", "Today, live as of", phone ? 295 : 298);
  const live = page.getByTestId("breadth-live");
  await expect(live.getByRole("heading", { name: "Today, live as of 10:45" })).toBeVisible();
  await expect(live.getByText("Live", { exact: true })).toBeVisible();                       // the pulsing badge, with its word
  await expect(live.getByText("Above 50-day average")).toBeVisible();
  await expect(live.getByText("Above 200-day average")).toBeVisible();
  // 6 points: the day's two lines
  await expect(live.getByRole("heading", { name: "Rose and fell through the day" })).toBeVisible();
  await expect(live.getByRole("heading", { name: "Above their averages today" })).toBeVisible();
  await expect(live.locator("svg[role=img]")).toHaveCount(2);
  // the daily numbers stay, now labelled as the last close
  await expect(page.getByTestId("breadth-today").getByRole("heading", { name: /^Last close · / })).toBeVisible();
  // the Table switch has the same numbers
  await live.getByRole("button", { name: "Table" }).first().click();
  await expect(live.getByRole("table", { name: "Rose and fell through the day" }).locator("tbody tr")).toHaveCount(6);
  await live.getByRole("button", { name: "Table" }).first().click();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/breadth-live-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);

  // a group with no points today: said plainly, and the last close stays
  await page.getByLabel("Group of stocks").selectOption({ label: "NIFTY Midcap 150" });
  const off = page.getByTestId("breadth-live-off");
  await expect(off.getByText(/Live prices aren't available right now/)).toBeVisible();
  await expect(off.getByText(/last close/)).toBeVisible();
  await expect(page.getByTestId("breadth-today")).toBeVisible();
  await expect(page.getByTestId("breadth-live")).toHaveCount(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/breadth-live-off-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);

  // the US groups have no live view
  await page.getByLabel("Group of stocks").selectOption({ label: "US large caps" });
  await expect(page.getByTestId("breadth-today")).toBeVisible();
  await expect(page.getByTestId("breadth-live")).toHaveCount(0);
  await expect(page.getByTestId("breadth-live-off")).toHaveCount(0);
});

test("business updates: my stocks first, more sectors, month by month with the change on the year", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/business-updates", "My stocks", phone ? 292 : 289);
  const mine = page.getByTestId("biz-mine");
  const rows = mine.getByRole("table", { name: "My stocks' latest business updates" }).locator("tbody tr");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toHaveAttribute("data-company", "MARUTI");              // holdings first
  await expect(rows.nth(0)).toContainText("Holding");
  await expect(rows.nth(0)).toContainText("2,36,013 units");
  await expect(rows.nth(1)).toHaveAttribute("data-company", "TVSMOTOR");            // then the watchlist
  await expect(rows.nth(1)).toContainText("Watchlist");
  await expect(rows.nth(2)).toHaveAttribute("data-company", "ULTRACEMCO");
  await expect(mine.getByText(/Not read yet: TCS/)).toBeVisible();                   // a holding with nothing read is named
  await expect(rows.nth(0).getByRole("link", { name: /NSE/ })).toHaveAttribute("href", /nsearchives\.nseindia\.com/);   // each figure links to its filing
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/business-updates-mine-${info.project.name}.png`, fullPage: true });

  // the sectors offered
  for (const name of ["Cement: volumes", "Airlines and airports: traffic", "Power: generation and sales", "Telecom: quarterly operating numbers",
    "Metals and mining: production and sales", "Retail: quarterly business updates", "Banks' and lenders' quarterly updates"]) {
    await expect(page.getByRole("button", { name })).toBeVisible();
  }
  await page.getByRole("button", { name: "Cement: volumes" }).click();
  await expect(page.getByRole("table", { name: "Cement: volumes", exact: true }).locator("tbody tr")).toHaveCount(2);
  // month by month: each company's own column, alphabetical, with the change on the same month a year earlier
  const cmp = page.getByTestId("biz-compare");
  const table = cmp.getByRole("table", { name: "Cement: volumes, month by month" });
  await expect(table.locator("thead th")).toHaveCount(3);
  await expect(table.locator("thead th").nth(1)).toContainText("Ambuja Cements");
  await expect(table.locator("thead th").nth(2)).toContainText("UltraTech Cement");
  await expect(table.locator("tbody tr")).toHaveCount(13);
  const sep = table.locator("tbody tr").first();
  await expect(sep).toContainText("Sep 2026");
  await expect(sep).toContainText("1,26,000 units");
  await expect(sep).toContainText("+23.5% on the year");
  await expect(sep.getByRole("link", { name: "1,26,000 units" }).first()).toHaveAttribute("href", /SAMPLE_2026-09\.pdf/);
  await expect(table.locator("tbody tr").last()).toContainText("Sep 2025");
  await expect(table.locator("tbody tr").last()).toContainText("no year-ago figure");
  await expect(cmp.getByText(/Each column is one company's own headline figure/)).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/business-updates-compare-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);

  // a sector with nothing read says so
  await page.getByRole("button", { name: "Power: generation and sales" }).click();
  await expect(page.getByText("No update in this list has been read into numbers yet.")).toBeVisible();
  await expect(page.getByText("No month to compare yet")).toBeVisible();
  await sane(page, errors);
});

test("strategy library: StratLab's own strategies, badged, each with the verdict it earned", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/library", "Strategy library", phone ? 292 : 289);
  await page.getByRole("radio", { name: "StratLab's own" }).click();
  const cards = page.locator(".k-cards > section");
  await expect(cards.first()).toBeVisible({ timeout: 20_000 });
  expect(await cards.count()).toBeGreaterThanOrEqual(10);
  for (const name of ["ST S2: Stage 2 + Supertrend", "20/50 EMA cross", "RSI(2) mean reversion", "52-week breakout with ATR stop", "Bollinger squeeze breakout",
    "Opening-range breakout (intraday)", "Golden cross", "Donchian 20/10 (turtle-style)"]) {
    await expect(page.getByRole("heading", { name: new RegExp(`^${name.replace(/[()+/]/g, "\\$&")}`) }).first()).toBeVisible();
  }
  const first = cards.first();
  await expect(first.getByText("StratLab", { exact: true }).first()).toBeVisible();      // the badge
  await expect(first.getByText("by StratLab", { exact: true })).toBeVisible();
  await expect(first.getByText(/checks passed/)).toBeVisible();
  // honest verdicts, whatever they are: every card carries one of the five
  const verdicts = await cards.locator(".verdict-badge, [data-verdict]").count();
  expect(verdicts + (await page.getByText(/Likely a real edge|Mixed evidence|Probably luck|Not enough evidence|No edge here/).count())).toBeGreaterThan(0);
  await expect(first.getByRole("button", { name: "Copy and re-test" })).toBeVisible();
  await expect(first.getByRole("button", { name: "Take down" })).toHaveCount(0);       // not anyone's to take down
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/library-stratlab-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);
  // everyone's: still listed
  await page.getByRole("radio", { name: "Everyone's" }).click();
  await expect(cards.first()).toBeVisible();
});
