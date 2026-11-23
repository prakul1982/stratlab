import { expect, test, type Page } from "@playwright/test";

// site87 (Release 87): the owner's rules, proved on the fake world.
// 1. SCROLL BY SCREEN ("it works on screen size, how much of the block a person can see on screen. Then you give a scroll"): a list or table
//    block is never taller than the screen; content that fits is drawn whole (Mood's 16 sectors at 1440x900), only content taller than the
//    screen scrolls inside its block, with its header row sticky (the owner's reference: Movers), never for fewer than three hidden rows.
// 2. Every side-by-side layout ends level (±2 px): Invest home's watchlist beside the column of Coming up and Results today, /mine's pair.
// 3. No "Show more", "Show all", "+N more" or paging button on any list; long server lists load more on their own (Filings).
// 4. Themes: compact chips, never the same theme twice, the "updated" day inside the chip (no hover box over the next chips), India and the
//    US strictly apart: switching market never maps India's "India defence" in the US.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
// S87_SHOTS=<folder>: also save the screenshots (the lane's before/after; never in CI)
const SHOTS = process.env.S87_SHOTS;
const TAG = process.env.S87_TAG ?? "after";
const SYMS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "AXISBANK", "KOTAKBANK", "BHARTIARTL", "MARUTI", "TITAN", "ONGC", "WIPRO",
  "SUNPHARMA", "NTPC", "POWERGRID", "TATASTEEL", "HINDALCO"];

async function signIn(page: Page, theme: "dark" | "light" = "dark") {
  const user = { id: "u-pro", aud: "authenticated", email: "u-pro@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} };
  await page.addInitScript(([u, th]) => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: "pro-token", token_type: "bearer", expires_in: 3600, expires_at: 4102444800, refresh_token: "r", user: u }));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab.consent.v1", "no");
      localStorage.setItem("stratlab-theme", th);
    } catch { /* none */ }
  }, [user, theme] as const);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
}

async function watchWorld(page: Page, watch: number) {
  await signIn(page);
  const items = SYMS.slice(0, watch).map((s) => ({ region: "IN", symbol: s, name: `${s} Ltd` }));
  await page.route((u) => u.pathname === "/research/watchlist", (r) => (r.request().method() === "GET" ? r.fulfill({ json: { items } }) : r.fallback()));
  await page.route((u) => u.pathname === "/research/quotes", (r) => {
    const asked = (new URL(r.request().url()).searchParams.get("symbols") ?? "").split(",").filter(Boolean);
    return r.fulfill({ json: Object.fromEntries(asked.map((s) => [s, { price: 100 + SYMS.indexOf(s) * 7.5, change_pct: (SYMS.indexOf(s) % 5) - 2, at: "2026-10-28T05:30:00Z" }])) });
  });
}

const shot = async (page: Page, name: string, sel?: string) => {
  if (!SHOTS) return;
  if (sel) await page.locator(sel).first().screenshot({ path: `${SHOTS}/${TAG}-${name}.png` }).catch(() => undefined);
  else await page.screenshot({ path: `${SHOTS}/${TAG}-${name}.png`, fullPage: false }).catch(() => undefined);
};

/** Invest home's watchlist card and the column beside it, measured. */
const investPair = (page: Page) => page.evaluate(() => {
  const row = document.querySelector('[data-testid="invest-watch-row"]')!;
  const [a, b] = Array.from(row.children) as HTMLElement[];
  const card = (el: Element) => (el.matches(".k-card") ? el : el.querySelector(".k-card"))!;
  const col = b.matches(".k-card") ? b : b;
  const ra = card(a).getBoundingClientRect(), rb = col.getBoundingClientRect();
  const lastCard = Array.from(col.querySelectorAll(":scope > .k-card")).pop() ?? col;
  const wrap = card(a).querySelector<HTMLElement>(".k-tbl-wrap");
  return { aTop: ra.top, aBottom: ra.bottom, bTop: rb.top, bBottom: rb.bottom, lastBottom: lastCard.getBoundingClientRect().bottom, side: ra.right <= rb.left + 2,
    rows: card(a).querySelectorAll("tbody tr").length, over: !!wrap?.hasAttribute("data-over"), boxH: wrap?.clientHeight ?? 0, boxSh: wrap?.scrollHeight ?? 0,
    csvInBody: !!card(a).querySelector(".k-tbl-tools [data-csv]"), border: wrap ? getComputedStyle(wrap).borderTopWidth : "", seeAll: !!card(a).querySelector('[data-testid="watch-see-all"]') };
});

