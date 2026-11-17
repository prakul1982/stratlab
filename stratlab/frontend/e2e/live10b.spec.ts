import { expect, test } from "@playwright/test";
import { open } from "./a11y-kit";

// LIVE10B (17 Nov 2026): the live end-to-end review of Release 60. What only a browser shows.

/** Every visible form control on the page with no accessible label: no <label> tied to it, no aria-label, no aria-labelledby. */
const unlabelled = (page: import("@playwright/test").Page) => page.evaluate(() => Array.from(document.querySelectorAll("main input:not([type=hidden]), main select, main textarea"))
  .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; })
  .filter((e) => !((e as HTMLInputElement).labels?.length || e.getAttribute("aria-label") || e.getAttribute("aria-labelledby")))
  .map((e) => `${e.tagName.toLowerCase()} ${(e as HTMLInputElement).type ?? ""} ${(e as HTMLInputElement).value ?? ""}`));

test("LIVE10B-018/022/038: the options builder's More settings, the scan view and the notification ticks are all labelled", async ({ page }) => {
  await open(page, "/options");
  await page.locator("summary", { hasText: "More settings" }).first().click();
  await expect(page.getByLabel("Entries a day")).toBeVisible({ timeout: 30_000 });
  expect(await unlabelled(page)).toEqual([]);
  await open(page, "/research/scan");
  await expect(page.getByLabel("Group to scan")).toBeVisible({ timeout: 30_000 });
  expect(await unlabelled(page)).toEqual([]);
  await open(page, "/settings#notifications");
  await expect(page.getByText("A short report after each market closes")).toBeVisible({ timeout: 30_000 });
  expect(await unlabelled(page)).toEqual([]);
});

test("LIVE10B-007: the running P&L of a journal with one closed trade draws that trade, on an axis that covers it", async ({ page, request }) => {
  const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
  const who = { access_token: "load-77", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: "u-load-77", aud: "authenticated", email: "load77@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
  const headers = { Authorization: "Bearer load-77" };
  await request.delete(`${API}/trade/journal`, { headers });
  const r = await request.post(`${API}/trade/journal/trades`, { headers, data: { symbol: "INFY", side: "long", entry_date: "2026-11-10", exit_date: "2026-11-13",
    qty: 10, entry_price: 1500, exit_price: 1550 } });
  expect(r.ok(), await r.text()).toBeTruthy();
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); localStorage.setItem("stratlab.onboarding.v1", "done"); }, who);
  await page.goto("/trade/journal");
  const curve = page.getByTestId("journal-curve");
  await expect(curve).toBeVisible({ timeout: 30_000 });
  await curve.scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);                                  // the axis eases to its range
  await curve.screenshot({ path: "test-results/live10b-007-curve.png" });
  const ticks = (await curve.locator("text").evaluateAll((els) => els.map((e) => e.textContent ?? ""))).join(" | ");
  expect(ticks, ticks).toMatch(/₹[1-9]\d{2}\b/);                      // a tick in the hundreds: the +₹451 trade is on the axis
  expect(ticks).not.toMatch(/₹0\.25/);
  await request.delete(`${API}/trade/journal`, { headers });
});
