import { expect, test, type Page, type Route } from "@playwright/test";

// Round 5, a signed-out visitor's review of the live site: a page that can't be blank, plans that don't flash or move, the
// hero demo's tabs, the public library, the sign-in panel and its errors, the menu, SEO tags per page, the gate pages,
// what loads on a policy page, and what the browser keeps before sign-in.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

async function open(page: Page, path = "/", opts: { config?: string } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  if (opts.config) await page.route("**/config.js", (r) => r.fulfill({ contentType: "application/javascript", body: opts.config! }));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.goto(path);
  return errors;
}
const h1 = (page: Page) => page.getByRole("heading", { level: 1 });
const config = (extra = "") => `window.STRATLAB_CONFIG = {API_BASE:"${API}",SUPABASE_URL:"https://demo.supabase.co",SUPABASE_ANON_KEY:"demo"${extra}};`;

const ENTRY = {
  id: "seed-ema-20-50-nifty50", name: "20/50 EMA cross · NIFTY 50", question: "", description: "Enters when the 20-day exponential average crosses above the 50-day one.",
  author: "StratLab", badge: "StratLab", official: true, market: "IN", instrument: null, group: { name: "NIFTY 50", members: [{ symbol: "TCS" }] }, tf: "1d", side: "long",
  range: { from: "2021-10-01", to: "2026-10-01" }, strategy: { entry: [{ l: { t: "ema", p: 20 }, op: "xa", r: { t: "ema", p: 50 } }], exit: [{ l: { t: "ema", p: 20 }, op: "xb", r: { t: "ema", p: 50 } }] },
  verdict: { verdict: "luck", headline: "Probably luck.", summary: "It lost on the years it had never seen.", passed: 1, total: 4,
    checks: [{ id: "unseen", status: "fail" }, { id: "nearby", status: "fail" }, { id: "shuffle", status: "warn" }, { id: "sample", status: "pass" }] },
  stats: { ret: 12.5, buy_hold: 40.1, mdd: -18.2, trades: 38, unseen: -4.1 }, published_at: "2026-10-02T04:00:00+00:00", copies: 3, ran: true, reason: "Passed: enough trades. Failed: unseen years, nearby settings.",
};
const LIST = { entries: [ENTRY, { ...ENTRY, id: "seed-rsi2-us-mega", name: "RSI(2) mean reversion · US mega caps", group: { name: "US mega caps", members: [] }, market: "US",
  verdict: { ...ENTRY.verdict, verdict: "edge", headline: "Likely a real edge.", passed: 4 } }], total: 2, reasons: {} };
const mockLibrary = async (page: Page) => {
  await page.route(/\/public\/library(\?.*)?$/, (r) => r.fulfill({ json: LIST }));
  await page.route("**/public/library/seed-ema-20-50-nifty50", (r) => r.fulfill({ json: ENTRY }));
};

