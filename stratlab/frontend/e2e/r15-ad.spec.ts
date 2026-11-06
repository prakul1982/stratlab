import { gunzipSync } from "node:zlib";
import { expect, test, type Page, type Request } from "@playwright/test";

// R15 (owner, 7 Nov): the ad landing. The social ad sends visitors to "/"; every one saw the full landing once and left. /start, and "/"
// for a visit from the ad (Meta's click id, or a social utm_source), is one phone screen with one way in; "/" without them is the
// landing page as before. A visitor here: no saved sign-in.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const HEADLINE = "Test trading ideas on real prices, research any company, track your money.";

async function open(page: Page, path: string, config = "") {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  if (config) await page.route("**/config.js", (r) => r.fulfill({ contentType: "application/javascript", body: config }));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.goto(path);
  return errors;
}

async function adView(page: Page, errors: string[]) {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(HEADLINE, { timeout: 30_000 });
  const cta = page.getByRole("button", { name: "Try free with Google" });
  await expect(cta, "the way in is on the first screen").toBeInViewport();
  for (const p of ["Backtests after costs, with four checks for luck.", "Company numbers and filings, India and US.", "Holdings, gains and tax from your own files."])
    await expect(page.getByText(p)).toBeVisible();
  const shots = page.getByRole("region", { name: /What StratLab looks like/ }).locator("figure");
  await expect(shots).toHaveCount(3);
  await expect(shots.first(), "the first sample card shows on the first screen").toBeInViewport({ ratio: 0.5 });
  await expect(page.getByRole("link", { name: "See everything StratLab does →" })).toBeVisible();
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/\b(you should|buy now|accumulate|recommend|tips?)\b/i);
  expect(errors).toEqual([]);
}

test("/start is the ad landing: one line, one way in, three points and three samples on the first screen; its own title", async ({ page }) => {
  const errors = await open(page, "/start");
  await adView(page, errors);
  await expect(page).toHaveTitle("Try StratLab free · StratLab");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://stratlab.studio/");
  // the full landing is one link away
  await page.getByRole("link", { name: "See everything StratLab does →" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Test it, research it, track it.", { timeout: 30_000 });
});

test("the live ad's address: / with fbclid or a social utm_source draws the ad landing and keeps its parameters", async ({ page }) => {
  let errors = await open(page, "/?fbclid=IwAR0test");
  await adView(page, errors);
  expect(new URL(page.url()).searchParams.get("fbclid"), "the click id stays in the address for analytics").toBe("IwAR0test");
  await page.waitForTimeout(800);
  expect(new URL(page.url()).searchParams.get("fbclid")).toBe("IwAR0test");
  errors = await open(page, "/?utm_source=instagram&utm_medium=paid_social");
  await adView(page, errors);
  expect(page.url()).toContain("utm_source=instagram");
});

test("/ with no ad parameters (or another source) is the landing page as before", async ({ page }) => {
  for (const path of ["/", "/?utm_source=google"]) {
    await open(page, path);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Test it, research it, track it.", { timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Try free with Google" })).toHaveCount(0);
  }
});

test("with analytics on, the ad landing sends ad_landing_view, and ad_signup_click on the button before it leaves for sign-in", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  // analytics stays off for a test browser (navigator.webdriver): look like a plain one, as review-r5's analytics test does. The batch's
  // requests are read as they go; a beacon (what the click sends, as the page leaves) is read in the page, its words said on the console
  await page.addInitScript(() => {
    Object.defineProperty(Navigator.prototype, "webdriver", { get: () => false });
    // CI's headless shell names itself "HeadlessChrome" in userAgentData and PostHog drops those events, as analytics.spec's test hides
    Object.defineProperty(Navigator.prototype, "userAgentData", { get: () => undefined });
    Object.defineProperty(Navigator.prototype, "userAgent", { get: () => "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36" });
    const send = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = (url, data) => {
      if (data instanceof Blob) void data.text().then((t) => {
        let words = t;
        try { words = atob(decodeURIComponent(t.replace(/^data=/, ""))); } catch { /* not base64 */ }
        console.log(`beacon ${words}`);
      });
      return send(url, data);
    };
  });
  const said: string[] = [];
  ctx.on("request", (r: Request) => {
    if (!/posthog/i.test(r.url())) return;
    const buf = r.postDataBuffer();
    if (buf) { try { said.push(gunzipSync(buf).toString("utf8")); } catch { said.push(buf.toString("utf8")); } }
  });
  page.on("console", (m) => { if (m.text().startsWith("beacon ")) said.push(m.text()); });
  // the sign-in service answers "no content", so the page stays where it is and the beacon can be read
  await page.route("https://demo.supabase.co/**", (r) => r.fulfill({ status: 204, body: "" }));
  const errors = await open(page, "/?fbclid=x", `window.STRATLAB_CONFIG = {API_BASE:"${API}",SUPABASE_URL:"https://demo.supabase.co",SUPABASE_ANON_KEY:"demo",POSTHOG_KEY:"phc_test"};`);
  await adView(page, errors);
  // analytics loads when the browser is idle after the first paint (lib/analytics.ts), then sends its batch
  await expect.poll(() => said.join("\n"), { timeout: 20_000 }).toContain("ad_landing_view");
  expect(said.join("\n")).toMatch(/"kind":"home","source":"fbclid"/);
  await page.getByRole("button", { name: "Try free with Google" }).click();
  await expect.poll(() => said.filter((x) => x.startsWith("beacon ")).join("\n"), { timeout: 20_000 }).toContain("ad_signup_click");
  await ctx.close();
});
