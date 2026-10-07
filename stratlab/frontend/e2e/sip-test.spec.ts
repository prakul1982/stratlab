import { expect, test, type Page } from "@playwright/test";

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

// Test a SIP: opened from a company page with that stock ready, a second one added, the result beside a lump sum, the
// same SIP from every start month, a dip rule with its luck check and the rule in plain words, on desktop and phone.
// Prices are the fake world's made-up ones. Each project signs in as its own fake Basic user.
const ADVICE = /\b(buy|sell|accumulate|avoid|you should|we suggest|recommend|don't stop|keep investing)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|amfi|cams|kfintech api/i;

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

async function sane(page: Page, errors: string[], text: string) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

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


test("test a SIP: from a company page, a split, the spread over start months and a dip rule", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 289 : 286;                     // Basic users of the fake database, one per project
  // the welcome question answered up front, so it can't open over the page later on a slow machine
  await request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer load-${n}` }, data: { focus: "both", level: "some", space: "all" } });
  const errors = await open(page, "/research/IN/INFY", "INFY", n);
  await page.locator("main").getByRole("button", { name: "More", exact: true }).first().click();      // under More on a company page
  await page.getByRole("menuitem", { name: "Test a SIP" }).click();
  await expect(page).toHaveURL(/\/money\/sip-test\?symbol=INFY/);
  await expect(page.getByRole("heading", { name: "Test a SIP" })).toBeVisible();
  const list = page.getByRole("list", { name: "In this SIP" });
  await expect(list.getByText("INFY", { exact: true })).toBeVisible({ timeout: 15_000 });

  // a second stock: the shares split evenly and must add up to 100
  await page.getByPlaceholder(/Search a stock, index or F&O/).fill("TCS");
  await page.locator(".results button", { hasText: "TCS" }).first().click();
  await expect(page.getByLabel("Share for TCS (%)")).toHaveValue("50");
  await page.getByLabel("Share for INFY (%)").fill("70");
  await expect(page.getByText("The shares add up to 120%; make them 100%.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run the test" })).toBeDisabled();
  await page.getByLabel("Share for TCS (%)").fill("30");
  await page.getByLabel("Years").selectOption("3");
  await page.getByLabel("Step-up a year (%)").fill("10");
  await page.getByRole("button", { name: "Run the test" }).click();

  const res = page.getByRole("region", { name: "What the SIP did" });
  await expect(res.getByRole("heading", { name: "What this SIP did" })).toBeVisible({ timeout: 60_000 });
  await expect(res.getByText(/instalments into 70% INFY, 30% TCS/)).toBeVisible();
  await expect(res.getByRole("table", { name: "Side by side" }).getByText(/All of it on/)).toBeVisible();
  await expect(res.getByRole("table", { name: "Each stock or ETF" }).getByText("TCS", { exact: true })).toBeVisible();
  await expect(res.getByRole("img", { name: "The SIP's value and the money put in, over time" })).toBeVisible();
  const spread = res.getByRole("region", { name: "Every start month" });
  await expect(spread.getByText("Lowest XIRR")).toBeVisible();
  await expect(spread.getByText(/runs of 3 years each/)).toBeVisible();
  await expect(res.getByTestId("sip-words")).toHaveText(/^On day 1 of every month \(or the next trading day\), invest ₹10,000 in 70% INFY, 30% TCS .*Raise the amount by 10% each year\.$/);
  await sane(page, errors, await page.locator("main").innerText());
  if (phone) await touchable(page);

  if (process.env.E2E_SHOTS) {
    await page.screenshot({ path: `${process.env.E2E_SHOTS}/sip-test-${info.project.name}.png`, fullPage: true });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.screenshot({ path: `${process.env.E2E_SHOTS}/sip-test-${info.project.name}-dark.png`, fullPage: true });
    await page.emulateMedia({ colorScheme: "light" });
  }
  // a dip rule: the plain SIP beside it and how often it beat it
  await page.getByLabel("Dip rule").selectOption("only_dips");
  await page.getByLabel("Fall from the recent high (%)").fill("5");
  await page.getByLabel("Recent high over").selectOption("60");
  await page.getByRole("button", { name: "Run the test" }).click();
  await expect(res.getByRole("table", { name: "Side by side" }).getByText("The same SIP, no dip rule")).toBeVisible({ timeout: 60_000 });
  await expect(res.getByText(/The dip rule's XIRR was above the plain SIP's in \d+ of \d+ start months/)).toBeVisible();
  await expect(res.getByTestId("sip-words")).toContainText("invest it only on a close at least 5% below the highest close of the last 60 trading days");
  await res.getByText("How this is worked out").click();
  await expect(res.getByText(/Only on dips: each instalment waits as cash/)).toBeVisible();
  await sane(page, errors, await page.locator("main").innerText());
  if (phone) await touchable(page);
});

test("test as a SIP: from the new-notebook flow, with the instrument and settings prefilled from the link", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 290 : 287;
  await request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer load-${n}` }, data: { focus: "both", level: "some", space: "all" } });
  const errors = await open(page, "/new", "What trading idea do you want to test?", n);
  await page.getByPlaceholder(/Search a stock, index or F&O/).first().fill("INFY");
  await page.locator(".results button", { hasText: "INFY" }).first().click();
  await page.getByRole("link", { name: "Test as a SIP instead" }).click();
  await expect(page).toHaveURL(/\/money\/sip-test\?symbol=INFY/);
  await expect(page.getByRole("list", { name: "In this SIP" }).getByText("INFY", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Amount each time (₹)")).toHaveValue("10000");        // nothing else asked for: the defaults

  // settings in the link are read; anything odd is ignored
  await page.goto("/money/sip-test?symbol=INFY&amount=5000&freq=weekly&years=3");
  await expect(page.getByRole("list", { name: "In this SIP" }).getByText("INFY", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Amount each time (₹)")).toHaveValue("5000");
  await expect(page.getByLabel("How often")).toHaveValue("weekly");
  await expect(page.getByLabel("Years")).toHaveValue("3");
  await page.goto("/money/sip-test?symbol=INFY&amount=-4&freq=hourly&years=99");
  await expect(page.getByLabel("Amount each time (₹)")).toHaveValue("10000");
  await expect(page.getByLabel("How often")).toHaveValue("monthly");
  await expect(page.getByLabel("Years")).toHaveValue("5");
  await sane(page, errors, await page.locator("main").innerText());
  if (phone) await touchable(page);
});
