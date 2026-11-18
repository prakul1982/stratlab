import { expect, test, type Page } from "@playwright/test";

// fix16: LIVE12B findings proved on the pages as drawn, on the desktop and phone projects.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const user = (id: string, token: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email: `${id}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const PRO = user("u-pro", "pro-token");
/** This lane's own account for a test (backend tests/fake_db.py fix16-N: 0-7 Free, 8-15 Pro), one per test and project, so no test meets
 * another's per-minute read limits or kept answers. */
const own = (n: number, phone: boolean) => user(`u-fix16-${n + (phone ? 1 : 0)}`, `fix16-${n + (phone ? 1 : 0)}`);
/** The account as one that has answered the welcome question (so no first-run dialog over the page). */
async function settled(page: Page) {
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
}

async function withConfig(page: Page, extra: Record<string, string>) {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(extra)});\n` });
  });
}

/** Counts the page's layout shifts from its first paint (each with what moved), and signs in as `session` when given. */
async function watchShifts(page: Page, session?: object, store: Record<string, string> = {}) {
  await page.addInitScript(([s, kept]) => {
    try {
      if (s) { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }
      for (const [k, v] of Object.entries(kept as Record<string, string>)) localStorage.setItem(k, v);
    } catch { /* none */ }
    const w = window as unknown as { __cls: number; __src: string[] };
    w.__cls = 0; w.__src = [];
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; startTime: number; sources?: { node?: Node; previousRect: DOMRect; currentRect: DOMRect }[] }[]) {
        if (e.hadRecentInput) continue;
        w.__cls += e.value;
        for (const x of e.sources ?? []) {
          const el = x.node as HTMLElement | undefined;
          w.__src.push(`${Math.round(e.startTime)}ms ${e.value.toFixed(3)} ${el?.tagName ?? "?"}.${String(el?.className ?? "").slice(0, 40)} y ${Math.round(x.previousRect.y)}→${Math.round(x.currentRect.y)} h ${Math.round(x.previousRect.height)}→${Math.round(x.currentRect.height)}`);
        }
      }
    }).observe({ type: "layout-shift", buffered: true });
  }, [session ?? null, store] as const);
}
const shifts = (page: Page) => page.evaluate(() => { const w = window as unknown as { __cls: number; __src: string[] }; return { cls: w.__cls, sources: w.__src }; });

// LIVE12B-008 / LIVE12A-015: on a phone /login's email form arrived after the first frame and pushed the small print and the footer 208 px down
// (CLS 0.136): its place is held from the first frame, at the project's width and at 390 px
for (const width of [0, 390]) {
  test(`/login holds the email form's place from its first frame${width ? ` at ${width}px` : ""} (LIVE12B-008)`, async ({ page }) => {
    if (width) await page.setViewportSize({ width, height: 844 });
    await withConfig(page, { EMAIL_SIGNIN: "on" });
    // the form's own file, late (as on a cold phone): nothing under it may move when it comes
    await page.route(/\/assets\/EmailSignIn-[^/]*\.js$/, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.fallback(); });
    await watchShifts(page);
    for (const path of ["/login", "/signup"]) {
      await page.goto(path);
      await expect(page.getByTestId("email-signin")).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(800);
      const got = await shifts(page);
      console.log(`${path} ${page.viewportSize()!.width}px: CLS ${got.cls.toFixed(3)}\n  ${got.sources.slice(0, 6).join("\n  ")}`);
      expect(got.cls, got.sources.join("\n")).toBeLessThan(0.02);
      // one width for the two ways in: the Google button is the email form's width (owner pattern 13)
      const g = (await page.locator(".lp-hero").getByRole("button", { name: "Continue with Google" }).boundingBox())!;
      const f = (await page.getByTestId("email-signin").boundingBox())!;
      expect(Math.abs(g.width - f.width), `Google ${g.width} vs email ${f.width}`).toBeLessThan(2);
    }
  });
}

