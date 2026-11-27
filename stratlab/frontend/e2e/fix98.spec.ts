import { expect, test, type Page, type Route } from "@playwright/test";

// fix98 on the fake world, desktop and phone: the sign-in page opened from a plan card's email button on a slow device.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

async function withConfig(page: Page, extra: Record<string, string>) {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(extra)});\n` });
  });
}

const frames = (page: Page) => page.evaluate(() => {
  const w = window as unknown as { __frames: [string, boolean, number][] };
  w.__frames = [];
  const t0 = performance.now();
  const look = () => {
    w.__frames.push([location.pathname, !!document.querySelector(".email-signin-form input[type=email]"), Math.round(scrollY)]);
    if (performance.now() - t0 < 6000) requestAnimationFrame(look);
  };
  requestAnimationFrame(look);
});

// CI's site80 on a phone (flaky): the press waited at most 1.5 s for the form's code, then opened /login anyway, a frame without the form.
// The form's code is held back 3 s here (longer than that cap): the button waits (no busy state: the landing page's code budget,
// review-r5 R5V-020; changed on purpose, fix98 in Release 98), and the sign-in page, when it opens, has its
// form from its first frame, at one scroll position.
test("a plan card's email button on a slow device: waits until the form's code is here, then the sign-in page with its form in every frame", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  await page.route(`${API}/pricing`, async (r: Route) => {
    const res = await r.fetch(); const j = await res.json();
    await r.fulfill({ response: res, json: { ...j, offer: { ...(j.offer ?? {}), mode: "paid", payments: true } } });
  });
  await page.route(/\/assets\/EmailSignIn-[^/]*\.js$/, async (r) => { await new Promise((ok) => setTimeout(ok, 3000)); await r.fallback(); });
  await page.goto("/plans");
  const way = page.locator('.lp-price[data-plan="basic"]').getByTestId("email-way");
  await expect(way).toBeVisible({ timeout: 30_000 });
  await way.scrollIntoViewIfNeeded();
  await frames(page);
  await way.click();
  expect(new URL(page.url()).pathname).toBe("/plans");                    // still here while the form's code comes
  await expect(page).toHaveURL(/\/login\?plan=basic#email$/, { timeout: 30_000 });
  await expect(page.getByLabel("Sign in with email")).toBeFocused({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  const got = await page.evaluate(() => (window as unknown as { __frames: [string, boolean, number][] }).__frames);
  const login = got.filter(([p]) => p === "/login");
  expect(login.length).toBeGreaterThan(5);
  expect(login.every(([, form]) => form), "every frame of the sign-in page has its email form").toBe(true);
  const ys = new Set(login.map(([, , y]) => y));
  expect(ys.size, `one scroll position on the sign-in page (${[...ys].join(", ")})`).toBe(1);
});

// a cold /login#email whose form's code is slow: the page waits for it as a whole, never drawn with an empty band where the form goes
test("a cold /login#email with a slow form: the sign-in page is never drawn without its form", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  await page.route(/\/assets\/EmailSignIn-[^/]*\.js$/, async (r) => { await new Promise((ok) => setTimeout(ok, 2500)); await r.fallback(); });
  await page.addInitScript(() => {
    const w = window as unknown as { __bad: number };
    w.__bad = 0;
    const look = () => {
      // the app's own sign-in panel (not the start-up frame's held words) drawn with the placeholder where the form goes
      if (document.querySelector("#root .lp-hero-login .email-slot")) w.__bad += 1;
      if (performance.now() < 15000) requestAnimationFrame(look);
    };
    requestAnimationFrame(look);
  });
  await page.goto("/login#email");
  await expect(page.getByLabel("Sign in with email")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => (window as unknown as { __bad: number }).__bad), "frames with the empty band").toBe(0);
});
