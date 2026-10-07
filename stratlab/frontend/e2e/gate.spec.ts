import { expect, test, type BrowserContext, type Page } from "@playwright/test";

// Build 3: what stands between a person and what they asked for. A signed-out visitor on an app address gets "Sign in to
// see …" and comes back to that address after Google sign-in (own pages only); an address nothing is at gets "Page not
// found"; Admin for someone else says so; /pricing and /help go somewhere; and the welcome question shows once per
// account, on a home page only, followed once by the short tour. Each test uses its own fake users (load-50 to load-59).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const session = (n: number) => ({ ...base, access_token: `load-${n}`,
  user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const who = (n: number, phone: boolean) => n + (phone ? 1 : 0);

/** Every outside request answered locally; collects uncaught errors. */
async function offline(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  return errors;
}
const signedIn = (ctx: BrowserContext | Page, n: number, tourSeen = true) => ctx.addInitScript(([s, seen]) => {
  localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
  if (seen) localStorage.setItem("stratlab.tour.v1", "1");
}, [session(n), tourSeen] as const);

async function noSideways(page: Page) {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
}

test("signed out: a company's address says what's there, and Google sign-in comes back to it", async ({ page }, info) => {
  const errors = await offline(page);
  let authorize: URL | null = null;
  await page.route("https://demo.supabase.co/auth/v1/authorize**", (r) => { authorize = new URL(r.request().url()); return r.fulfill({ status: 200, body: "signing in", contentType: "text/plain" }); });
  await page.goto("/research/IN/RELIANCE?tab=deals");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Sign in to see (RELIANCE|Reliance)/, { timeout: 30_000 });
  await expect(page.getByText("Test it, research it, track it")).toHaveCount(0);           // not the landing page
  // StratLab's public page for the company, no sign-in needed
  await expect(page.getByRole("link", { name: /Open the public page for/ })).toHaveAttribute("href", "/stocks/in/RELIANCE");
  await noSideways(page);
  if (info.project.name === "phone") await page.emulateMedia({ colorScheme: "dark" });
  await page.getByRole("button", { name: "Sign in with Google" }).click();
  await expect.poll(() => authorize?.href ?? "").toContain("provider=google");
  // Google comes back to the site's root (the address Supabase allows); the page itself was kept in this browser
  expect(new URL(authorize!.searchParams.get("redirect_to")!).pathname).toBe("/");
  await signedIn(page, who(50, info.project.name === "phone"));
  await page.goto("/");
  await expect(page).toHaveURL(/\/research\/IN\/RELIANCE\?tab=deals$/, { timeout: 30_000 });
  // and only once: home again is home
  await page.goto("/mine");
  await expect(page).toHaveURL(/\/mine$/);
  expect(errors).toEqual([]);
});

