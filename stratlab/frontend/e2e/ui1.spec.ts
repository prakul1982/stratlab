import { expect, test } from "@playwright/test";
import { open, sane } from "./pages-kit";

// Lane ui1, the owner's UI sweep (18 Nov). Item 6 ("fix ui dude", the Themes page): one line under the title; the market switch, the box
// and "Map it" on one row (the switch above them on a phone); the shared library as equal chips with short names, at most two rows, then
// "All N themes"; the ideas folded under "More ideas".
const LONG = ["Utilities (Indian power, gas and water-linked infrastructure)", "Automotive", "Banking and lenders", "Cement", "Defence and aerospace manufacturing",
  "Railways capex", "Renewables and solar", "EV and battery supply chain", "Digital payments", "Specialty chemicals", "Pharmaceuticals (generic drug makers and APIs)",
  "Steel and mining", "Telecom", "Consumer staples", "Hospitals", "Real estate", "Capital goods", "Shipbuilding", "Data centres", "Insurance", "Brokers", "Textiles",
  "Hotels", "Ports", "Agrochemicals", "Paints", "Electronics manufacturing (EMS and components)", "Water", "Sugar and ethanol", "FMCG"];

test("item 6: the Themes box is one row, the library two rows of equal short chips, the ideas folded (owner, 18 Nov)", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  await page.route("**/research/theme-library/suggest**", (r) => r.fulfill({ json: { items: LONG.map((name) => ({ name, q: name.toLowerCase(), region: "IN", at: "2026-11-10T09:00:00Z", day: "2026-11-10", members: 40, searched: 3 })) } }));
  const errors = await open(page, "/research/themes?region=IN", "Map it");
  // one line under the title on a laptop (two at most on a phone)
  const lede = page.locator(".k-page-head .k-lede");
  const lines = await lede.evaluate((el) => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)));
  expect(lines).toBeLessThanOrEqual(phone ? 2 : 1);
  // the box and Map it share a row, centred on each other; on a laptop the market switch is on that row too
  const box = await page.getByRole("textbox", { name: "Theme" }).boundingBox();
  const btn = await page.getByRole("button", { name: "Map it" }).boundingBox();
  const seg = await page.locator(".theme-map .k-seg").boundingBox();
  expect(Math.abs((box!.y + box!.height / 2) - (btn!.y + btn!.height / 2))).toBeLessThanOrEqual(1);
  expect(btn!.x).toBeGreaterThan(box!.x + box!.width - 1);
  if (!phone) expect(Math.abs((seg!.y + seg!.height / 2) - (box!.y + box!.height / 2))).toBeLessThanOrEqual(1);
  // (changed on purpose, site87, owner: 31 equal heavy pills, "Fewer themes" and a tooltip over the next row: every ready theme is a compact chip,
  // A to Z, its updated day small inside it (its full name and day in its accessible name), the area scrolling past three lines; the ideas a
  // row of their own with none the chips already show, never folded)
  const grid = page.getByTestId("theme-already");
  await expect(grid).toContainText("Ready to open:");
  const chips = grid.locator(".theme-ready > button");
  await expect(chips).toHaveCount(30);
  const util = grid.getByRole("button", { name: /^Utilities \(Indian power, gas and water-linked infrastructure\) · updated 10 Nov$/ });
  await expect(util.locator(".theme-chip-name")).toHaveText("Utilities");
  await expect(util.locator(".theme-chip-day")).toHaveText("10 Nov");
  expect(await grid.locator(".theme-ready > button[title]").count()).toBe(0);
  const boxes = await chips.evaluateAll((els) => els.map((e) => { const b = e.getBoundingClientRect(); return { h: Math.round(b.height) }; }));
  expect(new Set(boxes.map((b) => b.h)).size, "equal heights").toBe(1);
  const ideas = page.getByTestId("theme-ideas");
  await expect(ideas.locator("summary")).toHaveCount(0);
  await expect(grid.getByRole("button", { name: /^(All \d+ themes|Fewer themes)$/ })).toHaveCount(0);
  await sane(page, errors);
});

