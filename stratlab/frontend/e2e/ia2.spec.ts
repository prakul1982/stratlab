import { expect, test, type Page } from "@playwright/test";
import { NAV, startOf } from "../src/lib/nav";

// IA-2 (owner, 30 Oct). Items 37 and 43: on a laptop Market Watch's round button sits in a real margin clear of the cards (the owner picked
// this of the two ways shown; the menu-button way is gone).
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
/** A user of the fake world of its own for each project, so the desktop and phone runs never share a Market Watch layout. */
const who = (phone: boolean) => { const n = phone ? 147 : 141; return session(`load-${n}`, `u-load-${n}`, `load${n}@example.com`); };

async function open(page: Page, path: string, s: object, width: number, height = 800) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width, height });
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.addInitScript((x) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); localStorage.setItem("stratlab.tour.v1", "1");
    // each test starts with Market Watch shut and no choice kept
    if (!sessionStorage.getItem("fresh")) {
      sessionStorage.setItem("fresh", "1");
      for (const k of Object.keys(localStorage)) if (k.startsWith("stratlab.watch.") || k === "stratlab.side.slim") localStorage.removeItem(k);
    }
  }, s);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 2500 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}
const floating = (page: Page) => page.getByTestId("markets-launch");
const watch = (page: Page) => page.getByTestId("market-watch");

for (const width of [1280, 1440]) {
  test(`items 37, 43 at ${width}: the round button opens Market Watch; the menu's market line still lists the markets`, async ({ page }, info) => {
    test.skip(info.project.name === "phone", "a laptop's widths");
    const errors = await open(page, "/invest", who(false), width);
    const btn = floating(page);
    await expect(btn).toBeVisible({ timeout: 30_000 });
    expect((await btn.boundingBox())!.width).toBeCloseTo(44, 0);
    await expect(btn).toHaveAccessibleName("Open Market Watch");
    await expect(page.locator(".side-foot .mkt-btn")).toHaveAttribute("aria-haspopup", "dialog");
    await expect(page.locator("body")).not.toHaveAttribute("data-mw-button", /./);          // item 43: the switch is gone
    await btn.click();
    await expect(watch(page)).toBeVisible({ timeout: 30_000 });
    expect(errors).toEqual([]);
  });
}

test("items 37, 43 at 1280: the button sits at least 16px clear of every card on Invest, in the page's right margin", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a laptop's width");
  await open(page, "/invest", who(false), 1280);
  const btn = floating(page);
  await expect(btn).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main .k-card").first()).toBeVisible({ timeout: 30_000 });
  const b = (await btn.boundingBox())!;
  const cards = await page.locator("main .k-card").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, r: r.right, b: r.bottom }; })
    .filter((r) => r.r > r.x));
  expect(cards.length).toBeGreaterThan(0);
  // the gap to each card on the nearer side: beside it (the page scrolls under the fixed button)
  const near = cards.map((c) => Math.max(b.x - c.r, c.x - (b.x + b.width)));
  expect(Math.min(...near), "the button's distance from the nearest card's edge").toBeGreaterThanOrEqual(16);
  // centred in the margin: as far from the cards as from the window's edge
  const margin = 1280 - Math.max(...cards.map((c) => c.r));
  expect(Math.abs((1280 - (b.x + b.width)) - (b.x - (1280 - margin)))).toBeLessThanOrEqual(2);
  expect(b.y + b.height).toBeCloseTo(800 - 16, 0);                                      // its bottom where it was
  // the page still fits: no sideways scroll
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});

test("items 37, 43: the widest pages still fit beside the margin, and from 1600px the pill keeps its word", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a laptop's widths");
  await open(page, "/research/screens", who(false), 1280);
  await expect(floating(page)).toBeVisible({ timeout: 30_000 });
  for (const path of ["/research/screens", "/research/IN/RELIANCE", "/invest/flows", "/research/compare"]) {
    await page.goto(path);
    await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), `${path}: no sideways scroll`).toBeLessThanOrEqual(0);
  }
  await page.setViewportSize({ width: 1600, height: 900 });
  await expect(floating(page)).toBeVisible();
  await expect(floating(page)).toContainText("Markets");
});

