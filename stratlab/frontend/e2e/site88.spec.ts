import { expect, test, type Locator, type Page } from "@playwright/test";
import { parseDate, parseNumber } from "../src/lib/tableSort";

// site88 (Release 88), the owner's three asks on the fake world:
// 1. SORT EVERYWHERE: every kit table's header sorts on a click (numbers and days high to low first, words A to Z, a second click the other
//    way, the blanks last), an arrow and aria-sort on the sorted header; a phone's cards sort by a small "Sort by" select.
// 2. A holder's spellings: one folded line "N spellings counted as this holder · Review" opening a compact table (tick box, spelling on one
//    line cut with …, its companies at the right), not a column of tick boxes with "N companies" wrapping beside them.
// 3. Themes: no date on the Ready to open chips ("Cement 13 Nov").

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
  const th = table.locator("thead th").filter({ has: table.page().getByRole("button", { name: header, exact: true }) });
  const btn = th.getByRole("button", { name: header, exact: true });
  await expect(th).toHaveAttribute("aria-sort", "none");
  await btn.focus();
  await btn.press("Enter");                                           // a keyboard-operable button
  await expect(th).toHaveAttribute("aria-sort", firstDesc ? "descending" : "ascending");
  await expect(btn).toContainText(firstDesc ? "↓" : "↑");
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
  const errors = await open(page, "/invest/holders?q=kacholia", "Named holders across companies", 881);
  const table = page.locator("#holder").getByRole("table", { name: "Companies where the holder is named" });
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await sortBy(table, "Stake", num, true);
  await sortBy(table, "Company", word, false);
  await sortBy(table, "Quarter", day, true);
  // a column of no words (none here) and the table's own sort elsewhere keep theirs; no page error
  expect(errors).toEqual([]);
});

test("sorting by a day and a number on another page: FII and DII flows by day", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop headers");
  const errors = await open(page, "/invest/flows", "Every recorded day", 882);
  const table = page.getByRole("table", { name: "FII and DII net buying by day" });
  test.skip((await table.count()) === 0 || (await table.locator("tbody tr").count()) < 2, "no recorded days in this world");
  await sortBy(table, "FII/FPI net", num, true);
  await sortBy(table, "Day", day, true);
  // the totals row stays under the rows
  await expect(table.locator("tfoot tr")).toHaveCount(1);
  expect(errors).toEqual([]);
});

test("a phone's cards sort by a small Sort by select", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone cards");
  const errors = await open(page, "/invest/holders?q=kacholia", "Named holders across companies", 883);
  const card = page.locator("#holder");
  const select = card.getByTestId("k-sort-by");
  await expect(select).toBeVisible();
  await select.selectOption({ label: "Stake, high to low" });
  const stakes = await card.locator("tbody tr td[data-label='Stake']").allInnerTexts();
  ordered(stakes, num, true);
  await select.selectOption({ label: "Company, Z to A" });
  await expect(card.locator("tbody tr").first()).toHaveAttribute("data-company", "XPROINDIA");
  await select.selectOption({ label: "As listed" });
  await expect(card.locator("tbody tr").first()).toHaveAttribute("data-company", "RELIANCE");
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

test("a holder's spellings: one folded line opening a compact table", async ({ page }) => {
  const LONG = "ASHISH RAMESHCHANDRA KACHOLIA JOINTLY WITH RASHMI ASHISH KACHOLIA AS TRUSTEES OF THE FAMILY BENEFICIARY TRUST";
  await page.route(/\/invest\/holders\?q=kacholia/, async (r) => {
    const res = await r.fetch();
    const body = await res.json();
    body.groups = body.groups.slice(0, 1).map((g: { names: { key: string; name: string; companies: number }[] }) => ({
      ...g, names: [...g.names, { key: LONG, name: LONG, companies: 2 }, { key: "ASHISH R KACHOLIA", name: "ASHISH R KACHOLIA", companies: 12 }] }));
    await r.fulfill({ response: res, json: body });
  });
  const errors = await open(page, "/invest/holders?q=kacholia", "Named holders across companies", 884);
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
  // it sorts like every table: by companies, high to low first
  await sortBy(table, "Companies", num, true);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

test("themes: the Ready to open chips carry no date", async ({ page }) => {
  await open(page, "/research/themes?region=IN", "Map it", 885);
  const chips = page.getByTestId("theme-already").locator(".theme-chip");
  await expect(chips.first()).toBeVisible();
  await expect(page.getByTestId("theme-already").locator(".theme-chip-day")).toHaveCount(0);
  const texts = await chips.allInnerTexts();
  for (const t of texts) expect(t, "no date on a chip").not.toMatch(/\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/);
});
