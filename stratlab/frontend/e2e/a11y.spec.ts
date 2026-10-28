import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Accessibility: axe-core on the main pages (fails on serious or critical problems), and the keyboard behaviour axe
// can't see: every dialog keeps focus inside and hands it back to what opened it, the phone menu is a modal, pop-ups
// return focus, the (i) buttons are named after what they explain, and a skip link comes first.
// A11Y-1 widened the axe pass to the pages people use most (a notebook and an experiment, IPOs, mutual funds, the tax pages, Account, and the
// landing and Plans pages signed out; light and dark; phone and desktop) and added what axe can't see: a text field's edge is 3:1 against
// what is behind it, whatever takes a click takes the keyboard, every Tab stop shows where it is, a link in an (i) box can be read, a chart
// menu closed with Esc hands focus back, a changing placeholder stops for "reduce motion", and the (i) is 44px on a phone.
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

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const PAGES = ["/mine", "/trade", "/invest", "/money", "/holdings", "/money/net-worth", "/research/IN/RELIANCE", "/research/screens", "/library",
  "/notebooks", "/options", "/paper", "/trade/positioning", "/alerts", "/settings", "/new", "/admin/emails", "/invest/ipos", "/money/mutual-funds",
  "/tax-report", "/money/us-tax", "/account"];
/** A notebook with one finished experiment, made for this run (the pages of a notebook and of an experiment); the caller deletes it. */
async function ownNotebook(request: APIRequestContext, name: string) {
  const ema = { name: "Axe check", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
    exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name, question: "q", strategy: ema, instrument: "CRYPTO:BTC-USD" } })).json();
  await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 800 } });
  return nb.id as string;
}
const serious = (r: { violations: { id: string; impact?: string | null; help: string; nodes: { target: unknown[] }[] }[] }, where: string) =>
  r.violations.filter((x) => x.impact === "serious" || x.impact === "critical").map((v) => `${where} ${v.id}: ${v.help} (${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(", ")})`);

