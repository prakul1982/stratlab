import { expect, test, type Page } from "@playwright/test";

// fix11: open LIVE10A / LIVE10B findings proved on the pages as drawn. Each test sets its own width, so it is the same on the desktop and
// phone projects.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const EMA = { name: "Fix11", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
  exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 100000, sl: 0, tgt: 0, brokerage: 0, slippage: 0.05 } };

/** The page's layout shift while its answers arrive late and out of order (as on the live site), with what moved most. */
async function shiftOf(page: Page, path: string): Promise<{ cls: number; moved: string[] }> {
  const api = new URL(API);
  let n = 0;
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.host === api.host) return new Promise((ok) => setTimeout(ok, /\/chart\//.test(u.pathname) ? 2500 : 300 + ((n++ * 700) % 2600))).then(() => r.fallback());
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => {
    try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ }
    const w = window as unknown as { __cls: number; __moved: string[] };
    w.__cls = 0; w.__moved = [];
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Node }[] }[]) {
        if (e.hadRecentInput) continue;
        w.__cls += e.value;
        if (e.value > 0.01) for (const s of e.sources ?? []) {
          const el = s.node as HTMLElement | undefined;
          w.__moved.push(`${e.value.toFixed(3)} ${el?.tagName ?? "?"}.${String(el?.className ?? "").slice(0, 50)} "${(el?.textContent ?? "").slice(0, 40)}"`);
        }
      }
    }).observe({ type: "layout-shift", buffered: true });
  }, session);
  await page.goto(path);
  await page.waitForTimeout(9000);
  return page.evaluate(() => { const w = window as unknown as { __cls: number; __moved: string[] }; return { cls: w.__cls, moved: w.__moved }; });
}

// LIVE10A-028 / LIVE10B-004 / LIVE10B-041: late cards moved the page (/new 0.175, a notebook 0.432, corporate actions 0.17, the money
// calendar 0.121, holdings 0.102)
test("pages with late cards hold still: layout shift under 0.1 (LIVE10A-028, LIVE10B-004/041)", async ({ browser, request }, info) => {
  test.skip(info.project.name === "phone", "measured at the reviewer's 1440 desktop");
  test.setTimeout(300_000);
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: "Fix11 shift", strategy: EMA, instrument: "FX:EURUSD=X" } })).json();
  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 730 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  const over: string[] = [];
  for (const path of ["/new", `/n/${nb.id}`, "/research/corporate-actions", "/money/calendar", "/holdings"]) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p = await ctx.newPage();
    const { cls, moved } = await shiftOf(p, path);
    console.log(`CLS ${path}: ${cls.toFixed(3)}\n  ${moved.slice(0, 6).join("\n  ")}`);
    if (cls >= 0.1) over.push(`${path}: ${cls.toFixed(3)}\n  ${moved.slice(0, 6).join("\n  ")}`);
    await ctx.close();
  }
  expect(over, over.join("\n")).toEqual([]);
});