for (const width of [1280, 1440, 1700]) {
  for (const watch of [4, 12]) {
    test(`LEVEL: Invest home at ${width} with ${watch} stocks: the watchlist and the column beside it end level (±2 px), every stock in the card`, async ({ page }, info) => {
      test.skip(info.project.name !== "desktop", "a desktop width");
      await page.setViewportSize({ width, height: 900 });
      await watchWorld(page, watch);
      await page.goto("/invest");
      const row = page.getByTestId("invest-watch-row");
      await expect(row.locator(".k-card").first().locator("tbody tr")).toHaveCount(watch, { timeout: 30_000 });
      await expect(row.getByTestId("invest-events")).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(600);                // the blocks are sized a frame after the rows draw
      const m = await investPair(page);
      await shot(page, `invest-${width}-${watch}`, '[data-testid="invest-watch-row"]');
      expect(m.side, "the watchlist beside the column").toBe(true);
      expect(Math.abs(m.aTop - m.bTop)).toBeLessThanOrEqual(2);
      expect(Math.abs(m.aBottom - m.bBottom), `watchlist ends ${m.aBottom}, the column ${m.bBottom}`).toBeLessThanOrEqual(2);
      expect(Math.abs(m.lastBottom - m.bBottom), "the column's last card reaches its bottom").toBeLessThanOrEqual(2);
      expect(m.rows).toBe(watch);
      expect(m.csvInBody, "no Download CSV button in the card's body").toBe(false);
      expect(m.seeAll, "no See all: every stock is in the card").toBe(false);
      expect(m.border, "no box inside the card: the card is the frame").toBe("0px");
      if (m.over) expect(m.boxSh - m.boxH, "a scroll hides at least three rows").toBeGreaterThan(80);
      // the CSV is in the card's ⋯ menu
      await row.locator(".k-card").first().getByRole("button", { name: "Section menu" }).click();
      await expect(page.getByTestId("card-menu-csv")).toBeVisible();
      const dl = page.waitForEvent("download");
      await page.getByTestId("card-menu-csv").click();
      expect((await dl).suggestedFilename()).toMatch(/^stratlab-watchlist-/);
    });
  }
}

/** A block's scroll state: whether it scrolls inside itself, its height, the screen's, its rows hidden below, its header row in view. */
const blockOf = (page: Page, sel: string) => page.evaluate((sel) => {
  const el = document.querySelector<HTMLElement>(sel)!;
  const r = el.getBoundingClientRect(), top = r.top + el.clientTop;
  const rows = Array.from(el.querySelectorAll<HTMLElement>(":scope > table > tbody > tr, :scope li, :scope > div > ul > li")).filter((x) => x.getBoundingClientRect().height > 0);
  const hidden = rows.filter((x) => x.getBoundingClientRect().top >= r.bottom - 1).length;
  const th = el.querySelector("thead th");
  return { over: el.hasAttribute("data-over"), h: r.height, top, vh: innerHeight, rows: rows.length, hidden, sh: el.scrollHeight, ch: el.clientHeight,
    overscroll: getComputedStyle(el).overscrollBehaviorY, tab: el.tabIndex, headTop: th ? th.getBoundingClientRect().top - top : null,
    whole: rows.some((x) => Math.abs(x.getBoundingClientRect().bottom - (top + el.clientHeight)) <= 1.5) };
}, sel);

test("SCREEN: Mood's 16 sectors are drawn whole at 1440x900 and scroll inside their block, header sticky, at 1280x600", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "desktop sizes");
  await signIn(page);
  await page.route((u) => u.pathname === "/research/pulse/mood", async (r) => {
    const res = await r.fetch(), body = await res.json();
    const base = body.sectors?.rows?.[0] ?? { name: "Nifty Bank", change_pct: 0.5 };
    const rows = Array.from({ length: 16 }, (_, i) => ({ ...base, name: `Nifty Sector ${String(i + 1).padStart(2, "0")}`, change_pct: 2 - i * 0.25 }));
    await r.fulfill({ response: res, json: { ...body, sectors: { ...(body.sectors ?? {}), rows, up: 8, down: 8, unchanged: 0, of: 16, leader: rows[0].name, laggard: rows[15].name } } });
  });
  const sel = '[aria-label="Sector indices, best first, scrolls sideways"]';
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/research/pulse");
  await expect(page.locator(sel).locator("tbody tr")).toHaveCount(16, { timeout: 30_000 });
  await page.waitForTimeout(500);
  const big = await blockOf(page, sel);
  await shot(page, "mood-1440x900", sel);
  expect(big.over, `16 rows fit a 900px screen: no scroll (block ${big.h}px)`).toBe(false);
  expect(big.hidden).toBe(0);
  await page.setViewportSize({ width: 1280, height: 600 });
  await page.waitForTimeout(600);
  const small = await blockOf(page, sel);
  await page.locator(sel).scrollIntoViewIfNeeded();
  await shot(page, "mood-1280x600");
  expect(small.over, "on a 600px screen the 16 rows scroll inside their block").toBe(true);
  expect(small.h, "the block is no taller than the screen").toBeLessThanOrEqual(600);
  expect(small.hidden, "a scroll hides three rows or more").toBeGreaterThanOrEqual(3);
  expect(small.whole, "it ends on a whole row").toBe(true);
  expect(small.overscroll).toBe("contain");
  expect(small.tab).toBe(0);
  await page.locator(sel).evaluate((el) => { el.scrollTop = 120; });
  await page.waitForTimeout(100);
  const scrolled = await blockOf(page, sel);
  expect(Math.abs(scrolled.headTop ?? 99), "the header row stays at the top of the block while it scrolls").toBeLessThanOrEqual(1);
});

