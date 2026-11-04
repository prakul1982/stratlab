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
