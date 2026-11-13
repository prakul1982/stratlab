import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// AS1 (AdSense program policies): /about is a page of its own (what StratLab is, where its figures come from and how they are
// checked, who runs it, how to reach it), linked from every footer; the public frame's menu is the site's public pages; a page's
// HTML as built carries the same menu for a reader or crawler that runs no script.
const built = (file: string) => readFileSync(new URL(`../dist/${file}`, import.meta.url), "utf8");

async function quiet(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  return errors;
}

test("/about is its own page with what StratLab is, where the figures come from, how they are checked and who runs it", async ({ page }) => {
  const errors = await quiet(page);
  await page.goto("/about/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("About StratLab", { timeout: 30_000 });
  for (const h of ["What anyone can read without an account", "Where the figures come from", "How they are checked", "Facts, not advice", "Who runs it"]) {
    await expect(page.getByRole("heading", { level: 2, name: h })).toBeVisible();
  }
  await expect(page.locator("main").getByRole("link", { name: "support@stratlab.studio" })).toBeVisible();
  // the pages the server draws are plain links (a whole page load), not routes of the app
  await expect(page.locator('main a[href="/stocks"]')).toHaveCount(1);
  await expect(page.locator('main a[href="/themes"]')).toHaveCount(1);
  // the header's menu is the site's public pages
  const menu = page.locator("header.pub-nav");
  for (const [href, label] of [["/", "Home"], ["/library", "Library"], ["/stocks", "Companies"], ["/themes", "Themes"], ["/blog", "Blog"], ["/about", "About"], ["/contact", "Contact"]]) {
    await expect(menu.locator(`a[href="${href}"]`, { hasText: label }).first()).toBeAttached();
  }
  // nothing wider than the screen
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("every footer links to About StratLab: the landing page's and a policy page's", async ({ page }) => {
  const errors = await quiet(page);
  for (const path of ["/", "/terms/"]) {
    await page.goto(path);
    await expect(page.getByRole("navigation", { name: "Policies" }).getByRole("link", { name: "About StratLab" })).toBeAttached({ timeout: 30_000 });
  }
  expect(errors).toEqual([]);
});

test("a page's HTML as built has the site's menu and links to About, for a reader that runs no script", () => {
  for (const file of ["index.html", "terms/index.html", "faq/index.html", "about/index.html", "library/index.html"]) {
    const html = built(file);
    const nav = html.match(/<nav class="boot-nav" aria-label="Site">(.*?)<\/nav>/)?.[1] ?? "";
    for (const href of ["/library", "/stocks", "/themes", "/blog", "/about", "/contact"]) expect(nav, `${file} ${href}`).toContain(`href="${href}"`);
    expect(html, file).toContain('<a href="/about">About</a></p>');
  }
  const about = built("about/index.html");
  expect(about).toContain("<h2>Where the figures come from</h2>");
  expect(about).toMatch(/<meta name="robots" content="index, follow">/);
});
