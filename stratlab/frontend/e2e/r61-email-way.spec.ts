import { expect, test, type Page } from "@playwright/test";

// R61 (owner, on Release 60: "there is no option to sign in with email on the homepage"): with email sign-in on, every visitor's Continue
// with Google button has "or sign in with email" beside it, opening the sign-in page with the address box ready; off, none is drawn.

/** The built app's config.js with these switches added (as e2e/su1-email-usd.spec.ts). */
async function withConfig(page: Page, extra: Record<string, string>) {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(extra)});\n` });
  });
}
const errorsOf = (page: Page) => { const e: string[] = []; page.on("pageerror", (x) => e.push(x.message)); return e; };

test.use({ serviceWorkers: "block" });

test("email sign-in off: no email link anywhere a visitor signs in", async ({ page }) => {
  const errors = errorsOf(page);
  await page.goto("/");
  await expect(page.locator(".lp-hero").getByRole("button", { name: "Continue with Google" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("email-way")).toHaveCount(0);
  await page.goto("/library");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("email-way")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("email sign-in on: the landing hero offers email beside Google, and it opens the sign-in page with the address box ready", async ({ page }) => {
  const errors = errorsOf(page);
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  await page.goto("/");
  const hero = page.locator(".lp-hero");
  const google = hero.getByRole("button", { name: "Continue with Google" });
  await expect(google).toBeVisible({ timeout: 30_000 });
  const way = hero.getByTestId("email-way");
  await expect(way).toBeVisible();
  // (updated on purpose, R64 owner: "make it proper"): a button of the Google button's height in the row beside it, in the first screen
  await expect(way).toHaveText("Sign in with email");
  const g = (await google.boundingBox())!, w = (await way.boundingBox())!;
  expect(Math.abs(w.height - g.height)).toBeLessThan(4);
  if (page.viewportSize()!.width > 640) {
    expect(Math.abs(w.y - g.y)).toBeLessThan(4);                 // beside it on one row
    expect(w.x).toBeGreaterThan(g.x + g.width);
  } else {
    expect(w.y - (g.y + g.height)).toBeGreaterThan(0);           // a phone stacks them: right under it, the same full width
    expect(w.y - (g.y + g.height)).toBeLessThan(40);
    expect(Math.abs(w.width - g.width)).toBeLessThan(4);
  }
  expect(w.y + w.height).toBeLessThan(page.viewportSize()!.height);
  // the closing call and the plan cards have it too
  await expect(page.locator(".lp-final").getByTestId("email-way")).toHaveCount(1);
  expect(await page.locator("#pricing").getByTestId("email-way").count()).toBeGreaterThan(0);
  await way.click();
  await expect(page).toHaveURL(/\/login#email$/, { timeout: 30_000 });
  const box = page.getByLabel("Sign in with email");
  await expect(box).toBeFocused({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
  // the public library's header Sign in opens the page with both ways in; its wide button has the email way beside it
  await page.goto("/library");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("banner").getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/, { timeout: 30_000 });
  await expect(page.getByLabel("Sign in with email")).toBeVisible();
  expect(errors).toEqual([]);
});

// LIVE11B-001 (Release 66 live: the plan cards' email button took the feature list's grid row and boxed its ticks at 1440; on a phone the
// "What … includes" fold sat on the button): with email sign-in on, each plan card's email button sits under its Google button and above
// the list, overlapping nothing, at desktop and phone widths
test("email sign-in on: each plan card's email button is under its Google button and clear of the feature list", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  await page.goto("/plans");
  const cards = page.locator(".lp-price[data-plan]");
  await expect(cards.first().getByTestId("email-way")).toBeVisible({ timeout: 30_000 });
  const n = await cards.count();
  expect(n).toBeGreaterThanOrEqual(3);
  for (let i = 0; i < n; i++) {
    const card = cards.nth(i);
    const wayEl = card.getByTestId("email-way");
    if (!(await wayEl.count())) continue;                 // a card with a note instead of buttons (the plan you are on)
    const way = (await wayEl.boundingBox())!;
    const google = (await card.locator(".lp-plan-ways > .btn").first().boundingBox())!;
    expect(way.y, "email under Google").toBeGreaterThanOrEqual(google.y + google.height - 1);
    expect(way.height, "the email button is a button's height, not the list's").toBeLessThan(64);
    // the next thing below (the list, or on a phone its fold) starts under the email button
    const below = card.locator(".lp-plan-list, .k-phonefold, details, button[aria-expanded]").filter({ hasNot: page.getByTestId("email-way") });
    for (const b of await below.all()) {
      const r = await b.boundingBox();
      if (!r || r.y + r.height <= way.y) continue;
      expect(r.y, "nothing in the card starts over the email button").toBeGreaterThanOrEqual(way.y + way.height - 1);
    }
  }
});
