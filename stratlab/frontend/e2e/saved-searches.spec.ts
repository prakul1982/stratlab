import { expect, test, type Page } from "@playwright/test";

// R19 (owner, 7 Nov): "in themes make option to save the search and give option in them then to update it". On the fake world's theme
// (tests/fake_theme.py, "India steel and mining"), each project as its own fake Basic user: one click saves the theme, it appears in the
// saved list with when it was last updated, Update reads it again with the kit's bar and says what changed, Rename and Remove work, and My
// space shows the saved card while there is one. Desktop and phone.
const SHOTS = process.env.E2E_SHOTS;
const THEME_URL = "/research/themes?region=IN&q=" + encodeURIComponent("India steel and mining");

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, n: number, url = THEME_URL, scheme: "light" | "dark" = "light") {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.emulateMedia({ colorScheme: scheme });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(url);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => { await welcome.getByRole("button", { name: /^All of it/ }).click(); return true; }).catch(() => false);
  if (answered) await page.goto(url);
  return errors;
}

test("save a theme in one click, then update, rename and remove it from the saved list", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  // a fake Basic user of its own for each run (--repeat-each, retries): nothing saved before (load-<n> is Basic when n % 3 is 1)
  const n = (phone ? 52 : 4) + 3 * (info.repeatEachIndex + 3 * info.retry);
  const errors = await open(page, n);
  await expect(page.getByRole("heading", { name: "The whole chain in one table" })).toBeVisible({ timeout: 90_000 });
  const list = page.locator("#saved-themes");
  await expect(list).toHaveCount(0);                                     // nothing saved yet: no empty card
  // one click
  await page.getByTestId("save-search").click();
  await expect(page.getByTestId("saved-mark")).toHaveText("✓ Saved");
  await expect(list).toBeVisible();
  await expect(list.getByTestId("saved-count")).toHaveText("1 of 25 saved");
  const table = list.getByRole("table", { name: "Your saved themes" });
  await expect(table).toContainText(/India steel and mining/i);
  await expect(table.getByText("India", { exact: true })).toBeVisible();        // what it is for, without saying the name twice
  await expect(table).toContainText(/\d{1,2} [A-Z][a-z]{2} 20\d\d/);      // Last updated, a date
  // Update: reads it again and says what changed since the saved read (facts only, no raw error)
  await list.getByRole("button", { name: /^Update / }).click();
  const changed = list.getByTestId("saved-changes");
  await expect(changed).toBeVisible({ timeout: 90_000 });
  await expect(changed).toContainText(/What changed in “.+”/);
  await expect(changed).toContainText(/No change since the saved read\.|Read kept\.|added|removed|market value/);
  await expect(list).not.toContainText(/error|failed|exception|Traceback/i);
  if (SHOTS) {
    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      if (phone) await page.setViewportSize({ width: 390, height: 844 });
      await list.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${SHOTS}/saved-themes-${scheme}-${phone ? 390 : 1440}.png`, fullPage: false });
    }
    await page.emulateMedia({ colorScheme: "light" });
  }
  // Rename
  await list.getByRole("button", { name: /^Rename / }).click();
  const dialog = page.getByRole("dialog", { name: "Rename" });
  await dialog.getByRole("textbox", { name: "Name" }).fill("Steel names");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(table).toContainText("Steel names");
  // My space shows the saved card while there is one
  await page.goto("/mine");
  const card = page.locator('.mine-slot[data-card="saved"]');
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toContainText("Steel names");
  await expect(card.getByRole("link", { name: "Open Steel names" })).toHaveAttribute("href", /\/research\/themes\?region=IN&q=India\+steel\+and\+mining/);
  // Remove, asked in the page first
  await page.goto(THEME_URL);
  await expect(list).toBeVisible({ timeout: 30_000 });
  await list.getByRole("button", { name: "Remove Steel names" }).click();
  await page.getByRole("dialog", { name: /Remove “Steel names”\?/ }).getByRole("button", { name: "Remove" }).click();
  await expect(list).toHaveCount(0);
  await expect(page.getByTestId("save-search")).toBeVisible({ timeout: 90_000 });
  // nothing sideways on a phone
  if (phone) expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
});