// Item 3 (owner, 18 Nov: HDFC Bank's update filings): date | subject | link on every row, the link column fixed and right-aligned, a long
// subject two lines at most, the same subject filed four times one row with its other days, five rows then "Show all N".
test("item 3: a company's update filings are one clean list, repeats folded (owner, 18 Nov)", async ({ page }) => {
  const lodr = "Intimation under SEBI (LODR) Regulations, 2015";
  const long = "Disclosure under Regulation 30 of the SEBI (Listing Obligations and Disclosure Requirements) Regulations, 2015: business update for the quarter ended September 30, 2026 with advances, deposits and the CASA ratio as at the quarter's end";
  const f = (id: string, at: string, title: string) => ({ id, at: `${at}T10:00:00Z`, title, url: `https://example.com/${id}`, read: true, period: null, problem: null, exchange: "NSE" });
  await page.route("**/research/business-updates/**", async (r) => {
    const res = await r.fetch(); const d = await res.json();
    d.filings = [f("a1", "2026-10-14", lodr), f("a2", "2026-10-03", long), f("a3", "2026-07-12", lodr), f("a4", "2026-07-03", "Business update for the quarter ended June 30, 2026"),
      f("a5", "2026-04-15", lodr), f("a6", "2026-04-04", "Business update for the quarter ended March 31, 2026"), f("a7", "2026-01-14", lodr),
      f("a8", "2026-01-04", "Business update for the quarter ended December 31, 2025"), f("a9", "2025-10-04", "Business update for the quarter ended September 30, 2025")];
    await r.fulfill({ response: res, json: d });
  });
  const errors = await open(page, "/research/IN/RELIANCE", "What they do");
  const list = page.getByRole("list", { name: "Business update filings" });
  await expect(list).toBeVisible({ timeout: 30_000 });
  const rows = list.locator("li");
  await expect(rows).toHaveCount(6);                       // (changed on purpose, site87: every subject, no "Show all N")
  await expect(rows.filter({ hasText: lodr })).toHaveCount(1);
  await expect(rows.first().getByTestId("biz-also")).toHaveText("Also filed 12 Jul 2026, 15 Apr 2026, 14 Jan 2026");
  await expect(rows.first().getByTestId("biz-also").getByRole("link", { name: "15 Apr 2026" })).toHaveAttribute("href", "https://example.com/a5");
  // every row's link ends at one x, on its row (never on a line of its own under the subject), and the long subject is two lines at most
  const geo = await rows.evaluateAll((els) => els.map((li) => {
    const a = li.querySelector(".biz-link")!.getBoundingClientRect(), t = li.querySelector(".biz-title")!.getBoundingClientRect(), r = li.getBoundingClientRect();   // the link never under the subject
    return { right: Math.round(a.right), inRow: a.top < t.bottom && a.bottom > r.top, lines: Math.round(t.height / parseFloat(getComputedStyle(li.querySelector(".biz-title")!).lineHeight)) };
  }));
  expect(new Set(geo.map((g) => g.right)).size, `link ends ${geo.map((g) => g.right)}`).toBe(1);
  for (const g of geo) { expect(g.inRow).toBe(true); expect(g.lines).toBeLessThanOrEqual(2); }
  await expect(rows.nth(1).locator(".biz-title")).toHaveAttribute("title", long);
  // (changed on purpose, site87, owner: no "Show all N": every row, the list a block sized to the screen)
  await expect(rows).toHaveCount(6);
  await expect(page.getByRole("button", { name: /^Show all \d+$/ })).toHaveCount(0);
  await sane(page, errors);
});

