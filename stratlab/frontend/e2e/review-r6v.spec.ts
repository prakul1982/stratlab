import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Round 6, a visitor's review of the live site: library strategies that say what their checks showed, with readable
// dates and their own tags before any script runs; public company pages that name their year range and never call a
// capped search a count; a main landmark on every public page; an admin address that promises nothing; the landing's
// drawings inside their cards on a phone; and a purchase confirmed with its plan, period, GST and renewal first.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };

async function open(page: Page, path: string, user?: { token: string; id: string; email: string }) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  if (user) {
    const session = { ...base, access_token: user.token, user: { id: user.id, aud: "authenticated", email: user.email, role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
    await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  }
  await page.goto(path);
  return errors;
}
const h1 = (page: Page) => page.getByRole("heading", { level: 1 });
const noSideways = async (page: Page) => {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
};

test("a library strategy states its checks, buy and hold, its dates and its universe once; the card says the same (R6V-004, R6V-005)", async ({ page }) => {
  const errors = await open(page, "/library/seed-supertrend-us");
  await expect(h1(page)).toBeVisible({ timeout: 30_000 });
  const entry = await (await page.request.get(`${API}/public/library/seed-supertrend-us`)).json();
  const v = entry.verdict;
  await expect(h1(page)).toHaveText(v.fact_headline);
  await expect(h1(page)).not.toHaveText(/Likely a real edge|Probably luck/);
  if (entry.vs_hold) await expect(h1(page)).toContainText(/buy and hold/);
  await expect(page.locator("main")).not.toContainText("doesn't depend on one exact setting");
  // the dates as days, never the stored timestamps; the group named once
  await expect(page.getByTestId("lib-tested")).toHaveText(/^Tested \d{1,2} \w{3} \d{4} to \d{1,2} \w{3} \d{4}$/);
  await expect(page.locator("main")).not.toContainText("T00:00:00");
  const eyebrow = await page.locator(".k-eyebrow").first().innerText();
  expect(eyebrow.toLowerCase().split("20 us large caps").length - 1, eyebrow).toBe(1);
  // all four checks, each with its result in words; the one not run on a group says so
  const checks = page.getByRole("region", { name: "The four checks" }).or(page.locator("section.pub-checks"));
  await expect(checks.locator("h3")).toHaveText(["Unseen years", "Nearby settings", "Bad-luck drawdown", "Enough trades"]);
  await expect(checks.locator(".k-card", { hasText: "Nearby settings" })).toContainText("Not run");
  // the library card for the same strategy: the same label as the page's headline starts with
  await page.goto("/library");
  const card = page.locator(".k-card", { hasText: entry.name.split(" · ")[0] }).filter({ hasText: "20 US large caps" }).first();
  await expect(card.locator(".badge").first()).toHaveText(v.label);
  // the shortfall against buy and hold leads when there is one (R6V-005, round 7); the label follows it
  expect(v.fact_headline.toLowerCase()).toContain(v.label.toLowerCase());
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("a library strategy's own HTML carries its own title and address before any script runs (R6V-012)", async ({ page }) => {
  // the built file the site's host serves at /library/seed-supertrend-us (the local preview server falls back to
  // index.html for every address, so the file is read as built)
  const raw = readFileSync(new URL("../dist/library/seed-supertrend-us/index.html", import.meta.url), "utf8");
  expect(raw).toMatch(/<title>Supertrend flip · 20 US large caps: rules and verdict · StratLab<\/title>/);
  expect(raw).toMatch(/<link rel="canonical" href="https:\/\/stratlab\.studio\/library\/seed-supertrend-us">/);
  expect(raw).not.toMatch(/<link rel="canonical" href="https:\/\/stratlab\.studio\/">/);
  // and the app on that file still draws the strategy, with the same address in its tags
  const errors = await open(page, "/library/seed-supertrend-us");
  await expect(h1(page)).not.toHaveText("StratLab", { timeout: 30_000 });
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://stratlab.studio/library/seed-supertrend-us");
  expect(errors).toEqual([]);
});

test("every public page has one main landmark and a heading; an admin address promises nothing (R6V-013)", async ({ page }) => {
  for (const path of ["/library/seed-supertrend-us", "/nope-r6v", "/research/IN/TCS", "/library"]) {
    await open(page, path);
    await expect(h1(page).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("main"), path).toHaveCount(1);
  }
  await open(page, "/admin");
  await expect(h1(page)).toHaveText("Sign in to StratLab", { timeout: 30_000 });
  await expect(page.locator("main")).not.toContainText(/admin/i);
  await expect(page).toHaveTitle("Sign in · StratLab");
});

test("a page still loading is already a main landmark with a heading (R6V-013)", async ({ page }) => {
  let release: () => void = () => {};
  const held = new Promise<void>((ok) => { release = ok; });
  await page.route(/\/assets\/PublicLibrary-[^/]+\.js$/, async (r) => { await held; await r.fallback(); });
  await open(page, "/library/seed-supertrend-us");
  // changed on purpose in R10V-006: the page's own start-up words stay on screen while its code downloads (they are a main
  // landmark with a heading too), not an "Opening StratLab" splash that replaced them for a second
  await expect(page.locator("[data-held] h1")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Opening StratLab")).toHaveCount(0);
  await expect(page.locator("main")).toHaveCount(1);
  await expect(page.locator("main h1")).toHaveCount(1);
  release();
  await expect(h1(page)).not.toHaveText("StratLab", { timeout: 30_000 });
});

test("the landing's drawings stay inside their cards at phone width (R6V-006)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors = await open(page, "/");
  const cards = page.locator(".lp-checks .lp-card");
  await expect(cards.first()).toBeVisible({ timeout: 30_000 });
  for (const card of await cards.all()) {
    const [c, art] = [await card.boundingBox(), await card.locator(".lp-art").boundingBox()];
    expect(art!.x + art!.width, "a drawing runs past its card").toBeLessThanOrEqual(c!.x + c!.width + 0.5);
  }
  expect(await cards.first().evaluate((el) => getComputedStyle(el).minWidth)).toBe("0px");
  expect(await page.locator(".lp-art").first().evaluate((el) => getComputedStyle(el).overflow)).toBe("hidden");
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("a public company page names its year range intraday and a capped search says 'first' (R6V-014, R6V-015)", async ({ page }) => {
  const errors = await open(page, "/stocks/us/AAPL");
  await expect(page.locator(".stat", { hasText: "1-year range (intraday)" })).toHaveCount(1);
  for (const caption of await page.locator("[data-peers]").allInnerTexts())
    expect(caption).toMatch(/^(The largest companies in the (same industry|wider sector) \(.+\), by market value\.|Companies StratLab lists in the same sector, in no particular order\.)$/);
  await page.goto("/stocks?q=a&m=us");
  const head = await page.locator("main h2").first().innerText();
  expect(head).toMatch(/^US: (the first \d+ matches|\d+ match(es)?) for “a”$/);
  await page.goto("/stocks");
  await expect(page.locator("main")).not.toContainText(/\$\d[\d.,]*T\b.*\$\d[\d.,]*T\b.*\$\d[\d.,]*T\b.*\$\d[\d.,]*T\b/);   // no list of trillion-dollar values
  expect(errors).toEqual([]);
});

test("a purchase is confirmed on the page with its plan, period, GST and renewal; a given plan isn't sold again (R6V-009)", async ({ page }, info) => {
  // payments on, as the live site has them (the fake world's plans aren't on sale)
  await page.route(`${API}/me`, async (r) => {
    const res = await r.fetch();
    const j = await res.json();
    j.offer = { ...(j.offer ?? {}), payments: true, yearly: true };
    j.billing_enabled = true;
    await r.fulfill({ response: res, json: j });
  });
  let subscribed = false;
  await page.route(`${API}/billing/subscribe`, (r) => { subscribed = true; return r.fulfill({ status: 500, json: {} }); });
  const errors = await open(page, "/plans", { token: "load-297", id: "u-load-297", email: "load297@example.com" });
  await page.getByRole("button", { name: "Upgrade to Basic" }).click({ timeout: 30_000 });
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("plan-confirm")).toContainText(/Basic plan, billed monthly: ₹[\d,]+ incl\. 18% GST/);
  await expect(dialog).toContainText("renews automatically");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  expect(subscribed, "nothing is bought before the confirmation").toBe(false);
  await noSideways(page);
  expect(errors).toEqual([]);
  if (info.project.name !== "desktop") return;
  // the owner's gift: Pro with no subscription; Basic is included, not offered as a switch
  const other = await page.context().newPage();
  await other.route(`${API}/me`, async (r) => {
    const res = await r.fetch();
    const j = await res.json();
    j.offer = { ...(j.offer ?? {}), payments: true };
    j.billing = { ...(j.billing ?? {}), given_by_owner: true };
    await r.fulfill({ response: res, json: j });
  });
  await open(other, "/plans", { token: "load-299", id: "u-load-299", email: "load299@example.com" });
  await expect(other.getByTestId("plan-included")).toContainText("Included in the Pro plan you were given", { timeout: 30_000 });
  await expect(other.getByRole("button", { name: "Switch to Basic" })).toHaveCount(0);
});
