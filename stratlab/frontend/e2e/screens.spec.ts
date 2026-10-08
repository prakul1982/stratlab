import { expect, test, type Browser, type Page } from "@playwright/test";

// Every route at a spread of screen sizes, light and dark: nothing scrolls sideways, nothing throws, and on a touch
// screen every control is big enough for a finger. Runs as its own project (see playwright.config.ts).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const WEB = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? 5599}`;
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

const SIZES = [
  { name: "small phone 320x568", width: 320, height: 568, touch: true, theme: "light" },
  { name: "phone 360x780", width: 360, height: 780, touch: true, theme: "dark" },
  { name: "phone 390x844", width: 390, height: 844, touch: true, theme: "light" },
  { name: "large phone 414x896", width: 414, height: 896, touch: true, theme: "dark" },
  { name: "phone landscape 844x390", width: 844, height: 390, touch: true, theme: "dark" },
  { name: "tablet 768x1024", width: 768, height: 1024, touch: true, theme: "light" },
  { name: "tablet landscape 1024x768", width: 1024, height: 768, touch: true, theme: "dark" },
  { name: "laptop 1280x800", width: 1280, height: 800, touch: false, theme: "dark" },
  { name: "laptop 1440x900", width: 1440, height: 900, touch: false, theme: "light" },
  { name: "desktop 1920x1080", width: 1920, height: 1080, touch: false, theme: "light" },
];
// Five sizes on every run; E2E_ALL_SIZES=1 sweeps all ten, each in light and dark (a release check, ~20 minutes).
const VIEWPORTS = process.env.E2E_ALL_SIZES
  ? SIZES.flatMap((s) => (["light", "dark"] as const).map((theme) => ({ ...s, theme })))
  : SIZES.filter((s) => [320, 844, 768, 1280, 1920].includes(s.width));

const EMA = { name: "Trend follower", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
  exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }],
  risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };

/** A notebook with a run, a shared verdict, a paper session and a shared company card, so the pages that show one exist. */
async function seed(request: import("@playwright/test").APIRequestContext) {
  const post = async (path: string, data: object) => {
    const r = await request.post(API + path, { headers: admin, data });
    expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy();
    return r.json();
  };
  await request.put(`${API}/me/prefs`, { headers: admin, data: { level: "some", focus: "both" } });     // no welcome questions
  const nb = await post("/notebooks", { name: "Screens sweep", question: "Does the cross work?", strategy: EMA, instrument: "CRYPTO:BTC-USD" });
  await post(`/notebooks/${nb.id}/experiments`, { days: 1500 });
  await post(`/notebooks/${nb.id}/experiments`, { days: 800 });
  const verdict = await post(`/notebooks/${nb.id}/experiments/1/share`, {});
  const paper = await post("/live/sessions", { strategy: EMA, instrument: "CRYPTO:BTC-USD" });
  const card = await post("/cards/company/IN/RELIANCE", {});
  const app = ["/", "/trade", "/invest", "/money", "/notebooks", "/new", `/n/${nb.id}`, `/n/${nb.id}/market`, `/n/${nb.id}/compare`, `/n/${nb.id}/e/1`, "/import",
    "/library", "/options", "/trade/positioning", "/paper", `/paper/${paper.id}`, "/plans", "/account", "/settings", "/settings#experience", "/settings#accounts", "/settings#check", "/assistant", "/app", "/invite", "/admin", "/admin/users", "/admin/money", "/admin/data", "/admin/quality", "/admin/system", "/admin/emails", "/admin/emails/market_in", "/admin?tab=services", "/news", "/holdings", "/tax-report", "/money/net-worth", "/money/mutual-funds", "/money/tax-tools", "/money/calendar", "/alerts", "/research", "/research/themes", "/research/pulse",
    "/research/compare", "/research/watchlist", "/research/scan", "/research/scan?scan=high52", "/research/filings?view=all", "/research/filings?region=US&view=all", "/invest/holders?region=US", "/research/screens", "/research/rotation", "/research/filings", "/invest/breadth", "/invest/etf-gaps",
    "/research/results", "/research/investor", "/research/IN/RELIANCE", "/research/US/AAPL", "/research/IN/RELIANCE/deep",
    "/research/US/AAPL/deep",
    // corporate actions (the calendar, both scopes and the US), a company with a bonus and dividend ahead and deals,
    // and Admin's Users tab, which holds the invite rewards waiting for review
    "/research/corporate-actions", "/research/corporate-actions?scope=all", "/research/corporate-actions?region=US&scope=all",
    "/research/IN/TCS", "/research/IN/TCS/deep", "/invite"].map((p) => ({ url: WEB + p, label: p, signedIn: true }));
  const open = ["/terms", "/privacy", "/refunds", "/contact", `/verdict/${verdict.token}`].map((p) => ({ url: WEB + p, label: p, signedIn: false }));
  const landing = { url: WEB + "/", label: "/ (signed out)", signedIn: false };
  const api = ["/stocks/in/RELIANCE", "/stocks/us/AAPL", `/c/${card.token}`].map((p) => ({ url: API + p, label: p, signedIn: false }));
  return [...app, ...open, landing, ...api];
}