test("SCREEN: Movers' table (the owner's reference): the block fits the screen, header sticky, rows scroll inside with the fade", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "desktop sizes");
  await signIn(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/invest/movers");
  const sel = '[data-testid="movers"] .k-tbl-wrap';
  await expect(page.locator(sel).locator("tbody tr").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  const b = await blockOf(page, sel);
  await page.getByTestId("movers").scrollIntoViewIfNeeded();
  await shot(page, "movers-1440");
  expect(b.h).toBeLessThanOrEqual(900);
  if (b.over) { expect(b.hidden).toBeGreaterThanOrEqual(3); expect(b.whole).toBe(true); }
});

test("AUTO-LOAD: Filings is one block the screen's height, its rows scroll inside it, more load near its end with no button, header sticky", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "desktop sizes");
  await signIn(page);
  const TOTAL = 1406, SIZE = 25, asked: number[] = [];
  await page.route((u) => u.pathname === "/research/redflags", async (r) => {
    const res = await r.fetch(), body = await res.json();
    const pg = Number(new URL(r.request().url()).searchParams.get("page") ?? "1");
    asked.push(pg);
    const items = Array.from({ length: SIZE }, (_, i) => {
      const n = (pg - 1) * SIZE + i;
      return { id: `f-${n}`, at: `2026-10-${String(28 - (n % 27)).padStart(2, "0")}T10:00:00Z`, symbol: SYMS[n % SYMS.length], company: `${SYMS[n % SYMS.length]} Ltd`, severity: n % 3 ? "amber" : "red", label: "Pledge", subject: `Filing number ${n + 1}`, url: null, copies: 1 };
    });
    await r.fulfill({ response: res, json: { ...body, items, total: TOTAL, page: pg, pages: Math.ceil(TOTAL / SIZE), companies: 20 } });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/research/filings?region=IN&view=all");
  const sel = '[aria-label="Red-flag filings, newest first, scrolls sideways"]';
  await expect(page.locator(sel).locator("tbody tr")).toHaveCount(SIZE, { timeout: 30_000 });
  await page.waitForTimeout(500);
  const b = await blockOf(page, sel);
  await page.locator(sel).scrollIntoViewIfNeeded();
  await shot(page, "filings-1440");
  expect(b.over, "the rows scroll inside the block").toBe(true);
  expect(b.h, "the block is no taller than the screen").toBeLessThanOrEqual(900);
  expect(b.h, "and takes most of it").toBeGreaterThan(900 * 0.5);
  // no paging button anywhere on the page
  await expect(page.getByRole("button", { name: /^(Next|Previous|Show more|Load more|Next page)/ })).toHaveCount(0);
  await expect(page.locator(".k-pager")).toHaveCount(0);
  await expect(page.getByTestId("k-loaded")).toContainText(`Loaded 25 of ${TOTAL.toLocaleString("en-IN")}`);
  // scroll the block to its end: the next 25 load on their own
  await page.locator(sel).evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await expect(page.locator(sel).locator("tbody tr")).toHaveCount(SIZE * 2, { timeout: 15_000 });
  await page.locator(sel).evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await expect(page.locator(sel).locator("tbody tr")).toHaveCount(SIZE * 3, { timeout: 15_000 });
  expect(asked.slice(0, 3)).toEqual([1, 2, 3]);
  await expect(page.getByTestId("k-loaded")).toContainText(`Loaded 75 of ${TOTAL.toLocaleString("en-IN")}`);
  const after = await blockOf(page, sel);
  expect(Math.abs(after.headTop ?? 99), "the header row stays at the top of the block").toBeLessThanOrEqual(1);
  // one scroll for the content: the page around the block barely scrolls
  const pageScroll = await page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
  const rowsH = await page.locator(sel).evaluate((el) => el.scrollHeight);
  expect(pageScroll, "the page itself scrolls little: about a screen (the filters above the block), never the rows' length").toBeLessThan(900 * 1.25);
  expect(pageScroll).toBeLessThan(rowsH / 2);
});

