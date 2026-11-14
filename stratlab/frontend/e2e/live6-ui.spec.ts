import { expect, test, type Page } from "@playwright/test";
import { open, sane, session, sessionAs } from "./pages-kit";

// LIVE6 (11 Nov review), lane p2-ui: the app's layout fixes checked in the browser. Each test sets its own width, so it is the same on
// the desktop and phone projects. E2E_SHOTS=<dir> keeps a screenshot of each page at 1440 and 390 for a look by eye.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const FREE = sessionAs("free-token", "u-free", "free@example.com");
const SHOTS = process.env.E2E_SHOTS;

async function shot(page: Page, name: string, info: { project: { name: string } }) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/live6-${name}-${info.project.name}-${page.viewportSize()!.width}.png`, fullPage: false });
}

// LIVE6-020: on a phone IPOs moved by 0.40 and Net worth by 0.21 while loading: for a Free user the page's plan note was drawn under the
// title while the figures loaded, then taken away when the page's own plan note came with them. Measured here with the server's answers
// arriving late and out of order, as on the live site, for a Free user; each page stays under 0.1 (Google's "good").
for (const width of [390, 1440]) {
  test(`IPOs and Net worth hold still while they load for a Free user at ${width}px (LIVE6-020)`, async ({ page }) => {
    test.setTimeout(120_000);
    const over: string[] = [];
    for (const path of ["/invest/ipos", "/money/net-worth"]) {
      const p = await page.context().newPage();
      await p.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      const api = new URL(API);
      let n = 0;
      await p.route("**/*", (r) => {
        const u = new URL(r.request().url());
        if (u.host === api.host && !/\/me$/.test(u.pathname)) return new Promise((ok) => setTimeout(ok, 400 + ((n++ * 700) % 2200))).then(() => r.fallback());
        return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
      });
      await p.addInitScript((s) => {
        try { localStorage.clear(); localStorage.setItem("stratlab.tour.v1", "1"); localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); } catch { /* none */ }
        const w = window as unknown as { __shift: { v: number; n: string[] }[] };
        w.__shift = [];
        new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Element; previousRect: DOMRect; currentRect: DOMRect }[] }[]) if (!e.hadRecentInput) w.__shift.push({ v: e.value, n: (e.sources ?? []).map((x) => `${(x.node as Element | undefined)?.className ?? x.node?.nodeName} ${Math.round(x.previousRect.y)}->${Math.round(x.currentRect.y)}`) }); }).observe({ type: "layout-shift", buffered: true });
      }, FREE);
      await p.goto(path);
      await expect(p.locator("main .plan-note").first()).toBeVisible({ timeout: 30_000 });     // the page's own plan note: the page has loaded
      await p.waitForTimeout(2500);
      const shifts = await p.evaluate(() => (window as unknown as { __shift: { v: number; n: string[] }[] }).__shift);
      const cls = shifts.reduce((a, x) => a + x.v, 0);
      if (cls >= 0.1) over.push(`${path} ${width}: ${cls.toFixed(3)} ${JSON.stringify(shifts.filter((x) => x.v > 0.005))}`);
      await expect(p.locator("main .page-lock")).toHaveCount(0);                                  // one plan note, the page's own
      await p.close();
    }
    expect(over, over.join("\n")).toEqual([]);
  });
}

// LIVE6-019: on a phone the heatmap's settings filled the first screen and the map began about 1,150px down
test("on a phone the heatmap's settings fold into one row and the map starts on the first screen (LIVE6-019)", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors = await open(page, "/invest/heatmap?region=IN", "Closes of");
  const fold = page.getByTestId("hm-fold");
  await expect(fold).toBeVisible();
  await expect(fold).toContainText("India");
  await expect(page.getByRole("group", { name: "Colour by" }).first()).toBeHidden();
  await expect(page.getByRole("group", { name: "Period" }).first()).toBeVisible();                      // the period stays out
  const map = (await page.getByTestId("heatmap").boundingBox())!;
  expect(map.y, "the map's card starts on the first screen").toBeLessThan(844);
  await shot(page, "heatmap-folded", info);
  await fold.getByRole("button", { name: "Options" }).click();
  await expect(page.getByRole("group", { name: "Colour by" }).first()).toBeVisible();
  await page.getByRole("radiogroup", { name: "Colour by" }).getByRole("radio", { name: "Volume" }).click();
  await expect(page).toHaveURL(/c=volume/);
  await expect(fold).toContainText("Volume");
  await fold.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("group", { name: "Colour by" }).first()).toBeHidden();
  // a wide window never shows the row: every setting is out as before
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(fold).toBeHidden();
  await expect(page.getByRole("group", { name: "Colour by" }).first()).toBeVisible();
  await shot(page, "heatmap", info);
  await sane(page, errors);
});

// LIVE6-016: on the Themes page the orange Themes pill and the menu's Themes entry both looked selected
test("on the Themes page only the menu's Themes entry is highlighted (LIVE6-016)", async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const errors = await open(page, "/research/themes?region=IN", "Themes", session);
  const pill = page.locator(".side-feature");
  await expect(pill).toHaveClass(/\bhere\b/);
  const look = await pill.evaluate((e) => { const s = getComputedStyle(e); return { bg: s.backgroundColor, edge: s.borderLeftColor, top: s.borderTopColor }; });
  expect(look.bg === "rgba(0, 0, 0, 0)" || look.bg === "transparent", `the pill's background ${look.bg}`).toBe(true);
  expect(look.edge, "no orange edge").toBe(look.top);
  await expect(page.locator(".side-groups a[aria-current=page]")).toHaveCount(1);
  await shot(page, "themes-side", info);
  // on another page the pill is the orange feature again
  await page.goto("/invest");
  await expect(pill).not.toHaveClass(/\bhere\b/);
  await sane(page, errors);
});

