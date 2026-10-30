import { expect, type Locator, type Page } from "@playwright/test";

// The helpers the pages-*.spec.ts files share: signing in as the fake world's users, opening a page, the checks every page must pass.
// They were the top of one pages.spec.ts of 1,860 lines, split so the browser tests spread evenly over CI's shards (Playwright
// shards by file, and that file was 11 minutes on one runner, the longest shard's whole time).

// Signed in as the site owner (the fake database's admin-token), with the tour already seen.
export const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

/** Signed in as another of the fake database's users instead (free-token, basic-token, ...). */
export function sessionAs(token: string, id: string, email: string) {
  return { ...session, access_token: token, user: { ...session.user, id, email } };
}

/** A first visit asks what the person came for; answer it like a new user would (if it's asked). */
export async function answerWelcome(page: Page, choice: RegExp = /All of it/) {
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("dialog").getByRole("button", { name: choice }).first().click()).catch(() => undefined);
}

export async function open(page: Page, path: string, ready: string, who: typeof session = session) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    // fallback: a test's own route for a backend call (registered before this) still gets its turn
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(path);
  await answerWelcome(page);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);
  return errors;
}

/** What every page must get right: no crash, nothing wider than the screen, no broken numbers. */
export async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  await expect(page.getByText(/couldn't load your account|can't reach the StratLab server/i), "the page couldn't reach the server").toHaveCount(0);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\b0k\b/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
}

/** On a phone: every button, menu and stand-alone link is big enough for a finger (small icons that carry a larger
 * invisible touch area are left out). */
export async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true]")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || (el as HTMLInputElement).placeholder || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

/** Opens every "Earlier ..." fold on the page (past dates and finished things sit folded under one line). */
export async function openEarlier(page: Page) {
  for (const fold of await page.locator("details.earlier:not([open]) > summary").all()) await fold.click();
}

/** Waits for something that may sit in a fold, opening folds as the page fills in. */
export async function seeUnfolded(page: Page, what: ReturnType<Page["locator"]>) {
  await expect(async () => { await openEarlier(page); await expect(what).toBeVisible({ timeout: 1000 }); }).toPass({ timeout: 30_000 });
}

/** Bars for gains end at the zero line from above; bars for losses start at it and hang below. */
export async function barsAroundZero(page: Page) {
  const charts = page.locator(".tbars");
  expect(await charts.count()).toBeGreaterThan(0);
  let losses = 0;
  for (const chart of await charts.all()) {
    if (!(await chart.locator(".tbar-zero").count())) continue;        // no losses in this chart: no zero line drawn
    const zero = await chart.locator(".tbar-zero").first().boundingBox();
    for (const bar of await chart.locator(".tbar-bar").all()) {
      const v = Number(await bar.getAttribute("data-v"));
      const b = await bar.boundingBox();
      if (!b || !zero) continue;
      if (v < 0) { losses++; expect(Math.abs(b.y - zero.y), "a loss bar starts at the zero line").toBeLessThan(2); }
      else expect(Math.abs(b.y + b.height - zero.y), "a gain bar ends at the zero line").toBeLessThan(2);
    }
  }
  expect(losses, "loss years are drawn").toBeGreaterThan(0);
}

export const PAGES: [string, string][] = [
  ["/", "Net worth"], ["/trade", "Straddles, strangles"], ["/invest", "Invest home"], ["/money", "Your money"], ["/notebooks", "notebook"], ["/library", "librar"], ["/options", "Options"], ["/trade/positioning", "Participant-wise open interest"], ["/paper", "Paper"],
  ["/research", "Companies"], ["/research/IN/RELIANCE", "Reliance"], ["/research/US/AAPL", "AAPL"], ["/research/IN/RELIANCE/deep", "Growth and margins"],
  ["/research/scan", "Stage 2"], ["/research/screens", "Filter companies by plain facts"], ["/alerts", "Your stock alerts"], ["/research/watchlist", "Companies you're watching"], ["/research/rotation", "rotation"], ["/invest/breadth", "Rose / fell"], ["/invest/etf-gaps", "ETF price against NAV"], ["/research/results", "Results this week and next"], ["/research/corporate-actions", "Dividends, bonuses and splits"], ["/research/investor", "Investor"], ["/holdings", "By sector"], ["/tax-report", "How FY"], ["/money/tax-tools", "Tax tools"], ["/news", "Briefs"], ["/plans", "Plans"],
  ["/account", "Account"], ["/settings", "Where your alerts and emails go"], ["/assistant", "AI assistant"], ["/app", "Get the app"], ["/invite", "Invite friends"],
  ["/admin", "Needs your attention"], ["/admin/data", "Background jobs"], ["/admin/system", "Check every feature"], ["/admin/users", "Paper trading now"],
  ["/admin/money", "Prices outside India"], ["/admin/quality", "Rates and rules"], ["/admin/emails", "Confirm your email"],
];

/** Open "The same working in words" under the tax estimate's table, unless it is already open. The workings are folded until asked for
 *  (LIVE1B-010), so "How we got here" is opened first. */
