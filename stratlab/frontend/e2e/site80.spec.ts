import { readFileSync } from "node:fs";
import { expect, test, type Page, type Route } from "@playwright/test";

// site80 (Release 80) on the fake world, desktop and phone.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

async function withConfig(page: Page, extra: Record<string, string>) {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(extra)});\n` });
  });
}

/** /login as production serves it: the build's own page (dist/login/index.html), which vite preview serves only at /login/. */
async function servedAsLive(page: Page) {
  await page.route(/\/(login|signup)(\?[^#]*)?$/, (r) => r.request().resourceType() === "document"
    ? r.fulfill({ status: 200, contentType: "text/html", body: readFileSync(new URL(`../dist${new URL(r.request().url()).pathname}/index.html`, import.meta.url), "utf8") })
    : r.fallback());
}

async function signedIn(page: Page, token: "free-token" | "basic-token" | "pro-token", consent = true) {
  const ids = { "free-token": ["u-free", "free@example.com"], "basic-token": ["u-basic", "basic@example.com"], "pro-token": ["u-pro", "u-pro@example.com"] }[token];
  await page.addInitScript(([t, id, email, c]) => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: t, token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r",
        user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } }));
      localStorage.setItem("stratlab.tour.v1", "1");
      if (c) localStorage.setItem("stratlab.consent.v1", "no");
    } catch { /* none */ }
  }, [token, ids[0], ids[1], consent] as const);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
}

/** The page's layout shift, counted from the first paint (a `window.__moves` total). */
async function countShifts(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __moves: number };
    w.__moves = 0;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) w.__moves += e.value;
    }).observe({ type: "layout-shift", buffered: true });
  });
}
const shifts = (page: Page) => page.evaluate(() => (window as unknown as { __moves: number }).__moves);

test.use({ serviceWorkers: "block" });

// LIVE17B-001 (live, 19 Nov): the frame's two buttons were drawn grey (disabled) until 3.6 s while their script came in late behind the app's
// chunks. The script is now read from the head, first; while it is on its way the buttons look as they will, with a working cursor.
test("/login: the frame's buttons look as they will while their script is on its way, and are pressable once it runs", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  await servedAsLive(page);
  let early!: () => void;
  const gate = new Promise<void>((ok) => { early = ok; });
  await page.route(/\/signin-early\.js(\?|$)/, async (r) => { await gate; await r.continue().catch(() => undefined); });
  await page.goto("/login", { waitUntil: "commit" });
  const google = page.getByRole("button", { name: "Continue with Google" });
  const email = page.getByRole("button", { name: "Email me a code" });
  await expect(google).toBeDisabled({ timeout: 30_000 });
  const look = (b: typeof google) => b.evaluate((e) => { const c = getComputedStyle(e); return { bg: c.backgroundColor, color: c.color, opacity: c.opacity, cursor: c.cursor }; });
  const waiting = { google: await look(google), email: await look(email) };
  expect(waiting.google.cursor).toBe("progress");
  expect(waiting.email.cursor).toBe("progress");
  expect(waiting.email.opacity).toBe("1");
  early();
  await expect(google).toBeEnabled();
  await expect(email).toBeEnabled();
  const ready = { google: await look(google), email: await look(email) };
  // the same fill and words' colour as the pressable button: never the grey of one that can't be pressed
  expect(waiting.google.bg).toBe(ready.google.bg);
  expect(waiting.google.color).toBe(ready.google.color);
  expect(waiting.email.bg).toBe(ready.email.bg);
  // the script is in the head, before the app's module, so it runs first
  const order = await page.evaluate(() => [...document.querySelectorAll("script[src]")].map((s) => s.getAttribute("src") ?? ""));
  expect(order.findIndex((s) => s.includes("signin-early"))).toBeLessThan(order.findIndex((s) => s.startsWith("/assets/")));
});

// LIVE17B-002: after a plan card's "Sign in with email" the sign-in page was drawn for 0.3-0.45 s without its email form, and on a phone at
// /plans' scroll position (its footer) before it jumped. The sign-in page now opens with its form, at the form, from its first frame.
test("a plan card's email button opens the sign-in page with its form in place from the first frame, without a jump", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  await page.route(`${API}/pricing`, async (r: Route) => {
    const res = await r.fetch(); const j = await res.json();
    await r.fulfill({ response: res, json: { ...j, offer: { ...(j.offer ?? {}), mode: "paid", payments: true } } });
  });
  await page.goto("/plans");
  const way = page.locator('.lp-price[data-plan="basic"]').getByTestId("email-way");
  await expect(way).toBeVisible({ timeout: 30_000 });
  await way.scrollIntoViewIfNeeded();
  await page.evaluate(() => {
    const w = window as unknown as { __frames: [string, boolean, number][] };
    w.__frames = [];
    const t0 = performance.now();
    const look = () => {
      w.__frames.push([location.pathname, !!document.querySelector(".email-signin-form input[type=email]"), Math.round(scrollY)]);
      if (performance.now() - t0 < 2500) requestAnimationFrame(look);
    };
    requestAnimationFrame(look);
  });
  await way.click();
  await expect(page).toHaveURL(/\/login\?plan=basic#email$/);
  await expect(page.getByLabel("Sign in with email")).toBeFocused({ timeout: 30_000 });
  await page.waitForTimeout(2600);
  const frames = await page.evaluate(() => (window as unknown as { __frames: [string, boolean, number][] }).__frames);
  const login = frames.filter(([p]) => p === "/login");
  expect(login.length).toBeGreaterThan(5);
  expect(login.every(([, form]) => form), "every frame of the sign-in page has its email form").toBe(true);
  const ys = new Set(login.map(([, , y]) => y));
  expect(ys.size, `one scroll position on the sign-in page (${[...ys].join(", ")})`).toBe(1);
});

// LIVE17A-010: the US Movers list on a phone moved 88 px down when the "Stocks" field's names arrived (CLS 0.062)
test("Movers on a phone: the settings hold their rows when the lists arrive", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone's one-column settings");
  await signedIn(page, "basic-token");
  await countShifts(page);
  await page.goto("/invest/movers?market=US");
  await expect(page.getByTestId("mv-facts")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  expect(await shifts(page)).toBeLessThan(0.01);
});

// LIVE15B-012 / LIVE17B: the visitor's /plans on a phone: Free's price placeholder was a line taller than its price, so its card shrank and
// pulled the cards under it up when the prices came
test("visitor /plans: the cards hold still when the prices arrive", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone's stacked cards");
  await countShifts(page);
  await page.route(`${API}/pricing`, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.continue(); });
  await page.goto("/plans");
  await expect(page.locator('.lp-price[data-plan="free"] .lp-amount')).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  expect(await shifts(page)).toBeLessThan(0.005);
});

// LIVE17B-005: Money home on a phone: "My" / "Holdings" and "Tax," / "FY 2026-27" broke beside their links
test("Money home on a phone: each card's title is one line, its link under it", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone's card heads");
  await signedIn(page, "free-token");
  await page.goto("/money");
  for (const name of [/^My Holdings$/, /^Tax, FY \d{4}-\d{2}$/]) {
    const h = page.getByRole("heading", { name });
    await expect(h).toBeVisible({ timeout: 30_000 });
    const lines = await h.evaluate((e) => { const r = document.createRange(); r.selectNodeContents(e); return new Set([...r.getClientRects()].map((x) => Math.round(x.top))).size; });
    expect(lines, `${name} on one line`).toBe(1);
  }
  const link = await page.locator('[data-money="/holdings"]').boundingBox();
  const head = await page.getByRole("heading", { name: /^My Holdings$/ }).boundingBox();
  expect(link!.y).toBeGreaterThan(head!.y + head!.height - 2);
});

// LIVE17B-007: /trade/positioning on a phone: "59.2% / 40.8%" past the participant card's edge, and switches of two widths
test("Positioning on a phone: the long/short shares stay inside their cards and the head's controls are one width", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone's two-across participant cards");
  await signedIn(page, "pro-token");
  await page.goto("/trade/positioning");
  // the long/short shares are the participant table's extra column ("More columns", as the reviewer had it open)
  await page.locator("#pos-part").getByRole("button", { name: /^More columns/ }).click({ timeout: 30_000 });
  await expect(page.locator(".pos-split").first()).toBeVisible({ timeout: 30_000 });
  const out = await page.evaluate(() => [...document.querySelectorAll(".pos-split")].filter((s) => {
    let c = s.parentElement;
    while (c && !/\b(k-card|k-tbl-card|k-stack-card)\b/.test(c.className) && c.tagName !== "TR" && c.tagName !== "LI") c = c.parentElement;
    const box = (c ?? document.body).getBoundingClientRect(), r = s.getBoundingClientRect();
    return r.right > box.right + 0.5 || r.right > window.innerWidth;
  }).length);
  expect(out).toBe(0);
  const widths = await page.locator("#pos-part > .k-card-head > .k-card-actions > *").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
  expect(new Set(widths).size, `one width (${widths.join(", ")})`).toBe(1);
});

// LIVE17B-003: the company page's chart candles were asked for only after the page's own data and the chart's code had arrived
test("a company page asks for its chart's candles beside its first call", async ({ page }) => {
  await signedIn(page, "pro-token");
  const asked: string[] = [];
  page.on("request", (r) => { const u = r.url(); if (/\/research\/(chart|company)\//.test(u)) asked.push(u.replace(/^.*\/research\//, "")); });
  let release!: () => void;
  const held = new Promise<void>((ok) => { release = ok; });
  await page.route(/\/research\/company\/IN\/TCS\?lean/, async (r) => { await held; await r.continue(); });
  await page.goto("/research/IN/TCS");
  await expect.poll(() => asked.some((u) => u.startsWith("chart/IN/TCS?tf=1d&range=1y")), { timeout: 30_000 }).toBe(true);
  expect(asked.some((u) => u.startsWith("company/IN/TCS/more")), "the page's own answer is still held").toBe(false);
  release();
  await expect(page.locator(".pc-status")).toHaveCount(0, { timeout: 30_000 });
  // one read of the candles: the chart took the one already asked for
  expect(asked.filter((u) => u.startsWith("chart/IN/TCS?tf=1d&range=1y") && !u.includes("before=")).length).toBe(1);
});

// LIVE16B-005: on a phone the analytics question came in while the company page was still filling, and moved with it (CLS 0.088)
test("the analytics question waits until the page's calls are back", async ({ page }) => {
  await withConfig(page, { CLARITY_PROJECT_ID: "abc123def4", META_PIXEL_ID: "1234567890" });
  await signedIn(page, "pro-token", false);
  let release!: () => void;
  const held = new Promise<void>((ok) => { release = ok; });
  // the chart's candles slow (live: 9.5-11.3 s), past the shell's 6 s cap on waiting for the page's calls, after which the question came in
  await page.route(/\/research\/chart\/IN\/TCS\?tf=1d&range=1y$/, async (r) => { await held; await r.continue(); });
  await page.goto("/research/IN/TCS");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(8500);
  await expect(page.getByTestId("consent")).toHaveCount(0);
  release();
  await expect(page.getByTestId("consent")).toBeVisible({ timeout: 10_000 });
});

// LIVE17A-001: prices found off the day's settled closes are never labelled closes
test("Movers: a stored day found off its settled closes says its prices were read in the session", async ({ page }) => {
  await signedIn(page, "basic-token");
  await page.route(new RegExp(`${API.replace(/[.:/]/g, "\\$&")}/invest/movers\\?`), async (r) => {
    const res = await r.fetch(); const j = await res.json();
    await r.fulfill({ response: res, json: { ...j, unsettled: true, live: null } });
  });
  await page.goto("/invest/movers");
  const day = page.getByTestId("mv-day");
  await expect(day).toBeVisible({ timeout: 30_000 });
  await expect(day).toContainText("Prices read during the session of");
  await expect(day).not.toContainText("Closes of");
});
