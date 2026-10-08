import { expect, test, type Page } from "@playwright/test";

// Round 3, builder B: what a person sees on Settings > Connection check, weekend events, My space's one name, the library's
// groups and titles, toasts on a phone, tap targets, the notebook's name box, the heatmap's key. Signed in as the owner
// (the fake world's admin) or as a person of their own.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const ownerSession = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const personSession = (n: number) => ({ ...base, access_token: `load-${n}`, user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } });

async function open(page: Page, where: string, who: object = ownerSession) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(where);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}

const noSideways = async (page: Page) => {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
};

test("Connection check: a person sees plain words, the owner sees the server and the hosting steps (R3-009)", async ({ page, browser }, info) => {
  const n = info.project.name === "phone" ? 156 : 150;
  const errors = await open(page, "/settings#check", personSession(n));
  await page.getByRole("button", { name: "Run check" }).click();
  await expect(page.getByText("Your account")).toBeVisible({ timeout: 30_000 });
  const card = page.locator("#check");
  await expect(card).toContainText("StratLab server");
  for (const bad of [/https?:\/\//, /127\.0\.0\.1/, /localhost/, /Railway/i, /GROQ/, /Variables/, /redeploy/i, /FRONTEND_ORIGIN/]) await expect(card, `${bad} shown to a person`).not.toContainText(bad);
  await noSideways(page);
  expect(errors).toEqual([]);

  const owner = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const op = await owner.newPage();
  await open(op, "/settings#check");
  await op.getByRole("button", { name: "Run check" }).click();
  await expect(op.getByText("Your account")).toBeVisible({ timeout: 60_000 });
  await expect(op.locator("#check")).toContainText("127.0.0.1");                 // the owner sees where the server is
  await owner.close();
});

test("Market events: a weekend date says the exchanges are closed (R3-007)", async ({ request }) => {
  const evs = (await (await request.get(`${API}/trade/events`, { headers: admin })).json()).events as { date: string; kind: string; detail: string; weekend?: string; custom?: string }[];
  expect(evs.length).toBeGreaterThan(5);
  for (const e of evs) {
    const day = new Date(`${e.date}T12:00:00Z`).getUTCDay();
    const counted = (day === 0 || day === 6) && !["holiday", "expiry"].includes(e.kind) && !e.custom;
    if (counted) {
      expect(e.weekend, `${e.kind} on ${e.date}`).toBe(day === 0 ? "Sunday" : "Saturday");
      expect(e.detail).toContain("the exchanges are closed");
    } else expect(e.weekend, `${e.kind} on ${e.date}`).toBeUndefined();
  }
});

test("My space has one name, and Look up a company differs from the Invest home (R3-016)", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/mine");
  if (phone) await page.getByRole("button", { name: /menu/i }).first().click();
  const side = page.locator("aside.sidebar");
  await expect(side.getByRole("radio", { name: "My space" })).toHaveAttribute("aria-checked", "true", { timeout: 30_000 });
  await expect(side.getByRole("radio", { name: "Mine", exact: true })).toHaveCount(0);
  await expect(side.getByRole("link", { name: "My space", exact: true })).toBeVisible();
  const labels = await side.getByRole("radio").allInnerTexts();
  expect(labels).toEqual(["My space", "Trade", "Invest", "Money"]);
  // every label fits its tab
  expect(await side.locator(".space-switch button").evaluateAll((bs) => bs.filter((b) => b.scrollWidth > b.clientWidth + 1).map((b) => b.textContent))).toEqual([]);
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("My space");

  await page.goto("/invest");
  await expect(page.getByRole("heading", { level: 1, name: "Your research desk" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("[aria-label=\"Jump to a company\"]")).toBeAttached();
  await page.goto("/research");
  await expect(page.getByRole("heading", { level: 1, name: "Look up a company" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Your watchlist" }), "the watchlist is on the Invest home").toHaveCount(0);
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("Library: groups say what they hold and ST S2 is spelled out (R3-014)", async ({ page }) => {
  const errors = await open(page, "/library");
  await page.getByRole("radio", { name: "StratLab's own" }).click();
  const cards = page.locator(".k-cards > section");
  await expect(cards.first()).toBeVisible({ timeout: 30_000 });
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/\bST S2\b/);
  expect(text).toMatch(/Stage 2 \+ Supertrend/);
  expect(text, "a group's count says of how many").not.toMatch(/stocks \(\d+\)|large caps \(\d+\)/i);
  expect(text).toMatch(/\d+ of the (NIFTY 50 stocks|20 US large caps)|NIFTY 50 stocks|20 US large caps/);
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("a toast is as wide as the phone allows, up to 360px, with its button whole (R3-018)", async ({ page }, info) => {
  await open(page, "/mine");
  await expect(page.locator("main")).toBeVisible({ timeout: 30_000 });
  const m = await page.evaluate(() => {
    const t = document.createElement("div");
    t.className = "toast"; t.setAttribute("role", "status");
    t.innerHTML = "<span>Nothing has changed since v1: same rules, same stock, same dates, so there is nothing new to show.</span><button>Open v1</button>";
    document.body.append(t);
    const r = t.getBoundingClientRect(), b = t.querySelector("button")!.getBoundingClientRect();
    const out = { w: r.width, h: r.height, bw: b.width, bh: b.height, vw: window.innerWidth };
    t.remove();
    return out;
  });
  if (info.project.name === "phone") {
    expect(m.w, "a toast squeezed into a narrow column").toBeGreaterThanOrEqual(Math.min(360, m.vw - 32) - 1);
    expect(m.w).toBeLessThanOrEqual(361);
    expect(m.bw, "its button is squeezed").toBeGreaterThanOrEqual(60);
    expect(m.h, "the words wrap into a tall column").toBeLessThan(120);
  } else expect(m.w).toBeLessThanOrEqual(480 + 1);
  expect(m.bh).toBeGreaterThanOrEqual(40);
});

test("tap targets are 40px or more: (i), Remove leg, calendar days, rotation toggles (R3-018)", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const small = async (sel: string) => page.evaluate((s) => Array.from(document.querySelectorAll(s)).map((e) => {
    const b = e.getBoundingClientRect();
    return b.width && b.height ? `${s} "${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 24)}" ${Math.round(b.width)}x${Math.round(b.height)}` : "";
  }).filter((x) => x && /(\d+)x(\d+)/.test(x) && x.split(" ").slice(-1)[0].split("x").some((v) => Number(v) < 40)), sel);

  const errors = await open(page, "/mine");
  await expect(page.locator(".info-btn").first()).toBeAttached({ timeout: 30_000 });
  expect(await small(".info-btn")).toEqual([]);
  // the circle itself stays compact
  const circle = await page.evaluate(() => { const b = document.querySelector(".k-card-title .info-btn, .k-page-head .info-btn"); return b ? parseFloat(getComputedStyle(b).getPropertyValue("--i")) : 0; });
  expect(circle).toBeLessThanOrEqual(22);

  await page.goto("/trade/events");
  await expect(page.locator(".k-cal-cell").first()).toBeVisible({ timeout: 30_000 });
  expect(await small(".k-cal-cell:not(.empty)")).toEqual([]);

  await page.goto("/research/rotation");
  const toggles = page.locator(".k-tap");
  await expect(toggles.first()).toBeVisible({ timeout: 30_000 });
  expect(await small(".k-tap")).toEqual([]);

  // "Remove leg" in the options builder (the live option feed is offline here, so its button is drawn with the same class)
  const chip = await page.evaluate(() => {
    const b = document.createElement("button");
    b.className = "chip-x"; b.textContent = "×"; b.setAttribute("aria-label", "Remove leg 2");
    document.querySelector("main")!.append(b);
    const r = b.getBoundingClientRect();
    b.remove();
    return { w: r.width, h: r.height };
  });
  expect(chip.w, "Remove leg is too narrow to tap").toBeGreaterThanOrEqual(40);
  expect(chip.h, "Remove leg is too short to tap").toBeGreaterThanOrEqual(40);
  void phone;
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("the notebook's name box fits its name, and the heatmap has a key (R3-012)", async ({ page, request }, info) => {
  const SMA = { name: "Name box", tf: "1d", entry: [{ l: { t: "ema", p: 20 }, op: "xa", r: { t: "ema", p: 50 } }], exit: [{ l: { t: "ema", p: 20 }, op: "xb", r: { t: "ema", p: 50 } }],
    risk: { capital: 100000, sl: 2, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `EMA 20 over EMA 50 · NIFTY 50 · ${info.project.name}`, strategy: SMA, instrument: "CRYPTO:BTC-USD" } })).json();
  const errors = await open(page, `/n/${nb.id}`);
  const name = page.getByRole("textbox", { name: "Notebook name" });
  await expect(name).toBeVisible({ timeout: 30_000 });
  const w = await name.evaluate((el) => ({ box: el.getBoundingClientRect().width, parent: (el.closest("form") as HTMLElement).getBoundingClientRect().width, text: (el as HTMLInputElement).scrollWidth, client: (el as HTMLInputElement).clientWidth }));
  expect(w.box, "the name box is a sliver of its form").toBeGreaterThan(w.parent * 0.9);
  expect(w.text, "the name is clipped").toBeLessThanOrEqual(w.client + 1);

  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 730 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  {
    await page.goto(`/n/${nb.id}/e/1`);
    await expect(page.locator(".verdict-head, .k-verdict-hero").first()).toBeVisible({ timeout: 30_000 });
    const grid = page.getByRole("grid", { name: /nearby settings/ });
    await expect(grid).toBeVisible();
    {
      await expect(page.getByLabel("Colour key")).toContainText("Made money");
      await expect(page.getByLabel("Colour key")).toContainText("Lost money");
      await expect(grid.getByRole("gridcell").first()).toHaveAttribute("title", /%/);
    }
    const { box, card } = await page.evaluate(() => {
      const c = document.querySelector(".k-money > section, .k-money > div") as HTMLElement | null;
      const chart = c?.querySelector("svg") as SVGElement | null;
      return { box: chart ? c!.getBoundingClientRect().bottom - chart.getBoundingClientRect().bottom : 0, card: !!c };
    });
    expect(card).toBe(true);
    if (info.project.name !== "phone") expect(box, "blank space under the money chart").toBeLessThan(90);
  }
  await noSideways(page);
  expect(errors).toEqual([]);
});