test.describe("a page that is never blank (R5V-001)", () => {
  test("config.js fails twice: a plain message and a Reload button, not an empty page", async ({ page }) => {
    await page.route("**/config.js*", (r) => r.abort());
    await page.goto("/");
    await expect(page.getByRole("alert")).toContainText("Couldn't load StratLab.", { timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
  });

  test("config.js fails once: the retry gets it and the page opens", async ({ page }) => {
    let first = true;
    await page.route("**/config.js*", (r) => { if (first) { first = false; return r.abort(); } return r.fallback(); });
    await page.goto("/");
    await expect(h1(page)).toContainText("Test it, research it, track it", { timeout: 30_000 });
  });

  test("a page's code fails to download: reload once, then say so", async ({ page }) => {
    let loads = 0;
    await page.route("**/assets/Login-*.js", (r) => { loads++; return r.abort(); });
    await page.goto("/");
    await expect(page.getByRole("alert")).toContainText("Couldn't load StratLab.", { timeout: 30_000 });
    expect(loads, "one try, one reload, and then it stops").toBeLessThanOrEqual(4);
    await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
  });

  test("the static start-up page has the words, and JavaScript off shows a message", async ({ browser }) => {
    const ctx = await browser.newContext({ javaScriptEnabled: false });
    const page = await ctx.newPage();
    await page.goto("/");
    const html = await page.content();           // (Playwright's text search skips <noscript>, so read the page itself)
    expect(html).toContain("StratLab needs JavaScript");
    expect(html).toContain("Facts, not tips");
    expect(html).toContain('rel="canonical"');
    await ctx.close();
  });
});

test.describe("plans: the right currency at once, the charged amount on the card, one look (R5V-006)", () => {
  test.use({ timezoneId: "America/New_York", locale: "en-US" });
  const priced = async () => {
    const body = await (await fetch(`${API}/pricing`)).json();
    body.offer = { ...body.offer, mode: "paid", payments: true, yearly: true };
    return body;
  };

  test("no rupees flash before dollars, the layout holds, and the card says what is charged", async ({ page }) => {
    const body = await priced();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((ok) => { release = ok; });
    await page.route("**/pricing", async (r: Route) => { await gate; await r.fulfill({ json: body }); });
    await open(page);
    const sec = page.locator("#pricing");
    await sec.scrollIntoViewIfNeeded();
    await expect(sec.locator(".lp-skel-amount")).toHaveCount(3);
    await expect(sec).not.toContainText("₹");
    const before = await page.evaluate(() => (document.querySelector("#faq") as HTMLElement).getBoundingClientRect().top + scrollY);
    release();
    await expect(sec.locator('.lp-price[data-plan="basic"] .lp-amount')).toContainText("$8");
    await expect(sec.locator('.lp-price[data-plan="pro"] .lp-amount')).toContainText("$20");
    const after = await page.evaluate(() => (document.querySelector("#faq") as HTMLElement).getBoundingClientRect().top + scrollY);
    // (the heading and the lines under the cards wrap differently on a narrow screen, so a phone gets more room than a laptop)
    expect(Math.abs(after - before), "what is below the plans moved when the prices arrived").toBeLessThanOrEqual(page.viewportSize()!.width < 700 ? 120 : 60);
    const basic = sec.locator('.lp-price[data-plan="basic"]');
    await expect(basic).toContainText("Charged as ₹699 / month incl. GST");
    const size = await basic.locator(".lp-price-note").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(size, "the charged amount is in readable type").toBeGreaterThanOrEqual(13);
    // the yearly choice says "about" and each card states its exact saving
    await sec.getByRole("radio", { name: "Yearly · about 2 months free" }).click();
    await expect(sec.locator('.lp-price[data-plan="pro"]')).toContainText("Charged as ₹19,999 / year incl. GST");
    await expect(sec.locator('.lp-price[data-plan="basic"] .lp-save')).toContainText("Saves");
    await expect(sec.locator('.lp-price[data-plan="free"] .lp-save')).toHaveCount(0);
    await expect(sec.locator('.lp-price[data-plan="basic"] button')).toHaveText("Continue with Google to get Basic");
    await expect(sec).not.toContainText("Choose a plan after you sign in");
  });

  test("the prices can't be read: the same cards in rupees, a real button, nothing promised", async ({ page }) => {
    await page.route("**/pricing", (r) => r.fulfill({ status: 500, json: { detail: "no" } }));
    await open(page);
    const sec = page.locator("#pricing");
    await expect(sec.locator('.lp-price[data-plan="basic"] .lp-amount')).toContainText("₹699", { timeout: 30_000 });
    await expect(sec.getByRole("heading", { level: 2 })).toHaveText("Plans");
    await expect(sec).not.toContainText(/Free to start|Choose a plan after you sign in/);
    await expect(sec.locator('.lp-price[data-plan="pro"] button')).toHaveText("Continue with Google to see plans");
    await expect(sec.locator(".lp-price")).toHaveCount(3);
  });
});

test.describe("the hero demo (R5V-017, R5V-018)", () => {
  test("tabs are a real tab list: one stop, arrow keys, aria-selected; the headline never moves", async ({ page }, info) => {
    await open(page);
    const tabs = page.locator('.lp-demo-tabs [role="tab"]');
    await expect(tabs).toHaveCount(3);
    await expect(page.locator(".lp-demo-tabs [aria-pressed]")).toHaveCount(0);
    expect(await tabs.evaluateAll((els) => els.map((e) => e.getAttribute("tabindex")))).toEqual(["0", "-1", "-1"]);
    const y = async () => (await h1(page).boundingBox())!.y;
    const top = await y();
    await tabs.nth(0).focus();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(1)).toBeFocused();
    await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
    expect(await tabs.evaluateAll((els) => els.map((e) => e.getAttribute("tabindex")))).toEqual(["-1", "0", "-1"]);
    expect(Math.abs((await y()) - top), "the headline jumped").toBeLessThanOrEqual(1);
    await page.keyboard.press("End");
    await expect(tabs.nth(2)).toHaveAttribute("aria-selected", "true");
    expect(Math.abs((await y()) - top), "the headline jumped").toBeLessThanOrEqual(1);
    await page.keyboard.press("ArrowRight");                       // wraps round
    await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "true");
    // the panel it controls is the one shown, and the others are out of the page for everyone
    const panel = page.getByRole("tabpanel");
    await expect(panel).toHaveCount(1);
    await expect(panel).toContainText("Sample result");
    // the card is never dim, and on a phone it is on the first screens
    const demo = page.locator(".lp-demo");
    await expect(demo).toBeVisible();
    expect(await page.locator(".lp-demo-body.on").evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
    if (info.project.name === "phone") expect((await demo.boundingBox())!.y, "the demo is below two screens on a phone").toBeLessThan(1000);
  });

  test("the verdict lines are facts about the test, the Trade and Money pictures say they are samples", async ({ page }) => {
    await open(page);
    await expect(page.locator("body")).not.toContainText("Likely a real edge");
    await expect(page.locator(".lp-sample")).toHaveCount(5);           // each of the three demo results, the Trade picture and the Money picture
    await expect(page.locator(".lp-space[data-space=trade]")).toContainText("Sample");
    await expect(page.locator(".lp-space[data-space=money]")).toContainText("Sample");
    await expect(page.locator(".lp-ridea")).toContainText("A template for a test, not a suggestion");
    await expect(page.locator(".lp-ridea")).not.toContainText(/Buy NVDA/);
    // nothing on the landing page is drawn smaller than 12px
    const tiny = await page.evaluate(() => Array.from(document.querySelectorAll(".lp *")).filter((el) => el.childNodes.length && Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent!.trim())
      && parseFloat(getComputedStyle(el).fontSize) < 12).map((el) => `${el.tagName} ${getComputedStyle(el).fontSize} ${(el.textContent || "").slice(0, 20)}`));
    expect(tiny).toEqual([]);
  });
});

