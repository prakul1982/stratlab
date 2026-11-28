import { expect, test, type Page } from "@playwright/test";

// Lane social103 (owner, 28 Nov: "daily posting on X and LinkedIn fully automated; I have no time to post"; then LinkedIn only for now):
// Admin → Social shows each network's state, its switch (off, and only usable once connected), the next post and the last posts. The fake world has no X or LinkedIn
// app keys and never calls either network.
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
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(300);
  return errors;
}

test("social103 Admin → Social: each network's state, its switch off until connected, the next post and the last posts", async ({ page }) => {
  const errors = await open(page, "/admin/social", "Last posts");
  await expect(page.getByRole("heading", { level: 1, name: "Social" })).toBeVisible();
  // owner, 28 Nov: LinkedIn only for now (X charges per post): X's card isn't shown while SOCIAL_X is off on the server
  await expect(page.getByTestId("social-x")).toHaveCount(0);
  for (const [key, name, vars] of [["linkedin", "LinkedIn", "LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET"]] as const) {
    const card = page.getByTestId(`social-${key}`);
    await expect(card).toBeVisible();
    // no app keys in the fake world: it says which variables to add, and nothing can be pressed that would leave the site
    await expect(card).toContainText("Not set up");
    await expect(card).toContainText(vars);
    await expect(card.getByRole("button", { name: `Connect ${name}` })).toBeDisabled();
    await expect(card.getByRole("button", { name: "Post now" })).toBeDisabled();
    await expect(card.getByRole("checkbox", { name: new RegExp(`^Post daily on ${name}, 9:40 AM India time, Monday to Saturday`) })).not.toBeChecked();
    await expect(card.getByRole("checkbox", { name: new RegExp(`^Post daily on ${name}`) })).toBeDisabled();
    await expect(card).toContainText(`/admin/social/${key}/callback`);
    // the next post: its words with their length against the network's limit, or why there is none
    const next = page.getByTestId(`social-next-${key}`);
    await expect(next).toContainText(/Next post/);
    const text = await next.innerText();
    if (/of (280|1300) characters/.test(text)) {
      expect(text).toContain("Facts only, not investment advice.");
      expect(text).toContain(`?from=${key}`);
      expect(text).not.toMatch(/\b(buy|sell|target|recommend\w*)\b/i);
    } else {
      expect(text).toMatch(/No public theme page yet|Every public theme|public themes? not posted|No post to preview/);
    }
  }
  await expect(page.getByText("This server is a test copy: it never calls X or LinkedIn.")).toBeVisible();
  await expect(page.getByText("Nothing posted yet")).toBeVisible();
  const sw = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(sw).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
});

test("social103: back from a network's sign-in page, the page says how it went, once, and Overview asks nothing of a network not connected", async ({ page }) => {
  const errors = await open(page, "/admin/social?social=linkedin&result=denied", "Last posts");
  await expect(page.getByText("LinkedIn wasn't connected: the sign-in was cancelled on its page.")).toBeVisible();
  await expect(page).toHaveURL(/\/admin\/social$/);
  await page.getByRole("navigation", { name: "Admin sections" }).getByRole("link", { name: /^Overview/ }).click();
  const card = page.getByRole("region", { name: "Needs your attention" });
  await expect(card).toBeVisible({ timeout: 30_000 });
  expect((await card.innerText())).not.toMatch(/LinkedIn|X daily post/);
  expect(errors).toEqual([]);
});
