import { expect, test, type Page } from "@playwright/test";

// FIX-1B (LIVE1B-001..087): the pages the live review of the ship323 stack found fault with, checked in a browser at the
// widths it was reviewed at. Signed in as the owner (the fake world's admin, with holdings and trades).
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const owner = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, where: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
  }, owner);
  await page.goto(where);
  return errors;
}

const noSideways = async (page: Page, where: string) => {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, `${where} scrolls sideways`).toBeLessThanOrEqual(width + 1);
};

// the pages this branch changed for the review: each loads, has its heading, throws nothing and does not scroll sideways
const PAGES: [string, RegExp][] = [
  ["/holdings", /stocks/i],
  ["/tax-report", /tax/i],
  ["/money/mutual-funds", /funds/i],
  ["/money/net-worth", /net worth/i],
  ["/money/us-tax", /US/],
  ["/money/itr", /ITR|income tax/i],
  ["/money/tax-tools", /tax/i],
  ["/money/calendar", /calendar/i],
  ["/trade/journal", /journal/i],
  ["/settings", /Settings/],
  ["/help", /Help/],
  ["/plans", /Plans/],
  ["/alerts", /alerts/i],
];

for (const [path, heading] of PAGES) {
  test(`FIX1B: ${path} loads, has its heading and does not scroll sideways`, async ({ page }) => {
    const errors = await open(page, path);
    await expect(page.locator("main")).toContainText(heading, { timeout: 30_000 });
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await expect(page.locator("main"), `${path} says it could not load`).not.toContainText(/couldn't load|didn't load|Can't reach/);
    await noSideways(page, path);
    expect(errors).toEqual([]);
  });
}

test("LIVE1B-036, 055, 070: on a phone the small buttons and links are 44px tall", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the 44px targets are the phone's");
  const errors = await open(page, "/help");
  await expect(page.locator("main").getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  const summaries = page.locator("main .help-topic summary");
  await expect(summaries.first()).toBeVisible();
  const box = await summaries.first().boundingBox();
  expect(box?.height ?? 0, "a Help explanation's summary").toBeGreaterThanOrEqual(43.5);
  expect(errors).toEqual([]);
});

test("LIVE1B-043: Help is at the page's width and its explanations are under group headings", async ({ page }, info) => {
  const errors = await open(page, "/help");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(main.locator(".help-group h3").first()).toBeVisible();
  expect(await main.locator(".help-group h3").count(), "group headings").toBeGreaterThanOrEqual(4);
  if (info.project.name !== "phone") {
    const w = (await main.locator(".k-page").first().boundingBox())?.width ?? 0;
    expect(w, "Help is as wide as the other pages").toBeGreaterThan(600);
  }
  await noSideways(page, "/help");
  expect(errors).toEqual([]);
});