// LIVE12B-011: a Markets panel kept open under the guest's key was drawn in the first frame while the account loaded, then shut when the
// person's own layout (closed) came with the account at 1.8 s, and the whole page moved back (/new CLS 0.24): the first frame uses the
// person's own layout, read from their saved sign-in
test("/new is drawn at its final width: the Markets panel's state is the person's own from the first frame (LIVE12B-011)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.route(`${API}/me`, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.fulfill({ response: await r.fetch() }); });
  await watchShifts(page, PRO, {
    "stratlab.watch.layout.guest": JSON.stringify({ open: true, mode: "dock", w: 380, h: 560 }),
    "stratlab.watch.layout.u-pro": JSON.stringify({ open: false, mode: "dock", w: 380, h: 560 }),
  });
  await page.addInitScript(() => {
    const w = window as unknown as { __panel: boolean };
    w.__panel = false;
    new MutationObserver(() => { if (document.querySelector(".mw:not(.mw-launch)")) w.__panel = true; }).observe(document.documentElement, { childList: true, subtree: true });
  });
  await page.goto("/new");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(3500);
  const got = await shifts(page);
  console.log(`/new: CLS ${got.cls.toFixed(3)}\n  ${got.sources.slice(0, 8).join("\n  ")}`);
  expect(await page.evaluate(() => (window as unknown as { __panel: boolean }).__panel), "the guest's panel was drawn").toBe(false);
  expect(got.cls, got.sources.join("\n")).toBeLessThan(0.05);
  await expect(page.getByTestId("markets-launch")).toBeVisible();
});

// LIVE12B-012: on /trade a 250 px "Opening your notebooks" card was held between the market tiles and the tools for an account with no
// notebook and the first steps showing, then went at 1.8 s (CLS 0.149): what the person had last time on this device decides the first frame
test("/trade holds no card it then takes away for an account with no notebook (LIVE12B-012)", async ({ page }) => {
  const steps = { show: true, dismissed: false, done: 1, steps: [{ id: "idea", title: "Test your first idea", to: "/new", done: false },
    { id: "plans", title: "See the plans", to: "/plans", done: true }] };
  await page.route(`${API}/notebooks`, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.fulfill({ status: 200, json: [] }); });
  await page.route(`${API}/me/first-steps`, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.fulfill({ status: 200, json: steps }); });
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
  // a returning visit: no notebook and the first steps showing, last time on this device
  await watchShifts(page, PRO, { "stratlab.notebooks.had.u-pro": "0", "stratlab.firstSteps.shown.u-pro": "1" });
  await page.goto("/trade");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".first-steps:not(.fs-wait)")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  const got = await shifts(page);
  console.log(`/trade ${page.viewportSize()!.width}px: CLS ${got.cls.toFixed(3)}\n  ${got.sources.slice(0, 8).join("\n  ")}`);
  await expect(page.getByText("Opening your notebooks")).toHaveCount(0);
  expect(got.cls, got.sources.join("\n")).toBeLessThan(0.05);
});

const FREE = user("u-free", "free-token");
/** The page's first-load layout shift with its account answers late (as on the live site: /me at about 1.8 s). */
async function slowLoad(page: Page, path: string, session: object, slow: RegExp[], store: Record<string, string> = {}) {
  for (const re of slow) await page.route((u) => u.href.startsWith(API) && re.test(u.pathname + u.search), async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.fulfill({ response: await r.fetch() }); });
  await watchShifts(page, session, store);
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(4000);
  const got = await shifts(page);
  console.log(`${path} ${page.viewportSize()!.width}px: CLS ${got.cls.toFixed(3)}\n  ${got.sources.slice(0, 10).join("\n  ")}`);
  return got;
}

// LIVE12B-023: /money/us-tax drew an "Opening your US stocks…" card and took it away at 2.4 s, moving the cards under it (CLS 0.133)
test("/money/us-tax is drawn in its final layout from the first frame (LIVE12B-023)", async ({ page }) => {
  const got = await slowLoad(page, "/money/us-tax", PRO, [/^\/money\/us-tax(\?|$)/, /^\/me$/]);
  await expect(page.getByText("No US trades yet")).toBeVisible();
  expect(got.cls, got.sources.join("\n")).toBeLessThan(0.02);
});