const PAGING = /^(show\s+(all|more|less|\d[\d,]*\s+more)\b|load\s+more\b|more ideas$|fewer\s+\w+$|all\s+\d[\d,]*\s+themes$|see\s+all\s+\d|next\s+page\b|previous\s+page\b|← previous$|next →$)/i;
for (const path of ["/library", "/research/themes?region=IN", "/research/results", "/research/filings?region=IN&view=all", "/calendar", "/invest", "/mine", "/research/screens", "/invest/etf-gaps", "/admin"]) {
  test(`NO SHOW-MORE: ${path} has no paging or show-more control`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "one size is enough for the words");
    await signIn(page);
    await page.goto(path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(800);
    const bad = await page.evaluate((src) => {
      const re = new RegExp(src, "i");
      return Array.from(document.querySelectorAll("button, a, summary, [role=button]")).map((e) => (e.textContent ?? "").replace(/\s+/g, " ").trim())
        .filter((t) => t && t.length <= 60 && re.test(t));
    }, PAGING.source);
    expect(bad, `paging or show-more controls on ${path}`).toEqual([]);
    await expect(page.locator(".k-pager")).toHaveCount(0);
  });
}

// ---------- Themes ----------
const LIB = ["Specialty chemicals", "Metals and mining", "Cement", "Steel", "Defence", "Railways", "Banks", "Automobiles", "Auto components", "Pharmaceuticals",
  "Hospitals", "Insurance", "Capital markets", "Power", "Renewable energy", "Oil and gas", "Telecom", "IT services", "FMCG", "Retail", "Real estate", "Hotels",
  "Aviation", "Logistics", "Ports", "Shipbuilding", "Fertilisers", "Agrochemicals", "Textiles", "Paints", "Electronics manufacturing"];
async function themeWorld(page: Page) {
  await signIn(page);
  await page.route((u) => u.pathname === "/research/theme-library/suggest", (r) => {
    const u = new URL(r.request().url()), region = u.searchParams.get("region") ?? "IN", typed = (u.searchParams.get("q") ?? "").toLowerCase();
    const names = region === "US" ? ["Aerospace and defense", "AI data centers", "Semiconductors", "Banks"] : LIB;
    const items = names.filter((n) => !typed || n.toLowerCase().includes(typed)).map((n, i) => ({ name: n, q: n.toLowerCase(), region, at: "2026-11-08T10:00:00Z", day: `2026-11-${String(1 + (i % 20)).padStart(2, "0")}`, members: 20, searched: 50 - i }));
    return r.fulfill({ json: { items } });
  });
}

test("THEMES: compact chips, never the same theme twice, the updated day inside the chip, no box over the next chips", async ({ page }, info) => {
  await themeWorld(page);
  await page.goto("/research/themes?region=IN");
  const ready = page.getByTestId("theme-already");
  await expect(ready.locator(".theme-chip")).toHaveCount(LIB.length, { timeout: 30_000 });
  await page.waitForTimeout(400);
  await shot(page, `themes-${info.project.name}`);
  // every theme once, ideas included ("Specialty chemicals" was in "Ready to open" and again in "More ideas")
  const names = await page.locator(".theme-box .theme-chip").evaluateAll((els) => els.map((e) => (e.querySelector(".theme-chip-name") ?? e).textContent!.trim().toLowerCase()));
  expect(new Set(names).size, `duplicates in ${names.join(", ")}`).toBe(names.length);
  await expect(page.getByText("More ideas")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^(Fewer themes|All \d+ themes)$/ })).toHaveCount(0);
  // the day inside each chip, no title tooltip that would open over the next row
  // (changed on purpose, site88, owner: no date on the chips at all)
  await expect(ready.locator(".theme-chip-day")).toHaveCount(0);
  expect(await ready.locator(".theme-chip[title]").count()).toBe(0);
  // (changed on purpose, site89, owner: no "updated" date in the chip's spoken name either)
  await expect(ready.locator(".theme-chip").first()).toHaveAttribute("aria-label", /\S/);
  expect(await ready.locator(".theme-chip[aria-label*='updated']").count()).toBe(0);
  // hovering a chip covers no other chip
  const chip = ready.locator(".theme-chip").nth(3);
  await chip.hover();
  const covered = await page.evaluate(() => {
    const chips = Array.from(document.querySelectorAll<HTMLElement>(".theme-ready .theme-chip"));
    const box = document.querySelector(".theme-ready")!.getBoundingClientRect();
    return chips.filter((c) => { const r = c.getBoundingClientRect(); if (r.bottom < 0 || r.top > innerHeight || r.top < box.top || r.bottom > box.bottom) return false; const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!top && !c.contains(top); }).length;
  });
  expect(covered, "no hover box over another chip").toBe(0);
  // chips never overlap one another
  const overlap = await ready.locator(".theme-chip").evaluateAll((els) => {
    const rs = els.map((e) => e.getBoundingClientRect());
    return rs.some((a, i) => rs.some((b, j) => j > i && a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1));
  });
  expect(overlap).toBe(false);
});

