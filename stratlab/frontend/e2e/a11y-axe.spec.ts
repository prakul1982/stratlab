import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { open, API, admin, PAGES, ownNotebook, serious, viewFor } from "./a11y-kit";

// Accessibility, the axe passes: axe-core on the main pages in light and dark, the landing and policy pages and the library
// signed out, and the pages the API draws, failing on serious or critical problems (the keyboard checks axe can't see are in
// a11y.spec.ts).

test("axe finds no serious or critical problems on the main pages", async ({ page, request }, info) => {
  test.setTimeout(420_000);
  const found: string[] = [];
  const nb = await ownNotebook(request, `Axe ${info.project.name} light`);
  for (const path of [...PAGES, `/n/${nb}`, `/n/${nb}/e/1`]) {
    await open(page, path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(500);
    // a person opens the folded parts to use them: check them open
    await page.evaluate(() => document.querySelectorAll("details:not([open])").forEach((d) => d.setAttribute("open", "")));
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
    found.push(...serious(r, `${path.replace(nb, "<notebook>")} [${info.project.name}]`));
  }
  await request.delete(`${API}/notebooks/${nb}`, { headers: admin });
  expect(found, found.join("\n")).toEqual([]);
});

test("axe: the dark theme passes too", async ({ browser, request }, info) => {
  test.setTimeout(420_000);
  const phone = info.project.name === "phone";
  const ctx = await browser.newContext({ colorScheme: "dark", viewport: phone ? { width: 390, height: 844 } : { width: 1300, height: 900 }, hasTouch: phone, isMobile: phone });
  const page = await ctx.newPage();
  const found: string[] = [];
  const nb = await ownNotebook(request, `Axe ${info.project.name} dark`);
  for (const path of [...PAGES, `/n/${nb}`, `/n/${nb}/e/1`]) {
    await open(page, path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(300);
    await page.evaluate(() => document.querySelectorAll("details:not([open])").forEach((d) => d.setAttribute("open", "")));
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    found.push(...serious(r, `${path.replace(nb, "<notebook>")} [dark]`));
  }
  await ctx.close();
  await request.delete(`${API}/notebooks/${nb}`, { headers: admin });
  expect(found, found.join("\n")).toEqual([]);
});

test("axe: the landing page, Plans, the policies and the library, signed out, in both themes", async ({ browser }, info) => {
  test.setTimeout(420_000);
  const phone = info.project.name === "phone";
  const found: string[] = [];
  for (const scheme of ["light", "dark"] as const) {
    const ctx = await browser.newContext({ colorScheme: scheme, viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 900 }, hasTouch: phone, isMobile: phone });
    const page = await ctx.newPage();
    for (const path of ["/", "/plans", "/terms", "/privacy", "/library"]) {       // the landing page, Plans, the policies (the public frame) and the library
      await open(page, path, { as: true });                      // `as`: no sign-in, so this is what a visitor sees
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await page.waitForTimeout(300);
      await page.evaluate(() => document.querySelectorAll("details:not([open])").forEach((d) => d.setAttribute("open", "")));
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "best-practice"]).analyze();
      found.push(...serious(r, `${path} [signed out, ${scheme}]`));
    }
    await ctx.close();
  }
  expect(found, found.join("\n")).toEqual([]);
});

// ---- A11Y-2: the pages the API draws, the cookie banner, the public chart, the live refresh --------------------------------------------------------

test("axe: the company pages, directories and blog the API draws, in both themes", async ({ browser }, info) => {
  test.setTimeout(420_000);
  const found: string[] = [];
  for (const scheme of ["light", "dark"] as const) {
    const ctx = await browser.newContext({ colorScheme: scheme, ...viewFor(info.project.name) });
    const page = await ctx.newPage();
    for (const path of ["/stocks", "/stocks/in", "/stocks/in/RELIANCE", "/stocks/us/AAPL", "/stocks/in/browse/r", "/stocks/in/index/nifty-50", "/blog", "/blog/briefs", "/blog/research"]) {
      await page.goto(API + path, { waitUntil: "networkidle" });
      if (path.endsWith("/RELIANCE")) {                       // the chart and its table as a person uses them: drawn, and the table open
        await page.locator("[data-chart]").scrollIntoViewIfNeeded();
        await expect(page.locator("[data-chart]")).toHaveAttribute("data-ready", "1", { timeout: 20_000 });
        await page.locator("details[data-table] summary").click();
      }
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]).analyze();
      found.push(...serious(r, `${path} [${scheme}, ${info.project.name}]`));
    }
    await ctx.close();
  }
  expect(found, found.join("\n")).toEqual([]);
});
