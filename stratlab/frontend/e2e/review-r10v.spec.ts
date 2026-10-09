import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Round 10, a visitor's review of the live site: a cold /library, /pricing or /faq keeps its own words on screen until the
// page is ready (no splash that replaces them), keeps its tab title, and is drawn at its section, not moved there (R10V-006);
// a verdict page's title is about 60 characters and its description at most 160, and a page kept out of search results
// names no canonical address (R10V-005).
//
// The site's host serves each public address its own built file (dist/pricing/index.html). The local preview server serves
// that file for the address with a closing slash and index.html for the one without, so these tests open "/pricing/".
const built = (file: string) => readFileSync(new URL(`../dist/${file}`, import.meta.url), "utf8");
const h1 = (page: Page) => page.getByRole("heading", { level: 1 });

async function quiet(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  return errors;
}

test("a cold /library keeps its own words until the page is ready, with no splash between (R10V-006)", async ({ page }) => {
  const errors = await quiet(page);
  let release: () => void = () => {};
  const held = new Promise<void>((ok) => { release = ok; });
  await page.route(/\/assets\/PublicLibrary-[^/]+\.js$/, async (r) => { await held; await r.fallback(); });
  // every frame the visitor could have seen: the page's words, then (the old way) a splash, then the page
  await page.addInitScript(() => {
    (window as unknown as { __seen: string[] }).__seen = [];
    const look = () => {
      const w = window as unknown as { __seen: string[] };
      const text = document.body ? document.body.innerText.replace(/\s+/g, " ").trim() : "";
      const kind = /Opening StratLab/.test(text) ? "splash" : /StratLab's own strategies/.test(text) ? "words" : text ? "other" : "";
      if (kind && w.__seen[w.__seen.length - 1] !== kind) w.__seen.push(kind);
      requestAnimationFrame(look);
    };
    requestAnimationFrame(look);
  });
  await page.goto("/library/");
  // the app has started and is waiting for the page's code: the words are still the build's, drawn again
  await expect(page.locator("[data-held] h1")).toHaveText("StratLab's own strategies", { timeout: 30_000 });
  await expect(page.getByText("Opening StratLab")).toHaveCount(0);
  await expect(page).toHaveTitle("Strategy library · StratLab");
  await expect(h1(page)).toHaveCount(1);
  await expect(page.locator("main")).toHaveCount(1);
  release();
  await expect(page.locator("[data-held]")).toHaveCount(0, { timeout: 30_000 });
  await expect(h1(page)).toBeVisible();
  const seen = await page.evaluate(() => (window as unknown as { __seen: string[] }).__seen);
  expect(seen, `frames seen: ${seen.join(" > ")}`).not.toContain("splash");
  expect(seen[0]).toBe("words");
  expect(errors).toEqual([]);
});

test("/pricing and /faq are drawn at their section from the first frame, not moved there (R10V-006)", async ({ context }) => {
  for (const [path, section] of [["/pricing/", "#pricing"], ["/faq/", "#faq"]] as const) {
    const page = await context.newPage();            // a page of its own: init scripts and routes stay with it
    const errors = await quiet(page);
    // the first frames the landing page is on screen: where is its section?
    await page.addInitScript((sel) => {
      const w = window as unknown as { __frames: { y: number; top: number | null }[] };
      w.__frames = [];
      const look = () => {
        if (document.querySelector(".lp")) w.__frames.push({ y: window.scrollY, top: document.querySelector(sel)?.getBoundingClientRect().top ?? null });
        if (w.__frames.length < 40) requestAnimationFrame(look);
      };
      requestAnimationFrame(look);
    }, section);
    await page.goto(path);
    await expect(page.locator(".lp")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(section)).toBeInViewport();
    await expect.poll(() => page.evaluate(() => (window as unknown as { __frames: unknown[] }).__frames.length)).toBeGreaterThan(3);
    const frames = await page.evaluate(() => (window as unknown as { __frames: { y: number; top: number | null }[] }).__frames);
    const vh = await page.evaluate(() => window.innerHeight);
    // the first frame with the landing page on screen already has the section on screen: it was never drawn at the top
    expect(frames[0].top, `${path}: ${JSON.stringify(frames.slice(0, 4))}`).not.toBeNull();
    expect(frames[0].top!, path).toBeGreaterThanOrEqual(-40);
    expect(frames[0].top!, path).toBeLessThan(vh);
    expect(frames[0].y, path).toBeGreaterThan(200);
    expect(errors).toEqual([]);
    await page.close();
  }
});

test("a strategy's tab keeps the title its own HTML carries until its data names it (R10V-006)", async ({ page }) => {
  const errors = await quiet(page);
  // every title the page is given, in order
  await page.addInitScript(() => {
    const w = window as unknown as { __titles: string[] };
    w.__titles = [];
    let last = "";
    const look = () => { if (document.title !== last) { last = document.title; w.__titles.push(last); } requestAnimationFrame(look); };
    requestAnimationFrame(look);
  });
  await page.goto("/library/seed-supertrend-us/");
  await expect(h1(page)).toContainText(/buy and hold|checks run/, { timeout: 30_000 });
  await expect.poll(() => page.title()).toMatch(/ · StratLab$/);
  const titles = await page.evaluate(() => (window as unknown as { __titles: string[] }).__titles);
  expect(titles.length, titles.join(" | ")).toBeGreaterThan(0);
  expect(titles[0]).toBe(readTitle("library/seed-supertrend-us/index.html"));          // the title its own HTML carries
  expect(titles, titles.join(" | ")).not.toContain("Strategy library · StratLab");
  expect(titles, titles.join(" | ")).not.toContain("StratLab: test it, research it, track it");
  const title = await page.title();
  expect(title.length).toBeLessThanOrEqual(64);
  // the result leads, as the page's own headline does, then a short strategy name, then StratLab
  const head = (await h1(page).innerText()).split(/;|,(?!\d)|\.(?!\d)/)[0].trim();
  expect(title.startsWith(head.replace(/points/, "pts").slice(0, 12)) || title.startsWith(head.slice(0, 12)), `${title} | ${head}`).toBe(true);
  expect(title).toMatch(/^.+: .+ · StratLab$/);
  const desc = (await page.locator('meta[name="description"]').getAttribute("content")) ?? "";
  expect(desc.length).toBeGreaterThan(40);
  expect(desc.length).toBeLessThanOrEqual(160);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://stratlab.studio/library/seed-supertrend-us");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "index, follow");
  expect(errors).toEqual([]);
});

const readTitle = (file: string) => (built(file).match(/<title>([^<]*)<\/title>/) ?? [])[1];

test("/about and the 404 are kept out of search results with no canonical address, drawn and as built (R10V-005)", async ({ page }) => {
  for (const file of ["about/index.html", "404.html"]) {
    const html = built(file);
    expect(html, file).toMatch(/<meta name="robots" content="noindex, follow">/);
    expect(html, file).not.toMatch(/rel="canonical"/);
  }
  const errors = await quiet(page);
  await page.goto("/about/");
  await expect(page.locator(".lp")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, follow");
  await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
  await page.goto("/help/");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, follow");
  await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
  expect(errors).toEqual([]);
});
