import { expect, test, type Page } from "@playwright/test";

// Lane site76: the LIVE14A / LIVE14B site findings on the fake world.
const THEME_URL = "/research/themes?region=IN&q=" + encodeURIComponent("India steel and mining");

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function signedIn(page: Page, n: number, url: string) {
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(url);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => { await welcome.getByRole("button", { name: /^All of it/ }).click(); return true; }).catch(() => false);
  if (answered) await page.goto(url);
}

test("LIVE14A-008: the sortable 'Every company' table fits its card at 1280 and 1440, its sort buttons on one line", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a phone reads the table as cards");
  for (const width of [1440, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await signedIn(page, width === 1280 ? 287 : 286, THEME_URL);
    await expect(page.getByRole("heading", { name: "The whole chain in one table" })).toBeVisible({ timeout: 90_000 });
    const box = page.locator("#numbers-leaders .k-tbl-wrap").first();
    await box.scrollIntoViewIfNeeded();
    const m = await box.evaluate((el) => {
      const t = el.querySelector("table") as HTMLElement;
      const heads = [...el.querySelectorAll("thead .k-th-sort")].map((b) => ({ text: (b as HTMLElement).innerText, h: (b as HTMLElement).getBoundingClientRect().height,
        w: Math.round((b.closest("th") as HTMLElement).getBoundingClientRect().width) }));
      const was = t.style.width;
      t.style.width = "min-content";
      const natural = Math.round(t.getBoundingClientRect().width);
      t.style.width = was;
      return { scroll: el.scrollWidth, client: el.clientWidth, table: t.getBoundingClientRect().width, natural, heads };
    });
    expect(m.natural, `room left for longer names and figures at ${width}`).toBeLessThanOrEqual(m.client * 0.88);
    expect(m.scroll, `the table scrolls sideways at ${width}`).toBeLessThanOrEqual(m.client + 1);
    for (const h of m.heads) expect(h.h, `"${h.text}" wraps at ${width}`).toBeLessThan(30);
  }
});

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const TRADEBOOKS = new URL("../../backend/tests/fixtures/tradebooks/", import.meta.url).pathname;

test("LIVE14B-008: on a phone the tax report's figure and price pill come in without moving the upload card", async ({ page, request }, info) => {
  test.skip(info.project.name !== "phone", "the shift was measured on a phone");
  const n = 283;
  const auth = { Authorization: `Bearer load-${n}` };
  await request.delete(`${API}/tax`, { headers: auth });
  const { readFileSync } = await import("node:fs");
  const up = await request.post(`${API}/tax/import?filename=zerodha_console_tradebook.csv&mode=replace`, { headers: { ...auth, "Content-Type": "text/csv" },
    data: readFileSync(TRADEBOOKS + "zerodha_console_tradebook.csv") });
  expect(up.ok(), `${up.status()} ${await up.text()}`).toBeTruthy();
  await page.addInitScript(() => {
    const w = window as unknown as { __cls: number };
    w.__cls = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { hadRecentInput: boolean; value: number }[]) if (!e.hadRecentInput) w.__cls += e.value; })
      .observe({ type: "layout-shift", buffered: true });
  });
  // the report answers 2.5 s late, as on the live site, after the page has drawn its upload card
  await page.route("**/tax", async (r) => { if (r.request().method() !== "GET") return r.fallback(); await new Promise((ok) => setTimeout(ok, 2500)); return r.fallback(); });
  await signedIn(page, n, "/tax-report");                // answers the first-visit question; the place is held by default on this first visit
  await expect(page.locator('[aria-label="Total tax estimate"]').first()).toBeVisible({ timeout: 30_000 });
  for (const visit of [1, 2]) {                          // then twice more, from what the visit before kept
    await page.goto("/tax-report");
    await expect(page.getByRole("heading", { name: "Upload your trades" })).toBeVisible();
    const held = await page.evaluate(() => document.querySelector(".tax-head-hold")?.getBoundingClientRect().height ?? 0);
    expect(held, "the year's tax has its place while the report loads").toBeGreaterThan(40);
    await expect(page.locator('[aria-label="Total tax estimate"]').first()).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(800);
    const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
    expect(cls, `layout shift on visit ${visit}`).toBeLessThan(0.05);
  }
  await request.delete(`${API}/tax`, { headers: auth });
});

test("LIVE14B-007: a visitor's /plans has the sample deck link its table promises", async ({ page }) => {
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.goto("/plans");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const line = page.getByTestId("sample-deck-line");
  await expect(line).toContainText("Slide decks are on Basic and Pro.");
  const info = await page.request.get(`${API}/pricing/sample-deck/info`).then((r) => r.json());
  if (info.available) await expect(line.getByTestId("sample-deck")).toHaveAttribute("href", /\/pricing\/sample-deck/);
});

