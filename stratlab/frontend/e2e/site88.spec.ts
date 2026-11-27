import { expect, test, type Locator, type Page } from "@playwright/test";
import { parseDate, parseNumber } from "../src/lib/tableSort";

// site88 (Release 88), the owner's three asks on the fake world:
// 1. SORT EVERYWHERE: every kit table's header sorts on a click (numbers and days high to low first, words A to Z, a second click the other
//    way, the blanks last), an arrow and aria-sort on the sorted header; a phone's cards sort by a small "Sort by" select.
// 2. A holder's spellings: one folded line "N spellings counted as this holder · Review" opening a compact table (tick box, spelling on one
//    line cut with …, its companies at the right), not a column of tick boxes with "N companies" wrapping beside them.
// 3. Themes: no date on the Ready to open chips ("Cement 13 Nov").

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
// fake Pro users (tests/fake_db.py: load-N, the plan by N % 3) that only read here
function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, path: string, ready: string | RegExp, n: number) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(path);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(300);
  return errors;
}

/** The words of one column of a table's body rows (its index among the header cells). */
async function column(table: Locator, header: string): Promise<string[]> {
  const heads = await table.locator("thead th").allInnerTexts();
  const i = heads.findIndex((h) => h.replace(/[↑↓]/g, "").trim() === header);
  expect(i, `a "${header}" column in ${heads.join(" | ")}`).toBeGreaterThanOrEqual(0);
  return table.locator("tbody > tr:not(.k-detail-row)").evaluateAll((trs, at) => trs.map((tr) => ((tr.children[at] as HTMLElement | undefined)?.innerText ?? "").trim()), i);
}

const blank = (t: string) => /^\s*[–—-]?\s*$/.test(t);
/** Values in order, with the blanks only at the end. */
function ordered(texts: string[], read: (t: string) => number | string | null, desc: boolean) {
  const vals = texts.map((t) => (blank(t) ? null : read(t)));
  const firstBlank = vals.findIndex((v) => v == null);
  if (firstBlank >= 0) expect(vals.slice(firstBlank).every((v) => v == null), `blanks last in ${texts.join(", ")}`).toBe(true);
  const got = vals.filter((v): v is number | string => v != null);
  for (let k = 1; k < got.length; k++) {
    const a = got[k - 1], b = got[k];
    const c = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), "en-IN", { numeric: true, sensitivity: "base" });
    expect(desc ? c >= 0 : c <= 0, `${desc ? "high to low" : "low to high"}: ${texts.join(", ")}`).toBe(true);
  }
}

async function sortBy(table: Locator, header: string, read: (t: string) => number | string | null, firstDesc: boolean) {
  const th = table.locator("thead th").filter({ has: table.page().getByRole("button", { name: `Sort ${header}`, exact: true }) });
  const btn = th.getByRole("button", { name: `Sort ${header}`, exact: true });
  await expect(table.getByRole("columnheader", { name: header, exact: true })).toHaveCount(1);      // the column keeps its own name
  await expect(th).toHaveAttribute("aria-sort", "none");
  await btn.focus();
  await btn.press("Enter");                                           // a keyboard-operable button
  await expect(th).toHaveAttribute("aria-sort", firstDesc ? "descending" : "ascending");
  await expect(th).toContainText(firstDesc ? "↓" : "↑");
  ordered(await column(table, header), read, firstDesc);
  await btn.click();                                                  // the second click the other way
  await expect(th).toHaveAttribute("aria-sort", firstDesc ? "ascending" : "descending");
  ordered(await column(table, header), read, !firstDesc);
}

const num = (t: string) => parseNumber(t);
const day = (t: string) => parseDate(t);
const word = (t: string) => t.toLowerCase();

test("sorting by a number, a word and a day: a holder's companies", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the phone's Sort by select is its own test");
  const errors = await open(page, "/invest/holders?q=kacholia", "Named holders across companies", 176);
  const table = page.locator("#holder").getByRole("table", { name: "Companies where the holder is named" });
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await sortBy(table, "Stake", num, true);
  await sortBy(table, "Company", word, false);
  await sortBy(table, "Quarter", day, true);
  // a column of no words (none here) and the table's own sort elsewhere keep theirs; no page error
  expect(errors).toEqual([]);
});

test("sorting by a number, a word and a day on another page: corporate actions", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop headers");
  const errors = await open(page, "/research/corporate-actions?scope=all", "Corporate actions", 179);
  const tables = page.getByRole("table", { name: /^Corporate actions going ex on/ });
  await expect(tables.first()).toBeVisible();
  // the day with the most companies
  const counts = await tables.evaluateAll((ts) => ts.map((t) => t.querySelectorAll("tbody > tr").length));
  const table = tables.nth(counts.indexOf(Math.max(...counts)));
  expect(Math.max(...counts), "a day with two or more companies").toBeGreaterThanOrEqual(2);
  await sortBy(table, "Market value", num, true);                    // "₹9.60 lakh cr" beside "₹45,000 cr"
  await sortBy(table, "Company", word, false);
  // "Same day" is the table's ex day; "Not given" has no day and goes last
  const exOn = parseDate((await table.getAttribute("aria-label"))!.replace(/^Corporate actions going ex on /, ""));
  await sortBy(table, "Record date", (t) => (/^Same day/.test(t) ? exOn : parseDate(t)), true);
  expect(errors).toEqual([]);
});

