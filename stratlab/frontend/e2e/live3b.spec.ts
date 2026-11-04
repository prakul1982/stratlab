import { expect, test, type Page } from "@playwright/test";

// LIVE3 (live review of production, Wed 4 Nov), the FIXB lane. Each test sets its own width, so it is the same on the desktop and
// phone projects; signed-in tests only read.
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const ADMIN = session("admin-token", "u-admin", "owner@example.com");
const TRACK = { META_PIXEL_ID: "1234567890", CLARITY_PROJECT_ID: "abc123def4" };

async function open(page: Page, path: string, s: object | null, width: number, o: { track?: boolean; tour?: boolean; height?: number } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width, height: o.height ?? 860 });
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  if (o.track) await page.route(/\/config\.js(\?|$)/, async (r) => { const real = await (await r.fetch()).text(); await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(TRACK)});\n` }); });
  await page.addInitScript(([x, tour]) => { if (x) localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); if (!tour) localStorage.setItem("stratlab.tour.v1", "1"); }, [s, !!o.tour] as const);
  await page.goto(path);
  return errors;
}

test.use({ serviceWorkers: "block" });          // each visit reads the config.js the test gives, never one a service worker kept
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

// LIVE3-010 / 023: on a phone the analytics question stood over a company page's main buttons, Invest's shortcut cards and a
// result's headline figures (about 190px of an 860px screen). Now, on every page that asks it, signed in or out, it is a slim bar
// along the window's foot: one sentence, "What this means" and the two answers on one row; wide screens keep the full wording.
test("the analytics question is a slim bar on a phone on every page that asks it, the full card on a wide screen (LIVE3-010)", async ({ page }) => {
  const pages: [string, object | null][] = [["/", null], ["/library", null], ["/pricing", null], ["/research/IN/RELIANCE", ADMIN], ["/invest", ADMIN], ["/library/seed-supertrend-us", ADMIN]];
  for (const [path, who] of pages) {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await page.context().clearCookies();
    await open(page, path, who, 390, { track: true });
    const ask = page.getByTestId("consent");
    await expect(ask, path).toBeVisible({ timeout: 30_000 });
    const box = (await ask.boundingBox())!;
    expect(box.height, `${path}: the bar's height`).toBeLessThanOrEqual(112);
    expect(Math.round(box.y + box.height), `${path}: along the window's foot`).toBe(860);
    await expect(ask.locator(".consent-short"), path).toBeVisible();
    await expect(ask.locator(".consent-long"), path).toBeHidden();
    await expect(ask.getByRole("link", { name: "What this means" }), path).toBeVisible();
    // both answers on the row with the link, one width
    const ys = await ask.locator(".consent-btns > *").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2)));
    expect(Math.max(...ys) - Math.min(...ys), `${path}: one row ${ys}`).toBeLessThanOrEqual(4);
    await page.evaluate(() => localStorage.clear());
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  const ask = page.getByTestId("consent");
  await page.reload();
  await expect(ask).toBeVisible({ timeout: 30_000 });
  await expect(ask.locator(".consent-long")).toBeVisible();
  await expect(ask).toContainText("all text hidden");
  await expect(ask.locator(".consent-short")).toBeHidden();
});

