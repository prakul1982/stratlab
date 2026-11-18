import { expect, test, type Page } from "@playwright/test";

// fix14: LIVE11B findings proved on the pages as drawn, on the desktop and phone projects.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const session = { access_token: "pro-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-pro", aud: "authenticated", email: "pro@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const note = { closed: null, back_at: "2026-10-29T08:00:00+05:30" };

async function withConfig(page: Page, extra: Record<string, string>) {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(extra)});\n` });
  });
}

/** Indian data offline overnight, said by the public data status at once and by /me 1.5 s later (as on the live site). At the moment the
 * page's heading is first drawn, the line must already be there; the heading must not move after; the layout shift is measured. */
async function offlineFirstFrame(page: Page, path: string): Promise<{ bannerAtFirst: number; moved: number; cls: number; sources: string[] }> {
  await page.route(`${API}/public/data-online`, (r) => r.fulfill({ status: 200, json: { data_online: false, data_note: note } }));
  await page.route(`${API}/me`, async (r) => {
    await new Promise((ok) => setTimeout(ok, 1500));
    const res = await r.fetch();
    return r.fulfill({ response: res, json: { ...(await res.json()), data_online: false, data_note: note } });
  });
  await page.addInitScript((s) => {
    try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ }
    const w = window as unknown as { __cls: number; __src: string[]; __first: { banner: number; y: number } | null };
    w.__cls = 0; w.__src = []; w.__first = null;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Node }[] }[]) {
        if (e.hadRecentInput) continue;
        w.__cls += e.value;
        for (const x of e.sources ?? []) { const el = x.node as HTMLElement | undefined; w.__src.push(`${e.value.toFixed(3)} ${el?.tagName ?? "?"}.${String(el?.className ?? "").slice(0, 40)}`); }
      }
    }).observe({ type: "layout-shift", buffered: true });
    // the first frame with the page's own heading: is the line there, and where is the heading
    const look = () => {
      const h = document.querySelector("#main .page h1:not(.sr-only)");
      if (h && !w.__first) w.__first = { banner: document.querySelectorAll(".data-banner").length, y: h.getBoundingClientRect().top + window.scrollY };
      if (!w.__first) requestAnimationFrame(look);
    };
    requestAnimationFrame(look);
  }, session);
  await page.goto(path);
  await expect(page.locator(".data-banner")).toContainText("Indian price data reconnects on", { timeout: 30_000 });
  await page.waitForTimeout(4000);
  return page.evaluate(() => {
    const w = window as unknown as { __cls: number; __src: string[]; __first: { banner: number; y: number } | null };
    const h = document.querySelector("#main .page h1:not(.sr-only)");
    const y = h ? h.getBoundingClientRect().top + window.scrollY : -1;
    return { bannerAtFirst: w.__first?.banner ?? -1, moved: Math.abs(y - (w.__first?.y ?? -999)), cls: w.__cls, sources: w.__src };
  });
}

// LIVE11B-004: the overnight "Indian price data reconnects…" line came with /me, 1-1.4 s after the page, and pushed it down (/new 0.294,
// phone 0.11-0.16 on /mine, /trade, /options)
test("the overnight data line is drawn with the page, never pushed in over it (LIVE11B-004)", async ({ page }) => {
  test.setTimeout(150_000);
  for (const path of ["/new", "/mine", "/trade"]) {
    const got = await offlineFirstFrame(page, path);
    console.log(`${path}: line in the first frame ${got.bannerAtFirst}, heading moved ${got.moved.toFixed(1)}px, CLS ${got.cls.toFixed(3)}\n  ${got.sources.slice(0, 6).join("\n  ")}`);
    expect(got.bannerAtFirst, `${path}: the line is in the frame the heading first shows in`).toBe(1);
    expect(got.moved, `${path}: the heading stays where it was first drawn`).toBeLessThan(1);
    if (path === "/new") expect(got.cls, got.sources.join("\n")).toBeLessThan(0.05);
    await page.unrouteAll({ behavior: "ignoreErrors" });
  }
});

// LIVE11B-002: the signed-out view of an app page had its own narrower header, a footer without the logo or disclaimer, and Google-only words
test("a signed-out app page is drawn in /login's frame and names both ways in with email on (LIVE11B-002)", async ({ page }) => {
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  await page.goto("/holdings");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Sign in to see Holdings", { timeout: 30_000 });
  await expect(page.locator("header.lp-nav")).toHaveCount(1);
  await expect(page.locator("header.pub-nav")).toHaveCount(0);
  await expect(page.locator("section.lp-hero.ruled")).toHaveCount(1);
  await expect(page.locator("footer.lp-foot")).toContainText("Research and paper trading only. No real orders are placed.");
  await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
  await expect(page.getByTestId("email-signin")).toBeVisible();
  await expect(page.locator("main")).toContainText("Signing in only reads your name and email from Google, or only your email address by email.");
  // the same header box as /login's
  const gate = (await page.locator("header.lp-nav").boundingBox())!;
  await page.goto("/login");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  // R73: the start-up frame shows a heading before the app draws, so wait for /login's own header before measuring it
  await expect(page.locator("header.lp-nav")).toBeVisible({ timeout: 30_000 });
  const login = (await page.locator("header.lp-nav").boundingBox())!;
  expect(Math.abs(gate.height - login.height)).toBeLessThan(2);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll).toBeLessThanOrEqual(width + 1);
});

// LIVE11B-015: the briefs list came 6.9 s after the page and moved it (CLS 0.213)
test("the briefs page holds still while a slow list arrives (LIVE11B-015)", async ({ page }) => {
  test.setTimeout(120_000);
  await page.route(new RegExp(`${API.replace(/[.]/g, "\\.")}/news\\?`), async (r) => { await new Promise((ok) => setTimeout(ok, 3500)); return r.fallback(); });
  await page.addInitScript((s) => {
    try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ }
    const w = window as unknown as { __cls: number; __moved: string[] };
    w.__cls = 0; w.__moved = [];
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Node }[] }[]) {
        if (e.hadRecentInput) continue;
        w.__cls += e.value;
        for (const src of e.sources ?? []) { const el = src.node as HTMLElement | undefined; w.__moved.push(`${e.value.toFixed(3)} ${el?.tagName ?? "?"}.${String(el?.className ?? "").slice(0, 40)}`); }
      }
    }).observe({ type: "layout-shift", buffered: true });
  }, session);
  await page.goto("/news");
  await expect(page.locator(".news-pick").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2500);
  const { cls, moved } = await page.evaluate(() => { const w = window as unknown as { __cls: number; __moved: string[] }; return { cls: w.__cls, moved: w.__moved }; });
  console.log(`CLS /news: ${cls.toFixed(3)}\n  ${moved.slice(0, 8).join("\n  ")}`);
  expect(cls, moved.join("\n")).toBeLessThan(0.1);
});
