import { expect, test, type Page } from "@playwright/test";

// inv96 (owner, 26 Nov: "ok go ahead"): the Invest home's Coming up lists the person's own stocks' next dates (results, ex-dates with
// the record date, bonuses, splits), Date · Company · What, each company a link to its page; "See calendar" opens the Calendar on My
// stocks. With no stocks, the market's events under a label saying so, with the way to add stocks. Its wait holds the table's height.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const who = (n: number) => ({ access_token: `inv96-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: `u-inv96-${n}`, aud: "authenticated", email: `inv96${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } });
/** This test's own account, one per project. */
const own = (n: number, phone: boolean) => n + (phone ? 1 : 0);

async function signIn(page: Page, n: number, slow: RegExp | null = null) {
  if (slow) await page.route((u) => u.href.startsWith(API) && slow.test(u.pathname), async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.fulfill({ response: await r.fetch() }); });
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
  await page.addInitScript(([s]) => {
    try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ }
    const w = window as unknown as { __cls: number; __src: string[] };
    w.__cls = 0; w.__src = [];
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; startTime: number; sources?: { node?: Node; previousRect: DOMRect; currentRect: DOMRect }[] }[]) {
        if (e.hadRecentInput) continue;
        w.__cls += e.value;
        for (const x of e.sources ?? []) w.__src.push(`${Math.round(e.startTime)}ms ${e.value.toFixed(3)} ${(x.node as HTMLElement | undefined)?.className ?? "?"} y ${Math.round(x.previousRect.y)}→${Math.round(x.currentRect.y)} h ${Math.round(x.previousRect.height)}→${Math.round(x.currentRect.height)}`);
      }
    }).observe({ type: "layout-shift", buffered: true });
  }, [who(n)] as const);
}

test("a watchlist's own dates: Date · Company · What, each company linking to its page, See calendar on My stocks", async ({ page, request }, info) => {
  test.setTimeout(120_000);
  const n = own(0, info.project.name === "phone");
  await request.put(`${API}/research/watchlist`, { headers: { Authorization: `Bearer inv96-${n}` }, data: { items: ["RELIANCE", "TCS", "ITC"].map((symbol) => ({ region: "IN", symbol })) } });
  await signIn(page, n);
  await page.goto("/invest");
  const card = page.getByTestId("invest-events");
  const table = card.getByRole("table", { name: "Coming up" });
  await expect(table.locator("tbody tr").first()).toBeVisible({ timeout: 30_000 });
  for (const h of ["Date", "Company", "What"]) await expect(table.getByRole("columnheader", { name: h })).toBeAttached();
  const rows = await table.locator("tbody tr").evaluateAll((rs) => rs.map((r) => ({ to: r.querySelector("th a")?.getAttribute("href") ?? "", what: r.querySelector("td:last-child")?.textContent?.trim() ?? "" })));
  expect(rows.length).toBeGreaterThan(0);
  expect(rows.length).toBeLessThanOrEqual(5);
  for (const r of rows) { expect(r.to, JSON.stringify(rows)).toMatch(/^\/research\/IN\/(RELIANCE|TCS|ITC)$/); expect(r.what).not.toBe(""); }
  await expect(card.getByTestId("invest-coming-why")).toHaveCount(0);
  // every column on screen, on a phone too (ui-lint R18)
  expect(await table.evaluate((t) => { const b = t.closest(".k-tbl-wrap") as HTMLElement; return b.scrollWidth <= b.clientWidth + 1; })).toBe(true);
  await page.screenshot({ path: `test-results/inv96-mine-${info.project.name}.png`, fullPage: true });
  await card.getByTestId("see-calendar").click();
  await expect(page.getByRole("group", { name: "Which dates" }).locator('[aria-pressed="true"]')).toHaveText("My stocks", { timeout: 30_000 });
  // the Calendar lists the card's first company too
  await expect(page.getByTestId("cal-all").locator(`a[href="${rows[0].to}"]`).first()).toBeVisible({ timeout: 30_000 });
});

test("no stocks: the market's events, labelled, with the way to add stocks", async ({ page, request }, info) => {
  test.setTimeout(120_000);
  const n = own(2, info.project.name === "phone");
  await request.put(`${API}/research/watchlist`, { headers: { Authorization: `Bearer inv96-${n}` }, data: { items: [] } });
  await signIn(page, n);
  await page.goto("/invest");
  const why = page.getByTestId("invest-events").getByTestId("invest-coming-why");
  await expect(why).toHaveText("Market events (add stocks to see their dates)", { timeout: 30_000 });
  await expect(why.getByRole("link", { name: "add stocks" })).toHaveAttribute("href", "/research?region=IN");
  await expect(page.getByTestId("invest-events").getByRole("table", { name: "Coming up" }).locator("tbody tr")).toHaveCount(4);
  await page.screenshot({ path: `test-results/inv96-none-${info.project.name}.png`, fullPage: true });
});

test("the wait holds the card's place: nothing under it moves when the stocks' dates come late (LIVE12B-012)", async ({ page, request }, info) => {
  test.setTimeout(120_000);
  const n = own(4, info.project.name === "phone");
  await request.put(`${API}/research/watchlist`, { headers: { Authorization: `Bearer inv96-${n}` }, data: { items: [] } });
  await signIn(page, n, /^\/research\/(results|corp-actions)$/);
  await page.goto("/invest");
  await expect(page.getByTestId("invest-events").getByTestId("invest-coming-why")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  const got = await page.evaluate(() => { const w = window as unknown as { __cls: number; __src: string[] }; return { cls: w.__cls, src: w.__src }; });
  console.log(`/invest ${page.viewportSize()!.width}px: CLS ${got.cls.toFixed(3)}\n  ${got.src.slice(0, 8).join("\n  ")}`);
  expect(got.cls, got.src.join("\n")).toBeLessThan(0.05);
});
