import { expect, test, type Page } from "@playwright/test";

// India VIX: the panel on Positioning (value and change, the day's range, where it sits in the past year, NIFTY ATM IV,
// today's line and the year's closes), on desktop and phone; the Trade home only links to it. The fake
// world serves the exchange's real index list and one-day chart, trimmed (backend/tests/fixtures/vix: India VIX 15.03,
// up 0.57 from 14.46), and a made-up year of daily closes (backend/tests/fake_vix.py).
const ADVICE = /\b(buy|sell|hold|avoid|cheap|expensive|bullish|bearish|expected move|probability of profit)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|amfi|nseindia/i;
const SHOTS = process.env.E2E_SHOTS;

const sessionAs = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400,
  expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });

async function open(page: Page, path: string, ready: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); },
    sessionAs("free-token", "u-free", "free@example.com"));
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

async function sane(page: Page, errors: string[], scope = "main") {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator(scope).first().innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

test("India VIX on Positioning: today, the day's line, the past year and NIFTY ATM IV", async ({ page }, info) => {
  const errors = await open(page, "/trade/positioning", "India VIX");
  const panel = page.getByTestId("vix-panel");
  await panel.scrollIntoViewIfNeeded();
  await expect(panel.getByRole("heading", { name: "India VIX", level: 2 })).toContainText("India VIX");
  const figs = panel.getByTestId("vix-figs");
  await expect(figs).toContainText("15.03");
  await expect(panel.getByTestId("vix-change")).toHaveText("+0.57 (+3.94%) from 14.46");
  await expect(figs).toContainText("13.50 – 15.19");                       // today's low and high
  await expect(panel.getByTestId("vix-pct")).toContainText(/Higher than \d+% of the past year's closes; range \d+\.\d\d – \d+\.\d\d/);
  await expect(figs).toContainText("NIFTY ATM IV");
  // today's line from the exchange's one-day chart, and the year's closes with NIFTY ATM IV on the same chart
  await expect(panel.getByTestId("vix-intraday").locator("svg.ch-svg")).toBeVisible();
  const year = panel.getByTestId("vix-year");
  await expect(year.locator("svg.ch-svg")).toBeVisible();
  await expect(year.getByRole("button", { name: "Series: India VIX", exact: true })).toBeVisible();
  await expect(panel.getByTestId("vix-source")).toContainText(/trading days stored/);
  await expect(panel.getByTestId("vix-source")).toContainText("Facts, not advice.");
  // the panel's own width on a phone
  const box = (await panel.boundingBox())!;
  expect(box.width).toBeLessThanOrEqual((page.viewportSize()?.width ?? 1440) + 1);
  await sane(page, errors);
  if (SHOTS) await panel.screenshot({ path: `${SHOTS}/vix-panel-${info.project.name}.png` });
});

test("the Trade home has no positioning card, only a link to the Positioning page", async ({ page }, info) => {
  const errors = await open(page, "/trade", "Test an idea, then trade it on paper");
  await expect(page.getByTestId("positioning-card"), "the numbers show on the Positioning page only").toHaveCount(0);
  const link = page.getByTestId("positioning-link").getByRole("link", { name: "Positioning" });
  await link.scrollIntoViewIfNeeded();
  if (SHOTS) {
    await page.emulateMedia({ colorScheme: info.project.name === "phone" ? "light" : "dark" });
    await page.screenshot({ path: `${SHOTS}/trade-home-${info.project.name === "phone" ? "400-light" : "1300-dark"}.png`, fullPage: true });
  }
  await link.click();
  await expect(page).toHaveURL(/\/trade\/positioning$/);
  await expect(page.getByRole("heading", { name: "Positioning", level: 1 })).toBeVisible();
  await expect(page.getByTestId("vix-figs")).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);
});