test("axe finds no serious or critical problems on the main pages", async ({ page, request }, info) => {
  test.setTimeout(420_000);
  const found: string[] = [];
  const nb = await ownNotebook(request, `Axe ${info.project.name} light`);
  for (const path of [...PAGES, `/n/${nb}`, `/n/${nb}/e/1`]) {
    await open(page, path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(500);
    // a person opens the folded parts to use them: check them open
    await page.evaluate(() => document.querySelectorAll("details:not([open])").forEach((d) => d.setAttribute("open", "")));
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
    found.push(...serious(r, `${path.replace(nb, "<notebook>")} [${info.project.name}]`));
  }
  await request.delete(`${API}/notebooks/${nb}`, { headers: admin });
  expect(found, found.join("\n")).toEqual([]);
});

test("axe: the dark theme passes too", async ({ browser, request }, info) => {
  test.setTimeout(420_000);
  const phone = info.project.name === "phone";
  const ctx = await browser.newContext({ colorScheme: "dark", viewport: phone ? { width: 390, height: 844 } : { width: 1300, height: 900 }, hasTouch: phone, isMobile: phone });
  const page = await ctx.newPage();
  const found: string[] = [];
  const nb = await ownNotebook(request, `Axe ${info.project.name} dark`);
  for (const path of [...PAGES, `/n/${nb}`, `/n/${nb}/e/1`]) {
    await open(page, path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(300);
    await page.evaluate(() => document.querySelectorAll("details:not([open])").forEach((d) => d.setAttribute("open", "")));
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    found.push(...serious(r, `${path.replace(nb, "<notebook>")} [dark]`));
  }
  await ctx.close();
  await request.delete(`${API}/notebooks/${nb}`, { headers: admin });
  expect(found, found.join("\n")).toEqual([]);
});

test("axe: the landing page and Plans, signed out, in both themes", async ({ browser }, info) => {
  test.setTimeout(240_000);
  const phone = info.project.name === "phone";
  const found: string[] = [];
  for (const scheme of ["light", "dark"] as const) {
    const ctx = await browser.newContext({ colorScheme: scheme, viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 900 }, hasTouch: phone, isMobile: phone });
    const page = await ctx.newPage();
    for (const path of ["/", "/plans"]) {
      await open(page, path, { as: true });                      // `as`: no sign-in, so this is what a visitor sees
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await page.waitForTimeout(300);
      await page.evaluate(() => document.querySelectorAll("details:not([open])").forEach((d) => d.setAttribute("open", "")));
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "best-practice"]).analyze();
      found.push(...serious(r, `${path} [signed out, ${scheme}]`));
    }
    await ctx.close();
  }
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
  // the tour shows once per account, so the test opens it the way Help does (an account that has seen it would not show it)
  const errors = await open(page, "/mine");
  await page.evaluate(() => window.dispatchEvent(new Event("stratlab:tour")));
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

// ---- A11Y-1: what axe can't see ----------------------------------------------------------------------------------------------------------------

const viewFor = (name: string) => (name === "phone" ? { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true } : { viewport: { width: 1440, height: 900 } });

test("a text field's edge is 3:1 against what is behind it, in light and dark (WCAG 1.4.11)", async ({ browser }, info) => {
  test.setTimeout(240_000);
  const faint: string[] = [];
  for (const scheme of ["light", "dark"] as const) {
    const ctx = await browser.newContext({ colorScheme: scheme, ...viewFor(info.project.name) });
    const page = await ctx.newPage();
    for (const path of ["/new", "/options", "/account", "/tax-report", "/money/us-tax", "/library", "/holdings", "/research/IN/RELIANCE"]) {
      await open(page, path);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await page.waitForTimeout(300);
      const rows = await page.evaluate(() => {
        const lum = (c: number[]) => { const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
        const ratio = (a: number[], b: number[]) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
        const parse = (s: string): number[] | null => {
          const m = s.match(/rgba?\(([^)]+)\)/) ?? s.match(/color\(srgb ([^)]+)\)/);
          if (!m) return null;
          const p = m[1].split(/[ ,/]+/).map(Number);
          return s.startsWith("color(") ? [p[0] * 255, p[1] * 255, p[2] * 255, p[3] ?? 1] : [p[0], p[1], p[2], p[3] ?? 1];
        };
        const bgOf = (el: Element): number[] => {
          const chain: number[][] = [];
          for (let e: Element | null = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c[3] > 0) { chain.push(c); if (c[3] >= 1) break; } }
          let base = parse(getComputedStyle(document.body).backgroundColor)?.slice(0, 3) ?? [255, 255, 255];
          if (chain.length && chain[chain.length - 1][3] >= 1) base = chain[chain.length - 1].slice(0, 3);
          for (let i = chain.length - 1; i >= 0; i--) { const c = chain[i]; if (c[3] >= 1) continue; base = [0, 1, 2].map((k) => c[k] * c[3] + base[k] * (1 - c[3])); }
          return base;
        };
        const shown = (e: Element) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 4 && r.height > 4 && cs.visibility !== "hidden" && cs.display !== "none" && cs.opacity !== "0"; };
        const out: string[] = [];
        for (const e of Array.from(document.querySelectorAll("input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=range]):not([type=file]), select, textarea"))) {
          if (!shown(e) || e.closest("[aria-hidden=true]")) continue;
          // an edge is its own border, or (a bare box inside a bordered one, like the big search box) the nearest bordered box around it
          let edge: Element | null = e; let c: number[] | null = null;
          for (let i = 0; i < 4 && edge; i++, edge = edge.parentElement) {
            const cs = getComputedStyle(edge); const col = parse(cs.borderTopColor);
            if ((parseFloat(cs.borderTopWidth) || 0) > 0 && col && col[3] > 0) { c = col; break; }
          }
          const around = bgOf(e.parentElement ?? e);
          const best = Math.max(c ? ratio(c.slice(0, 3), around) : 0, ratio(bgOf(e), around));
          if (best < 3) out.push(`${e.tagName.toLowerCase()} "${(e.getAttribute("aria-label") ?? (e as HTMLInputElement).labels?.[0]?.textContent ?? e.className).toString().trim().slice(0, 30)}" ${best.toFixed(2)}:1`);
        }
        return out;
      });
      for (const r of rows) faint.push(`${path} [${scheme}] ${r}`);
    }
    await ctx.close();
  }
  expect(faint, faint.join("\n")).toEqual([]);
});

test("whatever takes a click can be reached and used from the keyboard", async ({ page }) => {
  test.setTimeout(180_000);
  const only: string[] = [];
  for (const path of ["/mine", "/trade", "/invest", "/holdings", "/research/IN/RELIANCE", "/library", "/options", "/money/net-worth", "/account"]) {
    await open(page, path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(300);
    const rows = await page.evaluate(() => {
      const focusable = "a[href],button,input,select,textarea,summary,[tabindex],[contenteditable=true]";
      const shown = (e: Element) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 2 && r.height > 2 && cs.visibility !== "hidden" && cs.display !== "none" && cs.opacity !== "0"; };
      const out: string[] = [];
      for (const e of Array.from(document.body.querySelectorAll("*"))) {
        if (!shown(e) || getComputedStyle(e).cursor !== "pointer") continue;
        if (e.matches(focusable) || e.closest(focusable) || e.querySelector(focusable) || e.closest("label, [role=button], [role=option], [role=tab], [role=menuitem]")) continue;
        if (e.parentElement && getComputedStyle(e.parentElement).cursor === "pointer") continue;
        out.push(`${e.tagName.toLowerCase()}.${(e.getAttribute("class") ?? "").split(" ")[0]} "${(e.textContent ?? "").trim().slice(0, 24)}"`);
      }
      return out;
    });
    for (const r of rows) only.push(`${path}: ${r}`);
  }
  expect(only, only.join("\n")).toEqual([]);
});

