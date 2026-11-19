import { readFileSync } from "node:fs";
import { expect, test, type Page, type Route } from "@playwright/test";

// site79 (Release 79) on the fake world, desktop and phone.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const SB = "https://demo.supabase.co/auth/v1";

async function withConfig(page: Page, extra: Record<string, string>) {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(extra)});\n` });
  });
}

/** /login and /signup as production serves them: the build's own page for the address (dist/login/index.html), which vite preview
 * serves only at /login/. */
async function servedAsLive(page: Page) {
  await page.route(/\/(login|signup)(\?[^#]*)?$/, (r) => r.request().resourceType() === "document"
    ? r.fulfill({ status: 200, contentType: "text/html", body: readFileSync(new URL(`../dist${new URL(r.request().url()).pathname}/index.html`, import.meta.url), "utf8") })
    : r.fallback());
}

/** The app's own code held back until `release()`: what shows meanwhile is the page's HTML alone (its start-up frame). */
async function holdCode(page: Page) {
  let release!: () => void;
  const gate = new Promise<void>((ok) => { release = ok; });
  await page.route(/\/(assets|src)\/.*\.(js|tsx?)(\?|$)/, async (r) => { await gate; await r.continue().catch(() => undefined); });
  return release;
}

test.use({ serviceWorkers: "block" });

// LIVE16B-001 (live, 19 Nov): /login said "StratLab signs in with your Google account: no password to set up." with no button for up to
// 3.25 s, though email sign-in is on; /signup on a phone was blank. The sign-in page's own HTML now draws both ways in (production serves
// dist/login/index.html for /login; vite preview serves it at /login/), and a press before the app is ready is done once it draws.
for (const [path, heading, verb] of [["/login", "Sign in to StratLab", "Sign in"], ["/signup", "Sign up for StratLab", "Sign up"]] as const) {
  test(`${path}: Google and the email form are drawn before the app's code, with true words`, async ({ page }) => {
    await withConfig(page, { EMAIL_SIGNIN: "on" });
    await servedAsLive(page);
    const release = await holdCode(page);
    await page.goto(path, { waitUntil: "commit" });
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading, { timeout: 30_000 });
    await expect(page.locator(".lp-lede")).toHaveText(`${verb} with your Google account or your email address: no password to set up.`, { useInnerText: true });
    await expect(page.getByText("signs in with your Google account")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
    await expect(page.getByLabel(`${verb} with email`)).toBeVisible();
    await expect(page.getByRole("button", { name: "Email me a code" })).toBeVisible();
    expect(await page.evaluate(() => !!document.querySelector(".lp > header")), "the app has not drawn yet").toBe(false);
    const box = (await page.getByRole("button", { name: "Continue with Google" }).boundingBox())!;
    release();
    // the app draws over the frame with the same page: the same controls, in the same place
    await expect(page.locator(".lp > header")).toBeAttached({ timeout: 30_000 });
    const after = (await page.getByRole("button", { name: "Continue with Google" }).boundingBox())!;
    expect(Math.abs(after.y - box.y), "Continue with Google stays where it was").toBeLessThan(2);
    await expect(page.getByLabel(`${verb} with email`)).toBeVisible();
  });
}

test("an address typed and sent in the start-up frame is emailed once the app is ready", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  const sent: Record<string, unknown>[] = [];
  await page.route(`${SB}/otp**`, (r) => { sent.push(r.request().postDataJSON()); return r.fulfill({ status: 200, contentType: "application/json", body: "{}" }); });
  await servedAsLive(page);
  const release = await holdCode(page);
  await page.goto("/login", { waitUntil: "commit" });
  const box = page.getByLabel("Sign in with email");
  await box.fill("early@example.com");
  await page.getByRole("button", { name: "Email me a code" }).click();
  release();
  await expect(page.getByTestId("email-sent")).toContainText("early@example.com", { timeout: 30_000 });
  expect(sent.length).toBe(1);
  expect(sent[0].email).toBe("early@example.com");
});

test("Continue with Google pressed in the start-up frame starts Google sign-in once the app is ready", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  let authorize: URL | null = null;
  await page.route(`${SB}/authorize**`, (r) => { authorize = new URL(r.request().url()); return r.fulfill({ status: 200, body: "signing in", contentType: "text/plain" }); });
  await servedAsLive(page);
  const release = await holdCode(page);
  await page.goto("/login", { waitUntil: "commit" });
  await page.getByRole("button", { name: "Continue with Google" }).click();
  release();
  await expect.poll(() => authorize?.searchParams.get("provider") ?? "", { timeout: 30_000 }).toBe("google");
});

test("with email sign-in off, the start-up frame offers Google alone and says so", async ({ page }) => {
  await servedAsLive(page);
  const release = await holdCode(page);
  await page.goto("/login", { waitUntil: "commit" });
  await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".lp-lede")).toHaveText("Sign in with your Google account: no password to set up.", { useInnerText: true });
  await expect(page.getByRole("button", { name: "Email me a code" })).toBeHidden();
  release();
  await expect(page.locator(".lp > header")).toBeAttached({ timeout: 30_000 });
  await expect(page.locator(".lp-lede")).toHaveText("Sign in with your Google account: no password to set up.", { useInnerText: true });
});

// LIVE16B-001: the plan cards' email buttons were plain links to /login#email: a full reload, and the plan chosen was dropped
test("a plan card's email button opens the sign-in page in place, with its plan kept for after sign-in", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  // Basic and Pro on sale, so their cards have their ways in (a card of a plan not on sale says "Opens soon")
  await page.route(`${API}/pricing`, async (r: Route) => {
    const res = await r.fetch(); const j = await res.json();
    await r.fulfill({ response: res, json: { ...j, offer: { ...(j.offer ?? {}), mode: "paid", payments: true } } });
  });
  await page.goto("/plans");
  const way = page.locator('.lp-price[data-plan="basic"]').getByTestId("email-way");
  await expect(way).toBeVisible({ timeout: 30_000 });
  await expect(way).toHaveAttribute("href", "/login?plan=basic#email");
  await page.evaluate(() => { (window as unknown as { __same: number }).__same = 1; });
  await way.click();
  await expect(page).toHaveURL(/\/login\?plan=basic#email$/);
  await expect(page.getByLabel("Sign in with email")).toBeFocused({ timeout: 30_000 });
  expect(await page.evaluate(() => (window as unknown as { __same?: number }).__same), "no page load: the same window").toBe(1);
  const kept = await page.evaluate(() => JSON.parse(sessionStorage.getItem("stratlab.next") ?? "null")?.to);
  expect(kept).toBe("/plans?plan=basic");
});

test("signed in, /plans?plan=basic marks the Basic card as the plan picked before signing in", async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: "free-token", token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r",
        user: { id: "u-free", aud: "authenticated", email: "free@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } }));
      localStorage.setItem("stratlab.tour.v1", "1");
    } catch { /* none */ }
  });
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
  await page.goto("/plans?plan=basic");
  await expect(page.getByTestId("plan-picked")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("plan-card-basic")).toHaveClass(/\bpicked\b/);
  await expect(page.getByTestId("plan-card-pro")).not.toHaveClass(/\bpicked\b/);
  await expect(page.getByTestId("plan-card-basic").getByTestId("plan-picked")).toHaveCount(1);
});