export async function openWorking(total: Locator) {
  const outer = total.locator("details", { has: total.page().locator("summary", { hasText: "How we got here" }) }).first();
  if (!(await outer.evaluate((d) => (d as HTMLDetailsElement).open))) await outer.locator("summary", { hasText: "How we got here" }).first().click();
  const fold = total.locator("details", { has: total.page().locator("summary", { hasText: "The same working in words" }) }).last();
  if (!(await fold.evaluate((d) => (d as HTMLDetailsElement).open))) await fold.locator("summary", { hasText: "The same working in words" }).click();
}

export const API = process.env.E2E_API ?? "http://127.0.0.1:8765";     // the fake backend (tests/visual_server.py)

export const HOLDINGS_FILES = new URL("../../backend/tests/fixtures/holdings/", import.meta.url).pathname;

/** The first-visit questions stay open over the page until answered; these tests click on the page, so answer them. */
export async function settle(page: Page) {
  const level = page.getByRole("dialog", { name: /How much .* have you done/ });
  await level.waitFor({ timeout: 4000 }).then(() => level.getByRole("button", { name: /done a bit/ }).click()).catch(() => undefined);
  await expect(level).toHaveCount(0);
}

export const TRADEBOOKS = new URL("../../backend/tests/fixtures/tradebooks/", import.meta.url).pathname;
export const TAXPNL = new URL("../../backend/tests/fixtures/taxpnl/", import.meta.url).pathname;

/** The experience question that follows the first one covers the page; answer it before clicking anything. */
export async function answerLevel(page: Page) {
  const ask = page.getByText(/How much (trading|investing) have you done\?/);
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("button", { name: /done a bit/ }).click()).catch(() => undefined);
  await expect(ask).toHaveCount(0);
}

/** Each project signs in as its own user, so two projects running together never set the same alert on the same stock. */
export function ownUser(info: { project: { name: string } }, desktop: number, phone: number) {
  const n = info.project.name === "phone" ? phone : desktop;
  return sessionAs(`load-${n}`, `u-load-${n}`, `load${n}@example.com`);
}

// ---------- the sidebar menu ----------
/** Open an entry's tab (IA-1): the row of tabs on a laptop; on a phone, where that row is folded away, the breadcrumb's menu. */
export async function tab(page: Page, phone: boolean, entry: string, name: string) {
  if (phone) {
    await page.getByRole("navigation", { name: "Breadcrumb" }).locator(".k-crumb-btn").click();
    await page.getByRole("menuitem", { name, exact: true }).click();
  } else await page.getByRole("navigation", { name: entry }).getByRole("link", { name, exact: true }).click();
}
/** On a phone the menu is a drawer: open it. */
export async function menu(page: Page, phone: boolean) {
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 1500 }).catch(() => undefined);   // the experience question
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  const side = page.locator("aside.sidebar");
  await expect(side.getByRole("navigation", { name: "Main" })).toBeVisible();
  return side;
}

// ---------- sharing: company fact cards and invite links ----------
/** Watch what the page shares: the phone's share sheet (stubbed, as headless browsers have none) and the clipboard. */
export async function watchSharing(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __shared: unknown[]; __copied: string[] };
    w.__shared = []; w.__copied = [];
    Object.defineProperty(navigator, "share", { configurable: true, value: async (d: { url?: string; text?: string; files?: File[] }) => {
      w.__shared.push({ url: d.url, text: d.text, files: (d.files ?? []).map((f) => ({ name: f.name, type: f.type, size: f.size })) });
    } });
    Object.defineProperty(navigator, "canShare", { configurable: true, value: () => true });
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (t: string) => { w.__copied.push(t); }, write: async () => undefined } });
  });
}

export type SharedCall = { url: string; files: { type: string; size: number }[] };
export const shared = (page: Page) => page.evaluate(() => (window as unknown as { __shared: SharedCall[] }).__shared);
export const copied = (page: Page) => page.evaluate(() => (window as unknown as { __copied: string[] }).__copied);

/** Phone: the share sheet got the card's link and image. Desktop: the link was copied. Returns the link. */
export async function sharedLink(page: Page, phone: boolean): Promise<string> {
  if (phone) {
    await expect.poll(async () => (await shared(page)).length, { timeout: 30_000 }).toBeGreaterThan(0);
    const s = (await shared(page))[0];
    expect(s.files[0]?.type, "the card image goes with the link").toBe("image/png");
    expect(s.files[0].size).toBeGreaterThan(5000);
    expect(await copied(page), "a phone uses its share sheet, not the clipboard").toEqual([]);
    return s.url;
  }
  await expect.poll(async () => (await copied(page)).length, { timeout: 30_000 }).toBeGreaterThan(0);
  // the toast is one of several live regions on a company page (the AI read's own status row is another)
  const toast = page.getByRole("status").filter({ hasText: "Link copied" });
  await expect(toast).toBeVisible();
  await expect(toast.getByRole("button", { name: "Save the image" })).toBeVisible();
  expect(await shared(page), "a computer copies the link instead of a share sheet").toEqual([]);
  return (await copied(page))[0];
}

export const MF = new URL("../../backend/tests/fixtures/mf/", import.meta.url).pathname;
