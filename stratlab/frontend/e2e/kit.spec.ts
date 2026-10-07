import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// The design kit page (/dev/kit, admins only) and its pieces working: the segmented switch and tile picker by keyboard,
// the chip bar's "+ Custom" remembered after a reload, the chart's Table switch. With E2E_SHOTS=<folder> it also saves
// screenshots of /dev/kit and Margin funding at 1300px and 400px wide, light and dark.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const HOLDINGS = new URL("../../backend/tests/fixtures/holdings/zerodha_kite_holdings.csv", import.meta.url).pathname;
const SHOTS = process.env.E2E_SHOTS;
const admin = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const load = (n: number) => ({ access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } });

async function prepare(page: Page, session: object, theme?: "light" | "dark") {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(([s, t]) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1");
    if (t) localStorage.setItem("stratlab-theme", t as string);
  }, [session, theme ?? null] as const);
  return errors;
}
async function go(page: Page, path: string, ready: string) {
  await page.goto(path);
  const ask = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await ask.waitFor({ timeout: 3000 }).then(async () => { await ask.getByRole("button", { name: /^All of it/ }).click(); return true; }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
}
async function mine(request: APIRequestContext, n: number) {
  const auth = { Authorization: `Bearer load-${n}` };
  await request.post(`${API}/holdings/import`, { headers: auth, data: { filename: "zerodha_kite_holdings.csv", data: readFileSync(HOLDINGS).toString("base64"), mode: "replace" } });
  await request.put(`${API}/research/watchlist`, { headers: auth, data: { items: [{ region: "IN", symbol: "RELIANCE" }, { region: "IN", symbol: "TCS" }] } });
}

test("dev kit: not for ordinary users", async ({ page }) => {
  await prepare(page, load(289));
  await page.goto("/dev/kit");
  await page.waitForTimeout(2500);
  await expect(page.getByRole("heading", { name: "One look, everywhere" })).toHaveCount(0);
  // said in the page, not a silent jump home (F4-011)
  await expect(page.getByRole("heading", { level: 1, name: "You don't have access to this page" })).toBeVisible();
});

test("dev kit: every component renders and the switches work", async ({ page }) => {
  const errors = await prepare(page, admin);
  await go(page, "/dev/kit", "One look, everywhere");

  const freq = page.getByRole("radiogroup", { name: "Frequency" });
  await freq.getByRole("radio", { name: "Daily" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(freq.getByRole("radio", { name: "Weekly" })).toHaveAttribute("aria-checked", "true");

  const tiles = page.getByRole("radiogroup", { name: "Asset type" });
  await tiles.getByRole("radio", { name: /^EPF/ }).click();
  await expect(tiles.getByRole("radio", { name: /^EPF/ })).toHaveAttribute("aria-checked", "true");
  await expect(tiles.getByRole("radio", { name: /^Fixed deposit/ })).toHaveAttribute("aria-checked", "false");

  const bar = page.getByRole("group", { name: "Timeframe" });
  await bar.getByRole("button", { name: "+ Custom" }).click();
  await page.getByLabel("How many").fill("35");
  await page.getByRole("button", { name: "Use this" }).click();
  await expect(bar.getByRole("button", { name: "35 minutes" })).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByRole("group", { name: "Timeframe" }).getByRole("button", { name: "35 minutes" })).toBeVisible();

  const frame = page.locator("section.k-card", { has: page.getByRole("heading", { name: "The market's MTF book" }) }).last();
  await frame.getByRole("button", { name: "Table" }).click();
  await expect(frame.getByRole("table", { name: "The book by day" })).toBeVisible();

  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors, "uncaught errors in the page").toEqual([]);
});

async function shoot(browser: Browser, request: APIRequestContext, name: string, session: object, path: string, ready: string, w: number, h: number, theme: "light" | "dark", n?: number) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  if (n) await mine(request, n);
  await prepare(page, session, theme);
  await go(page, path, ready);
  await page.screenshot({ path: `${SHOTS}/${name}-${w}-${theme}.png`, fullPage: true });
  await ctx.close();
}

test("screenshots: the kit page and Margin funding, wide and phone, light and dark", async ({ browser, request }, info) => {
  test.skip(!SHOTS || info.project.name !== "desktop", "set E2E_SHOTS to save screenshots");
  test.setTimeout(240_000);
  for (const [w, h] of [[1300, 900], [400, 800]]) {
    for (const theme of ["light", "dark"] as const) {
      await shoot(browser, request, "dev-kit", admin, "/dev/kit", "One look, everywhere", w, h, theme);
      await shoot(browser, request, "margin-funding", load(292), "/invest/margin-funding", "The market's MTF book", w, h, theme, 292);
    }
  }
});
