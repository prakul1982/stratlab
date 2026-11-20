import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// site83 (Release 83) on the fake world, desktop and phone. Every layout-shift check holds the slow part of the page back on purpose, so it
// holds on any machine and any fonts (CI has none of this machine's): the page must keep the room, not win a race.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const ZIP = path.resolve(process.cwd(), "../backend/tests/fixtures/taxpnl/zerodha_taxpnl_2024_2025.zip");

/** An address as production serves it: the build's own page (dist/<path>/index.html), which vite preview serves only with the slash. */
async function servedAsLive(page: Page, p: string) {
  await page.route((u) => u.pathname === p, (r) => r.request().resourceType() === "document"
    ? r.fulfill({ status: 200, contentType: "text/html", body: readFileSync(new URL(`../dist${p}/index.html`, import.meta.url), "utf8") })
    : r.fallback());
}

async function signedIn(page: Page, token: string) {
  const known: Record<string, [string, string]> = { "free-token": ["u-free", "free@example.com"], "pro-token": ["u-pro", "u-pro@example.com"], "admin-token": ["u-admin", "owner@example.com"] };
  const [id, email] = known[token] ?? [`u-${token}`, `${token.replace("-", "")}@example.com`];
  const user = { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} };
  await page.addInitScript(([t, u]) => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: t, token_type: "bearer", expires_in: 3600, expires_at: 4102444800, refresh_token: "r", user: u }));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab.consent.v1", "no");
    } catch { /* none */ }
  }, [token, user] as const);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
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
const held = (page: Page, re: RegExp, ms: number) => page.route(re, async (r) => { await new Promise((ok) => setTimeout(ok, ms)); await r.fallback(); });
const box = (page: Page, sel: string) => page.locator(sel).evaluateAll((es) => es.map((e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; }));

test.use({ serviceWorkers: "block" });


// LIVE20B-009: Free's /trade/positioning: the participant table was drawn, then "Part of this page is on the Basic plan…" was inserted above it at
// 6.0 s (CLS 0.057). The page words no note of its own, so the page's note is drawn under the title from the first frame.
test("positioning on Free: the plan note is there with the title, and nothing moves when the figures come", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "measured at 1440 as live");
  await signedIn(page, "site83-12");
  await countShifts(page);
  await held(page, /\/trade\/positioning/, 2500);
  await page.goto("/trade/positioning");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main .plan-note")).toHaveCount(1, { timeout: 5000 });
  await expect(page.locator("main .plan-note")).toContainText("Part of this page is on the Basic plan");
  await page.waitForTimeout(4000);
  await expect(page.locator("main .plan-note")).toHaveCount(1);
  expect(await shifts(page), "nothing moved when the figures came").toBeLessThan(0.01);
});

// LIVE20B-007: /options at 1440: the expiry's notes came with the dates under the choices and pushed the Strategy grid down 32px (0.021). They sit
// beside the choices now, in the room held from the first frame.
test("options builder on a desktop: the expiry row holds its place while the underlyings come", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "a desktop's layout");
  await signedIn(page, "site83-2");
  await countShifts(page);
  await held(page, /\/options\/underlyings/, 2500);
  await page.goto("/options");
  await expect(page.getByTestId("opt-expiry-note")).toBeVisible({ timeout: 30_000 });
  const before = await box(page, ".k-tile-groups");
  await page.waitForTimeout(3500);
  const after = await box(page, ".k-tile-groups");
  expect(after[0]?.y, "the Strategy grid stays where it was").toBe(before[0]?.y);
  expect(await shifts(page), "nothing moved when the underlyings came").toBeLessThan(0.01);
});

// LIVE20B-005: the Free journal's lock reads "Basic adds the trade journal: …" (it said "adds trade journal")
test("trade journal on Free: the plan note names the trade journal", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "words, once");
  await signedIn(page, "site83-13");
  await page.goto("/trade/journal");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  const note = page.locator("main .plan-note").first();
  await expect(note).toBeVisible({ timeout: 15_000 });
  const t = (await note.innerText()).replace(/\s+/g, " ");
  if (/adds/.test(t)) expect(t).toMatch(/adds the trade journal/);
  expect(t).not.toMatch(/adds trade journal/);
});
