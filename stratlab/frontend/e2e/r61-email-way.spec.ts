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
