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
