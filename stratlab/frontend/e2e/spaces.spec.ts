import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { NAV_GROUPS } from "../src/lib/navGroups";
import { NAV } from "../src/lib/nav";

// The three spaces: Trade (the strategy lab), Invest and Money. The switcher at the top of the menu, the welcome
// question that picks the first space, each space's home, deep links opening their own space, and search labelling
// results by space. Each test signs in as its own fake user (one per project), so choices saved here touch no other test.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };

/** A fake user for this test and project: load-N on desktop, load-(N+1) on a phone. */
function who(n: number, phone: boolean) {
  const i = n + (phone ? 1 : 0);
  return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` };
}
const ADMIN = { token: "admin-token", id: "u-admin", email: "owner@example.com" };
type Who = typeof ADMIN;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });

/** Signed in as `u`, tour seen; answers nothing, so a test can look at the welcome question itself. */
async function signIn(page: Page, u: Who, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: u.token, user: { id: u.id, aud: "authenticated", email: u.email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}

const prefs = async (request: APIRequestContext, u: Who) => (await (await request.get(`${API}/me`, { headers: auth(u) })).json()).prefs;

/** On a phone the menu is a drawer: open it. */
async function menu(page: Page, phone: boolean) {
  if (phone) await expect(async () => {
      if (!(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
      await expect(page.locator("aside.sidebar.open")).toBeInViewport({ timeout: 1500 });
    }).toPass({ timeout: 15_000 });
  const side = page.locator("aside.sidebar");
  await expect(side.getByRole("navigation", { name: "Main" })).toBeVisible();
  return side;
}

/** No crash, nothing wider than the screen, no broken numbers, no advice words; on a phone, big enough to tap. */
async function sane(page: Page, errors: string[], phone: boolean) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /yahoo|finnhub|screener\.in|kite connect/i,
    /\byou should\b/i, /\b(buy|sell|hold) (this|now)\b/i, /\btarget price\b/i]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio]), aside .space-switch button"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true]")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

/** The group titles in the menu, in order (each is a link to the group's own page). */
const groups = (side: ReturnType<Page["locator"]>) => side.getByRole("navigation", { name: "Main" }).locator(".side-group .side-title");
const labelsOf = (space: "trade" | "invest" | "money") => NAV[space].groups.map((g) => g.label);

test("spaces: the switcher goes to a space's home and shows its groups, Mine shows its own menu, and the choice is kept", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(230, phone);
  await request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus: "trade" } });     // came to trade
  const errors = await signIn(page, u, "/");
  // `/` opens the space's home: Trade, with Options first
  await expect(page).toHaveURL(/\/trade$/, { timeout: 30_000 });
  await expect(page.locator(".space-card-lead")).toContainText("Options");
  let side = await menu(page, phone);
  const space = side.getByRole("radiogroup", { name: "Space" });
  await expect(space.getByRole("radio")).toHaveText(["Mine", "Trade", "Invest", "Money"]);
  await expect(space.getByRole("radio", { name: "Trade" })).toHaveAttribute("aria-checked", "true");
  await expect(groups(side)).toHaveText(labelsOf("trade"));
  for (const g of NAV.trade.groups) await expect(side.locator(`[data-group="${g.id}"] > .side-nav > .side-entry > a`)).toHaveText(g.pages.map((p) => p.label));
  // the space's main action is a normal-sized button, not a banner
  const action = side.getByRole("button", { name: "New notebook" });
  await expect(action).toBeVisible();
  expect((await action.boundingBox())!.height).toBeLessThanOrEqual(40);

  // Money: a click goes to the space's home, and its menu has its three groups; the Money features come from the one list
  await space.getByRole("radio", { name: "Money" }).click();
  await expect(page).toHaveURL(/\/money$/);
  if (phone) side = await menu(page, phone);
  await expect(space.getByRole("radio", { name: "Money" })).toHaveAttribute("aria-checked", "true");
  await expect(groups(side)).toHaveText(labelsOf("money"));
  await expect(side.locator('[data-group="what-you-own"] .side-nav a')).toHaveText(["Net worth", "Holdings", "Mutual funds"]);
  expect(NAV.money.groups.flatMap((g) => g.pages.map((p) => p.to)).sort(), "every Money feature is in the menu").toEqual(NAV_GROUPS.Money.map((e) => e.to).sort());
  await expect(side.getByRole("link", { name: "Money home" })).toHaveAttribute("href", "/money");
  // kept on the account and on this device
  await expect.poll(async () => (await prefs(request, u)).space).toBe("money");
  expect(await page.evaluate(() => localStorage.getItem("stratlab.space"))).toBe("money");
  if (phone) await sane(page, errors, phone);

  // clicking the space that is already showing goes to its home too
  await page.goto("/money/tax-tools");
  side = await menu(page, phone);
  await side.getByRole("radiogroup", { name: "Space" }).getByRole("radio", { name: "Money" }).click();
  await expect(page).toHaveURL(/\/money$/);

  // Mine: its own menu, not the groups
  if (phone) await expect(page.locator("aside.sidebar.open")).toHaveCount(0);     // the drawer closes after a pick
  side = await menu(page, phone);
  await side.getByRole("radiogroup", { name: "Space" }).getByRole("radio", { name: "Mine" }).click();
  await expect(page).toHaveURL(/\/mine$/);
  if (phone) await expect(page.locator("aside.sidebar.open")).toHaveCount(0);
  side = await menu(page, phone);
  await expect(side.getByRole("link", { name: "My space" })).toHaveAttribute("href", "/mine");
  await expect(groups(side)).toHaveText(["Pinned"]);
  await expect(side.getByRole("link", { name: "Briefs" })).toHaveAttribute("href", "/news");
  await expect(side.getByRole("link", { name: "Connected accounts" })).toHaveAttribute("href", "/settings#accounts");
  await expect(side.getByRole("link", { name: "AI assistant" })).toHaveAttribute("href", "/assistant");
  await expect.poll(async () => (await prefs(request, u)).space).toBe("all");       // the server still calls it "all"
  expect(await page.evaluate(() => localStorage.getItem("stratlab.space"))).toBe("mine");

  // after a reload, and on a new device (nothing saved in the browser), the menu is still Mine
  await page.reload();
  side = await menu(page, phone);
  await expect(side.getByRole("radio", { name: "Mine" })).toHaveAttribute("aria-checked", "true");
  await page.evaluate(() => localStorage.removeItem("stratlab.space"));
  await page.reload();
  side = await menu(page, phone);
  await expect(side.getByRole("radio", { name: "Mine" })).toHaveAttribute("aria-checked", "true");
  // in Mine, a page that is neither pinned nor one of its own links opens its own space's menu
  await page.goto("/research/pulse");
  side = await menu(page, phone);
  await expect(side.getByRole("radio", { name: "Invest" })).toHaveAttribute("aria-checked", "true");
  await expect(side.locator('[data-group="market-view"] .side-toggle')).toHaveAttribute("aria-expanded", "true");
  await sane(page, errors, phone);
});

test("spaces: a deep link opens its own space, without changing the account's choice", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(232, phone);
  await request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus: "invest" } });
  const errors = await signIn(page, u, "/");
  await expect(page).toHaveURL(/\/invest$/, { timeout: 30_000 });
  for (const [path, ready, name] of [["/holdings", "Your stocks, at today", "Money"], ["/tax-report", "Capital gains on your shares", "Money"], ["/options", "Options", "Trade"],
    ["/library", "librar", "Trade"], ["/research/IN/TCS", "TCS", "Invest"], ["/alerts", "Your stock alerts", "Invest"], ["/account", "Account", "Mine"], ["/settings", "Settings", "Mine"], ["/assistant", "AI assistant", "Mine"], ["/app", "Get the app", "Mine"], ["/invite", "Invite friends", "Mine"]] as const) {
    await page.goto(path);
    await expect(page.locator("main").getByText(ready).first()).toBeVisible({ timeout: 30_000 });
    const side = await menu(page, phone);
    await expect(side.getByRole("radio", { name }), `${path} opens in ${name}`).toHaveAttribute("aria-checked", "true");
    if (name === "Money") await expect(side.getByRole("link", { name: path === "/holdings" ? "Holdings" : "Tax report", exact: true })).toHaveClass(/active/);
  }
  // a deep link only switches the menu on this device; `/` still opens the space the person picked
  expect((await prefs(request, u)).space ?? null).toBeNull();
  // picking a space in the switcher makes it the home
  const side = await menu(page, phone);
  await side.getByRole("radio", { name: "Money" }).click();
  await expect(page).toHaveURL(/\/money$/);
  await expect.poll(async () => (await prefs(request, u)).space).toBe("money");
  await page.goto("/");
  await expect(page).toHaveURL(/\/money$/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Your money" })).toBeVisible();
  await sane(page, errors, phone);
});

test("onboarding: one short step asks what brings you here, with the experience, and opens that space", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(234, phone);
  expect((await prefs(request, u)).focus ?? null, "a brand-new account").toBeNull();
  const errors = await signIn(page, u, "/");
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  await expect(welcome).toBeVisible({ timeout: 30_000 });
  await expect(welcome.getByRole("button", { name: /^(Trade|Invest|Manage my money|All of it)/ })).toHaveCount(4);
  await expect(welcome.locator(".explore-card b")).toHaveText(["Trade", "Invest", "Manage my money", "All of it"]);
  const exp = welcome.getByRole("radiogroup", { name: "Experience" });
  await expect(exp.getByRole("radio", { name: "I've done a bit" })).toHaveAttribute("aria-checked", "false");      // nothing is picked for them
  if (phone) for (const el of await welcome.locator(".explore-card, [role=radio]").all()) {
    const b = await el.boundingBox();
    if (b && b.height) expect(b.height, `"${(await el.innerText()).slice(0, 30)}" is too small to tap`).toBeGreaterThanOrEqual(32);
  }
  await exp.getByRole("radio", { name: "I do this actively" }).click();
  await welcome.getByRole("button", { name: /Manage my money/ }).click();
  // one answer, one step: no second question, and the Money home opens
  await expect(welcome).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(/\/money$/);
  await expect(page.getByRole("heading", { name: "Your money" })).toBeVisible();
  await expect.poll(() => prefs(request, u)).toEqual({ level: "pro", focus: "money", space: "money" });
  const side = await menu(page, phone);
  await expect(side.getByRole("radio", { name: "Money" })).toHaveAttribute("aria-checked", "true");
  await expect(side.getByRole("button", { name: "Add your holdings" })).toBeVisible();
  // answered once: not asked again
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your money" })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  await expect(page.getByRole("dialog", { name: "What brings you here?" })).toHaveCount(0);
  await sane(page, errors, phone);
});

test("space homes: Trade with Options first, Invest at a glance, Money with holdings, tax and its tools", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  // the owner: holdings and tradebooks are loaded by the fake world, and Basic tools are on
  const errors = await signIn(page, ADMIN, "/trade");
  await page.getByRole("button", { name: /All of it/ }).click({ timeout: 4000 }).catch(() => undefined);   // first visit of the run
  await page.goto("/trade");     // "All of it" opens My space now; this test is about the Trade home
  await expect(page.locator(".space-strip")).toBeVisible({ timeout: 30_000 });
  const strip = page.locator(".space-strip > a");
  await expect(strip.first()).toContainText("Options");
  await expect(strip.first()).toHaveAttribute("href", "/options");
  await expect(page.getByTestId("paper-summary")).toBeVisible({ timeout: 30_000 });     // the status, once its placeholder is gone
  // the one next step: start a first notebook, or pick up the latest ones
  await expect(page.getByRole("heading", { name: /Start here|Pick up where you left off/ })).toBeVisible();
  await sane(page, errors, phone);

  await page.goto("/invest");
  await expect(page.getByRole("heading", { name: "Which company do you want to look into?" })).toBeVisible({ timeout: 30_000 });
  for (const t of ["Your watchlist", "Results today", "Red flags in your holdings and watchlist"]) await expect(page.getByText(t, { exact: true }).first()).toBeVisible();
  await expect(page.locator(".panel-skel")).toHaveCount(0, { timeout: 30_000 });
  await sane(page, errors, phone);

  await page.goto("/money");
  await expect(page.getByRole("heading", { name: "Your money" })).toBeVisible({ timeout: 30_000 });
  const holdings = page.getByTestId("holdings-summary");
  await expect(holdings).toContainText(/Value · \d+ stocks/, { timeout: 30_000 });
  await expect(holdings).toContainText("₹");
  await expect(holdings.locator(".as-of")).toContainText("as of");
  const tax = page.getByTestId("tax-summary");
  await expect(tax).toContainText(/Capital gains tax, FY ?\d{4}/, { timeout: 30_000 });
  await expect(tax).toContainText("Assumes only the sales in the tradebooks you uploaded");       // every estimate says what it assumes
  await expect(tax.locator(".as-of")).toContainText("as of");
  // one card per Money feature that exists, and nothing for one that doesn't yet
  const cards = page.locator("[data-money]");
  await expect(cards).toHaveCount(NAV_GROUPS.Money.length);
  for (const e of NAV_GROUPS.Money) await expect(page.locator(`[data-money="${e.to}"]`)).toContainText(e.label);
  await sane(page, errors, phone);
  await cards.first().click();
  await expect(page).toHaveURL(new RegExp(NAV_GROUPS.Money[0].to + "$"));
});

/** How a space home is laid out: every section's left and right edges, the tool strip's cards and rows, figures whose
 * numbers don't share a line, and figures showing a bare dash. */
async function layout(page: Page) {
  return page.evaluate(() => {
    const box = (el: Element) => el.getBoundingClientRect();
    const shown = (el: Element) => { const b = box(el); return b.width > 0 && b.height > 0; };
    const home = document.querySelector(".space-home")!;
    const edges = Array.from(home.children).filter(shown).map((el) => [Math.round(box(el).left), Math.round(box(el).right)].join("-"));
    const strip = document.querySelector(".space-strip");
    const rows: Record<number, { right: number; heights: number[]; widths: number[] }> = {};
    const cards = strip ? Array.from(strip.children).filter(shown) : [];
    for (const a of cards) {
      const b = box(a), top = Math.round(b.top);
      rows[top] ??= { right: 0, heights: [], widths: [] };
      rows[top].right = Math.max(rows[top].right, Math.round(b.right));
      rows[top].heights.push(Math.round(b.height));     // the lead card too: it stands out by its tint, not its size
      rows[top].widths.push(Math.round(b.width));
    }
    // in a row of figures, the numbers share one line however their labels wrap
    const offLine: string[] = [];
    for (const figs of document.querySelectorAll(".k-stats")) {
      const tops: Record<number, number[]> = {};
      for (const f of Array.from(figs.children)) {
        const v = f.children[1];
        if (!v) continue;
        const fb = box(f);
        (tops[Math.round(fb.top)] ??= []).push(Math.round(box(v).top));
      }
      for (const t of Object.values(tops)) if (Math.max(...t) - Math.min(...t) > 1) offLine.push(t.join("/"));
    }
    const dashes = Array.from(document.querySelectorAll(".k-stat .k-stat-v")).filter((b) => /^\s*[-–—]\s*$/.test(b.textContent ?? "")).length;
    return { edges: Array.from(new Set(edges)), stripRight: strip ? Math.round(box(strip).right) : 0, cards: cards.length, rows: Object.values(rows), offLine, dashes };
  });
}

test("space homes line up: one content width, four equal tool cards without holes, each tool linked once, no bare dashes", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  // a new account (no notebooks yet: the Trade home embeds New notebook) and the owner (notebooks, holdings, tax)
  for (const [u, paths] of [[who(236, phone), ["/trade"]], [ADMIN, ["/trade", "/invest", "/money"]]] as const) {
    const errors = await signIn(page, u, paths[0]);
    await page.getByRole("button", { name: /All of it/ }).click({ timeout: 4000 }).catch(() => undefined);   // a first visit's question
    for (const path of paths) {
      await page.goto(path);
      await expect(page.locator(".space-home")).toBeVisible({ timeout: 30_000 });
      await expect(page.locator(".space-home .spinner")).toHaveCount(0, { timeout: 30_000 });
      await expect(page.locator(".space-home .panel-skel, .space-home .skel")).toHaveCount(0, { timeout: 30_000 });   // placeholders, not "Loading…" text
      const at = `${u.email} ${path}`;
      const l = await layout(page);
      expect(l.edges, `${at}: every section shares the same left and right edges`).toHaveLength(1);
      expect(l.offLine, `${at}: numbers in a row of figures share a line`).toEqual([]);
      expect(l.dashes, `${at}: a missing figure says why instead of a dash`).toBe(0);
      // every space: four tools, one row of four or two rows of two, every card the same size
      if (path === "/money") expect(l.cards, `${at}: Money has no strip: its two summaries stand for Holdings and Tax, the cards below are the rest`).toBe(0);
      else expect(l.cards, `${at}: four tools on the strip`).toBe(4);
      if (path !== "/money") expect([1, 2], `${at}: the strip is one row, or two by two`).toContain(l.rows.length);
      const heights = l.rows.flatMap((r) => r.heights), widths = l.rows.flatMap((r) => r.widths);
      expect(Math.max(...heights) - Math.min(...heights), `${at}: tool cards are the same height`).toBeLessThanOrEqual(1);
      expect(Math.max(...widths) - Math.min(...widths), `${at}: tool cards are the same width`).toBeLessThanOrEqual(1);
      for (const r of l.rows) {
        expect(r.heights.length, `${at}: rows of the strip have no holes`).toBe(4 / l.rows.length);
        expect(r.right, `${at}: each row of the tool strip reaches its right edge`).toBeGreaterThanOrEqual(l.stripRight - 1);
      }
      if (path === "/trade") {
        // each tool once: the strip's card, not again as a card, a button or a "what you can do" entry
        await expect(page.locator('main a[href="/trade/positioning"]')).toHaveCount(1);
        expect(await page.locator("main").getByRole("button", { name: /Import a strategy/ }).count(), `${at}: Import offered at most once`).toBeLessThanOrEqual(1);
        await expect(page.locator(".explore-card").filter({ hasText: /^(Strategy library|Paper trade options|Paper trade|Test an idea)/ })).toHaveCount(0);
      }
      if (path === "/invest") {
        await expect(page.locator(".explore-card").filter({ hasText: /^(Red flags in my watchlist|My watchlist at a glance)/ })).toHaveCount(0);
      }
      await sane(page, errors, phone);
    }
  }
});

test("search labels each result with its space", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await signIn(page, ADMIN, "/research");
  await page.getByRole("button", { name: /All of it/ }).click({ timeout: 4000 }).catch(() => undefined);
  await expect(page.getByText("Companies").filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: phone ? "Search or ask anything" : /Ask or do anything/ }).first().click();
  const box = page.getByRole("dialog", { name: "Ask or do anything" });
  await box.getByLabel("Search or ask anything").fill("tax report");
  await expect(box.getByRole("option", { name: /Tax report/ }).first().locator(".space-tag")).toHaveText("Money");
  await box.getByLabel("Search or ask anything").fill("options");
  await expect(box.getByRole("option", { name: /^Options builder/ }).locator(".space-tag")).toHaveText("Trade");
  await box.getByLabel("Search or ask anything").fill("sector rotation");
  await expect(box.getByRole("option", { name: /^Sector rotation/ }).first().locator(".space-tag")).toHaveText("Invest");
  await box.getByLabel("Search or ask anything").fill("money");
  await box.getByRole("option", { name: /^Money/ }).first().click();
  await expect(page).toHaveURL(/\/money$/);
  expect(errors).toEqual([]);
});
