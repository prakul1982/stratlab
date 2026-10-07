import { expect, test, type Page } from "@playwright/test";

// The trend scan's preset rule sets, red-flag filings across every company, US holders above 5%, and the US corporate-actions
// list, on desktop and phone. The fake world (tests/visual_server.py) holds what the evening jobs would have stored: the
// scans' matches for NIFTY 500 and the S&P 500 (worked out from made-up wavy prices), a made-up exchange list of flagged
// filings for every day of the last 45, made-up 8-K items and 13D/13G filings for the S&P 500, and dividends and splits
// read from made-up price histories. The prices move with the date, so what a scan finds changes from day to day: these
// tests check what is drawn, not which stocks happen to match today.
const ADVICE = /\b(buy|sell|accumulate|avoid|cheap|expensive|bullish|bearish|should|recommend)\b/i;
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
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
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
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
}

const user = (info: { project: { name: string } }) => (info.project.name === "phone" ? 286 : 283);
const shot = async (page: Page, name: string, info: { project: { name: string } }) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}-${info.project.name}.png`, fullPage: true }); };

test("trend scan: pick a preset rule set, scan NIFTY 500 and the S&P 500, each match a dated fact", async ({ page }, info) => {
  const errors = await open(page, "/research/scan?region=IN", "Trend scan", user(info));
  const chips = page.getByRole("group", { name: "Scan rule sets", exact: true });
  for (const name of ["Stage 2 + Supertrend", "52-week high breakout", "Golden cross (50/200)", "RSI oversold bounce", "Volume surge", "Bollinger squeeze breakout", "Near 52-week low", "Pullback in an uptrend"]) {
    await expect(chips.getByRole("button", { name, exact: true })).toBeVisible();
  }
  await chips.getByRole("button", { name: "52-week high breakout", exact: true }).click();
  await expect(page).toHaveURL(/scan=high52/);
  await expect(page.getByTestId("scan-rule")).toContainText("highest high of the previous 252 trading days");
  await expect(page.getByTestId("scan-rule")).toContainText("Counts as a match when it held on any of the last 3 candles");
  const group = page.getByLabel("Group to scan");
  await group.selectOption("nifty500");
  const checked = Number(((await group.locator("option:checked").innerText()).match(/\((\d+)\)/) ?? [])[1]);
  expect(checked, "the group says how many stocks the daily read checked").toBeGreaterThan(5);
  let found = 0;
  let shotTaken = false;
  for (const name of ["52-week high breakout", "Golden cross (50/200)", "RSI oversold bounce", "Near 52-week low", "Pullback in an uptrend", "Stage 2 + Supertrend"]) {
    await chips.getByRole("button", { name, exact: true }).click();
    await page.getByRole("button", { name: "Scan", exact: true }).click();
    if (name === "Stage 2 + Supertrend") {                       // the same stored answer, in the preset table
      await expect(page.getByRole("heading", { name: /Stage 2 \+ Supertrend: NIFTY 500/ })).toBeVisible();
    } else {
      await expect(page.getByRole("heading", { name: new RegExp(`${name.replace(/[()/]/g, ".")}: NIFTY 500`) })).toBeVisible();
    }
    await expect(page.getByText("Stocks checked").first().locator("xpath=..")).toContainText(String(checked));
    const table = page.getByRole("table", { name: new RegExp(`NIFTY 500: ${name.slice(0, 6)}`) });
    const rows = await table.locator("tbody tr").count();
    const none = await table.getByText("No stock matches this rule right now.").count();
    found += none ? 0 : rows;
    if (!none && rows && !shotTaken) { shotTaken = true; await shot(page, "scan-india", info); }
  }
  expect(found, "some rule matches some stock").toBeGreaterThan(0);
  await sane(page, errors);

  // the S&P 500, from the committed list, on the same page
  await page.getByRole("radio", { name: "$ United States" }).click();
  await expect(page.getByLabel("Group to scan")).toContainText("S&P 500");
  await page.getByLabel("Group to scan").selectOption("sp500");
  await chips.getByRole("button", { name: "Volume surge", exact: true }).click();
  await expect(page.getByTestId("scan-rule")).toContainText("2 times");
  await chips.getByRole("button", { name: "Pullback in an uptrend", exact: true }).click();
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Pullback in an uptrend: S&P 500/ })).toBeVisible();
  const us = page.getByRole("table", { name: /S&P 500: Pullback/ });
  await expect(us).toBeVisible();
  if (await us.locator("tbody tr").count() > 0 && !(await us.getByText("No stock matches").count())) {
    await expect(us.locator("tbody tr").first()).toContainText(/\$/);                      // dollars, with the date it matched on
    await expect(us.locator("tbody tr").first()).toContainText(/\d{4}/);
  }
  await shot(page, "scan-us", info);
  await sane(page, errors);
});

test("trend scan: the Stage 2 + Supertrend scan of a small group keeps its columns and its alert", async ({ page }, info) => {
  const errors = await open(page, "/research/scan?region=US&set=us_mega", "Trend scan", user(info));
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect(page.getByRole("table", { name: /stage and Supertrend/ })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Supertrend" })).toBeVisible();
  await expect(page.getByText("Alert me after each close")).toBeVisible();
  await page.getByRole("group", { name: "Scan rule sets", exact: true }).getByRole("button", { name: "Golden cross (50/200)", exact: true }).click();
  await expect(page.getByText("Alert me after each close")).toHaveCount(0);                  // the alert belongs to ST S2 only
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Golden cross \(50\/200\): 20 US large caps/ })).toBeVisible();
  await expect(page.getByText("Stocks checked").first()).toBeVisible();
  await sane(page, errors);
});

test("red flags across every company: newest first, paged, filtered by type and dates, India and the US", async ({ page }, info) => {
  const errors = await open(page, "/research/filings?view=all&region=IN", "Red flags across companies", user(info));
  const table = page.getByRole("table", { name: "Red-flag filings, newest first" });
  await expect(table.locator("tbody tr")).toHaveCount(25);
  const dates = await table.locator("tbody tr td:first-child").allInnerTexts();
  const ms = dates.map((d) => new Date(d).getTime());
  expect(ms, "newest first").toEqual([...ms].sort((a, b) => b - a));
  await expect(page.getByText(/Page 1 of \d+ · \d+ filings/)).toBeVisible();
  await page.getByRole("button", { name: "Next →" }).click();
  await expect(page.getByText(/Page 2 of/)).toBeVisible();
  await expect(page).toHaveURL(/page=2/);
  await page.getByRole("button", { name: "← Previous" }).click();
  await expect(page.getByText(/Page 1 of/)).toBeVisible();
  await shot(page, "redflags-india", info);

  // a type: every row is that flag, and the count in the chip matches the heading
  const types = page.getByRole("group", { name: "Flag types", exact: true });
  const chip = types.getByRole("button", { name: /^Auditor resigned · \d+$/ });
  const n = Number((await chip.innerText()).match(/· (\d+)/)![1]);
  await chip.click();
  await expect(page).toHaveURL(/flag=auditor_resign/);
  await expect(page.getByRole("heading", { name: new RegExp(`^${n} filings? across companies`) })).toBeVisible();
  for (const label of await table.locator("tbody tr td:nth-child(3)").allInnerTexts()) expect(label).toContain("Auditor resigned");
  // dates: the last 7 days holds fewer than the 90 days did
  await types.getByRole("button", { name: "All types" }).click();
  const count = async () => Number((await page.getByRole("heading", { name: /filings? across companies/ }).innerText()).replace(/\D.*/, "").replace(/,/g, ""));
  let all = 0;
  await expect(async () => { all = await count(); expect(all).toBeGreaterThan(n); }).toPass({ timeout: 10_000 });
  await page.getByRole("group", { name: "Date range", exact: true }).getByRole("button", { name: "Last 7 days" }).click();
  await expect(page).toHaveURL(/range=7/);
  await expect(async () => { expect(await count()).toBeLessThan(all); }).toPass({ timeout: 10_000 });
  // picking dates, and finding a company
  await page.getByRole("group", { name: "Date range", exact: true }).getByRole("button", { name: "Pick dates" }).click();
  await expect(page.getByLabel("From")).toBeVisible();
  await page.getByLabel("Find a company").fill("tcs");
  await expect(async () => { for (const c of await table.locator("tbody tr th").allInnerTexts()) expect(c).toContain("TCS"); }).toPass({ timeout: 10_000 });
  await sane(page, errors);

  // the US: 8-K items, from the SEC
  await page.getByRole("radio", { name: "$ United States" }).click();
  await expect(page.getByText("Form 8-K", { exact: false }).first()).toBeVisible();
  await expect(table.locator("tbody tr").first()).toContainText(/Item \d\.\d\d/);
  await expect(types.getByRole("button", { name: /^Change of auditor · \d+$/ })).toBeVisible();
  const usChip = types.getByRole("button", { name: /^Change of auditor · \d+$/ });
  const usN = Number((await usChip.innerText()).match(/· (\d+)/)![1]);
  await usChip.click();
  await expect(page.getByRole("heading", { name: new RegExp(`^${usN} filings? across companies`) })).toBeVisible();
  for (const label of await table.locator("tbody tr td:nth-child(3)").allInnerTexts()) expect(label).toContain("Change of auditor");
  await expect(page.getByText(/read through|S&P 500/).first()).toBeVisible();
  await shot(page, "redflags-us", info);
  await sane(page, errors);
});

test("red flags: your watchlist in the US reads the same stored list", async ({ page }, info) => {
  const errors = await open(page, "/research/filings?region=US", "Filings and red flags", user(info));
  await expect(page.getByText(/watchlist is empty|filings? on your watchlist/).first()).toBeVisible();
  await expect(page.getByRole("radio", { name: "Your watchlist" })).toBeChecked();
  await sane(page, errors);
});

test("US holders above 5%: the latest 13D and 13G filings, by company and by kind", async ({ page }, info) => {
  const errors = await open(page, "/invest/holders?region=US", "Holders above 5%", user(info));
  const table = page.getByRole("table", { name: "13D and 13G filings, newest first" });
  await expect(table.locator("tbody tr").first()).toBeVisible();
  await expect(table.locator("tbody tr").first()).toContainText(/Schedule 13[DG]/);
  await expect(table.locator("tbody tr").first()).toContainText(/\d+\.\d\d%/);
  await expect(page.getByRole("columnheader", { name: "Share of the class" })).toBeVisible();
  const heading = page.getByRole("heading", { name: /\d+ filings? across companies/ });
  const total = Number((await heading.innerText()).replace(/\D.*/, "").replace(/,/g, ""));
  await shot(page, "holders-us", info);
  await page.getByRole("radio", { name: "13D · active" }).click();
  await expect(page).toHaveURL(/form=13D/);
  await expect(async () => {
    const t = Number((await heading.innerText()).replace(/\D.*/, "").replace(/,/g, ""));
    expect(t).toBeGreaterThan(0);
    expect(t).toBeLessThan(total);
    for (const f of await table.locator("tbody tr td:nth-child(5)").allInnerTexts()) expect(f).toContain("Schedule 13D");
  }).toPass({ timeout: 10_000 });
  await page.getByRole("radio", { name: "All", exact: true }).click();
  // one company
  const first = (await table.locator("tbody tr th").first().innerText()).split("\n")[0].trim();
  await page.goto(`/invest/holders?region=US&symbol=${encodeURIComponent(first)}`);
  await expect(page.getByRole("heading", { name: new RegExp(`for ${first}$`) })).toBeVisible();
  for (const c of await table.locator("tbody tr th").allInnerTexts()) expect(c).toContain(first);
  await sane(page, errors);
  // India is still the shareholding-pattern search
  await page.getByRole("radio", { name: "₹ India" }).click();
  await expect(page.getByText("Named holders across companies")).toBeVisible();
});

test("US corporate actions: every company's dividends and splits for the last four weeks, with the source's limit in the (i)", async ({ page }, info) => {
  const errors = await open(page, "/research/corporate-actions?region=US&scope=all", "Dividends, bonuses and splits", user(info));
  const fold = page.locator("details.earlier", { hasText: "Last four weeks" });
  await expect(fold).toBeVisible();
  if (!(await fold.evaluate((el) => (el as HTMLDetailsElement).open))) await fold.locator("summary").click();       // it opens by itself when nothing is ahead
  await expect(fold).toContainText("MSFT");
  await expect(fold).toContainText(/Dividend \$\d/);
  await expect(fold).toContainText(/Split 10-for-1/);
  await page.getByRole("button", { name: "About the US list" }).click();
  await expect(page.getByText(/price history/).first()).toBeVisible();
  await expect(page.getByText(/companies read/).first()).toBeVisible();
  await shot(page, "corp-actions-us", info);
  await sane(page, errors);
});
