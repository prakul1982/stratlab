import { expect, test, type Page } from "@playwright/test";
import { open, sane, sessionAs } from "./pages-kit";

// R19 (owner, 7 Nov): a theme read is kept once for everyone and offered in the search box ("Ready to open", LIVE6-012); every stored read says
// "Last updated" with a Refresh and the refreshes left today (none left: the button is off); Settings' "Your usage" matches the server;
// Admin → Library shows what is kept. Each test signs in as its own Free user (refreshes are counted per person).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const THEME = "India steel and mining";
const SHOTS = process.env.E2E_SHOTS;

function who(info: { project: { name: string }; repeatEachIndex: number }, slot: number) {
  const i = (info.project.name === "phone" ? 24 : 0) + info.repeatEachIndex * 4 + slot;
  return { token: `r19-${i}`, session: sessionAs(`r19-${i}`, `u-r19-${i}`, `r19${i}@example.com`) };
}

async function usageOf(page: Page, token: string) {
  const r = await page.request.get(`${API}/me/usage`, { headers: { Authorization: `Bearer ${token}` } });
  expect(r.ok()).toBeTruthy();
  return (await r.json()) as { rows: { key: string; label: string; used: number | null; limit: number | null; left: number | null }[] };
}

test("a theme read is offered as already read, says when it was updated, and Refresh shows what's left", async ({ page }, info) => {
  const me = who(info, 0);
  const url = `/research/themes?region=IN&q=${encodeURIComponent(THEME)}`;
  // the refreshes left, as the server would say them, going down after a Refresh: 1 left, then none
  let left = 1;
  await page.route((u) => u.href.startsWith(API) && u.pathname === "/me/usage", async (r) => {
    const res = await r.fetch();
    const d = await res.json();
    // (updated on purpose, LIVE7B-002: the count beside Refresh is the fresh AI reads, the one Plans and Account state)
    d.rows = d.rows.map((x: { key: string }) => (x.key === "research_ai" ? { ...x, used: 3 - left, limit: 3, left } : x));
    // (updated on purpose, FREE-TIER: this user is on Free, which has no Refresh (refresh_off); the count beside it is a paid plan's here)
    d.refresh_off = false;
    await r.fulfill({ response: res, json: d });
  });
  const errors = await open(page, url, "The whole chain in one table", me.session);
  const head = page.getByTestId("stored-stamp").first();
  await expect(head.getByTestId("stored-at")).toHaveText(/^Last updated \d{1,2} [A-Z][a-z]{2}/, { timeout: 90_000 });
  await expect(head.getByTestId("refresh-left")).toHaveText("1 left today");
  left = 0;
  await head.getByRole("button", { name: "Refresh" }).click();
  await expect(head.getByTestId("refresh-left")).toHaveText("None left today", { timeout: 30_000 });
  await expect(head.getByRole("button", { name: /Refresh/ })).toBeDisabled();
  await expect(head.getByRole("button", { name: /Refresh/ })).toHaveAttribute("title", "No fresh AI reads left today, back at midnight IST");
  await expect(page.getByTestId("stored-note")).toBeVisible();                        // "already fresh" (just written) or what it did
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/r19-stamp-${info.project.name}-${scheme}.png`, fullPage: false });
  }
  await expect(page.getByText(/Traceback|Internal Server Error|undefined|NaN/)).toHaveCount(0);
  // the search box offers it, read and kept for everyone
  await page.goto("/research/themes?region=IN");
  await page.getByRole("textbox", { name: "Theme" }).fill("steel");
  const already = page.getByTestId("theme-already");
  await expect(already).toBeVisible({ timeout: 30_000 });
  // LIVE6-012: the shared library, never one person's reading ("Ready to open", the date the map was updated; no "Already read")
  await expect(already).toContainText("Ready to open:");
  await expect(already).not.toContainText(/Already read|, read \d/);
  await expect(already.getByRole("button", { name: /steel.*· India, updated \d{1,2} [A-Z][a-z]{2}/i }).first()).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/r19-theme-${info.project.name}.png`, fullPage: false });
  await sane(page, errors);
});

test("Settings' Your usage lists every limit as the server counts it", async ({ page }, info) => {
  const me = who(info, 1);
  const errors = await open(page, "/settings#usage", "Your usage", me.session);
  const table = page.getByRole("table", { name: "Your usage" });
  await expect(table).toBeVisible();
  const server = await usageOf(page, me.token);
  expect(server.rows.find((r) => r.key === "refresh")).toBeUndefined();            // (updated on purpose, LIVE7B-002: one daily count)
  // (updated on purpose, FREE-TIER: this user is on Free: 5 fresh AI reads a day and no Refresh)
  expect(server.rows.find((r) => r.key === "research_ai")?.limit).toBe(5);
  expect((server as { refresh_off?: boolean }).refresh_off).toBe(true);
  await expect(table.getByRole("row")).toHaveCount(server.rows.length + 1);
  for (const r of server.rows) {
    const row = table.getByRole("row").filter({ hasText: r.label });
    await expect(row).toHaveCount(1);
    if (r.used != null) await expect(row).toContainText(r.limit == null ? `${r.used} (no limit)` : `${r.used} of ${r.limit}`);
  }
  await expect(table.getByRole("row").filter({ hasText: "Fresh AI reads, refreshes included" })).toContainText("Midnight India time");
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/r19-usage-${info.project.name}-${scheme}.png`, fullPage: true });
  }
  await sane(page, errors);
});

test("Admin's Library shows every shared store and the theme library", async ({ page }, info) => {
  // a theme kept first, as a reader would have read it (the fake world writes it in a few seconds)
  const me = who(info, 2);
  for (let i = 0; i < 30; i++) {
    const r = await page.request.get(`${API}/research/sector?region=IN&q=${encodeURIComponent(THEME)}`, { headers: { Authorization: `Bearer ${me.token}` } });
    if ((await r.json()).ai === null) break;
    await page.waitForTimeout(2000);
  }
  const errors = await open(page, "/admin/library", "Kept for everyone");
  const stores = page.getByRole("table", { name: "Shared stores" });
  await expect(stores).toBeVisible({ timeout: 30_000 });
  await expect(stores.getByRole("row").filter({ hasText: "Theme library" })).toHaveCount(1);
  await expect(page.getByTestId("library-total")).toContainText("Served");
  const themes = page.getByRole("table", { name: "Themes in the library" });
  await expect(themes).toBeVisible({ timeout: 30_000 });
  await expect(themes.getByRole("row").filter({ hasText: /steel/i }).first()).toBeVisible();
  await expect(themes.getByRole("button", { name: "Refresh now" }).first()).toBeVisible();
  await expect(page.getByRole("table", { name: "Other shared data" }).getByRole("row").filter({ hasText: "Company pages" })).toHaveCount(1);
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/r19-admin-${info.project.name}-${scheme}.png`, fullPage: true });
  }
  await sane(page, errors);
});
