import { expect, test, type Page } from "@playwright/test";

// site89b (Release 89 site items), proved on the fake world:
// 2. The Results page's "Usual move" says what it stands on: how many earlier results days, and which ones on hover.
// 4. The corporate actions and earnings calls lists come a page at a time from the server; the next page is asked for as the reader
//    nears the end (no button), and "Loaded N of M" says how far the list has come.
// 5. FORMS SWEEP: Chart rules, Business updates and Figures' save form have the Search filings form's layout (site87): labels above
//    boxes, the market, the main box and the action on one line with their boxes level, one column on a phone.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
/** An API path on the fake backend (never the page of the same path on the web server). */
const apiPath = (path: string) => (u: URL) => u.origin === new URL(API).origin && u.pathname === path;

async function signIn(page: Page) {
  const user = { id: "u-pro", aud: "authenticated", email: "u-pro@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} };
  await page.addInitScript((u) => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: "pro-token", token_type: "bearer", expires_in: 3600, expires_at: 4102444800, refresh_token: "r", user: u }));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab.consent.v1", "no");
    } catch { /* none */ }
  }, user);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
}

const box = (page: Page, sel: string) => page.locator(sel).first().evaluate((el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right }; });

test("FORMS: Chart rules has the market, the group and Scan on one line inside its form, their boxes level", async ({ page }, info) => {
  await signIn(page);
  await page.goto("/research/scan");
  const form = page.getByRole("form", { name: "Scan a group" });
  await expect(form.getByRole("button", { name: "Scan", exact: true })).toBeVisible({ timeout: 20_000 });
  // the market toggle is in the form, not floating above the card
  await expect(form.getByRole("radiogroup", { name: "Market" }).or(form.getByRole("group", { name: "Market" })).first()).toBeVisible();
  const select = await form.getByLabel("Group to scan").evaluate((el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; });
  const go = await form.getByRole("button", { name: "Scan", exact: true }).evaluate((el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, w: r.width }; });
  if (info.project.name === "desktop") {
    expect(Math.abs(go.bottom - select.bottom), "Scan level with the group's box").toBeLessThanOrEqual(2);
    expect(Math.abs(go.top - select.top)).toBeLessThanOrEqual(2);
  } else {
    expect(go.top, "on a phone Scan is under the group's box").toBeGreaterThan(select.bottom - 1);
    const card = await box(page, "form.k-sform");
    expect(go.w, "a full-width Scan on a phone").toBeGreaterThan(card.right - card.left - 4);
    // the chart rules two to a row: the first two chips share a line
    const chips = form.getByRole("group", { name: "Scan rule sets" }).getByRole("button");
    const a = await chips.nth(0).boundingBox(), b = await chips.nth(1).boundingBox();
    expect(Math.abs(a!.y - b!.y), "two chart rules to a row").toBeLessThanOrEqual(2);
  }
  await expect(form.getByText("Chart rule", { exact: true })).toBeVisible();
});