test("every Tab stop shows where focus is, and Tab never gets stuck", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a phone has no Tab key in the way these pages are used; the desktop pass covers the same controls");
  test.setTimeout(180_000);
  const bad: string[] = [];
  for (const path of ["/mine", "/new", "/library", "/holdings", "/options", "visitor:/", "visitor:/plans"]) {
    await open(page, path.replace("visitor:", ""), { as: path.startsWith("visitor:") });        // the last two as a visitor, signed out
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
    const seen = new Set<string>();
    for (let i = 0; i < 70; i++) {
      await page.keyboard.press("Tab");
      const s = await page.evaluate(() => {
        const e = document.activeElement as HTMLElement | null;
        if (!e || e === document.body) return null;
        const mark = (el: Element) => { const cs = getComputedStyle(el); return (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 1) || cs.boxShadow !== "none"; };
        const wrap = e.closest(".search-box, .k-search");                 // a bare input inside a search box: the box around it shows the focus
        return { id: `${e.tagName}.${e.className}|${(e.getAttribute("aria-label") ?? e.textContent ?? "").trim().slice(0, 24)}|${Math.round(e.getBoundingClientRect().top + scrollY)}`, shows: mark(e) || (!!wrap && mark(wrap)) };
      });
      if (!s) break;                                                      // focus left the page: the loop is complete
      if (!s.shows) bad.push(`${path}: ${s.id}`);
      if (seen.has(s.id) && seen.size < 3) bad.push(`${path}: Tab is stuck on ${s.id}`);
      seen.add(s.id);
    }
  }
  expect(bad, bad.join("\n")).toEqual([]);
});

test("a link inside an (i) box is readable on it", async ({ page }) => {
  test.setTimeout(120_000);
  let links = 0;
  const bad: string[] = [];
  for (const path of ["/holdings", "/research/IN/RELIANCE"]) {
    await open(page, path);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    const n = Math.min(await page.locator(".info-btn").count(), 40);
    for (let i = 0; i < n; i++) {
      const b = page.locator(".info-btn").nth(i);
      if (!(await b.isVisible())) continue;
      await b.focus();
      await page.keyboard.press("Enter");
      const r = await page.evaluate(() => {
        const a = document.querySelector<HTMLElement>(".info-pop a");
        if (!a) return null;
        const pop = a.closest(".info-pop")!;
        const rgb = (s: string) => (s.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
        const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        const lum = (c: number[]) => 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
        const x = lum(rgb(getComputedStyle(a).color)), y = lum(rgb(getComputedStyle(pop).backgroundColor));
        return { ratio: (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05), text: (a.textContent ?? "").trim().slice(0, 30) };
      });
      if (r) { links++; if (r.ratio < 4.5) bad.push(`${path}: "${r.text}" is ${r.ratio.toFixed(2)}:1`); }
      await page.keyboard.press("Escape");
    }
  }
  expect(links, "no (i) box with a link was found to check").toBeGreaterThan(0);
  expect(bad, bad.join("\n")).toEqual([]);
});

test("a chart menu closed with Esc hands focus back to its button", async ({ page }) => {
  await open(page, "/research/IN/RELIANCE");
  const btn = page.getByRole("button", { name: "Compare", exact: true }).first();
  await expect(btn).toBeVisible({ timeout: 30_000 });
  await btn.click();
  const box = page.getByRole("textbox", { name: "Symbol to compare" });
  await expect(box).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(box).toHaveCount(0);
  await expect(btn).toBeFocused();
});

test("'reduce motion' stops the search placeholder changing by itself", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the search button is in the desktop sidebar");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page, "/mine");
  await page.locator(".search-btn").click();
  const box = page.getByRole("dialog", { name: "Ask or do anything" }).getByRole("textbox");
  const first = await box.getAttribute("placeholder");
  expect(first).toBeTruthy();
  await page.waitForTimeout(4600);                                        // longer than the 3.8 s a change takes
  expect(await box.getAttribute("placeholder")).toBe(first);
});

test("on a phone the (i) is a 44px box to tap", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone only");
  for (const path of ["/mine", "/holdings", "/research/IN/RELIANCE"]) {
    await open(page, path);
    await expect(page.locator(".info-btn").first()).toBeAttached();
    const small = await page.evaluate(() => Array.from(document.querySelectorAll(".info-btn")).flatMap((b) => {
      const r = b.getBoundingClientRect();
      return r.width > 0 && (r.width < 43.5 || r.height < 43.5) ? [`${b.getAttribute("aria-label")} ${Math.round(r.width)}x${Math.round(r.height)}`] : [];
    }));
    expect(small, path).toEqual([]);
  }
});

test("phone: the drawing sheet is a clean list of drawings under properly ordered headings", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the sheet is the phone's drawing tools");
  await open(page, "/research/IN/RELIANCE");
  await page.getByRole("button", { name: "Draw", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Drawing tools" });
  await expect(sheet).toBeVisible();
  // the whole page, not just the sheet: heading order is read against the headings before it, and the sheet sits under the chart's card
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "best-practice"]).analyze();
  const mine = r.violations.filter((v) => ["aria-required-children", "aria-required-parent", "list", "listitem", "heading-order"].includes(v.id));
  expect(mine.map((v) => `${v.id}: ${v.help}`), JSON.stringify(mine.map((v) => v.nodes.map((n) => n.target)))).toEqual([]);
  expect(await sheet.locator("h4").count()).toBe(0);
  expect(await sheet.locator("h2").count()).toBeGreaterThan(0);
});