// LIVE12B-022: /mine on a phone: the plan notice and the first-steps row came with the account and pushed the cards 147 px down (CLS 0.1)
// (a returning visit: both showed last time on this device). LIVE12B-006: the row fills its card, the buttons at its right edge
test("/mine holds the notice and first-steps rows from the first frame (LIVE12B-022, LIVE12B-006)", async ({ page }) => {
  const notice = { on: "2026-11-30T00:00:00+05:30", moves: [], rows: [{ key: "ai_reads_per_day", label: "Fresh AI reads a day", before: 60, after: 5 }] };
  const steps = { show: true, dismissed: false, done: 4, steps: ["idea", "watch", "holdings", "alert", "plans"].map((id, i) => ({ id, title: `Step ${id}`, to: "/plans", done: i < 4 })) };
  await page.route(`${API}/me`, async (r) => {
    await new Promise((ok) => setTimeout(ok, 1500));
    const res = await r.fetch();
    await r.fulfill({ response: res, json: { ...(await res.json()), established: true, free_change: notice } });
  });
  await page.route(`${API}/me/first-steps`, (r) => r.fulfill({ status: 200, json: steps }));
  const got = await slowLoad(page, "/mine", FREE, [], { "stratlab.firstSteps.shown.u-free": JSON.stringify(steps), "stratlab.freeChange.line.u-free": "Your Free plan changes on 30 Nov 2026" });
  await expect(page.getByTestId("free-change")).toBeVisible();
  const row = page.locator(".first-steps.fs-compact:not(.fs-wait)");
  await expect(row).toBeVisible();
  // the cards' grid never moves: what is above it is drawn at its height from the first frame (the cards' own loading is theirs)
  const moved = got.sources.filter((x) => /DIV\.mine-grid /.test(x) && !/y (\d+)→\1 /.test(x));
  expect(moved, got.sources.join("\n")).toEqual([]);
  // the row's line spans its card: the last button ends at the card's right padding
  const [card, last] = [(await row.boundingBox())!, (await row.locator(".fs-line > :last-child").boundingBox())!];
  expect(card.x + card.width - (last.x + last.width), "space right of the buttons").toBeLessThan(40);
});

// LIVE12B-021: the link said "Cement" and the file was the Oil and gas deck kept after the page asked which deck it was: the link asks for
// the deck it names, by its id
test("the sample deck link downloads the deck it names (LIVE12B-021)", async ({ page }, info) => {
  await page.route(`${API}/pricing/sample-deck/info`, (r) => r.fulfill({ status: 200, json: { available: true, theme: "Cement", region: "IN", id: "deck-cem" } }));
  await settled(page);
  await watchShifts(page, own(0, info.project.name === "phone"));
  await page.goto("/plans");
  const link = page.getByTestId("sample-deck");
  await expect(link).toHaveText(/: Cement$/, { timeout: 30_000 });
  await expect(link).toHaveAttribute("href", `${API}/pricing/sample-deck?id=deck-cem`);
});

// LIVE12B-017: on a phone no "·" left at a row name's end (its note was out of sight), and EPS in ₹ (the three periods' fit is not done)
test("a phone's statements end no row name in a dot and write EPS in rupees (LIVE12B-017)", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await settled(page);
  await watchShifts(page, own(8, info.project.name === "phone"));
  await page.goto("/research/IN/TATASTEEL");
  const st = page.locator("#co-statements");
  await st.scrollIntoViewIfNeeded();
  await expect(st.getByTestId("ct-window")).toBeVisible({ timeout: 30_000 });
  for (const name of ["Profit and loss", "Ratios"]) {
    const chip = st.getByRole("button", { name, exact: true }).or(st.getByRole("radio", { name, exact: true })).first();
    if (await chip.count()) await chip.click();
    const wrap = st.locator(".k-tbl-wrap").first();
    await expect(wrap.locator("table")).toBeVisible();
    const names = await wrap.locator("tbody th[scope=row]").allInnerTexts();
    expect(names.filter((n) => /·\s*$/.test(n)), "a row name ending in a dot").toEqual([]);
    expect(names.some((n) => /in Rs/.test(n))).toBe(false);
  }
});

// LIVE12B-007: every market tile has its day on the line under its change; the cards' titles in a row are level
test("My space's tiles share one layout and its card titles are level (LIVE12B-007)", async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await settled(page);
  await watchShifts(page, own(10, info.project.name === "phone"));
  await page.goto("/mine");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("mine-mkt-when").first()).toBeVisible({ timeout: 30_000 });
  for (const w of await page.getByTestId("mine-mkt-when").all()) await expect(w).toHaveCSS("display", "block");
  await page.waitForTimeout(2000);
  const tops = await page.locator(".mine-slot .k-card-head .k-card-title").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top * 10) / 10));
  for (const a of tops) for (const b of tops) if (Math.abs(a - b) < 12) expect(Math.abs(a - b), `titles at ${a} and ${b}`).toBeLessThan(1);
});