test.describe("addresses and sign-in (R5V-011, R5V-013, R5V-015)", () => {
  test("/faq opens the questions with a title and description of its own", async ({ page }) => {
    await open(page, "/faq");
    await expect(page.locator("#faq")).toBeInViewport({ timeout: 30_000 });
    await expect(page).toHaveTitle("Questions · StratLab");
    await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /whether it gives tips/);
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://stratlab.studio/faq");
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "index, follow");
    await expect(page.getByText("Page not found")).toHaveCount(0);
  });

  test("/login and /signup open the way in; /about and /help scroll to the right place", async ({ page }) => {
    await open(page, "/login");
    const panel = page.getByRole("dialog", { name: "Sign in to StratLab" });
    await expect(panel).toBeVisible({ timeout: 30_000 });
    await expect(panel.getByRole("button", { name: "Continue with Google" })).toBeVisible();
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, follow");
    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
    await open(page, "/signup");
    await expect(page.getByRole("dialog", { name: "Create your free account" })).toBeVisible({ timeout: 30_000 });
    await open(page, "/about");
    await expect(page.locator("#about")).toBeInViewport({ timeout: 30_000 });
    await open(page, "/help");
    await expect(page.locator("#faq")).toBeInViewport({ timeout: 30_000 });
  });

  test("a refused Google sign-in says so, from ?error= or #error=", async ({ page }) => {
    await open(page, "/?error=access_denied&error_description=The+user+denied+access");
    await expect(page.getByRole("alert").filter({ hasText: "not signed in" })).toContainText("Continue with Google to try again", { timeout: 30_000 });
    await expect(page).toHaveURL(/127\.0\.0\.1:\d+\/$/);                // the error is out of the address afterwards
    await page.goto("about:blank");
    await open(page, "/#error=server_error&error_code=unexpected_failure&error_description=Unable+to+exchange+external+code");
    await expect(page.getByRole("alert").filter({ hasText: "couldn't finish" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("alert")).not.toContainText(/Supabase|Client ID/);
  });

  test("marketing buttons that sign in say so", async ({ page }) => {
    await open(page);
    for (const b of await page.locator("main button.btn").all()) {
      const name = ((await b.textContent()) ?? "").trim();
      if (/Google|^Yearly|^Monthly/.test(name) || !name) continue;
      throw new Error(`a button that signs in is called "${name}"`);
    }
    await expect(page.locator("body")).not.toContainText(/Start free|Sign up free|Test an idea on NVDA/);
  });
});

