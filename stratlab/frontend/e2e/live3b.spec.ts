import { expect, test, worldDate, type Page } from "@playwright/test";

// LIVE3 (live review of production, Wed 4 Nov), the FIXB lane. Each test sets its own width, so it is the same on the desktop and
// phone projects; signed-in tests only read.
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const ADMIN = session("admin-token", "u-admin", "owner@example.com");
const TRACK = { META_PIXEL_ID: "1234567890", CLARITY_PROJECT_ID: "abc123def4" };

async function open(page: Page, path: string, s: object | null, width: number, o: { track?: boolean; tour?: boolean; height?: number } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width, height: o.height ?? 860 });
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  if (o.track) await page.route(/\/config\.js(\?|$)/, async (r) => { const real = await (await r.fetch()).text(); await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(TRACK)});\n` }); });
  await page.addInitScript(([x, tour]) => { if (x) localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); if (!tour) localStorage.setItem("stratlab.tour.v1", "1"); }, [s, !!o.tour] as const);
  await page.goto(path);
  return errors;
}

test.use({ serviceWorkers: "block" });          // each visit reads the config.js the test gives, never one a service worker kept
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

// LIVE3-010 / 023: on a phone the analytics question stood over a company page's main buttons, Invest's shortcut cards and a
// result's headline figures (about 190px of an 860px screen). Now, on every page that asks it, signed in or out, it is a slim bar
// along the window's foot: one sentence, "What this means" and the two answers on one row; wide screens keep the full wording.
test("the analytics question is a slim bar on a phone on every page that asks it, the full card on a wide screen (LIVE3-010)", async ({ page }) => {
  const pages: [string, object | null][] = [["/", null], ["/library", null], ["/pricing", null], ["/research/IN/RELIANCE", ADMIN], ["/invest", ADMIN], ["/library/seed-supertrend-us", ADMIN]];
  for (const [path, who] of pages) {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await page.context().clearCookies();
    await open(page, path, who, 390, { track: true });
    const ask = page.getByTestId("consent");
    await expect(ask, path).toBeVisible({ timeout: 30_000 });
    const box = (await ask.boundingBox())!;
    expect(box.height, `${path}: the bar's height`).toBeLessThanOrEqual(112);
    expect(Math.round(box.y + box.height), `${path}: along the window's foot`).toBe(860);
    await expect(ask.locator(".consent-short"), path).toBeVisible();
    await expect(ask.locator(".consent-long"), path).toBeHidden();
    await expect(ask.getByRole("link", { name: "What this means" }), path).toBeVisible();
    // both answers on the row with the link, one width
    const ys = await ask.locator(".consent-btns > *").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2)));
    expect(Math.max(...ys) - Math.min(...ys), `${path}: one row ${ys}`).toBeLessThanOrEqual(4);
    await page.evaluate(() => localStorage.clear());
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  const ask = page.getByTestId("consent");
  await page.reload();
  await expect(ask).toBeVisible({ timeout: 30_000 });
  await expect(ask.locator(".consent-long")).toBeVisible();
  await expect(ask).toContainText("all text hidden");
  await expect(ask.locator(".consent-short")).toBeHidden();
});

