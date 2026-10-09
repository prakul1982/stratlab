import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Round 8, a visitor's review of the live site: the heading a crawler reads in a landing address's own HTML is the one the
// page draws there, and a missing page names no canonical address (R8V-008); /library asks the server for its list
// alongside its code, once, and never downloads the sign-in library or the account code (R8V-013).

async function open(page: Page, path: string) {
  const errors: string[] = [];
  const asked: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => asked.push(r.url()));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.goto(path);
  return { errors, asked };
}
const h1 = (page: Page) => page.getByRole("heading", { level: 1 });
// the drawn landing page's own h1, told apart from the start-up block's (which has the same words: that is the point)
const appH1 = (page: Page) => page.locator(".lp").getByRole("heading", { level: 1 });
const built = (file: string) => readFileSync(new URL(`../dist/${file}`, import.meta.url), "utf8");
const rawH1 = (file: string) => [...built(file).matchAll(/<h1[^>]*>([^<]*)<\/h1>/g)].map((m) => m[1].replace(/&amp;/g, "&"));

test("each landing address draws the h1 its own HTML carries, with the tagline beside it (R8V-008)", async ({ page }) => {
  const { errors } = await open(page, "/pricing");
  await expect(appH1(page)).toHaveText("Plans and prices", { timeout: 30_000 });
  await expect(h1(page)).toHaveCount(1);
  expect(rawH1("pricing/index.html")).toEqual(["Plans and prices"]);
  await expect(page.locator("#pricing")).toBeInViewport();
  await expect(page.locator(".lp").getByText("it, research it, track it.").first()).toBeAttached();
  for (const [path, file, heading] of [["/faq", "faq/index.html", "Questions"], ["/about", "about/index.html", "About StratLab"],
    ["/", "index.html", "Test it, research it, track it."]] as const) {
    await page.goto(path);
    await expect(appH1(page)).toHaveText(heading, { timeout: 30_000 });
    expect(rawH1(file), path).toEqual([heading]);
    await expect(h1(page)).toHaveCount(1);
  }
  // /plans has no file of its own: the host serves index.html, whose h1 is the tagline the landing page draws there
  await page.goto("/plans");
  await expect(appH1(page)).toHaveText("Test it, research it, track it.", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("a missing page names no canonical address (R8V-008)", async ({ page }) => {
  const { errors } = await open(page, "/no-such-page-r8v");
  await expect(h1(page)).toHaveText("Page not found", { timeout: 30_000 });
  await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, follow");
  expect(built("404.html")).not.toMatch(/rel="canonical"/);
  // a page that is there keeps its own
  await page.goto("/terms");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://stratlab.studio/terms", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("/library asks for its list once, alongside its code, and never downloads the sign-in library (R8V-013)", async ({ page }) => {
  const { errors, asked } = await open(page, "/library");
  await expect(h1(page)).toHaveText("StratLab's own strategies", { timeout: 30_000 });
  await expect(page.getByTestId("lib-hold").first()).toBeVisible({ timeout: 30_000 });
  const lists = asked.filter((u) => new URL(u).pathname === "/public/library");
  expect(lists, lists.join("\n")).toHaveLength(1);
  const code = asked.filter((u) => /\/assets\/[^/]+\.js$/.test(new URL(u).pathname)).map((u) => new URL(u).pathname.split("/").pop()!);
  expect(code.filter((f) => /^(auth|account|kit-account|main|plans|research)-/.test(f)), code.join(" ")).toEqual([]);
  expect(code.length, code.join(" ")).toBeLessThan(25);
  expect(errors).toEqual([]);
});
