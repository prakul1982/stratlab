import { expect, test, type Page } from "@playwright/test";

// FIX-2 (29 Oct 2026): the findings of the live review LIVE-2 and the owner's items, in the browser, on desktop and phone.
// The fake world stores its newest Market Brief of each market (tests/visual_server.py), built from its own closes.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
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
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(300);
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
}

test("O5, O6: a brief's sections are tables, and the PDF button downloads the brief", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/news?tab=IN", "Briefs", phone ? 283 : 282);
  if (phone) await page.getByRole("button", { name: /Market Brief India/ }).first().click();
  const pane = page.locator(".news-issue");
  await expect(pane).toContainText("Market brief · India", { timeout: 30_000 });
  // the indices are a table with a header row, not a bullet list
  const indices = pane.getByRole("table", { name: "Indices" });
  await expect(indices).toBeVisible();
  if (!phone) {
    await expect(indices.locator("thead th")).toHaveText(["Index", "Close", "Day %", "From 52-week high"]);
    const first = indices.locator("tbody tr").first();
    await expect(first.locator("td").nth(0)).toHaveText(/^[\d,]+\.\d\d$/);
    await expect(first.locator("td").nth(1)).toHaveText(/^[▲▼] [+−]\d+\.\d\d%$|^– 0\.00%$/);            // an arrow and a sign
    const right = await indices.locator("tbody tr").first().locator("td").nth(0).evaluate((el) => getComputedStyle(el).textAlign);
    expect(right, "figures sit on the right").toBe("right");
  }
  await expect(pane.locator("ul.news-items li")).toHaveCount(0);                                   // no bullet-list section in a market brief
  await expect(pane).not.toContainText("(ST S2)");
  // the PDF: a file is downloaded
  const [download] = await Promise.all([page.waitForEvent("download"), pane.getByRole("button", { name: "Download PDF" }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  const path = await download.path();
  const { statSync, readFileSync } = await import("node:fs");
  expect(statSync(path).size).toBeGreaterThan(2000);
  expect(readFileSync(path).subarray(0, 5).toString()).toBe("%PDF-");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/brief-tables-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);
});
