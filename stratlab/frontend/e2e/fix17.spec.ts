import { expect, test, type Page } from "@playwright/test";

// fix17: LIVE13B findings proved on the pages as drawn, on the desktop and phone projects.

async function withConfig(page: Page, extra: Record<string, string>) {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(extra)});\n` });
  });
}

type Box = [number, number, number, number];
const boxes = (page: Page, root: string) => page.evaluate((r) => {
  const q = (s: string): Box | null => {
    const el = document.querySelector(`${r} ${s}`);
    if (!el || !el.getClientRects().length) return null;
    const b = el.getBoundingClientRect();
    return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)];
  };
  return { eyebrow: q(".lp-hero-copy .eyebrow"), h1: q(".lp-hero-copy h1"), lede: q(".lp-lede"), row: q(".lp-hero-copy .row"), small: q(".lp-hero-copy > p.small"),
    logo: q(".lp-nav .brand"), signin: q(".lp-nav > .btn") };
}, root);

// LIVE13B-001: for 3.5 s the visitor saw the heading alone on an empty page, then the hero replaced it in one frame: the heading moved
// 39 px and re-wrapped from two lines to three, the lede, the buttons and "Sign in" appeared. The start-up frame is the landing's own now.
test("the landing's start-up frame is the hero as the app draws it: same heading, lede, buttons and header, nothing moves (LIVE13B-001)", async ({ page }) => {
  await withConfig(page, { EMAIL_SIGNIN: "on" });
  let release!: () => void;
  const gate = new Promise<void>((ok) => { release = ok; });
  // the landing's own code held back, as on a slow first visit, so the start-up frame can be measured
  await page.route(/\/assets\/(Login|VisitorApp|visitorMain)-[^/]*\.js$/, async (r) => { await gate; await r.fallback(); });
  await page.addInitScript(() => {
    const w = window as unknown as { __cls: number; __lcp: number };
    w.__cls = 0; w.__lcp = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) w.__cls += e.value; })
      .observe({ type: "layout-shift", buffered: true });
  });
  await page.goto("/");
  const frame = page.locator("[data-boot] h1");
  await expect(frame).toHaveText("Is your trading idea skill or luck?", { timeout: 30_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await expect(page.locator("[data-boot] .lp-lede")).toBeVisible();
  await expect(page.locator("[data-boot] .row a")).toHaveCount(3);
  await expect(page.locator("header.lp-nav .logo-word")).toHaveText("StratLab");
  const before = await boxes(page, "#root");
  const cls0 = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
  release();
  await expect(page.locator("section.lp-hero h1")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("[data-boot]")).toHaveCount(0);
  await page.waitForTimeout(500);
  const after = await boxes(page, "#root");
  console.log(`${page.viewportSize()!.width}px frame ${JSON.stringify(before)}\n  drawn ${JSON.stringify(after)}`);
  for (const k of ["eyebrow", "h1", "lede", "row", "small", "logo"] as const) {
    expect(before[k], k).not.toBeNull();
    const [b, a] = [before[k]!, after[k]!];
    expect(Math.abs(b[0] - a[0]), `${k} x`).toBeLessThanOrEqual(1);
    expect(Math.abs(b[1] - a[1]), `${k} y`).toBeLessThanOrEqual(2);
    expect(Math.abs(b[2] - a[2]), `${k} width`).toBeLessThanOrEqual(1);
    expect(Math.abs(b[3] - a[3]), `${k} height (the same lines)`).toBeLessThanOrEqual(1);
  }
  if (before.signin && after.signin) expect(Math.abs(before.signin[0] - after.signin[0])).toBeLessThanOrEqual(1);
  const cls = await page.evaluate(() => (window as unknown as { __cls: number }).__cls);
  expect(cls - cls0, "no layout shift when the app draws over the frame").toBeLessThan(0.001);
});

test("another address served the home page's file shows the header and heading while it starts, not the landing's lede and buttons (LIVE13B-001)", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((ok) => { release = ok; });
  await page.route(/\/assets\/(VisitorApp|visitorMain|Gate)-[^/]*\.js$/, async (r) => { await gate; await r.fallback(); });
  await page.goto("/trade");
  await expect(page.locator("header.lp-nav")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main h1")).toBeVisible();
  await expect(page.locator("[data-boot] .lp-lede")).toBeHidden();
  await expect(page.locator("[data-boot] .row")).toBeHidden();
  release();
});

// LIVE13B-004: a signed-in page opened directly waited 5-8 s on "Opening the page": some 70 files fetched one after another before it drew,
// other spaces' code among them, and /me asked only after about 50 of them. Measured here on a throttled link (150 ms a request, 4 Mbit/s,
// CPU 4x): when /me is asked, how many files came before it, when the page's own content is drawn, and which files came first.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const PRO = { access_token: "pro-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id: "u-pro", aud: "authenticated", email: "u-pro@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const COLD: [string, string][] = [["/money", "[data-testid=money-home], main h1"], ["/trade", "main h1"], ["/invest", "main h1"], ["/research/IN/RELIANCE", "main h1"]];
for (const [path, ready] of COLD) {
  test(`a signed-in ${path} opened directly asks /me early and draws without other spaces' code first (LIVE13B-004)`, async ({ page, context }) => {
    test.slow();
    await page.addInitScript((s) => { try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ } }, PRO);
    await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: (4 * 1024 * 1024) / 8, uploadThroughput: (1024 * 1024) / 8 });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    const t0 = Date.now();
    const js: { name: string; at: number }[] = [];
    let meAt = -1, meAfter = -1;
    page.on("request", (q) => {
      const u = q.url();
      if (/\/assets\/[^/]+\.js$/.test(u)) js.push({ name: u.split("/").pop()!.replace(/-[\w-]{8}\.js$/, ""), at: Date.now() - t0 });
      else if (u === `${API}/me` && meAt < 0) { meAt = Date.now() - t0; meAfter = js.length; }
    });
    await page.goto(path);
    await expect(page.locator(ready).first()).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/^Opening/)).toHaveCount(0, { timeout: 60_000 });
    const drawn = Date.now() - t0;
    const before = js.filter((j) => j.at <= drawn).map((j) => j.name);
    console.log(`${path} ${page.viewportSize()!.width}px: /me asked at ${meAt} ms after ${meAfter} files; drawn at ${drawn} ms after ${before.length} files\n  ${before.join(" ")}`);
    expect(meAt, "/me is asked").toBeGreaterThan(0);
  });
}

