import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// site81 (Release 81) on the fake world, desktop and phone.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

/** An address as production serves it: the build's own page (dist/<path>/index.html), which vite preview serves only with the slash. */
async function servedAsLive(page: Page, path: string) {
  await page.route((u) => u.pathname === path, (r) => r.request().resourceType() === "document"
    ? r.fulfill({ status: 200, contentType: "text/html", body: readFileSync(new URL(`../dist${path}/index.html`, import.meta.url), "utf8") })
    : r.fallback());
}

async function signedIn(page: Page, token: "free-token" | "basic-token" | "pro-token", { consent = true, expired = false } = {}) {
  const ids = { "free-token": ["u-free", "free@example.com"], "basic-token": ["u-basic", "basic@example.com"], "pro-token": ["u-pro", "u-pro@example.com"] }[token];
  const user = { id: ids[0], aud: "authenticated", email: ids[1], role: "authenticated", app_metadata: {}, user_metadata: {} };
  await page.addInitScript(([t, u, c, old]) => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: t, token_type: "bearer", expires_in: 3600,
        expires_at: old ? Math.floor(Date.now() / 1000) - 8 * 3600 : 4102444800, refresh_token: "r", user: u }));
      localStorage.setItem("stratlab.tour.v1", "1");
      if (c) localStorage.setItem("stratlab.consent.v1", "no");
    } catch { /* none */ }
  }, [token, user, consent, expired] as const);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
  return user;
}

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

// LIVE18B-003 (High): a visitor's /plans showed a different, plain page for about 2 s (a 480 px column, the heading in Georgia, the links as a
// text list, prose, no buttons) before the Plans page replaced it. Its start-up frame is now the Plans page as the app first draws it.
test("visitor /plans: the start-up frame is the Plans page, and nothing moves when the app and the prices come", async ({ page }) => {
  await servedAsLive(page, "/plans");
  await countShifts(page);
  // production's offer (paid, yearly on, a dollar row, invoices without GST) after a moment, as live
  await page.route(`${API}/pricing`, async (r) => {
    const res = await r.fetch(); const j = await res.json();
    await new Promise((ok) => setTimeout(ok, 600));
    await r.fulfill({ response: res, json: { ...j, offer: { ...(j.offer ?? {}), mode: "paid", payments: true, yearly: true, promo_until: null }, invoice: { gst: false } } });
  });
  // the page's code held, so the frame is what is on screen
  let go!: () => void;
  const gate = new Promise<void>((ok) => { go = ok; });
  await page.route(/\/assets\/Login-[\w-]+\.js$/, async (r) => { await gate; await r.continue().catch(() => undefined); });
  await page.goto("/plans", { waitUntil: "commit" });
  const frame = page.locator("section.boot-plans[data-boot]");
  await expect(frame).toBeVisible({ timeout: 30_000 });
  await expect(frame.locator(".lp-price")).toHaveCount(3);
  await expect(frame.getByRole("heading", { name: "Plans and prices", level: 1 })).toBeVisible();
  const at = async () => page.evaluate(() => ["h1", ".lp-prices", '.lp-price[data-plan="free"] .lp-plan-ways'].map((s) => Math.round(document.querySelector(s)!.getBoundingClientRect().top)));
  await page.waitForTimeout(400);                 // the faces in
  const before = await at();
  expect(await page.locator("h1").evaluate((e) => getComputedStyle(e).fontFamily)).toMatch(/Fraunces/);
  go();
  await expect(page.locator("section.boot-plans")).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator('.lp-price[data-plan="basic"] .lp-amount')).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  expect(await at()).toEqual(before);
  expect(await shifts(page)).toBeLessThan(0.005);
});

// LIVE18B-008: /options with Indian data offline: the offline note came at 5.3 s above "What to trade" (phone CLS 0.093) after a 503 on
// every load. The list now answers as a list, and the note is in the page's first frame.
test("/options with the feed offline: the note is there from the first frame, and no 503", async ({ page }) => {
  await signedIn(page, "pro-token");
  await countShifts(page);
  const note = { closed: null, back_at: "2026-11-20T08:00:00+05:30" };
  await page.route(`${API}/public/data-online`, (r) => r.fulfill({ json: { data_online: false, data_note: note } }));
  await page.unroute(`${API}/me`);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true, data_online: false, data_note: note } }); });
  const asked: string[] = [];
  await page.route(/\/options\/underlyings/, async (r) => {
    asked.push(r.request().url());
    await new Promise((ok) => setTimeout(ok, 1500));
    await r.fulfill({ json: { offline: "Option quotes come from the live feed, which is offline until the daily data login completes. Indian market data comes back with the daily data login, on Fri 20 Nov at 08:00 IST.",
      rows: [{ exchange: "NFO", name: "NIFTY", venue: "NSE", lot: 75, freeze: 1800, popular: true, index: true, recorded: true, expiries: ["2026-11-24"] }] } });
  });
  await page.goto("/options");
  await expect(page.getByRole("heading", { name: "Options builder", level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Option quotes come from the live feed, which is offline/)).toBeVisible();
  expect(asked).toHaveLength(1);
  expect(asked[0]).toContain("offline=list");
  await page.waitForTimeout(2200);                // the list has answered
  expect(await shifts(page)).toBeLessThan(0.01);
});