for (const narrow of [false, true]) test(`LIVE14A-014 / LIVE14B-003: the landing's start-up hero is its largest paint: the app's drawn hero adds no later LCP, and nothing shifts${narrow ? " (360 px)" : ""}`, async ({ page }, info) => {
  test.skip(narrow && info.project.name !== "phone", "the narrow phone");
  if (narrow) await page.setViewportSize({ width: 360, height: 760 });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    // the faces arrive after the first paint, as on the live site (the frame's heading was painted first in the stand-in serif there)
    if (r.request().url().endsWith(".woff2")) return new Promise((ok) => setTimeout(ok, 1500)).then(() => r.fallback());
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 });
  await page.addInitScript(() => {
    const w = window as unknown as { __lcp: { t: number; size: number; boot: boolean }[]; __cls: number };
    w.__lcp = []; w.__cls = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { startTime: number; size: number; element?: Element }[]) w.__lcp.push({ t: e.startTime, size: e.size, boot: !!e.element?.closest("[data-boot]") }); })
      .observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { hadRecentInput: boolean; value: number }[]) if (!e.hadRecentInput) w.__cls += e.value; })
      .observe({ type: "layout-shift", buffered: true });
  });
  await page.goto("/");
  await expect(page.locator("main h1")).toBeVisible();
  await page.waitForTimeout(6000);
  const { lcp, cls } = await page.evaluate(() => { const w = window as unknown as { __lcp: { t: number; size: number; boot: boolean }[]; __cls: number }; return { lcp: w.__lcp, cls: w.__cls }; });
  const last = lcp[lcp.length - 1];
  expect(last.boot, `the largest paint is the start-up frame's, not the app's drawn hero: ${JSON.stringify(lcp)}`).toBe(true);
  expect(last.size, "the frame's heading or lede, at its final size").toBeGreaterThan(20000);
  expect(cls, "nothing on the landing moves").toBeLessThan(0.01);
});

// LIVE14B-001: the first signed-in page of a browser (live: /mine heading at 7.9 s, /trade/journal 9.3 s). Measured here, the fake world on
// a throttled link (150 ms, 1.6 Mbit/s): before, /me was asked for at ~2.9 s, once a file of the app's code had come behind ~40 others
// (1.15 s on a 100 ms, 20 Mbit/s link); now at ~0.4 s (0.25 s), when /config.js has run. (Asking for the page's own file beside the app's
// was tried and measured slower on the throttled link, 3.7 s against 3.2 s for the heading: it shared the bandwidth, so it is not done.)
for (const [path, file] of [["/mine", "MineHome"], ["/trade/journal", "JournalPage"]] as const) test(`LIVE14B-001: ${path} opened in a new browser asks for the account at the start`, async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one size is enough");
  const route = async (p: Page) => p.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const n = 281;
  await route(page);
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto("/mine");                   // the first-visit question answered once, outside the measured load
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  await welcome.waitFor({ timeout: 6000 }).then(() => welcome.getByRole("button", { name: /^All of it/ }).click()).catch(() => undefined);
  const ctx = await page.context().browser()!.newContext({ viewport: { width: 1440, height: 900 } });      // a cold browser: nothing cached
  const p = await ctx.newPage();
  await route(p);
  // the live server's /me takes its time and a preflight round trip from a browser far from it (0.3-1.4 s in its logs); here 800 ms
  await p.route(/:\d+\/me$/, async (r) => { if (r.request().method() === "GET") await new Promise((ok) => setTimeout(ok, Number(process.env.ME_DELAY ?? 800))); return r.fallback(); });
  await p.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  const cdp = await ctx.newCDPSession(p);
  await cdp.send("Network.enable");
  const fast = process.env.PROBE_FAST === "1";
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: fast ? 100 : 150, downloadThroughput: (fast ? 20 : 1.6) * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 });
  const t0 = Date.now();
  const asked: Record<string, number> = {}, done: Record<string, number> = {};
  const name = (u: string) => (new URL(u).pathname.match(/^\/assets\/([A-Za-z]+)-[\w-]{8}\.js$/)?.[1] ?? new URL(u).pathname);
  p.on("request", (q) => { asked[name(q.url())] ??= Date.now() - t0; });
  p.on("requestfinished", (q) => { done[name(q.url())] ??= Date.now() - t0; });
  await p.goto(path);
  await p.locator("main h1").first().waitFor({ timeout: 60_000 });
  const h1 = Date.now() - t0;
  await ctx.close();
  info.annotations.push({ type: "timing", description: `${path}: /me asked ${asked["/me"]} ms, ${file} asked ${asked[file]} ms, main done ${done.main} ms, h1 ${h1} ms` });
  expect(asked["/me"], "the account is asked for before the app's code has arrived").toBeLessThan(done.main);
});