// Item 36 (owner, 30 Oct: "you have squeezed the menu bar too much"): the 14 headings stay, and under each heading are its pages, the same
// pages, names and locks as its tabs. The section you are in is open, the others fold behind a disclosure button, and what the person
// opened or folded is kept. A heading with one page has no list. The current page is marked.
const side = (page: Page) => page.locator("aside.sidebar");
const mainNav = (page: Page) => side(page).getByRole("navigation", { name: "Main" });

test("item 36: each heading lists its pages; the section you are in is open, the others fold, and the choice is kept", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the phone's sheet has its own test below");
  const errors = await open(page, "/research/screens", who(false), 1280);
  const nav = mainNav(page);
  await expect(nav.locator(".side-entries > .side-entry > .side-head > a")).toHaveText(NAV.invest.groups.map((g) => g.label), { timeout: 30_000 });
  // Find stocks is open with its pages, as its tabs name them; Figures is the page marked
  const find = NAV.invest.groups.find((g) => g.id === "find-stocks")!;
  const sub = nav.locator("#side-sub-find-stocks");
  await expect(sub.getByRole("link")).toHaveText(find.pages.map((p) => p.label));
  await expect(page.getByTestId("hub-tabs").getByRole("link")).toHaveText(find.pages.map((p) => p.label));
  for (const p of find.pages) await expect(sub.getByRole("link", { name: p.label, exact: true })).toHaveAttribute("href", p.to);
  await expect(sub.getByRole("link", { name: "Figures", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(nav.locator("[aria-current=page]")).toHaveCount(1);
  await expect(nav.getByRole("link", { name: "Find stocks", exact: true })).not.toHaveClass(/active/);      // never two selected at once
  // the others are folded behind their buttons; a heading with one page has none
  for (const g of NAV.invest.groups) {
    const btn = nav.getByRole("button", { name: `${g.label} pages`, exact: true });
    if (g.pages.length === 1) { await expect(btn).toHaveCount(0); await expect(nav.locator(`#side-sub-${g.id}`)).toHaveCount(0); continue; }
    await expect(btn).toHaveAttribute("aria-expanded", g.id === "find-stocks" ? "true" : "false");
    await expect(btn).toHaveAttribute("aria-controls", `side-sub-${g.id}`);
  }
  // the keyboard opens a folded section; it stays open after a reload (kept for this person)
  const today = nav.getByRole("button", { name: "Market today pages", exact: true });
  await today.focus();
  await page.keyboard.press("Enter");
  await expect(today).toHaveAttribute("aria-expanded", "true");
  await expect(nav.locator("#side-sub-market-today").getByRole("link")).toHaveText(NAV.invest.groups.find((g) => g.id === "market-today")!.pages.map((p) => p.label));
  await page.reload();
  await expect(mainNav(page).getByRole("button", { name: "Market today pages", exact: true })).toHaveAttribute("aria-expanded", "true", { timeout: 30_000 });
  await mainNav(page).getByRole("button", { name: "Market today pages", exact: true }).click();
  await expect(mainNav(page).getByRole("button", { name: "Market today pages", exact: true })).toHaveAttribute("aria-expanded", "false");
  // the section you are in can be folded too; coming back into it opens it again
  await mainNav(page).getByRole("button", { name: "Find stocks pages", exact: true }).click();
  await expect(mainNav(page).locator("#side-sub-find-stocks")).toBeHidden();
  // a heading still opens its first page, and its section opens
  await mainNav(page).getByRole("link", { name: "Market data", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${startOf(NAV.invest.groups.find((g) => g.id === "market-data")!, "invest")}$`));
  await expect(mainNav(page).getByRole("button", { name: "Market data pages", exact: true })).toHaveAttribute("aria-expanded", "true");
  await mainNav(page).getByRole("link", { name: "Find stocks", exact: true }).click();
  await expect(mainNav(page).getByRole("button", { name: "Find stocks pages", exact: true })).toHaveAttribute("aria-expanded", "true");
  expect(errors).toEqual([]);
});

test("item 36: on a 1280x800 laptop the menu does not scroll with the section you are in open, in every space", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a laptop's size");
  await open(page, "/invest", who(false), 1280, 800);
  // a person with many notebooks: the menu lists six of them and "All 8 notebooks" under Notebooks, the longest a section gets
  await page.route(`${process.env.E2E_API ?? "http://127.0.0.1:8765"}/notebooks`, (r) => r.request().method() !== "GET" ? r.fallback() : r.fulfill({ json: Array.from({ length: 8 }, (_, i) => ({
    id: `nb-${i}`, name: `Opening range breakout with a long name ${i}`, pinned: i < 2, instrument: { market: "IN", symbol: "RELIANCE" }, summary: { experiments: 2, last_verdict: "robust" } })) }));
  await expect(mainNav(page)).toBeVisible({ timeout: 30_000 });
  const seen = new Set<string>(["/notebooks"]);
  for (const to of ["/notebooks"]) {
    await page.goto(to);
    const nav = side(page).locator("nav.side-groups");
    await expect(nav.locator(".nb-more")).toHaveText("All 8 notebooks", { timeout: 30_000 });
    const over = await nav.evaluate((el) => el.scrollHeight - el.clientHeight);
    expect(over, `${to} with 8 notebooks: the menu scrolls by ${over}px`).toBeLessThanOrEqual(0);
  }
  for (const space of ["trade", "invest", "money"] as const) for (const g of NAV[space].groups) {
    const to = startOf(g, space);
    if (seen.has(to)) continue;
    seen.add(to);
    await page.goto(to);
    const nav = side(page).locator("nav.side-groups");
    await expect(nav.locator(".side-entries")).toBeVisible({ timeout: 30_000 });
    const over = await nav.evaluate((el) => el.scrollHeight - el.clientHeight);
    expect(over, `${to}: the menu scrolls by ${over}px`).toBeLessThanOrEqual(0);
    await expect(side(page).locator(".side-more")).toHaveCount(0);
  }
});

test("item 36: the phone's menu sheet shows the same headings and pages", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone's sheet");
  await open(page, "/invest/breadth", who(true), 390, 844);
  await page.getByRole("button", { name: "Open menu" }).click();
  const nav = mainNav(page);
  await expect(nav.locator(".side-entries > .side-entry > .side-head > a")).toHaveText(NAV.invest.groups.map((g) => g.label), { timeout: 30_000 });
  await expect(nav.locator("#side-sub-market-today").getByRole("link", { name: "Breadth", exact: true })).toHaveAttribute("aria-current", "page");
  const btn = nav.getByRole("button", { name: "Companies pages", exact: true });
  expect((await btn.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await btn.click();
  await nav.getByRole("link", { name: "Compare", exact: true }).click();
  await expect(page).toHaveURL(/\/research\/compare$/);
  await expect(page.locator("aside.sidebar.open")).toHaveCount(0);
});

// screenshots of the menu for a person to LOOK at (IA2_SHOTS=<folder>)
const SHOTS = process.env.IA2_SHOTS;
test("item 36: menu screenshots", async ({ page }, info) => {
  test.skip(!SHOTS, "only when asked for");
  const phone = info.project.name === "phone";
  const sizes = phone ? [[390, 844], [360, 780]] : [[1440, 900], [1280, 800]];
  for (const [path, name] of [["/research/screens", "invest"], ["/notebooks", "trade"], ["/money/tax-tools", "money"]] as const) {
    await open(page, path, who(phone), sizes[0][0], sizes[0][1]);
    for (const [w, h] of sizes) for (const scheme of ["light", "dark"] as const) {
      await page.setViewportSize({ width: w, height: h });
      await page.emulateMedia({ colorScheme: scheme });
      if (phone && !(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
      await expect(mainNav(page).locator(".side-entries")).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${SHOTS}/menu-${name}-${w}-${scheme}.png` });
    }
    await page.goto("about:blank");
  }
});