test.describe("StratLab's own library, readable signed out (R5V-011)", () => {
  test("the landing page links a real verdict, /library lists them read only, and one opens with its rules and checks", async ({ page }) => {
    await mockLibrary(page);
    await open(page);
    const ex = page.locator("#examples");
    await expect(ex.getByRole("heading", { name: "Real verdicts, open to read." })).toBeVisible({ timeout: 30_000 });
    await expect(ex.locator("a.lp-example")).toHaveCount(2);
    await expect(ex.getByRole("link", { name: /See all 2 StratLab strategies/ })).toHaveAttribute("href", "/library");
    await ex.locator("a.lp-example", { hasText: "20/50 EMA" }).click();
    await expect(page).toHaveURL(/\/library\/seed-ema-20-50-nifty50$/);
    await expect(h1(page)).toHaveText("Probably luck.", { timeout: 30_000 });
    await expect(page).toHaveTitle(/20\/50 EMA cross.*Probably luck\. · StratLab/);
    await expect(page.locator("main")).toContainText("The rules that were tested");
    await expect(page.locator("main")).toContainText("Buy when");
    for (const c of ["Unseen years", "Nearby settings", "Bad-luck drawdown", "Enough trades"]) await expect(page.locator(".pub-checks")).toContainText(c);
    await expect(page.getByRole("button", { name: "Continue with Google to copy and re-test" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^(Copy|Report|Take down)/ })).toHaveCount(0);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "index, follow");
    await page.getByRole("link", { name: "All StratLab strategies" }).click();
    await expect(h1(page)).toHaveText("StratLab's own strategies");
    await expect(page.getByRole("link", { name: /^Open the verdict and rules of/ })).toHaveCount(2);
  });

  test("an id that isn't there is said so, with a title of its own", async ({ page }) => {
    await page.route("**/public/library/nothing-here-1", (r) => r.fulfill({ status: 404, json: { detail: { code: "not_found", message: "That strategy isn't in StratLab's public library." } } }));
    await open(page, "/library/nothing-here-1");
    await expect(page.getByText("This strategy isn't available")).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveTitle("Strategy not found · StratLab");
    await open(page, "/verdict/not-a-real-token");
    await expect(page.getByText("This verdict isn't available")).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveTitle("Verdict not available · StratLab");
  });
});

test.describe("gate and not-found pages (R5V-013, R5V-014)", () => {
  test("an unknown symbol is never promised; an unknown market is not found", async ({ page }) => {
    await open(page, "/research/IN/NOPESYMBOL");
    await expect(h1(page)).toHaveText("No company page for NOPESYMBOL", { timeout: 30_000 });
    await expect(page.locator("main")).not.toContainText("Sign in to see NOPESYMBOL");
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, follow");
    await open(page, "/research/XX/TCS");
    await expect(h1(page)).toHaveText("Page not found", { timeout: 30_000 });
    await open(page, "/holdings");
    await expect(h1(page)).toHaveText("Sign in to see Holdings", { timeout: 30_000 });
    await expect(page).toHaveTitle("Sign in · Holdings · StratLab");
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://stratlab.studio/holdings");
  });

  test("a page that isn't there has places to go", async ({ page }) => {
    await open(page, "/nowhere-at-all");
    await expect(h1(page)).toHaveText("Page not found", { timeout: 30_000 });
    const nav = page.getByRole("navigation", { name: "Places to go" });
    for (const [name, href] of [["Plans", "/pricing"], ["Questions", "/faq"], ["Strategy library", "/library"], ["Contact us", "/contact"]] as const)
      await expect(nav.getByRole("link", { name: new RegExp(`^${name}`) })).toHaveAttribute("href", href);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, follow");
  });
});

test.describe("keyboard, landmarks and small targets (R5V-016, R5V-017)", () => {
  test("a skip link is the first stop; the policies sit in a main landmark", async ({ page }) => {
    await open(page);
    await expect(page.locator(".lp-nav")).toBeVisible({ timeout: 30_000 });         // the page itself, not the plain start-up text it replaces
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("main#main")).toBeFocused();
    for (const p of ["/terms", "/privacy", "/refunds", "/contact"]) {
      await open(page, p);
      await expect(page.locator("main")).toHaveCount(1);
      await expect(h1(page)).toBeVisible({ timeout: 30_000 });
    }
  });

  test("the footer links and FAQ rows are at least 40px high", async ({ page }) => {
    await open(page);
    const low = await page.evaluate(() => Array.from(document.querySelectorAll(".lp-foot .legal-links a, .lp-faq summary")).map((el) => Math.round(el.getBoundingClientRect().height)).filter((h) => h < 40));
    expect(low).toEqual([]);
  });
});

