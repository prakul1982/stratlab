import { expect, test, type Page } from "@playwright/test";

// Round 12, the live site's review (9 Oct 2026): a cold /faq on a phone landed with its heading, "Good to know.", under the
// 71 px sticky header, once the plans' prices arrived and changed the height of the section above it (R12-008). The page
// is opened as the site's host serves it ("/faq/": its own built file), with the prices held back for a moment.
const webPort = process.env.E2E_WEB_PORT ?? "5173";

async function quiet(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  return errors;
}

for (const [path, section, heading] of [["/faq/", "#faq", "Good to know."], ["/pricing/", "#pricing", null]] as const) {
  test(`${path} lands with its section's heading clear of the sticky header, after the prices arrive (R12-008)`, async ({ page }) => {
    const errors = await quiet(page);
    let release: () => void = () => {};
    const held = new Promise<void>((ok) => { release = ok; });
    // the plans' prices, from the API (not the page's own address), come late: the layout above /faq changes after it is placed
    await page.route((url) => url.pathname === "/pricing" && url.port !== webPort, async (r) => { await held; await r.fallback(); });
    await page.goto(path);
    await expect(page.locator(".lp")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(section)).toBeInViewport();
    release();
    await page.waitForTimeout(800);                              // the prices drawn and the layout settled
    const nav = await page.locator(".lp-nav").boundingBox();
    const box = await page.locator(section).boundingBox();
    expect(nav && box, "header and section drawn").toBeTruthy();
    // the section starts at or just below the header's bottom edge: nothing of it is hidden under the header
    // (or lower, when the page ends before the section could reach the top)
    expect(box!.y, `${path}: section at ${box!.y}, header to ${nav!.y + nav!.height}`).toBeGreaterThanOrEqual(nav!.y + nav!.height - 1);
    const vh = await page.evaluate(() => window.innerHeight);
    expect(box!.y).toBeLessThan(vh / 2);
    if (heading) {
      const h = page.getByRole("heading", { name: heading });
      await expect(h).toBeInViewport();
      const hb = await h.boundingBox();
      expect(hb!.y, `${heading} at ${hb!.y}`).toBeGreaterThan(nav!.y + nav!.height);
    }
    expect(errors).toEqual([]);
  });
}

test("a visitor who scrolls is not pulled back to the section (R12-008)", async ({ page }) => {
  const errors = await quiet(page);
  await page.goto("/faq/");
  await expect(page.locator(".lp")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#faq")).toBeInViewport();
  await page.mouse.wheel(0, -2000);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(await page.evaluate(() => document.getElementById("faq")!.offsetTop - 500));
  const y = await page.evaluate(() => window.scrollY);
  await page.evaluate(() => document.querySelector(".lp")!.appendChild(Object.assign(document.createElement("div"), { style: "height:300px" })));
  await page.waitForTimeout(300);
  expect(Math.abs((await page.evaluate(() => window.scrollY)) - y)).toBeLessThan(2);
  expect(errors).toEqual([]);
});
