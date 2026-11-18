import { expect, test, type Page } from "@playwright/test";

// fix13: LIVE11A findings proved on the pages as drawn. Each test sets its own width, so it is the same on the desktop and phone projects.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

/** The page's layout shift while its answers arrive late and out of order (as on the live site), with what moved most (as fix11.spec). */
async function shiftOf(page: Page, path: string, opts: { signedIn?: boolean; scheme?: "light" | "dark" } = {}): Promise<{ cls: number; moved: string[] }> {
  const api = new URL(API);
  let n = 0;
  if (opts.scheme) await page.emulateMedia({ colorScheme: opts.scheme });
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.host === api.host) return new Promise((ok) => setTimeout(ok, /\/chart\//.test(u.pathname) ? 2500 : 300 + ((n++ * 700) % 2600))).then(() => r.fallback());
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(({ s, signedIn }) => {
    try { if (signedIn) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ }
    const w = window as unknown as { __cls: number; __moved: string[] };
    w.__cls = 0; w.__moved = [];
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Node }[] }[]) {
        if (e.hadRecentInput) continue;
        w.__cls += e.value;
        if (e.value > 0.01) for (const src of e.sources ?? []) {
          const el = src.node as HTMLElement | undefined;
          w.__moved.push(`${e.value.toFixed(3)} ${el?.tagName ?? "?"}.${String(el?.className ?? "").slice(0, 50)} "${(el?.textContent ?? "").slice(0, 40)}"`);
        }
      }
    }).observe({ type: "layout-shift", buffered: true });
  }, { s: session, signedIn: opts.signedIn !== false });
  await page.goto(path);
  await page.waitForTimeout(9000);
  return page.evaluate(() => { const w = window as unknown as { __cls: number; __moved: string[] }; return { cls: w.__cls, moved: w.__moved }; });
}

// LIVE11A-012: Sectors US 0.269, Results India 0.161, Watchlist 0.152, Corporate actions 0.151, Mood (light) 0.144, Results US 0.14, All dates 0.139,
// /login phone 0.136, My space phone 0.106, IPOs 0.097
test("LIVE11A-012: the pages the review measured hold still while their answers arrive: layout shift under 0.1", async ({ browser }, info) => {
  test.skip(info.project.name === "phone", "each page is measured at the reviewer's own width here");
  test.setTimeout(420_000);
  const pages: [string, number, { signedIn?: boolean; scheme?: "light" | "dark"; region?: "IN" | "US" }][] = [
    ["/research/rotation", 1440, { region: "US" }], ["/research/results", 1440, { region: "IN" }], ["/research/results", 1440, { region: "US" }],
    ["/watchlist", 1440, {}], ["/research/corporate-actions", 1440, {}], ["/research/pulse", 1440, { scheme: "light" }], ["/calendar", 1440, {}],
    ["/login", 390, { signedIn: false }], ["/mine", 390, {}], ["/invest/ipos", 1440, {}],
  ];
  const over: string[] = [];
  for (const [path, width, o] of pages) {
    const ctx = await browser.newContext({ viewport: { width, height: width < 500 ? 844 : 900 } });
    if (o.region) await ctx.addInitScript((r) => { try { localStorage.setItem("stratlab.research.region", r); } catch { /* none */ } }, o.region);
    const p = await ctx.newPage();
    const { cls, moved } = await shiftOf(p, o.region ? `${path}?region=${o.region}` : path, o);
    const line = `${path}${o.region ? ` ${o.region}` : ""}${o.scheme ? ` ${o.scheme}` : ""} @${width}: ${cls.toFixed(3)}\n  ${moved.slice(0, 6).join("\n  ")}`;
    console.log(`CLS ${line}`);
    if (cls >= 0.1) over.push(line);
    await ctx.close();
  }
  expect(over, over.join("\n")).toEqual([]);
});