/** What's wrong with the page as drawn: sideways scroll (and the widest culprits), and controls too small to tap. */
async function problems(page: Page, touch: boolean): Promise<string[]> {
  return page.evaluate((touch) => {
    const out: string[] = [];
    const vw = window.innerWidth;
    const name = (el: Element) => `${el.tagName.toLowerCase()}${typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/).join(".") : ""} "${(el.textContent || (el as HTMLInputElement).placeholder || "").trim().slice(0, 30)}"`;
    const clipped = (el: Element) => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(p).overflowX)) return true; return false; };
    if (document.documentElement.scrollWidth > vw + 1) {
      const wide = Array.from(document.querySelectorAll("body *")).filter((el) => {
        const b = el.getBoundingClientRect();
        return b.width && b.height && b.right > vw + 1 && !clipped(el);
      }).slice(-3).map(name);
      out.push(`scrolls sideways (${document.documentElement.scrollWidth}px on a ${vw}px screen): ${wide.join(", ")}`);
    }
    if (touch) {
      for (const el of document.querySelectorAll("button, select, a, [role=button], textarea, input:not([type=range]):not([type=checkbox]):not([type=radio]):not([type=hidden])")) {
        const b = el.getBoundingClientRect();
        if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true]")) continue;    // inline in text: the line is the target
        if (el.matches(".info-btn, .chip-x, .sr-only") || getComputedStyle(el).display === "inline") continue;
        if (b.height < 32) out.push(`too small to tap: ${name(el)} ${Math.round(b.height)}px`);
      }
    }
    return out;
  }, touch);
}

let routes: { url: string; label: string; signedIn: boolean }[] = [];
test.beforeAll(async ({ request }) => { routes = await seed(request); });

async function sweep(browser: Browser, vp: (typeof VIEWPORTS)[number]) {
  const found: string[] = [];
  for (const signedIn of [true, false]) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, hasTouch: vp.touch, isMobile: vp.touch && vp.width < 900,
                                           colorScheme: vp.theme as "light" | "dark" });
    await ctx.route("**/*", (r) => {
      const host = new URL(r.request().url()).hostname;
      return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
    });
    await ctx.addInitScript(([s, signedIn, theme]) => {
      if (signedIn) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab-theme", theme as string);
    }, [session, signedIn, vp.theme] as const);
    const page = await ctx.newPage();
    let errors: string[] = [];
    // the sweep's own sign-in script also runs inside Admin's sandboxed email frame, which rightly refuses it localStorage
    page.on("pageerror", (e) => { if (!/allow-same-origin/.test(e.message)) errors.push(e.message); });
    // a refused request the page answers in words (an AI read that couldn't be written) is the page working; a crash isn't
    page.on("console", (m) => { if (m.type() === "error" && !/status of 4\d\d/.test(m.text())) errors.push(m.text()); });
    for (const r of routes.filter((x) => x.signedIn === signedIn)) {
      errors = [];
      await page.goto(r.url);
      await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => undefined);     // paper pages keep polling
      await expect(page.locator(".spinner")).toHaveCount(0, { timeout: 15_000 }).catch(() => found.push(`${r.label} @ ${vp.name}: still loading after 15s`));
      for (const p of [...await problems(page, vp.touch), ...errors.map((e) => `error: ${e.slice(0, 160)}`)]) found.push(`${r.label} @ ${vp.name} (${vp.theme}): ${p}`);
    }
    await ctx.close();
  }
  expect(found, `problems at ${vp.name}`).toEqual([]);
}

test.describe.configure({ mode: "parallel" });       // one size per worker

for (const vp of VIEWPORTS) {
  test(`every route at ${vp.name}, ${vp.theme}`, async ({ browser }) => {
    test.setTimeout(240_000);
    await sweep(browser, vp);
  });
}

test("the search palette fits a landscape phone, and drops the keyboard hints", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true });
  await ctx.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  const page = await ctx.newPage();
  await page.goto(WEB + "/");
  await expect(page.getByRole("button", { name: /^Search or ask anything/ })).toBeVisible({ timeout: 30_000 });      // the app is drawn (a missing box would count as hidden)
  await expect(page.locator(".search-btn kbd").first()).toBeHidden({ timeout: 30_000 });
  await page.keyboard.press("Control+k");
  await expect(page.locator(".palette")).toBeVisible();
  const box = await page.locator(".palette").boundingBox();
  expect(box && box.y + box.height, "the palette's foot is on the screen").toBeLessThanOrEqual(390);
  await ctx.close();
});

