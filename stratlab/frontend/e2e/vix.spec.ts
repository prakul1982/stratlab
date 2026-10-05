import { expect, test, type Page } from "@playwright/test";

// India VIX: the panel on Positioning (value and change, the day's range, where it sits in the past year, NIFTY ATM IV,
// today's line and the year's closes) and its tile on the Trade home's positioning card, on desktop and phone. The fake
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
  await expect(panel.locator("#vix-h")).toContainText("India VIX");
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

test("India VIX on the Trade home's positioning card", async ({ page }, info) => {
  const errors = await open(page, "/trade", "Test an idea, then trade it on paper");
  const card = page.getByTestId("positioning-card");
  await card.scrollIntoViewIfNeeded();
  await expect(card.getByTestId("pos-card-vix")).toHaveText("15.03");
  await expect(card).toContainText("+0.57 (+3.94%)");
  await sane(page, errors, "[data-testid=positioning-card]");
  // the theme flips without anything going unreadable: the tile keeps its text colour token
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(card.getByTestId("pos-card-vix")).toBeVisible();
  if (SHOTS) await card.screenshot({ path: `${SHOTS}/vix-card-${info.project.name}.png` });
});
