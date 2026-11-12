import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { open, sessionAs } from "./pages-kit";

// f4: a theme's change log ("What changed") on the theme page, and its Excel workbook beside the deck downloads. Pro (export-16/17 in
// tests/fake_db.py) downloads the workbook and sees the whole log; Free (export-20/21) sees the latest refresh's counts and first rows with
// the plan note, and the workbook button says it is on Basic without asking the server.

const THEME = "/research/themes?region=IN&q=" + encodeURIComponent("India steel and mining");
const pro = (phone: boolean) => { const i = 16 + (phone ? 1 : 0); return sessionAs(`export-${i}`, `u-export-${i}`, `export${i}@example.com`); };
const free = (phone: boolean) => { const i = 20 + (phone ? 1 : 0); return sessionAs(`export-${i}`, `u-export-${i}`, `export${i}@example.com`); };

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

/** The dive as the server sends it to a plan without the whole log: the latest entry cut to 5 rows (theme_changes.view). */
async function withShortLog(page: Page) {
  await page.route("**/research/theme-dive?*", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.changes = {
      full: false, since: "2026-10-01", older: 2,
      entries: [{
        at: "2026-10-04T06:00:00+00:00", d: "2026-10-04", cause: "refresh", hidden: 2,
        counts: { removed: 3, added: 4, moved: 0, layers: 0, restated: 0 },
        removed: [0, 1, 2].map((i) => ({ symbol: `OUT${i}`, name: `Gone Company ${i}`, layer: "Steel making", why: "another business (filed under Power Generation)" })),
        added: [0, 1].map((i) => ({ symbol: `NEW${i}`, name: `New Company ${i}`, layer: "Coal and metal mining" })),
        moved: [], layers: [], restated: [],
      }],
    };
    await route.fulfill({ response: res, json: body });
  });
}

test("theme: Pro sees 'What changed' and saves the theme as an Excel workbook", async ({ page }, info) => {
  test.setTimeout(240_000);
  const phone = info.project.name === "phone";
  const errors = await open(page, THEME, "The whole chain in one table", pro(phone));
  const card = page.getByTestId("theme-changes");
  await expect(card.getByRole("heading", { name: "What changed" })).toBeVisible();
  // the theme's first stored read: nothing to compare yet, said plainly
  await expect(card.getByTestId("theme-changes-empty")).toBeVisible();
  const box = page.getByTestId("theme-downloads");
  const [file] = await Promise.all([page.waitForEvent("download"), box.getByRole("button", { name: "Workbook (XLSX)" }).click()]);
  expect(file.suggestedFilename()).toMatch(/^StratLab - India steel and mining theme \(India\) - \d{1,2} [A-Z][a-z]{2} \d{4}\.xlsx$/i);
  const bytes = await readFile((await file.path())!);
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  const text = bytes.toString("latin1");
  for (const part of ["xl/worksheets/sheet7.xml", "xl/styles.xml"]) expect(text).toContain(part);
  expect(errors).toEqual([]);
});

test("theme: Free sees the latest refresh's summary with the plan note, and the workbook's lock", async ({ page }, info) => {
  test.setTimeout(240_000);
  const phone = info.project.name === "phone";
  await withShortLog(page);
  let asked = 0;
  await page.route("**/research/theme-dive/workbook?*", (r) => { asked++; return r.fallback(); });
  const errors = await open(page, THEME, "The whole chain in one table", free(phone));
  const card = page.getByTestId("theme-changes");
  await expect(card.getByText("Latest refresh", { exact: true })).toBeVisible();
  await expect(card.getByText("4 companies added, 3 companies removed.")).toBeVisible();
  const table = card.getByRole("table", { name: /What changed on 4 Oct 2026/ });
  await expect(table.getByRole("row")).toHaveCount(6);                    // the header and the first 5 changes
  await expect(table.getByText("From Steel making: another business (filed under Power Generation)").first()).toBeVisible();
  await expect(card.locator(".plan-note")).toContainText("The full change log, with 2 earlier refreshes, is on the Basic plan.");
  await card.scrollIntoViewIfNeeded();
  await page.getByTestId("theme-downloads").getByRole("button", { name: "Workbook (XLSX)" }).click();
  await expect(page.getByTestId("theme-workbook-lock")).toContainText("A theme's workbook (Excel) is on the Basic plan");
  expect(asked).toBe(0);
  expect(errors).toEqual([]);
});
