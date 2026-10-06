import { expect, test, type Page } from "@playwright/test";

// The closing auction desk (Trade space): today's auction as the fake exchange publishes it just after it ended
// (RELIANCE 0.50% above its reference price, TCS 1.20% below, INFY at it; NIFTY 50 and NIFTY BANK), the timetable,
// the stock search, and the 60-day history on Basic (8 stored days). Each project signs in as its own Basic account.
const SHOTS = process.env.CAS_SHOTS ?? "/tmp/claude-0/-home-user-stratlab/336f6e68-98b8-5cb9-ae6f-089a8eabd8fc/scratchpad/feat-closing-auction";

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, where: string, ready: string, who: ReturnType<typeof sessionFor>) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(where);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(where);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /nseindia|yahoo|finnhub|screener\.in|kite connect/i]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(/\b(you should|buy|accumulate|avoid|squeeze)\b/i);
}

test("Closing auction: stocks by gap, indices, timetable, search and the history", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 280 : 277;                   // Basic accounts in the fake world
  const errors = await open(page, "/trade/closing-auction", "F&O stocks", sessionFor(n));
  await expect(page.getByRole("heading", { name: "Closing auction", level: 1 })).toBeVisible();
  await expect(page.getByTestId("cas-phase")).not.toBeEmpty();
  await expect(page.getByRole("region", { name: "Status" })).toBeVisible();
  const coming = page.getByRole("region", { name: "Rule changes coming" });          // proposals only, with the source
  await expect(coming).toContainText("consultation paper");
  await expect(coming.getByRole("link", { name: /consultation paper/ })).toHaveAttribute("href", /^https:/);

  const stocks = page.getByRole("region", { name: /F&O stocks/ });
  const rows = stocks.locator("tr[data-cas-stock]");
  await expect(rows).toHaveCount(3);
  await expect(rows.first()).toHaveAttribute("data-cas-stock", "TCS");        // the widest gap first
  await expect(stocks.locator("tr[data-cas-stock=TCS]")).toContainText("−1.20%");
  await expect(stocks.locator("tr[data-cas-stock=RELIANCE]")).toContainText("+0.50%");
  await expect(stocks.locator("tr[data-cas-stock=RELIANCE]")).toContainText("final");
  await stocks.getByLabel("Find a stock").fill("inf");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("0.00%");
  await stocks.getByLabel("Find a stock").fill("");

  const idx = page.getByRole("region", { name: "Indices" });
  await expect(idx.locator("tr[data-cas-index='NIFTY 50']")).toBeVisible();
  await expect(page.getByRole("region", { name: "Today's timetable" })).toContainText("futures and options to");

  const hist = page.getByRole("region", { name: "Past auctions" });
  await expect(hist.locator("tr[data-cas-day]")).toHaveCount(5);
  await hist.getByText("Earlier auctions").click();
  await expect(hist.locator("tr[data-cas-day]")).toHaveCount(8);
  await sane(page, errors);
  await page.screenshot({ path: `${SHOTS}/closing-auction-${info.project.name}.png`, fullPage: true });
});
