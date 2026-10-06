import { expect, test, type Page } from "@playwright/test";

// F&O contract changes (Trade space): the dated list from the exchange's contract file and circulars (the fake world's,
// made up around today's month: EXIDEIND and NUVAMA leave, NIFTY's lot goes 75 → 65, RELIANCE's 500 → 250), its
// filters, the "only mine" switch, the alert setting, and the badge on a watchlist stock. Each project signs in as its
// own Basic account.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const SHOTS = process.env.FO_SHOTS ?? "/tmp/claude-0/-home-user-stratlab/336f6e68-98b8-5cb9-ae6f-089a8eabd8fc/scratchpad/feat-fo-changes";

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
  expect(text).not.toMatch(/\b(you should|buy|sell|accumulate|avoid)\b/i);
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

test("F&O contract changes: the dated list, filters, only mine, the alert and a watchlist badge", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 274 : 271;                   // Basic accounts in the fake world
  const who = sessionFor(n);
  const auth = { Authorization: `Bearer load-${n}` };
  expect((await request.put(`${API}/research/watchlist`, { headers: auth, data: { items: [{ region: "IN", symbol: "RELIANCE" }, { region: "IN", symbol: "EXIDEIND" }] } })).ok()).toBeTruthy();
  expect((await request.put(`${API}/trade/fo-changes/alerts`, { headers: auth, data: { on: false } })).ok()).toBeTruthy();

  const errors = await open(page, "/trade/fo-changes", "Every change", who);
  await expect(page.getByRole("heading", { name: "F&O changes", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Where this comes from" }).click();
  await expect(page.getByTestId("fo-asof")).toContainText(/Contract file as of .*Circulars as of/);
  const coming = page.getByRole("region", { name: "Every change" });      // one dated list: what is coming up is at its top
  await expect(coming.getByText(/EXIDEIND leaves F&O\. The .* series, expiring .*, is the last one the contract file lists\./)).toBeVisible();
  await expect(coming.getByText(/NIFTY's lot size goes from 75 to 65/)).toBeVisible();
  if (phone) await touchable(page);

  const all = page.getByRole("region", { name: "Every change" });
  await all.getByRole("group", { name: "Kind of change" }).getByRole("button", { name: "Leaving" }).click();
  await expect(all.locator(".fo-day .fo-row[data-kind=exit]").first()).toBeVisible();
  await expect(all.locator(".fo-day .fo-row:not([data-kind=exit])")).toHaveCount(0);
  // the exclusion circular is the source under each leaving line, as a link
  const src = all.locator(".fo-row[data-symbol=EXIDEIND] .fo-sources").getByRole("link", { name: /Circular FAOP\/71001: Exclusion of EXIDEIND and NUVAMA from F&O segment/ });
  await expect(src).toHaveAttribute("href", /FAOP71001\.pdf/);
  await all.getByRole("button", { name: "All", exact: true }).click();

  await all.getByLabel("Find a symbol").fill("nifty");
  await expect(all.locator(".fo-day .fo-row[data-symbol=NIFTY][data-kind=lot]")).toContainText("NIFTY's lot size goes from 75 to 65");
  await expect(all.locator(".fo-day .fo-row[data-symbol=RELIANCE]")).toHaveCount(0);
  await all.getByLabel("Find a symbol").fill("");

  await all.getByLabel("Only my watchlist and sessions").check();
  const rel = all.locator(".fo-day .fo-row[data-symbol=RELIANCE]");
  await expect(rel).toContainText("RELIANCE's lot size goes from 500 to 250");
  await expect(rel.getByText("Your watchlist or sessions")).toBeVisible();
  await expect(all.locator(".fo-day .fo-row[data-symbol=NIFTY]")).toHaveCount(0);
  await sane(page, errors);
  await page.screenshot({ path: `${SHOTS}/fo-changes-${info.project.name}.png`, fullPage: true });

  const alert = page.getByRole("region", { name: "Alert" }).getByRole("checkbox");
  await expect(alert).not.toBeChecked();
  const saved = page.waitForResponse((r) => r.url().endsWith("/trade/fo-changes/alerts") && r.request().method() === "PUT");
  await alert.click();                            // saved first, then shown checked
  expect((await saved).ok()).toBeTruthy();
  await expect(alert).toBeChecked();
  const back = await (await request.get(`${API}/trade/fo-changes`, { headers: auth })).json();
  expect(back.alerts.on).toBe(true);
  expect(back.mine).toEqual(["EXIDEIND", "RELIANCE"]);

  await page.goto("/research/watchlist");
  const badge = page.locator("[data-fo-changes=RELIANCE] .surv-badge");
  await expect(badge).toHaveText(/^Lot 500→250 from \d{1,2} [A-Z][a-z]{2}$/, { timeout: 20_000 });
  await expect(page.locator("[data-fo-changes=EXIDEIND] .surv-badge")).toHaveText(/^Leaves F&O after \d{1,2} [A-Z][a-z]{2}$/);
  await sane(page, errors);
  await page.screenshot({ path: `${SHOTS}/fo-badges-watchlist-${info.project.name}.png`, fullPage: false });
});