test("FORMS: Business updates' choices are in one card, each under its label", async ({ page }, info) => {
  await signIn(page);
  await page.goto("/invest/business-updates");
  const card = page.getByTestId("biz-pick");
  await expect(card.getByText("Kind of update", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(card.getByText("Small charts", { exact: true })).toBeVisible();
  await expect(card.getByRole("group", { name: "Sector" })).toBeVisible();
  await expect(card.getByRole("group", { name: "Range of the small charts" }).or(card.getByRole("radiogroup", { name: "Range of the small charts" })).first()).toBeVisible();
  if (info.project.name !== "desktop") {
    const chips = card.getByRole("group", { name: "Sector" }).getByRole("button");
    const a = await chips.nth(0).boundingBox(), b = await chips.nth(1).boundingBox();
    expect(Math.abs(a!.y - b!.y), "two kinds to a row on a phone").toBeLessThanOrEqual(2);
    expect(Math.abs(a!.width - b!.width), "equal cells").toBeLessThanOrEqual(2);
  }
});

test("FORMS: Figures' save form has the name, the weekly email and Save screen on one line, their boxes level", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the save card is under the folded filters on a phone");
  await signIn(page);
  await page.goto("/research/screens");
  const form = page.getByRole("form", { name: "Save this screen" });
  await expect(form.getByRole("button", { name: "Save screen" })).toBeVisible({ timeout: 20_000 });
  // measured once the card has settled (its saved count and plan line come after the form)
  await expect.poll(async () => { const n = await form.getByLabel("Name").boundingBox(), g = await form.getByRole("button", { name: "Save screen" }).boundingBox();
    return Math.abs(n!.y + n!.height - (g!.y + g!.height)); }, { message: "Save screen level with the name's box" }).toBeLessThanOrEqual(2);
  const name = await form.getByLabel("Name").boundingBox(), go = await form.getByRole("button", { name: "Save screen" }).boundingBox();
  const tick = await form.locator(".k-check").first().boundingBox();
  expect(Math.abs(tick!.y + tick!.height - (name!.y + name!.height)), "the weekly email level with the name's box (VR3-007)").toBeLessThanOrEqual(2);
  expect(tick!.x, "between the name and Save screen").toBeGreaterThan(name!.x + name!.width - 1);
  expect(go!.x).toBeGreaterThan(tick!.x + tick!.width - 1);
  // the size chips two to a row of equal cells in the filter column
  const sizes = page.getByRole("group", { name: "Company size", exact: true }).getByRole("button");
  const a = await sizes.nth(0).boundingBox(), b = await sizes.nth(1).boundingBox();
  expect(Math.abs(a!.y - b!.y)).toBeLessThanOrEqual(2);
  expect(Math.abs(a!.width - b!.width)).toBeLessThanOrEqual(2);
});

test("PAGING: the earnings calls list asks the server for its next page as the reader scrolls, and says how far it has come", async ({ page }) => {
  await signIn(page);
  const rows = Array.from({ length: 130 }, (_, i) => ({ id: `C${i}|2026-12-0${1 + (i % 5)}|results`, region: "US", symbol: `C${String(i).padStart(3, "0")}`, name: `Company ${i}`,
    date: `2026-12-0${1 + (i % 5)}`, until: null, dates: null, time: null, tz: "ET", session: "after the close", type: "results", type_label: "Results", links: [], noticed: true, mine: false }));
  const asked: number[] = [];
  await page.route(apiPath("/research/earnings-calls"), (r) => {
    const off = Number(new URL(r.request().url()).searchParams.get("offset") ?? 0);
    asked.push(off);
    return r.fulfill({ json: { region: "US", scope: "all", when: "upcoming", kind: "all", today: "2026-11-30", from: "2026-11-30", to: "2026-12-30", updated_at: null,
      matching: rows.length, rows: rows.slice(off, off + 50), offset: off, more: Math.max(0, rows.length - off - 50), counts: { call: 0, meet: 0, results: rows.length },
      note: "", pending: false, full: true, plan_needed: null, mine_count: 0 } });
  });
  await page.goto("/research/earnings-calls?region=US");
  const loaded = page.getByTestId("calls-table").getByTestId("k-loaded");
  await expect(loaded).toContainText("Loaded 50 of 130", { timeout: 20_000 });
  expect(asked).toEqual([0]);
  await expect(page.getByText(/The first .* are shown/)).toHaveCount(0);
  for (let i = 0; i < 12 && !(await loaded.textContent())?.includes("Loaded 130 of 130"); i++) {
    await page.getByTestId("calls-table").locator(".k-tbl-wrap").first().evaluate((el) => { el.scrollTop = el.scrollHeight; window.scrollTo(0, document.body.scrollHeight); });
    await page.waitForTimeout(400);
  }
  await expect(loaded).toContainText("Loaded 130 of 130");
  expect(asked).toEqual([0, 50, 100]);
});

test("PAGING: the corporate actions list loads its next page from its last day's table, the day filter knowing every ex-date", async ({ page }, info) => {
  await signIn(page);
  const act = (i: number, day: string) => ({ id: `CO${i}|dividend|${day}|`, region: "IN", symbol: `CO${i}`, name: `Company ${i}`, kind: "dividend", sub: "", label: "Dividend",
    text: "Dividend ₹1 a share", short: "Dividend", amount: 1, ratio: null, factor: null, premium: null, currency: "INR", ex_date: day, record_date: null, purpose: "", src: "exchange",
    mine: false, cap: null, band: null, sector: null, last: null, last_at: null, fo: false, indices: [], yield_pct: null });
  const days = ["2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04", "2026-12-07"];
  const ahead = Array.from({ length: 120 }, (_, i) => act(i, days[Math.floor(i / 24)]));
  const asked: string[] = [];
  await page.route(apiPath("/research/corp-actions"), (r) => {
    const q = new URL(r.request().url()).searchParams, part = q.get("part") ?? "", off = Number(q.get("offset") ?? 0);
    asked.push(`${part}:${off}`);
    return r.fulfill({ json: { region: "IN", scope: "all", kind: "", today: "2026-11-30", updated_at: null, ahead: part === "recent" ? [] : ahead.slice(off, off + 50), recent: [],
      ahead_total: ahead.length, recent_total: 0, part, offset: off, days, more: 0, mine_count: 0, alerts: false, kinds: ["dividend"], ahead_known: true, note: "", recent_days: 14,
      ahead_note: null, universe: null, total: ahead.length, matching: ahead.length, unknown_size: 0, filters: { size: [], sector: "", index: "", fo: false, on: "", sort: "date" },
      facets: { sizes: [], sectors: [], indices: [], fo: null } } });
  });
  await page.goto("/research/corporate-actions?region=IN");
  await expect(page.getByTestId("k-loaded")).toContainText("Loaded 50 of 120", { timeout: 20_000 });
  // the day filter lists every ex-date, not only those of the first page (a phone folds the filters)
  if (info.project.name === "desktop") await expect(page.getByLabel("Day").locator("option", { hasText: "7 Dec" })).toHaveCount(1);
  for (let i = 0; i < 12 && !(await page.getByTestId("k-loaded").textContent())?.includes("Loaded 120 of 120"); i++) {
    await page.evaluate(() => { document.querySelectorAll(".k-tbl-wrap").forEach((el) => { el.scrollTop = el.scrollHeight; }); window.scrollTo(0, document.body.scrollHeight); });
    await page.waitForTimeout(400);
  }
  await expect(page.getByTestId("k-loaded")).toContainText("Loaded 120 of 120");
  expect(asked).toEqual([":0", "ahead:50", "ahead:100"]);
  await expect(page.getByTestId("actions-day")).toHaveCount(5);
});

test("USUAL MOVE: the figure says how many earlier results days it stands on, and which ones on hover", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "one size is enough for a label");
  await signIn(page);
  await page.route(apiPath("/research/results/moves"), async (r) => {
    const asked = (new URL(r.request().url()).searchParams.get("symbols") ?? "").split(",").filter(Boolean);
    return r.fulfill({ json: { moves: Object.fromEntries(asked.map((s) => [s, { moves: { avg: 6.7, n: 3, last: [10, -4, 6], dates: ["2026-08-27", "2026-05-28", "2026-03-05"],
      basis: "close before the results day to the close of the session after it" }, since: null }])), pending: [] } });
  });
  await page.goto("/research/results?region=IN&scope=all");
  const n = page.getByTestId("res-mv-n").first();
  await expect(n).toHaveText("3 results days", { timeout: 30_000 });
  await expect(page.locator("b[title^='Average size of the move over 3 earlier results days (Thu 27 Aug, Thu 28 May, Thu 5 Mar)']").first()).toBeVisible();
});