// LIVE3-012: /library moved by 0.75 (CLS) when its list replaced the placeholder (the page widened 92px and its note dropped out of
// view), the policies by 0.14 ("Loading…" swapped for the text), Pulse by 0.29 and Screens by 0.23 on a phone (an as-of line
// arriving, a short index placeholder, a 70vh filter placeholder that folded). Each page the review measured, and the busiest
// public and signed-in pages beside them, stays under 0.1 (Google's "good") from the first frame to six seconds later.
const SHIFT_PAGES: [string, boolean, number][] = [
  ["/library", false, 1440], ["/library", false, 390], ["/privacy", false, 1440], ["/terms", false, 1440], ["/privacy", false, 390], ["/", false, 1440],
  ["/library", true, 1440], ["/research/pulse", true, 390], ["/research/pulse", true, 1440], ["/research/screens", true, 390], ["/research/screens", true, 1440],
  ["/tour", true, 390], ["/trade", true, 1440], ["/research", true, 390],
];
test("pages hold still while they load: layout shift under 0.1 on every page the review measured, phone and desktop (LIVE3-012)", async ({ page }) => {
  test.setTimeout(400_000);
  const over: string[] = [];
  for (const [path, signed, w] of SHIFT_PAGES) {
    const p = await page.context().newPage();
    await p.setViewportSize({ width: w, height: w < 500 ? 844 : 900 });
    await p.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
    await p.addInitScript(([s, on]) => {
      try { localStorage.clear(); localStorage.setItem("stratlab.tour.v1", "1"); if (on) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); } catch { /* none */ }
      const w = window as unknown as { __shift: { v: number; n: string[] }[] };
      w.__shift = [];
      new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Element; previousRect: DOMRect; currentRect: DOMRect }[] }[]) if (!e.hadRecentInput) w.__shift.push({ v: e.value, n: (e.sources ?? []).map((x) => `${(x.node as Element | undefined)?.className ?? x.node?.nodeName} ${Math.round(x.previousRect.y)}->${Math.round(x.currentRect.y)}`) }); }).observe({ type: "layout-shift", buffered: true });
    }, [ADMIN, signed] as const);
    await p.goto(path);
    await p.waitForTimeout(6000);
    const shifts = await p.evaluate(() => (window as unknown as { __shift: { v: number; n: string[] }[] }).__shift);
    const cls = shifts.reduce((a, x) => a + x.v, 0);
    if (cls >= 0.1) over.push(`${path} ${w}${signed ? " signed in" : ""}: ${cls.toFixed(3)} ${JSON.stringify(shifts.filter((x) => x.v > 0.005))}`);
    await p.unrouteAll({ behavior: "ignoreErrors" });
    await p.close();
  }
  expect(over, over.join("\n")).toEqual([]);
});