// LIVE18B-009: /research/scan on a phone: two scan chips, then nine when the groups came, moved the group, the Scan button and the note
test("/research/scan: every scan's chip is drawn at once, and the form holds still when the groups come", async ({ page }) => {
  await signedIn(page, "pro-token");
  await countShifts(page);
  await page.route(/\/research\/scan\/sets/, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.continue(); });
  await page.goto("/research/scan");
  const chips = page.getByRole("group", { name: "Scan rule sets" }).getByRole("button");
  await expect(page.getByRole("heading", { name: "Trend scan", level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(chips).toHaveCount(9);
  await expect(page.getByTestId("scan-rule")).toContainText("Supertrend");
  await page.waitForTimeout(2000);
  await expect(chips).toHaveCount(9);
  expect(await shifts(page)).toBeLessThan(0.01);
});

// LIVE18B-010: the analytics question came beside "Opening…" (no call was out while the sign-in was renewed and the code came) and the
// page's content then pushed it down. It waits for the page now.
test("the analytics question never comes while the page is still opening", async ({ page }) => {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, {CLARITY_PROJECT_ID:"abc123def4",META_PIXEL_ID:"1234567890"});\n` });
  });
  await page.route(/clarity\.ms|facebook|fbcdn/, (r) => r.abort());
  const user = await signedIn(page, "pro-token", { consent: false, expired: true });
  // the first visit of a day: the saved sign-in has ended and the sign-in service renews it slowly
  await page.route(/demo\.supabase\.co\/auth\/v1\//, async (r) => {
    await new Promise((ok) => setTimeout(ok, 4000));
    await r.fulfill({ json: { access_token: "pro-token", token_type: "bearer", expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600, refresh_token: "r2", user } });
  });
  await page.goto("/research/IN/INFY");
  const seen = await page.evaluate(() => new Promise<string[]>((done) => {
    const out: string[] = [];
    const t0 = performance.now();
    const look = () => {
      if (document.querySelector('[data-testid="consent"]')) out.push(document.querySelector("#root .k-loading") ? "consent while opening" : "consent");
      if (performance.now() - t0 < 6000) setTimeout(look, 100); else done(out);
    };
    look();
  }));
  expect(seen).not.toContain("consent while opening");
  await expect(page.getByTestId("consent")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Infosys");
});

// LIVE18B-002: Trade's India VIX tile asked /trade/vix only once the page's code had come (9.5 s live). The page's first reads now go out
// from the start-up script, beside /me, and the page takes them.
test("/trade: the strip's reads go out with the account, before the page's code, and are taken once", async ({ page }) => {
  await signedIn(page, "pro-token");
  const order: string[] = [];
  page.on("request", (rq) => {
    const u = rq.url();
    if (/\/trade\/vix|\/trade\/positioning\?brief/.test(u)) order.push("read " + u.replace(/^.*\/trade\//, ""));
    if (/\/assets\/SpaceHomes-[\w-]+\.js$/.test(u)) order.push("page code");
  });
  await page.goto("/trade");
  await expect(page.locator('[data-tile="vix"] b')).toBeVisible({ timeout: 30_000 });
  expect(order.indexOf("read vix?brief=true")).toBeGreaterThanOrEqual(0);
  expect(order.indexOf("read vix?brief=true")).toBeLessThan(order.indexOf("page code"));
  expect(order.filter((x) => x === "read vix?brief=true")).toHaveLength(1);           // taken by the page, not asked again
});

// LIVE18B-012: the open page's item below the menu's fold ("Calendar › IPOs" under "More below" at 1440×900)
test("the menu shows the open page's own item", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the phone's menu is a drawer");
  await page.setViewportSize({ width: 1280, height: 480 });          // a short window: the item is under the fold of the menu
  await signedIn(page, "pro-token");
  await page.goto("/invest/ipos");
  const box = page.locator("nav.side-groups");
  const cur = box.locator('[aria-current="page"]');
  await expect(cur).toHaveCount(1, { timeout: 30_000 });
  await page.waitForTimeout(300);
  const [b, r] = await Promise.all([box.boundingBox(), cur.boundingBox()]);
  expect(r!.y).toBeGreaterThanOrEqual(b!.y);
  expect(r!.y + r!.height).toBeLessThanOrEqual(b!.y + b!.height + 1);
  expect(await page.evaluate(() => scrollY)).toBe(0);          // the page itself didn't move
});