// Item 38 (owner screenshot, 30 Oct: a theme's "against NIFTY 500" chart): the time axis's first two labels ran together ("13 Oct 20232 Feb
// 2024") and the end-of-line names ran past the card's right edge. Every chart drawn by the shared chart (chart/XYChart) is checked on the
// drawn page, at the four widths: no two of its labels overlap, and none is outside its card.
const API38 = process.env.E2E_API ?? "http://127.0.0.1:8765";
const ADMIN38 = session("admin-token", "u-admin", "owner@example.com");
const CHART_PAGES = ["/research/themes?region=IN&q=" + encodeURIComponent("India steel and mining"), "/invest/breadth", "/invest/flows", "/research/rotation",
  "/invest/etf-gaps", "/invest/margin-funding", "/invest/stock-lending", "/research/IN/RELIANCE", "/trade/positioning"];
/** Each chart's labels that cross another, or reach past the chart's card, as text for the failure message. */
const chartFaults = (page: Page) => page.evaluate(() => {
  const out: string[] = [];
  const svgs = Array.from(document.querySelectorAll("svg.ch-svg")).filter((s) => { const r = s.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  for (const svg of svgs) {
    const name = svg.getAttribute("aria-label")?.slice(0, 50) ?? "a chart";
    const card = (svg.closest(".k-card, .card, [class*=-card]") ?? svg.parentElement!).getBoundingClientRect();
    const texts = Array.from(svg.querySelectorAll("text")).filter((t) => (t.textContent ?? "").trim()).map((t) => ({ s: (t.textContent ?? "").trim(), r: t.getBoundingClientRect() }))
      .filter((t) => t.r.width > 0);
    for (const t of texts) if (t.r.right > card.right + 1 || t.r.left < card.left - 1) out.push(`${name}: "${t.s}" outside its card (${Math.round(t.r.left)}–${Math.round(t.r.right)} vs ${Math.round(card.left)}–${Math.round(card.right)})`);
    for (let i = 0; i < texts.length; i++) for (let k = i + 1; k < texts.length; k++) {
      const [a, b] = [texts[i].r, texts[k].r];
      if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1) out.push(`${name}: "${texts[i].s}" and "${texts[k].s}" overlap`);
    }
  }
  return { charts: svgs.length, faults: out };
});

test("item 38: on every page of charts, at 1440, 1280, 390 and 360, no chart label overlaps another or leaves its card", async ({ page, request }, info) => {
  test.skip(info.project.name === "phone", "each width is set here");
  test.setTimeout(300_000);
  const auth = { Authorization: "Bearer admin-token" };
  // a notebook with two finished tests: an experiment's charts and the comparison of two
  const ema = { name: "Labels check", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
    exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${API38}/notebooks`, { headers: auth, data: { name: "Item 38 labels", question: "q", strategy: ema, instrument: "CRYPTO:BTC-USD" } })).json();
  for (const days of [800, 400]) await request.post(`${API38}/notebooks/${nb.id}/experiments`, { headers: auth, data: { days } });
  try {
    const pages = [...CHART_PAGES, `/n/${nb.id}/e/1`, `/n/${nb.id}/compare?a=1&b=2`];
    await open(page, "/invest", ADMIN38, 1440, 900);
    const faults: string[] = [];
    let charts = 0;
    for (const path of pages) for (const [w, h] of [[1440, 900], [1280, 800], [390, 844], [360, 780]]) {
      await page.setViewportSize({ width: w, height: h });
      await page.goto(path);
      await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await page.waitForTimeout(400);
      const got = await chartFaults(page);
      charts += got.charts;
      faults.push(...got.faults.map((f) => `${path} at ${w}: ${f}`));
      if (SHOTS) for (const scheme of ["light", "dark"] as const) {
        await page.emulateMedia({ colorScheme: scheme });
        const cards = page.locator("svg.ch-svg");
        for (let k = 0; k < Math.min(await cards.count(), 4); k++) {
          const card = cards.nth(k).locator("xpath=ancestor::*[contains(@class,'card')][1]");
          await (await card.count() ? card : cards.nth(k)).screenshot({ path: `${SHOTS}/chart-${path.replace(/[^a-z0-9]+/gi, "_").slice(0, 40)}-${k}-${w}-${scheme}.png` }).catch(() => undefined);
        }
      }
    }
    expect(charts, "the pages drew their charts").toBeGreaterThan(20);
    expect(faults).toEqual([]);
  } finally {
    await request.delete(`${API38}/notebooks/${nb.id}`, { headers: auth });
  }
});

// Item 39 (owner screenshot, 30 Oct: Market today, "these not colored"): every ▲/▼ change is green up and red down, the same pill everywhere;
// the FII/DII and volatility tables' grey pills were the odd ones out. On each page, every piece of text with an arrow is drawn in the up or
// down colour.
const arrowFaults = (page: Page) => page.evaluate(() => {
  const probe = (cls: string) => { const s = document.createElement("span"); s.className = cls; document.body.appendChild(s); const c = getComputedStyle(s).color; s.remove(); return c; };
  const ok = new Set([probe("k-delta up"), probe("k-delta down"), probe("k-up"), probe("k-down")]);
  const out: string[] = [];
  let arrows = 0;
  const walk = document.createTreeWalker(document.querySelector("main") ?? document.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    if (!/[▲▼]/.test(n.textContent ?? "")) continue;
    const el = n.parentElement!;
    const r = el.getBoundingClientRect();
    if (!r.width || el.closest("[hidden], .sr-only, svg")) continue;
    arrows++;
    const pill = el.closest(".k-delta");
    if (pill && !/\b(up|down)\b/.test(pill.className)) out.push(`a pill "${pill.textContent?.trim()}" without its up/down class (${pill.className})`);
    if (!ok.has(getComputedStyle(el).color)) out.push(`"${(el.closest(".k-delta") ?? el).textContent?.trim().slice(0, 40)}" is ${getComputedStyle(el).color}, not the up or down colour`);
  }
  return { arrows, faults: out };
});

test("item 39: every ▲/▼ change is green up or red down, light and dark, on the pages with changes", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "colours are the same on a phone");
  test.setTimeout(240_000);
  await open(page, "/research/pulse", ADMIN38, 1440, 900);
  let arrows = 0;
  const faults: string[] = [];
  for (const path of ["/research/pulse", "/invest/flows", "/invest/breadth", "/invest/margin-funding", "/research/IN/RELIANCE", "/research/watchlist", "/research/rotation", "/mine"]) {
    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(path);
      await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
      await page.waitForLoadState("networkidle").catch(() => undefined);
      const got = await arrowFaults(page);
      arrows += got.arrows;
      faults.push(...got.faults.map((f) => `${path} (${scheme}): ${f}`));
    }
  }
  expect(arrows, "the pages drew their changes").toBeGreaterThan(20);
  expect(faults).toEqual([]);
  // Market today's two tables the owner pointed at: their pills are green or red
  await page.goto("/research/pulse");
  for (const id of ["pulse-flows", "pulse-risk"]) {
    const pills = page.getByTestId(id).locator(".k-delta");
    await expect(pills.first()).toBeVisible({ timeout: 30_000 });
    for (const cls of await pills.evaluateAll((els) => els.map((e) => e.className))) expect(cls, id).toMatch(/\bk-delta (up|down|flat)\b/);
    expect(await pills.evaluateAll((els) => els.filter((e) => /\b(up|down)\b/.test(e.className)).length), `${id}: coloured pills`).toBeGreaterThan(0);
  }
});

