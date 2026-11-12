import { expect, test, type Page } from "@playwright/test";
import { open, sane, sessionAs } from "./pages-kit";

// LIVE7B (12 Nov review of Release 41), lane u1: the app's general layout fixes checked in the browser. Each test sets its own width, so it is
// the same on the desktop and phone projects.
const BASIC = sessionAs("basic-token", "u-basic", "basic@example.com");
const ADS_ON = { ADS_ENABLED: "true", ADSENSE_CLIENT: "ca-pub-1234567890123456", ADSENSE_SLOT_PUBLIC: "1111111111", ADSENSE_SLOT_AI: "2222222222", CLARITY_PROJECT_ID: "abc123def4" };

async function adsOn(page: Page) {
  await page.route(/connect\.facebook\.net|clarity\.ms|googlesyndication/, (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(ADS_ON)});\n` });
  });
}

/** What shows through the question's box: every element drawn at a grid of points over it that is neither the question, inside it, nor one
 * of the boxes it sits in. Empty when the question covers nothing. */
async function under(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const c = document.querySelector("[data-testid=consent]")!;
    const r = c.getBoundingClientRect();
    const hits = new Set<string>();
    for (let i = 1; i < 12; i++) for (let j = 1; j < 4; j++) {
      const x = r.left + (r.width * i) / 12, y = r.top + (r.height * j) / 4;
      for (const e of document.elementsFromPoint(x, y)) {
        if (c.contains(e) || e.contains(c)) continue;
        hits.add(`${e.tagName.toLowerCase()}.${String(e.className).split(" ")[0]} "${(e.textContent ?? "").trim().slice(0, 24)}"`);
      }
    }
    return [...hits];
  });
}

// LIVE7B-006: the analytics question was a bar along the window's foot, over the Markets tiles at 1440 and the P&L card on a phone
for (const width of [1440, 390]) {
  test(`the analytics question covers nothing, signed in and out, and the side menu never moves, at ${width}px (LIVE7B-006)`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
    await adsOn(page);
    const errors = await open(page, "/mine", "Markets", BASIC);
    const ask = page.getByTestId("consent");
    await expect(ask).toBeVisible({ timeout: 30_000 });
    for (const y of [0, 400, 1200]) {                                   // at the top, and scrolled: nothing is ever under it
      await page.evaluate((y) => window.scrollTo(0, y), y);
      if (await ask.isVisible() && (await ask.boundingBox())!.y + 10 < page.viewportSize()!.height) expect(await under(page), `under the question, scrolled ${y}`).toEqual([]);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(Math.round((await page.locator(".shell").boundingBox())!.y)).toBe(0);
    if (width > 900) expect(Math.round((await page.locator(".sidebar").boundingBox())!.y), "the side menu starts at the top").toBe(0);
    // Do Not Track and Global Privacy Control are kept as they were: the question is not asked
    await sane(page, errors);
    await ask.getByRole("button", { name: "No thanks" }).click();
    await expect(ask).toHaveCount(0);
  });

  test(`a visitor's analytics question covers nothing at ${width}px (LIVE7B-006)`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
    await adsOn(page);
    await page.route("**/*", (r) => {
      const host = new URL(r.request().url()).hostname;
      return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
    });
    for (const path of ["/", "/start"]) {
      await page.goto(path);
      const ask = page.getByTestId("consent");
      await expect(ask).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(500);
      expect(await under(page), path).toEqual([]);
    }
  });
}

test("with Do Not Track the analytics question is not asked, as before (LIVE7B-006)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await adsOn(page);
  await page.addInitScript(() => Object.defineProperty(Navigator.prototype, "globalPrivacyControl", { get: () => true }));
  await open(page, "/mine", "Markets", BASIC);
  await page.waitForTimeout(800);
  await expect(page.getByTestId("consent")).toHaveCount(0);
});


// LIVE7B-007: a panel kept open under the guest's key showed while the account loaded, then went (the person's own was shut), and its
// button took focus on every page load: the first Tab left the page and the skip links were skipped
test("the Markets button never takes focus as a page loads; the first Tab is the skip link (LIVE7B-007)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => {
    localStorage.setItem("stratlab.watch.layout.guest", JSON.stringify({ open: true, mode: "dock", w: 380, h: 560 }));
    localStorage.setItem("stratlab.watch.layout.u-basic", JSON.stringify({ open: false, mode: "dock", w: 380, h: 560 }));
  });
  for (const path of ["/mine", "/invest"]) {
    await open(page, path, path === "/mine" ? "Markets" : "Invest home", BASIC);
    await page.waitForTimeout(1500);
    await expect(page.getByTestId("markets-launch")).toBeVisible();
    await expect(page.getByTestId("markets-launch")).not.toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  }
  // closing the panel from inside it still gives focus back to the button
  await page.getByTestId("markets-launch").click();
  await page.getByTestId("market-watch").getByRole("button", { name: "Close Market Watch" }).click();
  await expect(page.getByTestId("markets-launch")).toBeFocused();
});
