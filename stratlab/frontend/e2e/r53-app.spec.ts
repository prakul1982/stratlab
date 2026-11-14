import { expect, test, type Page } from "@playwright/test";
import { answerWelcome, sessionAs } from "./pages-kit";

// Release 53, lane app53: whole-app fixes from the LIVE8A / LIVE8B reviews, checked in the browser. Each test sets its own width.
const BASIC = sessionAs("basic-token", "u-basic", "basic@example.com");
const TRACK = { META_PIXEL_ID: "1234567890", CLARITY_PROJECT_ID: "abc123def4" };

/** The analytics question switched on (a fake config), everything off the machine answered with nothing, the page's layout shifts summed. */
async function withQuestion(page: Page, who: object | null) {
  await page.route(/connect\.facebook\.net|clarity\.ms/, (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(TRACK)});\n` });
  });
  await page.addInitScript((s) => {
    if (s) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    const w = window as unknown as { __cls: number };
    w.__cls = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) w.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
  }, who);
}

// LIVE8B-004 (/trade 0.50, company pages 0.40: the band drawn above the page after its first paint pushed it down) and LIVE8A-017 (/about at
// 390, 0.435): the question comes after the page, once it has drawn, so nothing moves under it; "Skip to content" lands on the page
for (const [width, path, who, ready] of [[1440, "/trade", BASIC, "Trade"], [1440, "/research/IN/RELIANCE", BASIC, "Reliance"], [390, "/about", null, "About"]] as const) {
  test(`the analytics question never moves the page: ${path} at ${width}px (LIVE8B-004, LIVE8A-017)`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
    await withQuestion(page, who);
    await page.goto(path);
    if (who) await answerWelcome(page);
    await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
    const ask = page.getByTestId("consent");
    await expect(ask).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(1500);
    const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
    expect(cls, `layout shift ${cls.toFixed(3)}`).toBeLessThan(0.05);
    // after the page: its top is at or below the end of the page's main content
    const main = (await page.locator("main#main").boundingBox())!, a = (await ask.boundingBox())!;
    expect(a.y, "the question comes after the page").toBeGreaterThanOrEqual(main.y + main.height - 1);
    // and answering it takes it away without moving anything above it
    const top = () => page.locator("h1").filter({ visible: true }).first().evaluate((e) => Math.round(e.getBoundingClientRect().top + window.scrollY));
    const before = await top();
    await ask.getByRole("button", { name: "No thanks" }).click();
    await expect(ask).toHaveCount(0);
    expect(await top()).toBe(before);
  });
}