// Item 2 (owner, 18 Nov): a long intro is one short sentence with "More"; a card's method notes are one closed "About these figures" fold
test("item 2: a long intro is one sentence with More, and a card's notes are a closed fold (owner, 18 Nov)", async ({ page }) => {
  // (updated on purpose, fix18: an intro is cut only at a sentence's end; Flows' first sentence is long, so it shows whole, and the
  // screener's two sentences show the first with More)
  let errors = await open(page, "/invest/flows", "Flows");
  await expect(page.locator(".k-page-head .k-lede")).toContainText("the exchange's provisional figures, published each trading evening");
  await expect(page.locator(".k-page-head .k-lede").getByRole("button", { name: "More" })).toHaveCount(0);
  errors = errors.concat(await open(page, "/research/screens", "Filter companies by plain facts"));
  const lede = page.locator(".k-page-head .k-lede");
  const rest = lede.getByTestId("lede-rest");
  await expect(rest).toBeHidden();
  await expect(lede).toContainText("Pick the conditions; see every company that meets them.");
  await lede.getByRole("button", { name: "More" }).click();
  await expect(rest).toBeVisible();
  await expect(lede.getByRole("button", { name: "Less" })).toHaveAttribute("aria-expanded", "true");
  await page.goto("/research/IN/RELIANCE");
  const deals = page.locator(".k-card", { has: page.getByRole("heading", { name: "Deals and insider trades" }) });
  await deals.scrollIntoViewIfNeeded();
  const fold = deals.locator(".k-cardnote");
  await expect(fold.locator("summary")).toHaveText("About these figures", { timeout: 30_000 });
  await expect(deals.getByText(/From exchange disclosures over the last year/)).toBeHidden();
  await fold.locator("summary").click();
  await expect(deals.getByText(/From exchange disclosures over the last year/)).toBeVisible();
  await sane(page, errors);
});

// Item 1 (owner, 18 Nov: "center align everything properly"): a row of figures centred in its tiles, a card head's control centred on its
// title's line, a stat row's figures centred in their columns, and every table header aligned as its column's cells
test("item 1: figure rows centred, card heads' controls on the title's line, headers over their cells (owner, 18 Nov)", async ({ page }) => {
  const errors = await open(page, "/mine", "Good");
  const tiles = page.getByTestId("mine-markets").locator(".mine-mkt");
  await expect(tiles.first()).toBeVisible({ timeout: 30_000 });
  const off = await tiles.evaluateAll((els) => els.map((t) => { const r = t.getBoundingClientRect(), v = t.querySelector(".mine-mkt-v")!, rg = document.createRange(); rg.selectNodeContents(v);
    const vr = rg.getBoundingClientRect(); return Math.abs((vr.left + vr.width / 2) - (r.left + r.width / 2)); }));
  for (const d of off) expect(d, "a tile's level is centred in it").toBeLessThanOrEqual(2);
  const heads = async () => page.locator("main .k-card-head").evaluateAll((els) => els.flatMap((h) => {
    const t = h.querySelector(".k-card-title"), a = h.querySelector(":scope > .k-card-actions");
    if (!t || !a || h.querySelector(".k-card-headtext")) return [];
    const tr = t.getBoundingClientRect(), ar = a.getBoundingClientRect(), line = Math.min(parseFloat(getComputedStyle(t).lineHeight) || tr.height, tr.height);
    if (!ar.width || ar.top > tr.top + line || ar.left < tr.right) return [];
    return [{ t: (t.textContent ?? "").slice(0, 24), d: Math.round(Math.abs((tr.top + line / 2) - (ar.top + ar.height / 2)) * 10) / 10 }];
  }));
  for (const h of await heads()) expect(h.d, `${h.t}: its control on the title's line`).toBeLessThanOrEqual(2);
  await page.goto("/invest");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  for (const h of await heads()) expect(h.d, `${h.t}: its control on the title's line`).toBeLessThanOrEqual(2);
  await page.goto("/research/IN/RELIANCE/deep");
  const stats = page.locator(".k-stats .k-stat").first();
  await expect(stats).toBeVisible({ timeout: 30_000 });
  expect(await stats.evaluate((s) => getComputedStyle(s).textAlign)).toBe("center");
  await sane(page, errors);
});