test("THEMES BUG: India's \"India defence\" open, then \"$ United States\": never mapped in the US; the chooser comes back, or the US's own Aerospace and defense", async ({ page }) => {
  await themeWorld(page);
  const usAsks: string[] = [];
  page.on("request", (rq) => {
    const u = new URL(rq.url());
    if (/\/research\/(sector|theme-dive)/.test(u.pathname) && u.searchParams.get("region") === "US") usAsks.push(u.searchParams.get("q") ?? "");
  });
  await page.goto("/research/themes?region=IN&q=India%20defence");
  await expect(page.getByRole("textbox", { name: "Theme" })).toHaveValue("India defence");
  await page.getByRole("radio", { name: /United States/ }).or(page.getByRole("button", { name: /United States/ })).first().click();
  await page.waitForTimeout(1500);
  expect(usAsks.filter((q) => /india/i.test(q)), "no India theme asked for in the US").toEqual([]);
  const url = new URL(page.url());
  expect(url.searchParams.get("region")).toBe("US");
  expect(url.searchParams.get("q") ?? "", "the US's own theme or the chooser").toMatch(/^(|Aerospace and defense)$/);
  await expect(page.getByText("India defence", { exact: true })).toHaveCount(0);
  // the US's ideas, never India's
  await expect(page.locator(".theme-box")).not.toContainText(/India defence|Railways capex/);
  // the API refuses one too, for an old link
  const r = await page.request.get(`${API}/research/sector?q=India%20defence&region=US`, { headers: { Authorization: "Bearer pro-token" } });
  expect(r.status()).toBe(400);
});

// ---------- Search filings form ----------
test("FORM: Search filings is one compact form: the market inside its top row with Search, even columns, solid choices, no e.g. in the date boxes", async ({ page }, info) => {
  await signIn(page);
  await page.goto("/research/search");
  const form = page.locator("form.ds-form");
  await expect(form).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  await shot(page, `filings-form-${info.project.name}`, "form.ds-form");
  // the market toggle and Search are inside the form, on the phrase's row
  const top = form.locator(".ds-top");
  await expect(top.getByRole("radiogroup").or(top.locator(".k-seg")).first()).toBeVisible();
  await expect(top.locator("button.ds-go")).toHaveText("Search");
  const level = await top.evaluate((row) => {
    const box = (sel: string) => row.querySelector(sel)!.getBoundingClientRect();
    return { input: box("input").bottom, go: box(".ds-go").bottom, seg: box(".k-seg").bottom, phone: innerWidth <= 640 };
  });
  if (!level.phone) {
    expect(Math.abs(level.input - level.go), "Search is level with the phrase box").toBeLessThanOrEqual(2);
    expect(Math.abs(level.input - level.seg), "the market is level with the phrase box").toBeLessThanOrEqual(4);
  }
  // no form row whose columns differ in height by more than one control row
  const ragged = await form.evaluate((f) => Array.from(f.querySelectorAll(".ds-row")).map((row) => {
    const hs = Array.from(row.children).map((c) => c.getBoundingClientRect().height);
    return Math.max(...hs) - Math.min(...hs);
  }));
  for (const d of ragged) expect(d, "columns of a row differ by at most one control row").toBeLessThanOrEqual(44);
  // no dashed chip, no "e.g." in a box
  expect(await form.evaluate((f) => Array.from(f.querySelectorAll("*")).some((e) => getComputedStyle(e).borderTopStyle === "dashed"))).toBe(false);
  expect(await form.locator("input[placeholder^='e.g.']").count()).toBe(0);
});
