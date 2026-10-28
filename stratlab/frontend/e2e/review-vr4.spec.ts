import { expect, test, type Page } from "@playwright/test";

// VR-4 (28 Oct 2026): what a visual review of that day's pages found, checked on the drawn pages (desktop and phone).
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const ADMIN = session("admin-token", "u-admin", "owner@example.com"), FREE = session("free-token", "u-free", "free@example.com");

async function open(page: Page, path: string, s: object, tour = true) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.addInitScript(([x, t]) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); if (t) localStorage.setItem("stratlab.tour.v1", "1"); }, [s, tour] as const);
  await page.goto(path);
  return errors;
}

test("VR4-001: Account's six data cards share the rows, three and three, on a desktop", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "a desktop layout");
  await open(page, "/account", ADMIN);
  const tiles = page.locator("#data .k-linkcards > *");
  await expect(tiles).toHaveCount(6);
  const tops = await tiles.evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
  const rows = [...new Set(tops)];
  expect(rows.length, `rows of tops ${tops}`).toBe(2);
  expect(tops.filter((t) => t === rows[0]).length).toBe(3);
});

test("VR4-005 and VR4-013: a company page's update filings start their titles at one x, and 'What they do' says each thing once", async ({ page }) => {
  await open(page, "/research/IN/RELIANCE", ADMIN);
  const days = page.locator(".biz-filings .biz-day");
  await expect(days.first()).toBeVisible({ timeout: 30_000 });
  const widths = await days.evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
  expect(new Set(widths).size, `date widths ${widths}`).toBe(1);
  const lefts = await page.locator(".biz-filings li > span").evaluateAll((els) => els.map((e) => { const d = e.querySelector(".biz-day")!.getBoundingClientRect(); return Math.round(d.right); }));
  expect(new Set(lefts).size, `title starts ${lefts}`).toBe(1);
  const card = page.locator(".k-card", { has: page.getByRole("heading", { name: "What they do" }) });
  await expect(card).toBeVisible();
  const text = await card.innerText();
  const desc = (await card.locator(".k-sub").count()) ? await card.locator(".k-sub").first().innerText() : "";
  const body = await card.locator("p.k-small").first().innerText();
  expect(desc && body.toLowerCase().includes(desc.toLowerCase()), "the one-line description is said again by the entry's first sentence").toBeFalsy();
  expect(text).not.toMatch(/\nListed\s*\n?NSE · RELIANCE/);
});

test("VR4-011: the Invest breadth card does not date each of its three figures with the same day", async ({ page }) => {
  await open(page, "/invest", ADMIN);
  const card = page.getByTestId("breadth-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  const notes = await card.locator(".k-stat-n, .k-stat-note").allInnerTexts();
  expect(notes.filter((n) => /^Today, \d/.test(n.trim())).length, `notes ${notes}`).toBeLessThan(2);
});

test("VR4-008: the welcome question does not say the four spaces, which the tour's first step says next", async ({ page }) => {
  // the account's answers are saved on the server and other tests answer for it: read it as an account that has not been asked
  await page.route(/\/me$/, async (r) => { const res = await r.fetch(); const j = await res.json(); j.prefs = {}; j.onboarding = {}; await r.fulfill({ response: res, json: j }); });
  await open(page, "/trade", FREE, false);
  const dlg = page.getByRole("dialog");
  await expect(dlg.getByText("What brings you here?")).toBeVisible({ timeout: 30_000 });
  await expect(dlg).toContainText("StratLab is a lab for testing trading ideas");
  await expect(dlg).toContainText("You're on Trade now");
  await expect(dlg).not.toContainText("four spaces");
  await dlg.getByRole("button", { name: /All of it/ }).first().click();
  await expect(page.getByText("Four spaces")).toBeVisible({ timeout: 15_000 });
});

test("VR4-owner-1 and VR4-014: My space's six market tiles are all green or red, and the watchlist title stays on one line", async ({ page }, info) => {
  await open(page, "/mine", ADMIN);
  const strip = page.getByTestId("mine-markets");
  await expect(strip.locator(".mine-mkt")).toHaveCount(6, { timeout: 30_000 });
  await expect(strip.locator(".k-skel")).toHaveCount(0, { timeout: 30_000 });
  for (const t of await strip.locator(".mine-mkt").all()) {
    const id = await t.getAttribute("data-market");
    expect(await t.locator(".k-delta").getAttribute("class"), `${id} pill`).toMatch(/\b(up|down)\b/);
    expect(await t.locator("svg.k-spark").getAttribute("class"), `${id} line`).toMatch(/\b(up|down)\b/);
  }
  if (info.project.name === "desktop") {
    await page.setViewportSize({ width: 1280, height: 800 });
    const title = page.getByTestId("mine-watch").getByRole("heading").first();
    await expect(title).toBeVisible();
    const h = await title.evaluate((e) => e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight));
    expect(h).toBeLessThan(1.6);
  }
});
