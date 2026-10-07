import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Accessibility: axe-core on the main pages (fails on serious or critical problems), and the keyboard behaviour axe
// can't see: every dialog keeps focus inside and hands it back to what opened it, the phone menu is a modal, pop-ups
// return focus, the (i) buttons are named after what they explain, and a skip link comes first.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string, { tour = true, as = false } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(([s, seen, own]) => {
    if (!own) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    if (seen) localStorage.setItem("stratlab.tour.v1", "1"); else localStorage.removeItem("stratlab.tour.v1");
  }, [session, tour, as] as const);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 4000 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.locator("main")).toBeVisible();
  return errors;
}

/** What has focus, and whether it is inside `sel`. */
const focusIn = (page: Page, sel: string) => page.evaluate((s) => !!document.activeElement?.closest(s), sel);

/** Tab `n` times (Shift+Tab for the second half) and say whether focus ever left `sel`. */
async function staysIn(page: Page, sel: string, n = 24) {
  for (let i = 0; i < n; i++) {
    await page.keyboard.press(i < n / 2 ? "Tab" : "Shift+Tab");
    if (!(await focusIn(page, sel))) return false;
  }
  return true;
}

const PAGES = ["/mine", "/trade", "/invest", "/money", "/holdings", "/money/net-worth", "/research/IN/RELIANCE", "/research/screens", "/library",
  "/notebooks", "/options", "/paper", "/trade/positioning", "/alerts", "/settings", "/new", "/admin/emails"];