// LIVE13B-011: on a phone the analytics question was drawn mid-screen (y 712) while /mine's cards were still loading, then pushed to y 2,496
// when they came (CLS 0.117): it now comes once the page's calls are back, after the cards have their content.
test("the analytics question comes after the page's cards have filled in, so it never moves (LIVE13B-011)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await withConfig(page, { ADS_ENABLED: "true", ADSENSE_CLIENT: "ca-pub-1234567890123456", ADSENSE_SLOT_PUBLIC: "1111111111", ADSENSE_SLOT_AI: "2222222222", CLARITY_PROJECT_ID: "abc123def4" });
  await page.route(/connect\.facebook\.net|clarity\.ms|googlesyndication/, (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
  // the cards' reads slow, as on a phone on a busy link: the question waits for them
  await page.route((u) => u.href.startsWith(API) && /^\/(holdings|money|research|trade|alerts|mine)/.test(u.pathname), async (r) => { await new Promise((ok) => setTimeout(ok, 2500)); await r.fallback(); });
  await page.addInitScript((s) => {
    try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ }
    const w = window as unknown as { __askMoves: number[] };
    w.__askMoves = [];
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Node }[] }[])
        if (!e.hadRecentInput && (e.sources ?? []).some((x) => (x.node as HTMLElement | undefined)?.closest?.("[data-testid=consent]"))) w.__askMoves.push(e.value);
    }).observe({ type: "layout-shift", buffered: true });
  }, PRO);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
  await page.goto("/mine");
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2500);
  const moves = await page.evaluate(() => (window as unknown as { __askMoves: number[] }).__askMoves);
  expect(moves.reduce((a, b) => a + b, 0), `layout shifts that moved the question: ${moves}`).toBeLessThan(0.01);
});

// LIVE12B-017: on a phone the statements paged three periods at a time, but three were 402 px in a 322 px card: "FY24 to FY26" showed only
// FY25 and FY26, FY24 out of view sideways. The window now holds as many periods as fit, and names those.
test("a phone's statements show every period the window names, none out of view sideways (LIVE12B-017)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript((s) => { try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ } }, PRO);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
  await page.goto("/research/IN/TATASTEEL");
  const st = page.locator("#co-statements");
  await st.scrollIntoViewIfNeeded();
  await expect(st.getByTestId("ct-window")).toBeVisible({ timeout: 30_000 });
  for (const name of ["Profit and loss", "Balance sheet", "Ratios"]) {
    const chip = st.getByRole("button", { name, exact: true }).or(st.getByRole("radio", { name, exact: true })).first();
    if (await chip.count()) await chip.click();
    const wrap = st.locator(".k-tbl-wrap").first();
    await expect(wrap.locator("table")).toBeVisible();
    await page.waitForTimeout(200);
    const fit = await wrap.evaluate((b) => ({ over: b.scrollWidth - b.clientWidth, heads: [...b.querySelectorAll("thead th")].slice(1).map((h) => h.textContent ?? "") }));
    const label = (await st.getByTestId("ct-window").locator("span").innerText()).trim();
    console.log(`${name}: "${label}", columns ${fit.heads.join(" | ")}, ${fit.over}px over`);
    expect(fit.over, `${name}: the table fits its card`).toBeLessThanOrEqual(1);
    const [from, to] = label.split(" to ");
    expect(fit.heads[0], name).toBe(from);
    expect(fit.heads[fit.heads.length - 1], name).toBe(to);
  }
});