test("the sidebar fits a short laptop, a tablet drawer and a phone drawer: slim header and footer, one scrolling menu", async ({ browser }) => {
  for (const vp of [{ width: 1280, height: 720, touch: false }, { width: 1024, height: 768, touch: true }, { width: 768, height: 1024, touch: true }, { width: 390, height: 844, touch: true }]) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, hasTouch: vp.touch, isMobile: vp.touch && vp.width < 900 });
    await ctx.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); localStorage.setItem("stratlab.space", "trade"); }, session);
    const page = await ctx.newPage();
    await page.goto(WEB + "/notebooks");
    const side = page.locator("aside.sidebar");
    if (vp.width <= 900) await page.getByRole("button", { name: "Open menu" }).click();      // a shut drawer is hidden from the accessibility tree
    await expect(side.getByRole("navigation", { name: "Main" })).toBeAttached({ timeout: 30_000 });
    await expect(side.getByRole("button", { name: /markets open$/ })).toBeVisible({ timeout: 30_000 });
    const at = `${vp.width}x${vp.height}`;
    const m = await side.evaluate((aside) => {
      const h = (sel: string) => aside.querySelector(sel)!.getBoundingClientRect();
      const nav = aside.querySelector(".side-groups")!;
      return { top: h(".side-top").height, foot: h(".side-foot").height, footBottom: h(".side-foot").bottom, nav: nav.clientHeight,
        asideOverflow: aside.scrollHeight - aside.clientHeight, navSideways: nav.scrollWidth - nav.clientWidth, width: aside.getBoundingClientRect().width };
    });
    expect(m.top, `${at}: the header stays slim`).toBeLessThanOrEqual(vp.touch ? 230 : 200);
    expect(m.foot, `${at}: the footer stays slim`).toBeLessThanOrEqual(100);
    expect(m.footBottom, `${at}: the footer is on the screen`).toBeLessThanOrEqual(vp.height + 1);
    expect(m.nav, `${at}: the menu keeps most of the height`).toBeGreaterThanOrEqual(vp.height - 340);
    expect(m.asideOverflow, `${at}: only the menu scrolls`).toBeLessThanOrEqual(0);
    expect(m.navSideways, `${at}: nothing in the menu is cut off sideways`).toBeLessThanOrEqual(0);
    if (vp.width > 900) expect(m.width, `${at}: the sidebar's width`).toBeLessThanOrEqual(260);
    await ctx.close();
  }
});

/** Geometry on a 400px window, in a plain (not "mobile") browser so the page cannot quietly widen itself: the page must not
 * scroll sideways, and no text may spill out of the box that holds it. Boxes that scroll on purpose (a table, a chip bar)
 * and chart drawings are left out. */
async function spills(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const vw = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth > vw + 1) out.push(`the page is ${document.documentElement.scrollWidth}px wide on a ${vw}px window`);
    const label = (el: Element) => `${el.tagName.toLowerCase()}${typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/).join(".") : ""} "${(el.textContent || "").trim().slice(0, 40)}"`;
    const scrolls = (el: Element) => { for (let p: Element | null = el; p && p !== document.body; p = p.parentElement) if (/(auto|scroll)/.test(getComputedStyle(p).overflowX) || /(auto|scroll)/.test(getComputedStyle(p).overflowY)) return true; return false; };
    for (const el of Array.from(document.querySelectorAll("body *"))) {
      if (el.closest("svg, canvas, .sr-only, [hidden], .k-chipbar, .k-tbl-wrap, .info-pop, .popover") || el.matches(".sr-only")) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "inline" || cs.display === "none" || cs.visibility === "hidden" || !el.clientWidth) continue;
      const own = [...el.childNodes].filter((n) => n.nodeType === 3 && (n.textContent || "").trim());
      if (!own.length) continue;                                                                          // its own words only
      const box = el.getBoundingClientRect();
      if (box.right <= 1 || box.left >= vw) continue;                                                      // the menu drawer, parked off the screen
      const range = document.createRange();
      let right = 0;
      for (const n of own) { range.selectNodeContents(n); right = Math.max(right, range.getBoundingClientRect().right); }
      if (right > box.right + 1 && cs.textOverflow !== "ellipsis" && !scrolls(el)) out.push(`text spills out of ${label(el)} (${Math.round(right)}px in a box ending at ${Math.round(box.right)}px)`);
      if (box.right > vw + 1 && !scrolls(el)) out.push(`${label(el)} reaches ${Math.round(box.right)}px on a ${vw}px window`);
    }
    return out.slice(0, 8);
  });
}

test("every route at 400px: the page never scrolls sideways and no text spills out of its box", async ({ browser }) => {
  test.setTimeout(360_000);
  const found: string[] = [];
  for (const signedIn of [true, false]) {
    const ctx = await browser.newContext({ viewport: { width: 400, height: 860 }, colorScheme: "light" });
    await ctx.route("**/*", (r) => {
      const host = new URL(r.request().url()).hostname;
      return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
    });
    await ctx.addInitScript(([s, signedIn]) => {
      if (signedIn) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
      localStorage.setItem("stratlab.tour.v1", "1");
    }, [session, signedIn] as const);
    const page = await ctx.newPage();
    for (const r of routes.filter((x) => x.signedIn === signedIn && x.url.startsWith(WEB))) {
      await page.goto(r.url);
      await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => undefined);
      await expect(page.locator(".spinner")).toHaveCount(0, { timeout: 15_000 }).catch(() => found.push(`${r.label}: still loading after 15s`));
      for (const p of await spills(page)) found.push(`${r.label}: ${p}`);
    }
    await ctx.close();
  }
  expect(found, "geometry problems at 400px").toEqual([]);
});
