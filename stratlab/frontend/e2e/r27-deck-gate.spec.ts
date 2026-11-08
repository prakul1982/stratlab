import { expect, test } from "@playwright/test";
import { open, sane } from "./pages-kit";

// R27 (the owner's outside review of the R26 decks): a publication check runs before a theme deck is kept; its result, pass or fail per item
// and what was dropped, is kept with the deck and shown in Admin → Library, one row a deck.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const THEME = "India steel and mining";
const SHOTS = process.env.E2E_SHOTS;

test("Admin's Library lists each kept theme deck with its publication check", async ({ page }, info) => {
  // a Pro account of the fake world (no monthly deck limit); the same deck again the same day is the kept file, so repeats are cheap
  const headers = { Authorization: "Bearer pro-token" };
  // the theme read and its deck made, as a reader would download it (the fake world writes the map in a few seconds; a deck waits for it)
  let made = false;
  let last = "";
  for (let i = 0; i < 25 && !made; i++) {
    const r = await page.request.get(`${API}/research/theme-dive/deck?region=IN&format=pdf&q=${encodeURIComponent(THEME)}`, { headers });
    made = r.status() === 200;
    if (!made) { last = `${r.status()} ${(await r.text()).slice(0, 200)}`; await page.waitForTimeout(2000); }
  }
  expect(made, last).toBeTruthy();
  const errors = await open(page, "/admin/library", "Kept for everyone");
  const decks = page.getByRole("table", { name: "Theme decks and their publication check" });
  await expect(decks).toBeVisible({ timeout: 30_000 });
  const row = decks.getByRole("row").filter({ hasText: /steel/i }).first();
  await expect(row).toContainText(/\d of 9 passed/);
  await row.locator("summary").first().click();
  const items = row.getByTestId("deck-gate-items");
  await expect(items).toBeVisible();
  for (const label of ["Headlines reproduce from the tables", "Counts, periods, shares and rounding reconcile", "Peers pass comparability",
    "No advice words, forecasts or unsupported causes"]) await expect(items).toContainText(label);
  await expect(items).toContainText(/(Pass|Fail) · Figures have a period, source and formula/);
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    if (SHOTS) await decks.screenshot({ path: `${SHOTS}/r27-gate-${info.project.name}-${scheme}.png` });
  }
  await sane(page, errors);
});
