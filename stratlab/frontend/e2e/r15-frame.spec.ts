import { expect, test, type Locator, type Page } from "@playwright/test";

// Release 15, the page frame (owner, 7 Nov), in the fake world: sections that close and move, remembered across a reload; "Show less"
// after "Show all"; the "Estimate only" note at the top; one click that acts at once everywhere; the kit's calendar; no light stripe
// at a table's edge.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };

async function open(page: Page, where: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(where);
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

const section = (page: Page, key: string) => page.locator(`main [data-section="${key}"]`);
const top = async (l: Locator) => (await l.boundingBox())!.y;

// ---------- 1: every section closes to its header, and stays closed ----------
test("a section closes to its header row with one click and stays closed after a reload; it opens again the same way", async ({ page }) => {
  const errors = await open(page, "/money/tax-tools");
  const card = section(page, "how-these-are-worked-out");
  await expect(card).toBeVisible({ timeout: 30_000 });
  const fold = card.getByRole("button", { name: "Close section" });
  await expect(fold).toHaveAttribute("aria-expanded", "true");
  const tall = (await card.boundingBox())!.height;
  await fold.click();
  await expect(card.getByRole("button", { name: "Open section" })).toHaveAttribute("aria-expanded", "false");
  await expect(card).toHaveClass(/k-folded/);
  expect((await card.boundingBox())!.height).toBeLessThan(Math.min(tall, 90));
  await expect(card.getByRole("heading", { level: 2 })).toBeVisible();          // the header row stays
  await page.reload();
  await expect(section(page, "how-these-are-worked-out")).toHaveClass(/k-folded/, { timeout: 30_000 });
  // another page's sections are its own
  await page.goto("/tax-report");
  await expect(section(page, "tax-total")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main .k-folded")).toHaveCount(0);
  await page.goto("/money/tax-tools");
  const again = section(page, "how-these-are-worked-out");
  await again.getByRole("button", { name: "Open section" }).click();
  await expect(again).not.toHaveClass(/k-folded/);
  await page.reload();
  await expect(section(page, "how-these-are-worked-out").getByRole("button", { name: "Close section" })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
});

// ---------- 2: sections move up and down, and keep their place ----------
test("Move up puts a section above its neighbour, kept after a reload; On this page follows; Reset order puts it back", async ({ page }) => {
  const errors = await open(page, "/tax-report");
  const total = section(page, "tax-total"), gains = section(page, "tax-gains");
  await expect(gains).toBeVisible({ timeout: 30_000 });
  expect(await top(gains)).toBeGreaterThan(await top(total));
  const menu = gains.getByRole("button", { name: "Move section" });
  await menu.click();
  await expect(page.getByRole("menu", { name: "Move section" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Reset order" })).toHaveAttribute("aria-disabled", "true");
  await page.getByRole("menuitem", { name: "Move up" }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect.poll(async () => (await top(gains)) < (await top(total))).toBe(true);
  // "On this page" lists them where they now are
  const nav = page.getByRole("navigation", { name: "On this page" });
  await expect(nav.getByRole("link").nth(0)).toHaveText("Gains");
  await page.reload();
  await expect(section(page, "tax-gains")).toBeVisible({ timeout: 30_000 });
  await expect.poll(async () => (await top(section(page, "tax-gains"))) < (await top(section(page, "tax-total")))).toBe(true);
  // by keyboard: Enter opens the menu on its first item, the arrows move, Enter chooses
  await section(page, "tax-gains").getByRole("button", { name: "Move section" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "Move up" })).toBeFocused();
  await page.keyboard.press("ArrowUp");
  await expect(page.getByRole("menuitem", { name: "Reset order" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await top(section(page, "tax-gains"))) > (await top(section(page, "tax-total")))).toBe(true);
  await page.reload();
  await expect(section(page, "tax-gains")).toBeVisible({ timeout: 30_000 });
  expect(await top(section(page, "tax-gains"))).toBeGreaterThan(await top(section(page, "tax-total")));
  expect(errors).toEqual([]);
});

// ---------- 3: Show less after Show all ----------
test("Show all has a Show less that goes back to the first rows with the section's top in view", async ({ page }) => {
  const errors = await open(page, "/research/IN/RELIANCE");
  await expect(page.getByRole("button", { name: /^Show all \d+$/ }).first()).toBeVisible({ timeout: 30_000 });
  const key = (await page.locator("main [data-section]").filter({ has: page.getByRole("button", { name: /^Show all \d+$/ }) }).first().getAttribute("data-section"))!;
  const card = section(page, key);
  const all = card.getByRole("button", { name: /^Show all \d+$/ });
  const label = (await all.textContent())!;
  const short = (await card.boundingBox())!.height;
  await all.click();
  const less = card.getByRole("button", { name: "Show less" });
  await expect(less).toBeVisible();
  expect((await card.boundingBox())!.height).toBeGreaterThan(short);
  await less.click();
  await expect(card.getByRole("button", { name: label })).toBeVisible();
  await expect(less).toHaveCount(0);
  // the section's top comes back on screen (a smooth scroll)
  await expect.poll(async () => { const y = (await card.boundingBox())!.y; return y >= -1 && y < page.viewportSize()!.height; }).toBe(true);
  expect(errors).toEqual([]);
});

// ---------- 4: the standing note at the top ----------
test("the Estimate only note sits at the top of the page under its title, above every section", async ({ page }) => {
  for (const [path, first] of [["/tax-report", "upload-your-trades"], ["/money/tax-tools", "dividends-fy-2025-26"]] as const) {
    await open(page, path);
    const note = page.getByRole("note", { name: "Estimate only" });
    await expect(note).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".k-page-head + .page-lock-slot > .k-notice")).toHaveCount(1);
    await expect(section(page, first)).toBeVisible({ timeout: 30_000 });
    // measured once the page has settled (its figures arriving move everything down together)
    await expect.poll(async () => {
      const n = (await note.boundingBox())!, head = (await page.locator(".k-page-head").boundingBox())!;
      return n.y > head.y + head.height - 1 && n.y < (await top(section(page, first)));
    }).toBe(true);
  }
});

// ---------- 5: one click acts, everywhere ----------
test("a click on a page whose code is still on its way shows its loading bar at once, not the old page standing still", async ({ page }) => {
  await open(page, "/money/tax-tools");
  await expect(page.locator("main h1").first()).toHaveText("Tax tools", { timeout: 30_000 });
  await page.route(/\/assets\/.*\.js$/, async (r) => { await new Promise((ok) => setTimeout(ok, 2500)); await r.fallback(); });
  await page.locator('main a[href="/tax-report"]').filter({ visible: true }).first().click();
  await expect(page.locator(".k-loading").filter({ hasText: "Opening" })).toBeVisible({ timeout: 700 });
  await expect(page.locator("main h1").filter({ visible: true }).first()).toHaveText("Capital gains on your shares", { timeout: 30_000 });
});

test("with a menu open, a click on something else both closes the menu and acts, the page not jumping back to the menu", async ({ page }) => {
  const errors = await open(page, "/tax-report");
  const low = section(page, "tax-below"), up = section(page, "upload-your-trades");
  await expect(low).toBeVisible({ timeout: 30_000 });
  await low.getByRole("button", { name: "Move section" }).click();
  await expect(page.getByRole("menu")).toBeVisible();
  const fold = up.getByRole("button", { name: "Close section" });
  await fold.scrollIntoViewIfNeeded();
  const b = (await fold.boundingBox())!;
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.mouse.down(); await page.mouse.up();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(up).toHaveClass(/k-folded/);
  expect(errors).toEqual([]);
});

/** What a click can change: the address, open menus and dialogs, chosen options, the text, the focus, the scroll. */
const state = (page: Page) => page.evaluate(() => {
  const attrs = (sel: string, a: string) => Array.from(document.querySelectorAll(sel)).map((e) => e.getAttribute(a)).join("");
  const f = document.activeElement;
  return [location.href, document.querySelectorAll('[role=dialog], dialog[open], [role=menu], .info-pop').length, attrs("[aria-expanded]", "aria-expanded"),
    attrs("[aria-checked]", "aria-checked"), attrs("[aria-pressed]", "aria-pressed"), attrs("[aria-selected]", "aria-selected"),
    document.querySelectorAll("details[open], :checked, .k-folded").length, document.querySelector("main")?.textContent?.length,
    f ? `${f.tagName}${f.getAttribute("aria-label") ?? ""}${f.textContent?.slice(0, 30)}` : "", Math.round(window.scrollY)].join("|");
});

test("every button, link and fold on the tax and money pages acts on its first click", async ({ page }, info) => {
  test.setTimeout(240_000);
  const phone = info.project.name === "phone";
  await open(page, "/money/tax-tools");
  let acted = 0;
  page.on("download", () => { acted++; });
  page.on("filechooser", () => { acted++; });
  page.on("popup", (p) => { acted++; void p.close(); });
  const dead: string[] = [];
  for (const path of ["/money/tax-tools", "/tax-report", "/money"]) {
    await page.goto(path);
    await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(1500);
    const mark = () => page.evaluate(() => {
      const els = Array.from(document.querySelectorAll<HTMLElement>("main button, main a[href], main summary, main [role=radio], main [role=tab]"))
        .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !(e as HTMLButtonElement).disabled && !e.closest("tbody"); });
      els.forEach((e, i) => e.setAttribute("data-one", String(i)));
      return els.length;
    });
    const n = Math.min(await mark(), 45);
    for (let i = 0; i < n; i++) {
      const el = page.locator(`[data-one="${i}"]`);
      if (!(await el.count()) || !(await el.isVisible())) continue;
      const name = await el.evaluate((e) => `${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 40)} <${e.tagName.toLowerCase()}>`);
      if (/delete|remove|sign out|revoke|forget/i.test(name)) continue;
      await el.scrollIntoViewIfNeeded();
      const before = await state(page), was = acted;
      if (phone) await el.tap();
      else {
        const b = (await el.boundingBox())!;
        await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
        await page.mouse.down(); await page.mouse.up();
      }
      const moved = await expect.poll(async () => acted > was || (await state(page)) !== before, { timeout: 1500 }).toBe(true).then(() => true, () => false);
      if (!moved) dead.push(`${path}: ${name}`);
      if (new URL(page.url()).pathname !== path) {
        await page.goto(path);
        await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
        await page.waitForTimeout(800);
        await mark();
      } else {
        await page.keyboard.press("Escape");
        if (await page.locator("[role=dialog]").count()) await page.keyboard.press("Escape");
      }
    }
  }
  expect(dead, "controls that did nothing on their first click").toEqual([]);
});

// ---------- 6: the kit's calendar ----------
test("a date box opens the kit's calendar on its first click; a day picks; Esc and a click outside close it", async ({ page }) => {
  const errors = await open(page, "/money/calendar");
  const box = page.locator("main .k-date").first();
  await expect(box).toBeVisible({ timeout: 30_000 });
  const input = box.locator("input");
  await input.click();
  const cal = box.getByRole("dialog");
  await expect(cal).toBeVisible();
  await expect(cal.getByRole("grid")).toBeVisible();
  await expect(input).toBeFocused();                       // typing still works while it is open
  const title = (await cal.locator(".k-cal-title").textContent())!;
  await cal.getByRole("button", { name: "Next month" }).click();
  await expect(cal.locator(".k-cal-title")).not.toHaveText(title);
  const day = cal.locator(".k-cal-day:not(.out):not(:disabled)").nth(10);
  const said = (await day.getAttribute("aria-label"))!;      // "Tuesday 10 November 2026"
  await day.click();
  await expect(cal).toHaveCount(0);
  const [, d, m, y] = said.match(/(\d+) (\w+) (\d{4})$/)!;
  await expect(input).toHaveValue(`${d} ${m.slice(0, 3)} ${y}`);
  // its button opens it with focus on the chosen day; the arrows move; Esc closes and goes back to the box
  await box.getByRole("button", { name: /on a calendar$/ }).click();
  await expect(cal).toBeVisible();
  await expect(cal.locator(".k-cal-day.on")).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(cal.locator(".k-cal-day:focus")).not.toHaveClass(/\bon\b/);
  await page.keyboard.press("Escape");
  await expect(cal).toHaveCount(0);
  await expect(input).toBeFocused();
  await input.click();
  await expect(cal).toBeVisible();
  await page.locator("main h1").first().click();
  await expect(cal).toHaveCount(0);
  expect(errors).toEqual([]);
});

// ---------- 7: no light stripe ----------
test("a table that does not scroll has no painted edge or fade at its right side", async ({ page }) => {
  await open(page, "/tax-report");
  await expect(page.locator("main .k-tbl-wrap").first()).toBeVisible({ timeout: 30_000 });
  const edges = await page.evaluate(() => Array.from(document.querySelectorAll<HTMLElement>(".k-tbl-wrap, .table-wrap"))
    .filter((w) => w.scrollWidth <= w.clientWidth + 1)
    .map((w) => { const s = getComputedStyle(w); return `${s.backgroundImage} ${s.maskImage === "none" ? "" : s.getPropertyValue("--k-edge").trim()}`; }));
  expect(edges.length).toBeGreaterThan(0);
  for (const e of edges) expect(e.trim()).toMatch(/^none( 0px)?$/);
});
