import { expect, test, type Page } from "@playwright/test";

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

// Floating-rate loan check, in Net worth: a repo-linked home loan's expected rate against the rate on its statement,
// the gap, what each repo change did, the draft rules panel, and the loan form's floating-rate fields, on desktop and
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


test("loan check: a repo-linked loan against repo + spread, each change's effect, and the floating-rate fields", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 277 : 298;                     // Basic users of the fake database, one per project
  const auth = { Authorization: `Bearer load-${n}` };
  await request.put(`${API}/me/prefs`, { headers: auth, data: { focus: "both", level: "some", space: "all" } });
  expect((await request.delete(`${API}/money/net-worth`, { headers: auth })).ok()).toBeTruthy();
  expect((await request.post(`${API}/money/net-worth/items`, { headers: auth, data: { kind: "loan", loan_type: "home", lender: "Example Bank", principal: 5000000, rate: 8.5,
    tenure_months: 240, start: "2024-04-01", benchmark: "repo", reset_months: 3, last_reset: "2026-07-01", current_rate: 7.65 } })).ok()).toBeTruthy();

  const errors = await open(page, "/money/net-worth", "What you own minus what you owe", n);
  const card = page.getByRole("region", { name: "Floating-rate loan check" });
  await expect(card.getByRole("heading", { name: "Is your rate following its benchmark?" })).toBeVisible({ timeout: 30_000 });
  // sanctioned at 8.5% with the repo rate at 6.5%: a spread of 2; after the 1 Oct 2026 reset, 5.25 + 2 = 7.25%
  await expect(card.getByText("7.25%").first()).toBeVisible();
  await expect(card.getByText("+0.40 pts")).toBeVisible();
  await expect(card.getByText(/Your entered rate is 0.40% above repo \+ spread after the 1 Oct 2026 reset/)).toBeVisible();
  const changes = card.getByRole("list", { name: "Rate changes on Home loan, Example Bank" });
  await expect(changes.getByText(/1 Jan 2026: 7.50% to 7.25%/)).toBeVisible();
  await expect(card.getByText(/Earlier rate changes/)).toBeVisible();
  await card.getByText("Draft: what the Reserve Bank's 2026 loan pricing rules propose").click();
  await expect(card.getByText(/Not in force: the final rules may differ/)).toBeVisible();
  if (process.env.E2E_SHOTS) {
    await card.screenshot({ path: `${process.env.E2E_SHOTS}/loan-check-${info.project.name}.png` });
    await page.emulateMedia({ colorScheme: "dark" });
    await card.screenshot({ path: `${process.env.E2E_SHOTS}/loan-check-${info.project.name}-dark.png` });
    await page.emulateMedia({ colorScheme: "light" });
  }
  await sane(page, errors, await card.innerText());
  if (phone) await touchable(page);

  // the loan form asks the floating-rate questions only for a floating loan
  await page.getByRole("button", { name: /^Edit Home loan/ }).click();
  await expect(page.getByLabel("Rate type")).toHaveValue("repo");
  await expect(page.getByLabel(/Rate on your latest statement/)).toHaveValue("7.65");
  await page.getByLabel("Rate type").selectOption("fixed");
  await expect(page.getByLabel(/Rate on your latest statement/)).toHaveCount(0);
});