test("signed out: other app addresses, a page that doesn't exist, and no way back to another site", async ({ page }) => {
  const errors = await offline(page);
  for (const [path, title] of [["/holdings", "Sign in to see Holdings"], ["/n/abc123", "Sign in to see this notebook"],
    ["/library", "Sign in to see Strategy library"], ["/tax-report", "Sign in to see Tax report"]] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }), path).toHaveText(title, { timeout: 30_000 });
  }
  await page.goto("/no-such-page");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found", { timeout: 30_000 });
  await expect(page.getByText("/no-such-page")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to the StratLab home page" })).toHaveAttribute("href", "/");
  // the landing page's own addresses open the landing page at their section
  await page.goto("/pricing");
  await expect(page.locator("#pricing")).toBeInViewport({ timeout: 30_000 });
  // a crafted return address is dropped: sign-in never leads off the site
  await page.goto("/");
  await page.evaluate(() => sessionStorage.setItem("stratlab.next", JSON.stringify({ to: "//evil.example/x", at: Date.now() })));
  await signedIn(page, 55);
  await page.goto("/");
  await expect(page).toHaveURL(/127\.0\.0\.1:\d+\/(mine|trade|invest|money)$/, { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("signed in: a page that doesn't exist, Admin for someone else, /pricing and /help", async ({ page }, info) => {
  const errors = await offline(page);
  const n = who(56, info.project.name === "phone");
  await page.request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer load-${n}` }, data: { level: "some", focus: "both" } });
  await signedIn(page, n);
  await page.goto("/nonexistent-page");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { level: 1 })).toHaveText("Page not found", { timeout: 30_000 });
  await expect(page).toHaveURL(/\/nonexistent-page$/);                                     // no silent redirect
  await main.getByRole("button", { name: "Search StratLab" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(main.getByRole("link", { name: /^Invest/ })).toHaveAttribute("href", "/invest");
  await noSideways(page);

  await page.goto("/admin");
  await expect(main.getByRole("heading", { level: 1 })).toHaveText("You don't have access to this page", { timeout: 30_000 });
  await expect(main).toContainText(`load${n}@example.com`);
  await expect(page).toHaveURL(/\/admin$/);

  await page.goto("/pricing");
  await expect(page).toHaveURL(/\/plans$/, { timeout: 30_000 });
  await expect(main.getByRole("heading", { level: 1, name: "Plans" })).toBeVisible();
  await expect(main).toContainText("Basic and Pro aren't on sale yet");                     // the same words as the landing page
  await page.goto("/upgrade");
  await expect(page).toHaveURL(/\/plans$/);
  await page.goto("/help");
  await expect(main.getByRole("heading", { level: 1, name: "Help" })).toBeVisible({ timeout: 30_000 });
  await main.getByRole("button", { name: "Start the tour" }).click();
  await expect(page.getByRole("dialog", { name: "A quick tour" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "A quick tour" })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("onboarding: asked once, on a home page only; the short tour once; the account remembers on a new device", async ({ browser }, info) => {
  const phone = info.project.name === "phone";
  const n = who(58, phone);
  const make = () => browser.newContext(phone ? { viewport: { width: 412, height: 860 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 1000 } });
  const ctx = await make();
  const page = await ctx.newPage();
  const errors = await offline(page);
  await signedIn(ctx, n, false);                                       // a brand-new account on a brand-new browser
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });

  // a deep link: no question over the page someone came to see
  await page.goto("/holdings");
  await expect(page.locator("main").getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  await expect(welcome).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  // home: the question, with no experience picked for them (the standard layout applies if they leave it)
  await page.goto("/");
  await expect(welcome).toBeVisible({ timeout: 30_000 });
  await expect(welcome.getByRole("radio", { checked: true })).toHaveCount(0);
  await expect(welcome.locator(":focus")).toHaveCount(1);
  await expect(page.getByText("Your first steps")).toHaveCount(0);                         // one guide at a time
  await welcome.getByRole("button", { name: /^Trade/ }).click();
  await expect(welcome).toHaveCount(0);
  await expect(page).toHaveURL(/\/trade$/);

  // then the short tour, pointed at the real controls
  const tour = page.getByRole("dialog", { name: "A quick tour" });
  await expect(tour).toBeVisible();
  await expect(tour).toContainText("Step 1 of 4");
  await expect(tour).toContainText("Four spaces");
  await expect(tour).not.toContainText(/\bAll\b tab|three spaces/i);
  for (let i = 2; i <= 4; i++) { await tour.getByRole("button", { name: "Next" }).click(); await expect(tour).toContainText(`Step ${i} of 4`); }
  // the last step: Back and Done, nothing else to guess at
  await expect(tour.getByRole("button", { name: "Skip tour" })).toHaveCount(0);
  await expect(tour.getByRole("button", { name: "Done" })).toBeFocused();
  await tour.getByRole("button", { name: "Done" }).click();
  await expect(tour).toHaveCount(0);
  // now the checklist, under the heading
  await expect(page.getByText("Your first steps")).toBeVisible({ timeout: 30_000 });
  const [h1, steps] = await Promise.all([page.locator("main h1").boundingBox(), page.locator(".first-steps").boundingBox()]);
  expect(steps!.y, "the checklist sits under the page heading").toBeGreaterThan(h1!.y);
  await expect(page.getByRole("heading", { name: "Start here: your first notebook" }), "one guide at a time").toHaveCount(0);
  const me = await (await page.request.get(`${API}/me`, { headers: { Authorization: `Bearer load-${n}` } })).json();
  expect(me.onboarding.tour).toBe("done");
  expect(me.onboarding.welcome).toBeTruthy();
  await page.reload();
  await expect(page.getByText("Your first steps")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1000);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await ctx.close();

  // a new device: nothing in its browser, and still neither the question nor the tour
  const ctx2 = await make();
  const page2 = await ctx2.newPage();
  await offline(page2);
  await signedIn(ctx2, n, false);
  await page2.goto("/");
  await expect(page2.locator("main").getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await page2.waitForTimeout(1500);
  await expect(page2.getByRole("dialog")).toHaveCount(0);
  await ctx2.close();
  expect(errors).toEqual([]);
});
