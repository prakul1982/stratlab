import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// ETF price against NAV: the list (widest gap first, filters, one ETF's own view with its 30-day history) and the badge
// on an ETF in My Holdings, on desktop and phone. The fake world's ETFs and numbers are made up (tests/fake_etf.py):
// SILVERBEES trades 6.1% above its iNAV, NIFTYBEES 0.19% above. Each project signs in as its own fake Basic user.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const HOLDINGS_FILES = new URL("../../backend/tests/fixtures/holdings/", import.meta.url).pathname;
const ADVICE = /\b(buy|sell|hold|accumulate|avoid|cheap|expensive|overpriced|underpriced|overvalued|undervalued)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|amfi|nseindia/i;
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

async function sane(page: Page, errors: string[], words = true) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  if (!words) return;                    // another page's own copy (My Holdings) is checked by its own tests
  const text = await page.locator("main").innerText();
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

test("ETF vs NAV: the widest gap first, filters, and one ETF's own view", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/etf-gaps", "ETF price against NAV", phone ? 265 : 262);
  const table = page.getByRole("table", { name: "ETFs by gap to NAV" });
  const rows = table.locator("tbody tr");
  await expect(rows).toHaveCount(5);
  await expect(rows.first()).toHaveAttribute("data-etf", "SILVERBEES");
  await expect(rows.first()).toContainText("6.1% above");
  await expect(rows.last()).toHaveAttribute("data-etf", "LIQUIDBEES");
  // the scans' tabs lead here too
  await expect(page.getByRole("navigation", { name: "Scans" }).getByRole("link", { name: "ETF vs NAV" })).toBeVisible();

  await page.getByRole("button", { name: /^Gold/ }).click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toHaveAttribute("data-etf", "GOLDBEES");
  await expect(rows.first()).toContainText("0.79% below");
  await page.getByRole("button", { name: /^All/ }).click();
  await page.getByLabel("Order").selectOption("below");
  await expect(rows.first()).toHaveAttribute("data-etf", "BANKBEES");
  await page.getByLabel("Find an ETF").fill("nifty 50");
  await expect(rows).toHaveCount(1);
  await page.getByLabel("Find an ETF").fill("");

  // one ETF's own view: the gap now and each close against that day's NAV
  await table.getByRole("link", { name: "SILVERBEES" }).click();
  await expect(page).toHaveURL(/etf=SILVERBEES/);
  const panel = page.locator("#etf-gap");
  await expect(panel.getByRole("heading", { name: "Price against NAV" })).toBeVisible();
  await expect(panel.getByText("SILVERBEES trades 6.1% above its indicative NAV.")).toBeVisible();
  await expect(panel.getByRole("img", { name: /SILVERBEES's gap to NAV at each close/ })).toBeVisible();
  await expect(panel.getByText(/Over 30 trading days/)).toBeVisible();
  await expect(panel.getByRole("button", { name: "Alert on the gap" })).toBeVisible();          // a Basic user
  await panel.getByRole("button", { name: "Alert on the gap" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Alert me when")).toHaveValue("etfgap_either");
  await expect(dialog.getByText("Gap to its NAV (%)")).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toHaveCount(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/etf-gaps-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);
  if (phone) await touchable(page);
});

test("my holdings: an ETF shows its gap to NAV, and it opens the ETF's view", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 271 : 268;
  const file = "zerodha_console_holdings.xlsx";                // has NIFTYBEES, an equity ETF
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: `Bearer load-${n}` },
    data: { filename: file, data: readFileSync(HOLDINGS_FILES + file).toString("base64"), mode: "replace" } })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "By sector", n);
  const table = page.getByRole("table", { name: "Positions" });
  const row = (s: string) => table.getByRole("row").filter({ has: page.getByText(s, { exact: true }) });
  const badge = row("NIFTYBEES").locator("[data-etf-gap='NIFTYBEES']");
  await expect(badge).toHaveText("0.19% above iNAV");
  await expect(row("RELIANCE").locator("[data-etf-gap]")).toHaveCount(0);           // shares get no gap
  if (SHOTS) await row("NIFTYBEES").screenshot({ path: `${SHOTS}/holdings-etf-badge-${info.project.name}.png` });
  await sane(page, errors, false);
  if (phone) await touchable(page);
  await badge.click();
  await expect(page).toHaveURL(/\/invest\/etf-gaps\?etf=NIFTYBEES/);
  await expect(page.locator("#etf-gap").getByText("NIFTYBEES trades 0.19% above its indicative NAV.")).toBeVisible();
});