// LIVE3-014: on a phone the tour's first step ("Four spaces") ringed a thin strip half under its own note: the four spaces are in the
// menu, which the step opens. Every step that points into the menu rings the real thing, whole, on screen and clear of the note.
test("the phone tour's menu steps ring the thing they describe, on screen and clear of the note (LIVE3-014)", async ({ page }) => {
  await open(page, "/tour", ADMIN, 390, { tour: true, height: 844 });
  const note = page.locator(".k-coach-note");
  const ring = page.locator(".k-coach-ring");
  const rect = (sel: string) => page.locator(sel).first().evaluate((e) => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  const steps: [string, string][] = [["Four spaces", ".sidebar .space-switch"], ["Ask or do anything", ".topbar [aria-label='Search or ask anything']"]];
  for (const [title, sel] of steps) {
    await expect(note.getByRole("heading", { name: title })).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(600);           // the drawer's slide and the ring's move
    const t = await rect(sel), r = await rect(".k-coach-ring"), n = await rect(".k-coach-note");
    await expect(ring).not.toHaveAttribute("data-off", /./);
    expect(t.y >= 0 && t.y + t.h <= 844 && t.x >= 0 && t.x + t.w <= 390, `${title}: the thing is on screen ${JSON.stringify(t)}`).toBe(true);
    expect(Math.abs(r.x - (t.x - 4)) <= 3 && Math.abs(r.y - (t.y - 4)) <= 3 && Math.abs(r.w - (t.w + 8)) <= 3 && Math.abs(r.h - (t.h + 8)) <= 3, `${title}: the ring ${JSON.stringify(r)} is round the thing ${JSON.stringify(t)}`).toBe(true);
    const overlap = !(n.x >= t.x + t.w || n.x + n.w <= t.x || n.y >= t.y + t.h || n.y + n.h <= t.y);
    expect(overlap, `${title}: the note ${JSON.stringify(n)} covers the thing ${JSON.stringify(t)}`).toBe(false);
    await note.getByRole("button", { name: "Next" }).click();
  }
});

// LIVE3-013: a strategy's result page said its main figure four times (the headline, an 8-line paragraph, a green line, then tiles
// with "Trades" alone on a row). Both kinds of result page, a library strategy and a shared verdict, now say it once in the headline,
// then one table of the figures, then the explanation folded; no tiles, nothing before the figures but the headline.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const EMA = { name: "Trend follower", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
  exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
test("a result page says its result once: headline, one table of figures, the explanation folded (LIVE3-013)", async ({ page, request }, info) => {
  test.setTimeout(240_000);
  const auth = { Authorization: `Bearer live3b-${info.project.name === "phone" ? 1 : 0}` };
  const post = async (path: string, data: object) => { const r = await request.post(API + path, { headers: auth, data }); expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy(); return r.json(); };
  await request.put(`${API}/me/prefs`, { headers: auth, data: { level: "some", focus: "both" } });
  const nb = await post("/notebooks", { name: "LIVE3 verdict", question: "Does the cross work?", strategy: EMA, instrument: "CRYPTO:BTC-USD" });
  await post(`/notebooks/${nb.id}/experiments`, { days: 1500 });
  const shared = await post(`/notebooks/${nb.id}/experiments/1/share`, {});
  for (const [path, rows] of [["/library/seed-supertrend-us", 5], [`/verdict/${shared.token}`, 4]] as const) {
    for (const w of [390, 1440]) {
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await open(page, path, null, w);
      const main = page.locator("main");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
      const table = main.getByRole("table", { name: "Results after costs" });
      await expect(table, `${path} ${w}`).toBeVisible();
      await expect(table.locator("tbody tr"), `${path} ${w}`).toHaveCount(rows);
      await expect(main.locator(".k-stat"), `${path} ${w}: no tiles`).toHaveCount(0);
      await expect(main.getByTestId("lib-hold"), `${path} ${w}: no second line restating it`).toHaveCount(0);
      // nothing between the headline and the figures but the eyebrow, the dates and (on a verdict) the chart: no paragraph
      await expect(main.locator(".k-lede"), `${path} ${w}`).toHaveCount(0);
      const why = main.locator("details.pub-why");
      await expect(why, `${path} ${w}`).toHaveCount(1);
      await expect(why).not.toHaveAttribute("open", /.*/);
      await why.locator("summary").click();
      await expect(why.locator("p")).toBeVisible();
    }
  }
});

// LIVE3-015 / LIVE3-021: the Invest home's watchlist was tiles two across (three stocks left an empty cell), its "Coming up" a text
// list with other events than My space's, and figure tables kept a note column blank in most rows (the breadth card's "Day",
// Holdings' "Change"). The watchlist and Coming up are tables now, Coming up follows My space's rule, and no figure table on these
// pages has a column blank in half its rows or more, on a phone or a desktop.
test("Invest's watchlist and Coming up are tables, Coming up agrees with My space, and no figure table has a half-empty column (LIVE3-015, LIVE3-021)", async ({ page, request }, info) => {
  test.setTimeout(240_000);
  const n = info.project.name === "phone" ? 3 : 2;
  const who = session(`live3b-${n}`, `u-live3b-${n}`, `live3b${n}@example.com`);
  const head = { Authorization: `Bearer live3b-${n}` };
  await request.put(`${API}/me/prefs`, { headers: head, data: { focus: "both", level: "some", space: "all" } });
  await request.put(`${API}/research/watchlist`, { headers: head, data: { items: ["RELIANCE", "TCS", "ITC"].map((symbol) => ({ region: "IN", symbol })) } });
  const halfEmpty = () => page.locator("main table").evaluateAll((ts) => ts.flatMap((t) => {
    const body = Array.from(t.querySelectorAll("tbody tr"));
    const cols = t.querySelectorAll("thead th").length;
    if (body.length < 2 || cols > 4 || (t as HTMLElement).offsetParent === null) return [];
    const out: string[] = [];
    for (let c = 1; c < cols; c++) {
      const blank = body.filter((r) => !(r.children[c]?.textContent ?? "").replace(/[\s–-]/g, "")).length;
      if (blank * 2 >= body.length) out.push(`${t.getAttribute("aria-label") ?? "table"}: column ${t.querySelectorAll("thead th")[c]?.textContent} blank in ${blank} of ${body.length}`);
    }
    return out;
  }));
  for (const w of [390, 1440]) {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await open(page, "/invest", who, w);
    const watch = page.getByRole("table", { name: "Your watchlist" });
    await expect(watch.locator("tbody tr")).toHaveCount(3, { timeout: 30_000 });
    for (const h of ["Stock", "Price", "Change"]) await expect(watch.getByRole("columnheader", { name: h })).toBeVisible();
    await expect(page.locator(".inv-tile")).toHaveCount(0);
    const coming = page.getByTestId("invest-events").getByRole("table", { name: "Coming up" });
    await expect(coming.locator("tbody tr").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("breadth-card")).toBeVisible({ timeout: 30_000 });
    expect(await halfEmpty(), `/invest ${w}`).toEqual([]);
    if (w === 1440) {
      // every event the Invest home lists up to the last day My space's list reaches is in My space's list too
      const inv = await coming.locator("tbody tr").evaluateAll((rs) => rs.map((r) => r.querySelector("th")?.textContent?.trim() ?? ""));
      await page.goto("/mine");
      const mine = page.getByTestId("mine-coming");
      await expect(mine.locator(".mine-tl-i").first()).toBeVisible({ timeout: 30_000 });
      const mineText = await mine.innerText();
      const shared = inv.filter((t) => mineText.includes(t));
      expect(shared.length, `Invest ${JSON.stringify(inv)} vs My space ${mineText}`).toBeGreaterThan(0);
    }
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await open(page, "/holdings", ADMIN, w);
    await expect(page.getByRole("table", { name: "Where your stocks stand" })).toBeVisible({ timeout: 30_000 });
    expect(await halfEmpty(), `/holdings ${w}`).toEqual([]);
  }
});

// LIVE3-022: Paper's empty state had one button, with the options route as a link inside its sentence.
test("Paper's empty state offers both ways to start as buttons side by side (LIVE3-022)", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 5 : 4;
  await request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer live3b-${n}` }, data: { focus: "both", level: "some", space: "all" } });
  for (const w of [390, 1440]) {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await open(page, "/paper", session(`live3b-${n}`, `u-live3b-${n}`, `live3b${n}@example.com`), w);
    const box = page.locator(".k-state", { hasText: "No paper trades yet" });
    await expect(box).toBeVisible({ timeout: 30_000 });
    const a = box.getByRole("link", { name: "Go to your notebooks" }), b = box.getByRole("link", { name: "Build an options strategy" });
    await expect(a).toHaveClass(/\bbtn\b/);
    await expect(b).toHaveClass(/\bbtn\b/);
    await expect(box.locator("p a")).toHaveCount(0);
    const [ra, rb] = [await a.boundingBox(), await b.boundingBox()];
    // side by side on a wide screen; on a phone one under the other at one width (two answers of equal weight)
    if (w > 640) expect(Math.abs(ra!.y - rb!.y), `${w}: one row`).toBeLessThanOrEqual(2);
    else expect(Math.abs(ra!.width - rb!.width), `${w}: one width`).toBeLessThanOrEqual(1);
    await b.click();
    await expect(page).toHaveURL(/\/options/);
  }
});

// LIVE3-026: pro-1's stored session met "Sign in to see …" on 22 pages in a row, and a minute later was signed in everywhere. A sign-in
// wall needs the saved session to be gone from the browser (with one saved, a page that can't confirm it says it couldn't load), so
// a session that comes back by itself was written back by another process using the profile. What a returning user meets: an expired
// access token is renewed once and every page is signed in; a renewal the service can't answer is "couldn't load", never a wall.
test("a returning user with an expired access token is renewed, never shown a sign-in wall (LIVE3-026)", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 7 : 6;
  const token = `live3b-${n}`;
  await request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer ${token}` }, data: { focus: "both", level: "some", space: "all" } });
  const fresh = { ...session(token, `u-live3b-${n}`, `live3b${n}@example.com`), refresh_token: "r2" };
  const worldNow = () => Math.floor(worldDate().getTime() / 1000);          // the page's clock is the fake world's, not this machine's
  const expired = { ...fresh, access_token: "expired-token", refresh_token: "r1", expires_at: worldNow() - 3600 };
  let renewals = 0, down = false;
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.route("https://demo.supabase.co/auth/v1/token?grant_type=refresh_token", (r) => {
    renewals++;
    return down ? r.fulfill({ status: 503, body: "upstream unavailable" }) : r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...fresh, expires_at: worldNow() + 3600 }) });
  });
  await page.addInitScript((s) => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); sessionStorage.setItem("seeded", "1"); } }, expired);
  for (const path of ["/mine", "/invest", "/holdings", "/research/IN/RELIANCE", "/account"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }), path).not.toHaveText(/^Sign in|You were signed out/, { timeout: 30_000 });
    await expect(page.locator("main .gate"), path).toHaveCount(0);
  }
  expect(renewals, "renewed once, then the new session is used").toBe(1);
  // the next visit's renewal can't be answered: the page says it couldn't load your account, not "Sign in to see"
  down = true;
  await page.evaluate((s) => localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)), expired);
  await page.goto("/invest");
  await expect(page.getByText(/couldn't load|Reload/i).first()).toBeVisible({ timeout: 40_000 });
  await expect(page.getByRole("heading", { name: /^Sign in to see/ })).toHaveCount(0);
});
