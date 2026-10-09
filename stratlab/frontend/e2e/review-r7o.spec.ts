import { expect, test, type Page } from "@playwright/test";

// Round 7, the owner's review of the live site (9 Oct 2026): tap targets of 32 px on the pages it measured, the
// Breadth "+ Custom" chip inside its card, one h1 on every page, the paper chart's dates across days, Red flags and the
// breadth card on the reader's own market, a net-worth snapshot that can be removed alone, and the admin's words.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const owner = { token: "admin-token", id: "u-admin", email: "owner@example.com" };

async function open(page: Page, path: string, user = owner) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: user.token, user: { id: user.id, aud: "authenticated", email: user.email, role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(path);
  return errors;
}

/** Buttons, links and fields smaller than 32 px either way, as the reviewer measured them (skip links are 1 px by design). */
async function smallTargets(page: Page) {
  return page.evaluate(() => [...document.querySelectorAll<HTMLElement>("button,a,input,select")]
    .filter((b) => {
      const r = b.getBoundingClientRect();
      if (!(r.width > 0 && r.height > 0) || getComputedStyle(b).visibility === "hidden") return false;
      if (b.closest(".skip-links, .skip") || b.classList.contains("skip-link") || (r.width <= 1 && r.height <= 1)) return false;
      return r.height < 32 || r.width < 32;
    })
    .map((b) => `${b.tagName.toLowerCase()}.${String(b.className).split(" ").slice(0, 3).join(".")} "${(b.innerText || b.getAttribute("aria-label") || "").trim().slice(0, 30)}" ${Math.round(b.getBoundingClientRect().width)}x${Math.round(b.getBoundingClientRect().height)}`));
}

for (const [path, ready] of [["/features", "h1"], ["/trade/events", "h1"], ["/invest/holders", "h1"], ["/research/rotation", "h1"], ["/admin/quality", "h1"]] as const) {
  test(`phone: every tap target on ${path} is at least 32 px (R7O-010)`, async ({ page }, info) => {
    test.skip(info.project.name !== "phone", "the phone's widths");
    await page.setViewportSize({ width: 400, height: 860 });
    await open(page, path);
    await expect(page.locator(ready).first()).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(2500);
    expect(await smallTargets(page)).toEqual([]);
  });
}

test("Red flags open on India for an India reader, whatever market was looked up last (R7O-003)", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("stratlab.research.region", "US"));
  const errors = await open(page, "/research/filings?view=all");
  await expect(page.getByRole("heading", { level: 1, name: "Filings and red flags" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main")).toContainText("What companies told the exchange");
  await expect(page.locator("main")).not.toContainText("What S&P 500 companies told the SEC");
  expect(errors).toEqual([]);
});

test("The Invest home breadth card follows India even with an old S&P 500 pick remembered (R6O-007 residue)", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("stratlab.breadth", JSON.stringify({ group: "sp500", range: "1y" }));
    localStorage.setItem("stratlab.research.region", "US");
  });
  const errors = await open(page, "/invest");
  const card = page.getByTestId("breadth-card").or(page.getByText(/The first counts for/)).first();
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).not.toContainText("S&P 500");
  expect(errors).toEqual([]);
});

test("Pages keep one h1 on a desktop: My space, Options, Plans (R7O-010)", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the reviewer's desktop pages");
  await open(page, "/mine");
  for (const path of ["/mine", "/options", "/plans"]) {
    if (path !== "/mine") await page.goto(path);
    await expect(page.locator("main h1:not(.sr-only)").first()).toBeVisible({ timeout: 30_000 });
    expect(await page.locator("main h1:not(.sr-only)").count(), `${path}: one visible h1`).toBe(1);
  }
});

test("The Breadth time-range chips keep + Custom inside the card on a phone (R7O-010)", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "a phone's width");
  await page.setViewportSize({ width: 400, height: 860 });
  await open(page, "/invest/breadth");
  const add = page.getByRole("button", { name: "+ Custom" }).first();
  await expect(add).toBeVisible({ timeout: 30_000 });
  const fits = await add.evaluate((el) => {
    const card = (el.closest(".k-card") ?? el.closest("main")) as HTMLElement;
    const a = el.getBoundingClientRect(), b = card.getBoundingClientRect();
    return a.right <= b.right + 0.5 && a.left >= b.left - 0.5 && a.right <= window.innerWidth;
  });
  expect(fits, "+ Custom is cut off at the card's edge").toBe(true);
});

test("Net worth: one snapshot is removed from the history after a confirm; the entries stay (R7O-013)", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 251 : 248;                  // Pro accounts in the fake world: the history is shown
  const auth = { Authorization: `Bearer load-${n}` };
  expect((await request.delete(`${API}/money/net-worth`, { headers: auth })).ok()).toBeTruthy();
  const added = await request.post(`${API}/money/net-worth/items`, { headers: auth, data: { kind: "cash", name: "Savings account", value: 100000 } });
  expect(added.ok(), await added.text()).toBeTruthy();
  const user = { token: `load-${n}`, id: `u-load-${n}`, email: `load${n}@example.com` };
  const errors = await open(page, "/money/net-worth", user);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  if (await welcome.waitFor({ timeout: 4000 }).then(() => true).catch(() => false)) {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await page.goto("/money/net-worth");
  }
  const snaps = page.getByTestId("nw-snapshots");
  await expect(snaps).toBeVisible({ timeout: 30_000 });
  await snaps.locator("summary").click();
  await snaps.getByRole("button", { name: /^Remove the snapshot of/ }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Only that day's net worth leaves the history chart");
  await dialog.getByRole("button", { name: "Remove this snapshot" }).click();
  await expect(page.getByText("Snapshot removed.")).toBeVisible();
  await expect(page.getByTestId("nw-snapshots")).toHaveCount(0);
  await expect(page.locator("main")).toContainText("Savings account");
  expect(errors).toEqual([]);
  await request.delete(`${API}/money/net-worth`, { headers: auth });
});
