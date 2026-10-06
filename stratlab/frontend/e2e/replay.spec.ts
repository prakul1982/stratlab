import { expect, test, type Page } from "@playwright/test";

// Chart replay practice (Trade space): a random stock and date with both hidden, step through candles on the price
// chart, go long, flat, finish into the journal (symbol and dates revealed), and the journal's real/practice switch.
// Each project signs in as its own Basic account.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

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
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /nseindia|yahoo|finnhub|coinbase|kite connect/i]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(/\b(you should|buy|sell|accumulate|avoid)\b/i);
}

test("chart replay: a hidden random replay, practice orders, finish into the journal", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 220 : 217;                  // Basic accounts in the fake world
  const auth = { Authorization: `Bearer load-${n}` };
  expect((await request.delete(`${API}/trade/journal`, { headers: auth })).ok()).toBeTruthy();
  expect((await request.delete(`${API}/trade/replay`, { headers: auth })).ok()).toBeTruthy();
  const errors = await open(page, "/trade/replay", "New replay", sessionFor(n));
  await expect(page.getByText("No practice trades yet")).toBeVisible();
  await sane(page, errors);

  await page.getByRole("group", { name: "Candle size" }).getByRole("button", { name: "Daily" }).click();
  await page.getByRole("button", { name: "Random stock and date" }).click();
  await expect(page.getByTestId("rp-label")).toHaveText("Hidden symbol", { timeout: 30_000 });
  const chart = page.getByTestId("price-chart");
  await expect(chart).toHaveAttribute("data-bars", /\d+/);
  const before = Number(await chart.getAttribute("data-bars"));
  await expect(page.getByTestId("rp-progress")).toHaveText(/^Candle 0 of \d+$/);

  await page.getByLabel("Quantity").fill("10");
  await page.getByRole("button", { name: "Long", exact: true }).click();
  await expect(page.getByTestId("rp-position")).toHaveText(/^Long 10 at /);
  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "Next candle" }).click();
  await expect(page.getByTestId("rp-progress")).toHaveText(/^Candle 3 of /);
  await expect(chart).toHaveAttribute("data-bars", String(before + 3));
  await expect(chart).toHaveAttribute("data-markers", "1");
  // a stop picked on the chart: the button arms the chart, a click on the candles sets it below the price
  await page.getByRole("button", { name: "Stop on chart" }).click();
  await expect(chart).toHaveAttribute("data-picking", "true");
  await page.getByRole("button", { name: "Stop on chart" }).click();
  await expect(chart).toHaveAttribute("data-picking", "false");
  await page.getByRole("button", { name: "Flat" }).click();
  await expect(page.getByTestId("rp-position")).toHaveText("None");
  await expect(page.getByTestId("rp-closed")).toHaveText(/^1 \([01] won\)$/);
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: "Pause" }).click();
  await sane(page, errors);

  await page.getByRole("button", { name: "Finish and save to journal" }).click();
  await expect(page.getByRole("heading", { name: /^Replay finished: \S+/ })).toBeVisible();
  await expect(page.getByTestId("rp-reveal")).toContainText("candles played from");
  await expect(page.getByText("1 practice trade saved to your")).toBeVisible();
  await sane(page, errors);

  await page.goto("/trade/journal");
  const which = page.getByRole("radiogroup", { name: "Which trades" });
  await expect(which.getByRole("radio", { name: "Practice (1)" })).toBeVisible({ timeout: 30_000 });
  await which.getByRole("radio", { name: "Practice (1)" }).click();
  await expect(page.getByRole("heading", { name: "1 closed trade" })).toBeVisible();
  await expect(page.getByText("Chart replay", { exact: true }).first()).toBeVisible();
  await which.getByRole("radio", { name: "Real trades (0)" }).click();
  await expect(page.getByText("No real trades yet")).toBeVisible();
  await which.getByRole("radio", { name: "Both" }).click();
  expect(errors).toEqual([]);
});
