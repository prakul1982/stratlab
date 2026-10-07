import { expect, test, type Page } from "@playwright/test";

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

// Money → Rates: the Reserve Bank's rates (a trimmed real copy of its Current Rates panel), small savings, the floating
// rate bond and a deposit from Net worth, after tax at the user's own estimate and at a picked slab, on desktop and
// phone. Each project signs in as its own fake Basic user.
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
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
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
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true]")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || (el as HTMLInputElement).placeholder || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}


test("rates: the Reserve Bank's rates, small savings and a deposit after tax, at a slab and at your own estimate", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 295 : 292;                     // Basic users of the fake database, one per project
  const auth = { Authorization: `Bearer load-${n}` };
  await request.put(`${API}/me/prefs`, { headers: auth, data: { focus: "both", level: "some", space: "all" } });
  expect((await request.delete(`${API}/money/net-worth`, { headers: auth })).ok()).toBeTruthy();
  expect((await request.post(`${API}/money/net-worth/items`, { headers: auth, data: { kind: "fd", name: "Bank FD", principal: 100000, rate: 7, compounding: "quarterly",
    start: "2026-01-01", maturity: "2027-01-01" } })).ok()).toBeTruthy();
  const now = new Date();
  const fy = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  expect((await request.put(`${API}/tax/inputs`, { headers: auth, data: { fy, regime: "new", other: 2000000, salary: 2000000 } })).ok()).toBeTruthy();

  const errors = await open(page, "/money/rates", "Rates and your yield after tax", n);
  // your own estimate: ₹20 lakh of salary is in the 20% slab, 20.8% with cess
  await expect(page.getByText(/After-tax figures use 20.8%: the tax on the next ₹10,000 of interest/)).toBeVisible({ timeout: 30_000 });
  const market = page.getByRole("table", { name: "Market rates" });
  await expect(market.getByText("91-day Treasury bill")).toBeVisible();
  await expect(market.getByText("5.52%")).toBeVisible();
  await expect(market.getByText("Policy repo rate")).toBeVisible();
  const small = page.getByRole("table", { name: "Small savings rates" });
  const ppf = small.getByRole("row").filter({ hasText: "Public Provident Fund" });
  await expect(ppf).toContainText("7.10%");
  await expect(ppf).toContainText("Tax-free");
  await expect(small.getByRole("row").filter({ hasText: "National Savings Certificate" })).toContainText("6.10%");     // 7.7 × 0.792
  await expect(page.getByRole("table", { name: "Floating rate bond" })).toContainText("8.05%");
  await expect(page.getByRole("table", { name: "Your deposits" }).getByText("Bank FD")).toBeVisible();

  // a slab picked instead
  await page.getByRole("group", { name: "Tax rate" }).getByRole("button", { name: "30%" }).click();
  await expect(page.getByText(/After-tax figures use 31.2%: the 30% slab with 4% cess/)).toBeVisible();
  await expect(small.getByRole("row").filter({ hasText: "National Savings Certificate" })).toContainText("5.30%");
  if (process.env.E2E_SHOTS) {
    await page.screenshot({ path: `${process.env.E2E_SHOTS}/rates-${info.project.name}.png`, fullPage: true });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.screenshot({ path: `${process.env.E2E_SHOTS}/rates-${info.project.name}-dark.png`, fullPage: true });
    await page.emulateMedia({ colorScheme: "light" });
  }
  await sane(page, errors, await page.locator("main").innerText());
  if (phone) await touchable(page);
});