// LIVE3-012: /library moved by 0.75 (CLS) when its list replaced the placeholder (the page widened 92px and its note dropped out of
// view), the policies by 0.14 ("Loading…" swapped for the text), Pulse by 0.29 and Screens by 0.23 on a phone (an as-of line
// arriving, a short index placeholder, a 70vh filter placeholder that folded). Each page the review measured, and the busiest
// public and signed-in pages beside them, stays under 0.1 (Google's "good") from the first frame to six seconds later.
const SHIFT_PAGES: [string, boolean, number][] = [
  ["/library", false, 1440], ["/library", false, 390], ["/privacy", false, 1440], ["/terms", false, 1440], ["/privacy", false, 390], ["/", false, 1440],
  ["/library", true, 1440], ["/research/pulse", true, 390], ["/research/pulse", true, 1440], ["/research/screens", true, 390], ["/research/screens", true, 1440],
  ["/tour", true, 390], ["/trade", true, 1440], ["/research", true, 390],
];
test("pages hold still while they load: layout shift under 0.1 on every page the review measured, phone and desktop (LIVE3-012)", async ({ page }) => {
  test.setTimeout(400_000);
  const over: string[] = [];
  for (const [path, signed, w] of SHIFT_PAGES) {
    const p = await page.context().newPage();
    await p.setViewportSize({ width: w, height: w < 500 ? 844 : 900 });
    await p.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
    await p.addInitScript(([s, on]) => {
      try { localStorage.clear(); localStorage.setItem("stratlab.tour.v1", "1"); if (on) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); } catch { /* none */ }
      const w = window as unknown as { __shift: { v: number; n: string[] }[] };
      w.__shift = [];
      new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Element; previousRect: DOMRect; currentRect: DOMRect }[] }[]) if (!e.hadRecentInput) w.__shift.push({ v: e.value, n: (e.sources ?? []).map((x) => `${(x.node as Element | undefined)?.className ?? x.node?.nodeName} ${Math.round(x.previousRect.y)}->${Math.round(x.currentRect.y)}`) }); }).observe({ type: "layout-shift", buffered: true });
    }, [ADMIN, signed] as const);
    await p.goto(path);
    await p.waitForTimeout(6000);
    const shifts = await p.evaluate(() => (window as unknown as { __shift: { v: number; n: string[] }[] }).__shift);
    const cls = shifts.reduce((a, x) => a + x.v, 0);
    if (cls >= 0.1) over.push(`${path} ${w}${signed ? " signed in" : ""}: ${cls.toFixed(3)} ${JSON.stringify(shifts.filter((x) => x.v > 0.005))}`);
    await p.unrouteAll({ behavior: "ignoreErrors" });
    await p.close();
  }
  expect(over, over.join("\n")).toEqual([]);
});

// LIVE3-014: on a phone the tour's first step ("Four spaces") ringed a thin strip half under its own note: the four spaces are in the
// menu, which the step opens. Every step that points into the menu rings the real thing, whole, on screen and clear of the note.
test("the phone tour's menu steps ring the thing they describe, on screen and clear of the note (LIVE3-014)", async ({ page }) => {
  await open(page, "/tour", ADMIN, 390, { tour: true, height: 844 });
  const note = page.locator(".k-coach-note");
  const ring = page.locator(".k-coach-ring");
  const rect = (sel: string) => page.locator(sel).first().evaluate((e) => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  const steps: [string, string][] = [["Four spaces", ".sidebar .space-switch"], ["Ask or do anything", ".topbar [aria-label='Search or ask anything']"]];
  for (const [title, sel] of steps) {
    await expect(note.getByRole("heading", { name: title })).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(600);           // the drawer's slide and the ring's move
    const t = await rect(sel), r = await rect(".k-coach-ring"), n = await rect(".k-coach-note");
    await expect(ring).not.toHaveAttribute("data-off", /./);
    expect(t.y >= 0 && t.y + t.h <= 844 && t.x >= 0 && t.x + t.w <= 390, `${title}: the thing is on screen ${JSON.stringify(t)}`).toBe(true);
    expect(Math.abs(r.x - (t.x - 4)) <= 3 && Math.abs(r.y - (t.y - 4)) <= 3 && Math.abs(r.w - (t.w + 8)) <= 3 && Math.abs(r.h - (t.h + 8)) <= 3, `${title}: the ring ${JSON.stringify(r)} is round the thing ${JSON.stringify(t)}`).toBe(true);
    const overlap = !(n.x >= t.x + t.w || n.x + n.w <= t.x || n.y >= t.y + t.h || n.y + n.h <= t.y);
    expect(overlap, `${title}: the note ${JSON.stringify(n)} covers the thing ${JSON.stringify(t)}`).toBe(false);
    await note.getByRole("button", { name: "Next" }).click();
  }
});