test.describe("what a visitor's browser loads and keeps (R5V-020, R5V-022)", () => {
  test("a policy page doesn't download the app or the sign-in library", async ({ page }) => {
    const js: { url: string; size: number }[] = [];
    page.on("response", async (r) => { if (/\.js(\?|$)/.test(r.url()) && r.ok()) js.push({ url: r.url(), size: (await r.body().catch(() => Buffer.alloc(0))).length }); });
    await open(page, "/terms");
    await expect(h1(page)).toHaveText("Terms of service", { timeout: 30_000 });
    await page.waitForLoadState("networkidle");
    const total = js.reduce((a, b) => a + b.size, 0);
    expect(total, `${Math.round(total / 1024)} KB of JavaScript: ${js.map((j) => j.url.split("/").pop()).join(", ")}`).toBeLessThan(400 * 1024);
    expect(js.some((j) => /\/(auth|account|main)-/.test(j.url)), "the sign-in library or the app came with a policy page").toBe(false);
  });

  test("the landing page is lighter than before and loads no sign-in library until someone signs in", async ({ page }) => {
    const js: { url: string; size: number }[] = [];
    page.on("response", async (r) => { if (/\.js(\?|$)/.test(r.url()) && r.ok()) js.push({ url: r.url(), size: (await r.body().catch(() => Buffer.alloc(0))).length }); });
    await open(page);
    await expect(h1(page)).toBeVisible({ timeout: 30_000 });
    await page.waitForLoadState("networkidle");
    const total = js.reduce((a, b) => a + b.size, 0);
    expect(total, `${Math.round(total / 1024)} KB: ${js.map((j) => j.url.split("/").pop()).join(", ")}`).toBeLessThan(450 * 1024);
    expect(js.some((j) => /\/(auth|account|main)-/.test(j.url))).toBe(false);
  });

  test("with analytics on, a visitor's browser keeps one ph_ entry; with Do Not Track or Global Privacy Control, none and nothing is sent", async ({ browser }) => {
    const run = async (init: () => void) => {
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      const sent: string[] = [];
      page.on("request", (r) => { if (/posthog/i.test(r.url())) sent.push(r.url()); });
      await page.addInitScript(() => {
        Object.defineProperty(Navigator.prototype, "webdriver", { get: () => false });
        Object.defineProperty(Navigator.prototype, "userAgent", { get: () => "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36" });
      });
      await page.addInitScript(init);
      await open(page, "/", { config: config(',POSTHOG_KEY:"phc_test"') });
      await expect(h1(page)).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(4500);
      const keys = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("ph_")));
      await ctx.close();
      return { keys, sent };
    };
    const normal = await run(() => undefined);
    expect(normal.keys, "analytics storage is set before sign-in (the Privacy page says so)").toEqual(["ph_phc_test_posthog"]);
    const dnt = await run(() => Object.defineProperty(Navigator.prototype, "doNotTrack", { get: () => "1" }));
    expect(dnt.keys).toEqual([]);
    expect(dnt.sent).toEqual([]);
    const gpc = await run(() => Object.defineProperty(Navigator.prototype, "globalPrivacyControl", { get: () => true }));
    expect(gpc.keys).toEqual([]);
    expect(gpc.sent).toEqual([]);
  });

  test("the Privacy page names the storage and every AI provider; Contact lists the owner's address and GSTIN only when they are set", async ({ page }) => {
    await open(page, "/privacy");
    const main = page.locator("main");
    await expect(main.getByRole("heading", { name: "Cookies and storage" })).toBeVisible({ timeout: 30_000 });
    await expect(main).toContainText("Before you sign in");
    await expect(main).toContainText("ph_");
    await expect(main).toContainText("not to any account");
    await expect(main).toContainText("any of these thirteen: Anthropic, Cerebras, Cloudflare Workers AI");
    await expect(main).not.toContainText("such as Groq");
    await open(page, "/contact");
    await expect(page.locator("main")).not.toContainText(/GSTIN|Address:/, { timeout: 30_000 });
    await open(page, "/contact", { config: config(',BUSINESS_ADDRESS:"1 Example Road, Pune 411001",BUSINESS_GSTIN:"27AAAAA0000A1Z5"') });
    await expect(page.locator("main")).toContainText("Address: 1 Example Road, Pune 411001", { timeout: 30_000 });
    await expect(page.locator("main")).toContainText("GSTIN: 27AAAAA0000A1Z5");
  });

  test("config.js reaches the page with no notes in it", async ({ request }) => {
    const r = await request.get("/config.js");
    const text = await r.text();
    expect(text).not.toMatch(/(^|\s)\/\/|\/\*/m);
  });
});