test("axe finds no serious or critical problems on the main pages", async ({ page }, info) => {
  test.setTimeout(240_000);
  const found: string[] = [];
  for (const path of PAGES) {
    await open(page, path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(500);
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
    for (const v of r.violations.filter((x) => x.impact === "serious" || x.impact === "critical"))
      found.push(`${path} [${info.project.name}] ${v.id}: ${v.help} (${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(", ")})`);
  }
  expect(found, found.join("\n")).toEqual([]);
});

test("axe: the dark theme passes too", async ({ browser }) => {
  test.setTimeout(120_000);
  const ctx = await browser.newContext({ colorScheme: "dark", viewport: { width: 1300, height: 900 } });
  const page = await ctx.newPage();
  const found: string[] = [];
  for (const path of ["/mine", "/trade", "/holdings", "/research/IN/RELIANCE", "/options"]) {
    await open(page, path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    for (const v of r.violations.filter((x) => x.impact === "serious" || x.impact === "critical")) found.push(`${path} ${v.id}: ${v.help}`);
  }
  await ctx.close();
  expect(found, found.join("\n")).toEqual([]);
});

test("the command palette keeps focus inside, Esc closes it and focus goes back to its button", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the button is in the desktop sidebar");
  const errors = await open(page, "/mine");
  const btn = page.locator(".search-btn");
  await btn.click();
  const dialog = page.getByRole("dialog", { name: "Ask or do anything" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("textbox")).toBeFocused();
  expect(await staysIn(page, ".palette")).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(btn).toBeFocused();
  expect(errors).toEqual([]);
});

test("the welcome tour keeps focus inside and gives it back when it closes", async ({ page }) => {
  const errors = await open(page, "/mine", { tour: false });
  const dialog = page.getByRole("dialog", { name: "A quick tour" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Next" })).toBeFocused();
  expect(await staysIn(page, "[role=dialog]")).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(await page.evaluate(() => document.activeElement && document.activeElement !== document.body)).toBe(true);
  expect(errors).toEqual([]);
});

test("Set alert: a modal that keeps focus and returns it to the button", async ({ page }) => {
  const errors = await open(page, "/research/IN/RELIANCE");
  const btn = page.getByRole("button", { name: "Set alert" }).first();
  await btn.click();
  const dialog = page.getByRole("dialog", { name: /Alert on/ });
  await expect(dialog).toBeVisible();
  expect(await focusIn(page, "[role=dialog]")).toBe(true);
  expect(await staysIn(page, "[role=dialog]")).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(btn).toBeFocused();
  expect(errors).toEqual([]);
});

test("on a phone the menu is a modal: named, expanded, focus kept inside, Esc returns to the menu button", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the drawer is the phone's menu");
  const errors = await open(page, "/mine");
  const btn = page.getByRole("button", { name: "Open menu" });
  await expect(btn).toHaveAttribute("aria-expanded", "false");
  // shut, none of its links take focus
  expect(await page.evaluate(() => Array.from(document.querySelectorAll("aside.sidebar a, aside.sidebar button")).some((el) => (el as HTMLElement).checkVisibility({ visibilityProperty: true })))).toBe(false);
  await btn.click();
  const drawer = page.getByRole("dialog", { name: "Menu" });
  await expect(drawer).toBeVisible();
  await expect(btn).toHaveAttribute("aria-expanded", "true");
  await expect(drawer).toHaveAttribute("aria-modal", "true");
  expect(await focusIn(page, "aside.sidebar")).toBe(true);
  expect(await staysIn(page, "aside.sidebar", 30)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.locator("aside.sidebar.open")).toHaveCount(0);
  await expect(btn).toBeFocused();
  expect(errors).toEqual([]);
});

test("a skip link is the first Tab stop and moves focus to the page", async ({ page }) => {
  await open(page, "/mine");
  await page.locator("body").focus();
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page.locator("main#main")).toBeFocused();
});

test("(i) buttons are named after what they explain and sit beside headings, not inside them", async ({ page }) => {
  for (const path of ["/mine", "/holdings", "/research/screens", "/options"]) {
    await open(page, path);
    await expect(page.locator(".info-btn").first()).toBeAttached();
    const bad = await page.evaluate(() => Array.from(document.querySelectorAll(".info-btn")).flatMap((b) => {
      const name = b.getAttribute("aria-label") ?? "";
      return [b.closest("h1, h2, h3, h4, h5, h6") ? `inside a heading: ${name}` : "", /^About this\b/.test(name) && !/^About this (data|card)$/.test(name) ? `generic name: ${name}` : ""].filter(Boolean);
    }));
    expect(bad, path).toEqual([]);
  }
  await open(page, "/mine");
  await expect(page.getByRole("button", { name: "About Markets" })).toBeAttached();
});

test("accessible names start with the visible text", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the sidebar buttons are in the drawer on a phone");
  await open(page, "/mine");
  for (const sel of [".search-btn", ".acct-btn"]) {
    const el = page.locator(sel);
    const visible = (await el.innerText()).replace(/\s+/g, " ").trim();
    const name = await el.evaluate((e) => (e.getAttribute("aria-label") ?? e.textContent ?? "").replace(/\s+/g, " ").trim());
    expect(name.startsWith(visible.split(" ")[0]), `${sel}: "${name}" vs "${visible}"`).toBe(true);
    expect(name.replace(/\s/g, "")).toContain(visible.replace(/\s/g, ""));
  }
});

test("a pop-up hands focus back: a rule word's editor closes with Esc onto the word", async ({ page, request }, info) => {
  const api = process.env.E2E_API ?? "http://127.0.0.1:8765";
  const headers = { Authorization: "Bearer admin-token" };
  const ema = { name: "Focus check", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
    exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${api}/notebooks`, { headers, data: { name: `Focus ${info.project.name}`, question: "q", strategy: ema, instrument: "CRYPTO:BTC-USD" } })).json();
  await open(page, `/n/${nb.id}`);
  const word = page.locator("button.token").first();
  await expect(word).toBeVisible({ timeout: 30_000 });
  await word.click();
  await expect(page.locator(".k-popover")).toBeVisible();
  expect(await focusIn(page, ".k-popover")).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.locator(".k-popover")).toHaveCount(0);
  await expect(word).toBeFocused();
  await request.delete(`${api}/notebooks/${nb.id}`, { headers });
});

test("removing a holding moves focus to the next row's Edit button, not the top of the page", async ({ page, request }, info) => {
  // each project signs in as its own fake user, so the two runs never share holdings
  const [token, id, email] = info.project.name === "phone" ? ["load-94", "u-load-94", "load94@example.com"] : ["load-91", "u-load-91", "load91@example.com"];
  const api = process.env.E2E_API ?? "http://127.0.0.1:8765";
  const headers = { Authorization: `Bearer ${token}` };
  const res = await request.put(`${api}/holdings`, { headers, data: { items: [{ symbol: "RELIANCE", qty: 10, avg: 2400, market: "IN" }, { symbol: "TCS", qty: 5, avg: 3500, market: "IN" }, { symbol: "INFY", qty: 8, avg: 1500, market: "IN" }] } });
  expect(res.ok()).toBe(true);
  await page.addInitScript(([t, i, e]) => localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: t, token_type: "bearer", expires_in: 86400,
    expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r", user: { id: i, aud: "authenticated", email: e, role: "authenticated", app_metadata: {}, user_metadata: {} } })), [token, id, email]);
  await open(page, "/holdings", { as: true });
  const edits = page.locator("[data-row-edit]");
  await expect(edits).toHaveCount(3, { timeout: 30_000 });
  const third = (await edits.nth(2).getAttribute("aria-label"))!;
  await edits.nth(1).click();
  await page.getByRole("dialog").getByRole("button", { name: /Remove from holdings/ }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(edits).toHaveCount(2);
  await expect(page.getByRole("button", { name: third })).toBeFocused();
  await request.put(`${api}/holdings`, { headers, data: { items: [] } });
});
