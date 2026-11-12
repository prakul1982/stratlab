import { expect, test, type Page } from "@playwright/test";

// The customer and supplier map (lane b2) on desktop and phone. The fake world (tests/visual_server.py supply_links_world) holds
// RELIANCE's five links (two linked, one waiting in Admin's queue, two unlisted buyers kept as filed), TCS's filing naming
// RELIANCE, and Apple's supplier. Free sees the latest 3 and a lock; Basic all; Pro the CSV. Admin settles the queued name.
const ADVICE = /\b(buy|sell|accumulate|avoid|cheap|expensive|target price|undervalued)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|trendlyne|nseindia/i;
const SHOTS = process.env.E2E_SHOTS;

function sessionFor(token: string, id: string, email: string) {
  return { access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}
const load = (n: number) => sessionFor(`load-${n}`, `u-load-${n}`, `load${n}@example.com`);

async function open(page: Page, path: string, ready: string, session: object) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

async function sane(page: Page, errors: string[], scope: string) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator(scope).first().innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

test("company card: Free sees the latest three links and a Basic lock", async ({ page }, info) => {
  const errors = await open(page, "/research/IN/RELIANCE", "Reliance", load(info.project.name === "phone" ? 243 : 240));
  const card = page.locator("#customers-suppliers");
  await card.scrollIntoViewIfNeeded();
  await expect(card.getByRole("heading", { name: "Customers and suppliers" })).toBeVisible({ timeout: 20_000 });
  await expect(card.getByRole("heading", { name: "Names as customers" })).toBeVisible();
  await expect(card.locator("li[data-link]")).toHaveCount(3);
  await expect(card.getByRole("link", { name: "Tata Steel Limited" })).toHaveAttribute("href", "/research/IN/TATASTEEL");
  await expect(card.getByText("as filed, not linked").first()).toBeVisible();          // Indian Railways: an unlisted buyer
  await expect(card.getByText(/3 more links are on the Basic plan/)).toBeVisible();
  await expect(card.getByRole("button", { name: "CSV" })).toHaveCount(0);
  await sane(page, errors, "#customers-suppliers");
  if (SHOTS) await card.screenshot({ path: `${SHOTS}/card-free-${info.project.name}.png` });
});

test("company card: Basic sees every link with its quote and filing, both sides", async ({ page }, info) => {
  const errors = await open(page, "/research/IN/RELIANCE", "Reliance", load(info.project.name === "phone" ? 244 : 241));
  const card = page.locator("#customers-suppliers");
  await card.scrollIntoViewIfNeeded();
  await expect(card.locator("li[data-link]")).toHaveCount(6, { timeout: 20_000 });
  await expect(card.getByRole("heading", { name: "Named as a supplier by" })).toHaveCount(0);
  await expect(card.getByRole("heading", { name: "Named as a customer by" })).toBeVisible();     // TCS's order from RELIANCE
  const tcs = card.locator('li[data-link="Tata Consultancy Services Limited"]');
  await expect(tcs.getByRole("link", { name: "Tata Consultancy Services Limited" })).toHaveAttribute("href", "/research/IN/TCS");
  const steel = card.locator('li[data-link="Tata Steel Limited"]');
  await expect(steel.getByText("Order win · Rs 820 crore · said on 4 Nov 2026")).toBeVisible();
  await expect(steel.locator("blockquote")).toContainText("received an order worth Rs 820 crore from Tata Steel Limited");
  await expect(steel.getByRole("link", { name: /Receipt of order/ })).toHaveAttribute("href", /nsearchives\.nseindia\.com/);
  await expect(card.getByText(/more links? (is|are) on the Basic plan/)).toHaveCount(0);
  await expect(card.getByText(/as a CSV, and the links among a theme's companies, are on the Pro plan/)).toBeVisible();
  await sane(page, errors, "#customers-suppliers");
  if (SHOTS) await card.screenshot({ path: `${SHOTS}/card-basic-${info.project.name}.png` });
});

test("company card: Pro downloads the links as a CSV; a US company's supplier", async ({ page }, info) => {
  const errors = await open(page, "/research/IN/RELIANCE", "Reliance", load(info.project.name === "phone" ? 245 : 242));
  const card = page.locator("#customers-suppliers");
  await card.scrollIntoViewIfNeeded();
  const [file] = await Promise.all([page.waitForEvent("download"), card.getByRole("button", { name: "CSV" }).click()]);
  expect(file.suggestedFilename()).toBe("reliance-customers-suppliers.csv");
  await sane(page, errors, "#customers-suppliers");
  await page.goto("/research/US/AAPL");
  const us = page.locator("#customers-suppliers");
  await us.scrollIntoViewIfNeeded();
  await expect(us.getByRole("heading", { name: "Names as suppliers" })).toBeVisible({ timeout: 30_000 });
  await expect(us.getByRole("link", { name: "Taiwan Semiconductor Manufacturing Company Limited" })).toHaveAttribute("href", "/research/US/TSM");
  if (SHOTS) await us.screenshot({ path: `${SHOTS}/card-us-pro-${info.project.name}.png` });
});

test("Admin settles a name that fits more than one company", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "one run is enough: it changes the shared world");
  const errors = await open(page, "/admin/data", "Data", sessionFor("admin-token", "u-admin", "owner@example.com"));
  const panel = page.getByRole("region", { name: "Customer and supplier names" }).or(page.locator("section", { hasText: "Customer and supplier names" })).first();
  await panel.scrollIntoViewIfNeeded();
  const item = panel.locator('li[data-queue="Tata"]');
  await expect(item).toBeVisible({ timeout: 20_000 });
  await expect(item.getByText(/work order from Tata for polymer supplies/)).toBeVisible();
  if (SHOTS) await panel.screenshot({ path: `${SHOTS}/admin-queue-desktop.png` });
  await item.getByRole("button", { name: "Keep as filed" }).click();
  await expect(panel.getByText("Kept as filed, unlinked.")).toBeVisible();
  await expect(panel.locator('li[data-queue="Tata"]')).toHaveCount(0);
  expect(errors).toEqual([]);
});
