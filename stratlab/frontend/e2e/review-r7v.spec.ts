import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Round 7, a visitor's review of the live site: a library strategy's tab title and description lead with its result and
// name its universe once (R7V-006); the library and policy pages carry their own heading and words in the HTML the host
// serves, one h1 each, with the FAQ's structured data on /faq, and those words show with JavaScript off (R7V-008).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.goto(path);
  return errors;
}
const h1 = (page: Page) => page.getByRole("heading", { level: 1 });
const built = (file: string) => readFileSync(new URL(`../dist/${file}`, import.meta.url), "utf8");

test("a library strategy's tab title and description lead with its result and name its universe once (R7V-006)", async ({ page }) => {
  const errors = await open(page, "/library/seed-supertrend-us");
  const entry = await (await page.request.get(`${API}/public/library/seed-supertrend-us`)).json();
  const v = entry.verdict;
  await expect(h1(page)).toHaveText(v.fact_headline ?? v.headline, { timeout: 30_000 });
  const lead = String(v.fact_headline ?? v.label ?? v.headline).split(";")[0].replace(/\.\s*$/, "").trim();
  // changed on purpose in R10V-005: the title is the result, a short strategy name and StratLab in about 60 characters (it was
  // "<result>: <full name with its universe> · StratLab", up to 117), and the description at most 160
  await expect.poll(() => page.title()).toMatch(/ · StratLab$/);
  const title = await page.title();
  expect(title.length).toBeLessThanOrEqual(64);
  expect(title.startsWith(lead.replace(/\bpoints\b/, "pts").slice(0, 14)) || title.startsWith(lead.slice(0, 14)), `${title} | ${lead}`).toBe(true);
  expect(title).toContain(entry.name.split(" · ")[0]);
  const desc = await page.locator('meta[name="description"]').getAttribute("content");
  expect(desc!.length).toBeLessThanOrEqual(160);
  expect(desc?.startsWith(String(v.fact_headline ?? v.headline).slice(0, 60))).toBe(true);
  expect((desc ?? "").toLowerCase().split("20 us large caps").length - 1, desc ?? "").toBe(1);
  expect(desc).not.toMatch(/ on 20 US large caps/);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "index, follow");
  expect(errors).toEqual([]);
});

test("the library and policy pages' own HTML has their heading and words, one h1 each, and /faq its FAQ markup (R7V-008)", async () => {
  const pages: [string, string, RegExp][] = [
    ["library/seed-supertrend-us/index.html", "Supertrend flip · 20 US large caps", /Enters when the price crosses above the Supertrend \(10, 3\)/],
    ["library/index.html", "StratLab's own strategies", /verdict it earned/],
    ["terms/index.html", "Terms of service", /No real orders are ever placed/],
    ["privacy/index.html", "Privacy policy", /What StratLab collects and why/],
    ["refunds/index.html", "Cancellation and refunds", /cancel a StratLab plan/],
    ["contact/index.html", "Contact us", /support@stratlab\.studio/],
    ["pricing/index.html", "Plans and prices", /Free, Basic and Pro/],
    ["faq/index.html", "Questions", /Does StratLab tell me what to buy\?/],
    ["about/index.html", "About StratLab", /Facts, not tips/],
  ];
  for (const [file, heading, words] of pages) {
    const raw = built(file);
    expect([...raw.matchAll(/<h1[^>]*>([^<]*)<\/h1>/g)].map((m) => m[1].replace(/&amp;/g, "&")), file).toEqual([heading]);
    expect(raw, file).toMatch(words);
    expect(raw, file).not.toMatch(/<h1>StratLab: test it/);
  }
  const ld = JSON.parse(built("faq/index.html").match(/<script type="application\/ld\+json">(.*?)<\/script>/s)![1]);
  expect(ld.map((x: { "@type": string }) => x["@type"])).toEqual(["FAQPage"]);
  expect(ld[0].mainEntity.length).toBeGreaterThan(5);
  // an unknown strategy's address is the host's 404 page, which says noindex
  expect(built("404.html")).toMatch(/<meta name="robots" content="noindex, follow">/);
});

test("with JavaScript off the page's own words show, and the note about JavaScript is not a second heading (R7V-008)", async ({ browser }) => {
  const ctx = await browser.newContext({ javaScriptEnabled: false });
  const page = await ctx.newPage();
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Facts, not tips.").first()).toBeVisible();
  expect(await page.content()).toContain("StratLab needs JavaScript.");
  await ctx.close();
});