// LIVE6-014: signed in, the analytics question (a band in the page's flow) pushed the whole app, side menu included, down 75-95 px.
// LIVE6-013: at 1440 a docked Markets panel floated half the window high over the page. Both checked here at 1440 and 390.
const ADS_ON = { ADS_ENABLED: "true", ADSENSE_CLIENT: "ca-pub-1234567890123456", ADSENSE_SLOT_PUBLIC: "1111111111", ADSENSE_SLOT_AI: "2222222222" };
for (const width of [1440, 390]) {
  test(`the analytics question never moves the app, and the Markets panel docks in its own column at ${width}px (LIVE6-013, LIVE6-014)`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
    await page.route(/\/config\.js(\?|$)/, async (r) => {
      const real = await (await r.fetch()).text();
      await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(ADS_ON)});\n` });
    });
    const errors = await open(page, "/invest", "Invest", FREE);
    const ask = page.getByTestId("consent");
    await expect(ask).toBeVisible({ timeout: 30_000 });
    // (updated on purpose, LIVE7B-006: as a bar along the window's foot it covered the page's tiles) the first row of the page column, in the
    // page's flow: the app and its side menu still start at the top of the window, and the page starts under the question
    expect(await ask.evaluate((e) => getComputedStyle(e).position)).not.toBe("fixed");
    const shell = (await page.locator(".shell").boundingBox())!;
    expect(Math.round(shell.y), "the app starts at the top of the window").toBe(0);
    if (width > 900) expect(Math.round((await page.locator(".sidebar").boundingBox())!.y), "the side menu starts at the top of the window").toBe(0);
    const box = (await ask.boundingBox())!;
    // (updated on purpose, LIVE8B-004: above the page, its arrival after the first paint pushed the page down) the page ends above the question
    const page0 = (await page.locator("#main").boundingBox())!;
    expect(box.y, "the question comes after the page").toBeGreaterThanOrEqual(page0.y + page0.height - 1);
    await shot(page, "consent", info);
    if (width < 500) { await sane(page, errors); return; }
    // the panel: docked at 1440 in its own column, the full window high; the page and the question make room
    await page.getByTestId("markets-launch").click();
    const mw = page.getByTestId("market-watch");
    await expect(mw).toBeVisible();
    await expect(mw).toHaveClass(/\bmw-dock\b/);
    const p = (await mw.boundingBox())!;
    expect(Math.round(p.x + p.width)).toBe(1440);
    expect(Math.round(p.height)).toBe(900);
    const main = (await page.locator("#main").boundingBox())!;
    expect(main.x + main.width, "the page reflows beside it").toBeLessThanOrEqual(p.x + 1);
    const a2 = (await ask.boundingBox())!;
    expect(a2.x + a2.width, "the question is left of the panel").toBeLessThanOrEqual(p.x + 1);
    await shot(page, "markets-docked", info);
    // it goes with the next page (the person's choice: docked, open)
    await page.goto("/research/rotation");
    await expect(mw).toBeVisible();
    await sane(page, errors);
  });
}

// LIVE6-012: the Themes search box's list is the shared library, never worded as the viewer's own reading
test("the Themes search box offers the shared library as Ready to open, never Already read (LIVE6-012)", async ({ page }, info) => {
  test.setTimeout(150_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  // a theme kept first, as someone else read it (the fake world maps it in a few seconds)
  await open(page, "/research/themes?region=IN&q=" + encodeURIComponent("India steel and mining"), "Download", session);
  const other = await page.context().newPage();                                                   // someone who never opened it
  await other.setViewportSize({ width: 1440, height: 900 });
  const errors = await open(other, "/research/themes?region=IN", "Map it", FREE);
  await expect(other.locator(".side-account, .sidebar").getByText("Free").first()).toBeVisible();
  await other.getByRole("textbox", { name: "Theme" }).fill("steel");
  const list = other.getByTestId("theme-already");
  await expect(list).toBeVisible({ timeout: 30_000 });
  await expect(list).toContainText("Ready to open:");
  await expect(list).not.toContainText(/Already read|, read \d/);
  await expect(list.getByRole("button", { name: /· India, updated \d{1,2} [A-Z][a-z]{2}/ }).first()).toBeVisible();
  await shot(other, "themes-library", info);
  await sane(other, errors);
});
