import { expect, test, type Page } from "@playwright/test";

// The third fresh-eyes review's data-trust fixes, in the browser against the fake world (backend/tests/visual_server.py):
// a company page shows only its own description and news, in one unit; compare fills both companies with their units
// and says when there's no AI comparison; the market read never fails a request; a missing notebook is a page.

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string, ready: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

test("a company page is about its own company, in one unit, and says when its price is the last close (R3-001, R3-003, R3-005)", async ({ page, request }) => {
  const errors = await open(page, "/research/IN/TCS", "Sales and profit, by year");
  const main = page.locator("main");
  await expect(main.getByText("Tata Consultancy Services provides IT services").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#co-news")).toContainText("TCS shares");
  const text = await main.innerText();
  expect(text, "another company's text on TCS's page").not.toMatch(/Reliance|Jio|hydrocarbon/);
  // the sales and the profit charts read in the same unit
  const units = await page.locator(".tbars").evaluateAll((els) => els.map((el) => el.parentElement?.querySelector(".inv-plain")?.textContent ?? ""));
  expect(new Set(units.filter(Boolean)).size).toBe(1);
  // out of hours the price is labelled the last close
  const c = await (await request.get(`${API}/research/company/IN/TCS`, { headers: { Authorization: "Bearer admin-token" } })).json();
  const price = page.getByTestId("company-price");
  if (c.market_open === false) { await expect(price).toContainText("Last close"); await expect(price).toContainText("on the day"); }
  else { await expect(price).not.toContainText("Last close"); await expect(price).toContainText("today"); }
  expect(errors).toEqual([]);
});

test("compare fills both companies, with units, and says when there's no AI comparison (R3-004)", async ({ page }) => {
  const errors = await open(page, "/research/compare?region=IN&a=TCS&b=INFY", "The numbers side by side");
  const table = page.getByRole("table", { name: "Measures for both companies" });
  const debt = table.getByRole("row").filter({ hasText: /^Debt/ }).first();
  await expect(debt).toContainText(/₹[\d.,]+ (lakh )?cr.*₹[\d.,]+ (lakh )?cr/);
  const pe = table.getByRole("row").filter({ hasText: "P/E" }).first();
  expect(await pe.locator("td").last().innerText()).not.toBe("–");                    // Infosys has its numbers
  // the AI's part always has its place: the comparison, or one line saying there's none right now
  await expect(page.getByRole("heading", { name: "AI comparison" })).toBeVisible();
  const off = page.getByTestId("compare-ai-off");
  if (await off.count()) await expect(off).toContainText("No AI comparison right now");
  expect(errors).toEqual([]);
});

test("the market read never fails a request, and sends no empty focus (R3-010)", async ({ page }) => {
  const failed: string[] = [], asked: string[] = [];
  page.on("response", (r) => { if (r.url().includes("/research/pulse")) { asked.push(r.url()); if (r.status() >= 400) failed.push(`${r.status()} ${r.url()}`); } });
  const errors = await open(page, "/research/pulse", "index levels");
  await expect(page.getByText(/No AI read of the mood right now|Written /).first()).toBeVisible({ timeout: 30_000 });
  expect(failed).toEqual([]);
  expect(asked.some((u) => /focus=(&|$)/.test(u))).toBeFalsy();
  expect(errors).toEqual([]);
});

test("a notebook that isn't there is a not-found page with the way to the notebooks (R3-008)", async ({ page }) => {
  const errors = await open(page, "/n/00000000-0000-0000-0000-000000000000", "Notebook not found");
  await expect(page.getByRole("heading", { name: "Notebook not found" })).toBeVisible();
  await expect(page.getByLabel("Opening notebook")).toHaveCount(0);
  await page.getByRole("link", { name: "Go to notebooks" }).click();
  await expect(page).toHaveURL(/\/notebooks$/);
  expect(errors).toEqual([]);
});