test("a phone's cards sort by a small Sort by select", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone cards");
  // a long list (the select is only for 8 rows or more): the holder's three companies and six made-up ones
  await page.route((u) => u.href.startsWith(API) && u.pathname === "/invest/holders/holdings", async (r) => {
    const res = await r.fetch();
    const body = await res.json();
    const first = body.rows[0];
    body.rows = [...body.rows, ...[1, 2, 3, 4, 5, 6].map((k) => ({ ...first, symbol: `TEST${k}`, company: `Test company ${k}`, pct: k * 1.5, prev_pct: k * 1.5, change: "same" }))];
    body.count = body.rows.length;
    await r.fulfill({ response: res, json: body });
  });
  const errors = await open(page, "/invest/holders?q=kacholia", "Named holders across companies", 185);
  const card = page.locator("#holder");
  const select = card.getByTestId("k-sort-by");
  await expect(select).toBeVisible();
  await select.selectOption({ label: "Stake, high to low" });
  // the cards re-sort on the next render: wait for the largest stake (TEST6's 9%) at the top before reading the order (CI read the old
  // order straight after the pick, Release 98's run)
  await expect(card.locator("tbody tr td[data-label='Stake']").first()).toHaveText(/^9(\.0+)?%$/);
  const stakes = await card.locator("tbody tr td[data-label='Stake']").allInnerTexts();
  ordered(stakes, num, true);
  await select.selectOption({ label: "Company, Z to A" });
  await expect(card.locator("tbody tr").first()).toHaveAttribute("data-company", "XPROINDIA");
  await expect(card.getByLabel("Sort the table by")).toHaveCount(1);
  await select.selectOption({ label: "As listed" });
  await expect(card.locator("tbody tr").first()).toHaveAttribute("data-company", "RELIANCE");
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

test("a holder's spellings: one folded line opening a compact table", async ({ page }) => {
  const LONG = "ASHISH RAMESHCHANDRA KACHOLIA JOINTLY WITH RASHMI ASHISH KACHOLIA AS TRUSTEES OF THE FAMILY BENEFICIARY TRUST";
  await page.route((u) => u.href.startsWith(API) && u.pathname === "/invest/holders" && u.searchParams.get("q") === "kacholia", async (r) => {
    const res = await r.fetch();
    const body = await res.json();
    body.groups = body.groups.slice(0, 1).map((g: { names: { key: string; name: string; companies: number }[] }) => ({
      ...g, names: [...g.names, { key: LONG, name: LONG, companies: 2 }, { key: "ASHISH R KACHOLIA", name: "ASHISH R KACHOLIA", companies: 12 }] }));
    await r.fulfill({ response: res, json: body });
  });
  const errors = await open(page, "/invest/holders?q=kacholia", "Named holders across companies", 206);
  const card = page.locator("#holder");
  const fold = card.getByTestId("holder-spellings");
  await expect(fold.locator("summary")).toHaveText(/^\d+ spellings counted as this holder · Review$/);
  const n = Number((await fold.locator("summary").innerText()).match(/^\d+/)![0]);
  await expect(card.getByRole("table", { name: "Spellings counted as this holder" })).toBeHidden();
  await fold.locator("summary").click();
  const table = card.getByRole("table", { name: "Spellings counted as this holder" });
  await expect(table).toBeVisible();
  await expect(table.locator("tbody tr")).toHaveCount(n);
  // one line per spelling, cut with …, the whole of it on hover; the companies right-aligned
  const long = table.locator("tbody tr").filter({ hasText: "TRUSTEES" });
  const name = long.locator(".holder-spelling");
  await expect(name).toHaveAttribute("title", LONG);
  const box = await name.evaluate((el) => ({ h: el.getBoundingClientRect().height, lh: parseFloat(getComputedStyle(el).lineHeight) || 20, cut: el.scrollWidth > el.clientWidth }));
  expect(box.h, "one line").toBeLessThanOrEqual(box.lh * 1.3);
  expect(box.cut, "cut with …").toBe(true);
  const rowH = await table.locator("tbody tr").evaluateAll((trs) => trs.map((tr) => tr.getBoundingClientRect().height));
  expect(Math.max(...rowH), "compact rows").toBeLessThanOrEqual(56);
  await expect(long.locator("td.k-num")).toHaveText("2");
  expect(await long.locator("td.k-num").evaluate((el) => getComputedStyle(el).textAlign)).toBe("right");
  // unticking one says so on the folded line and reads the holdings again; the header box counts them all back
  await long.getByRole("checkbox", { name: `Count ${LONG}` }).uncheck();
  await expect(fold.locator("summary")).toHaveText(`${n - 1} of ${n} spellings counted as this holder · Review`);
  const all = table.locator("thead").getByRole("checkbox", { name: "Count every spelling" });
  await all.check();
  await expect(fold.locator("summary")).toHaveText(`${n} spellings counted as this holder · Review`);
  // it sorts like every table: by companies, high to low first (a phone has no header buttons: its select is for long lists)
  if (!(await page.evaluate(() => matchMedia("(max-width: 640px)").matches))) await sortBy(table, "Companies", num, true);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

test("themes: the Ready to open chips carry no date", async ({ page }) => {
  const names = ["Cement (Indian cement makers and their suppliers)", "Utilities (Indian power, gas and water-linked infrastructure)", "Defence (India's defence makers)"];
  await page.route("**/research/theme-library/suggest**", (r) => r.fulfill({ json: { items: names.map((name) => ({ name, q: name.toLowerCase(), region: "IN", at: "2026-11-13T09:00:00Z", day: "2026-11-13", members: 40, searched: 3 })) } }));
  await open(page, "/research/themes?region=IN", "Map it", 176);
  const chips = page.getByTestId("theme-already").locator(".theme-chip");
  await expect(chips.first()).toBeVisible();
  await expect(page.getByTestId("theme-already").locator(".theme-chip-day")).toHaveCount(0);
  const texts = await chips.allInnerTexts();
  expect(texts).toContain("Cement");
  for (const t of texts) expect(t, "no date on a chip").not.toMatch(/\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/);
});
