import { expect, test } from "@playwright/test";

// Lane land77: LIVE14A-014 / LIVE14B-003, the landing's LCP (2.8-2.9 s) and the phone's layout shift (0.026). The start-up frame's heading
// and lede painted first in a stand-in serif, then the app's hero in Fraunces was a later, larger paint (the LCP), and the swap moved the
// phone's lede. The hero's words now wait, hidden, for their own faces (public/boot.js sets data-faces; index.html), so nothing on the
// landing is ever painted in a stand-in: no local font's metrics (CI's DejaVu, a Mac's Georgia) decide where anything sits.

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

for (const narrow of [false, true]) test(`LIVE14A-014 / LIVE14B-003: the landing's hero is painted once, in its own faces: no later, larger paint, nothing shifts${narrow ? " (360 px)" : ""}`, async ({ page }, info) => {
  test.skip(narrow && info.project.name !== "phone", "the narrow phone");
  if (narrow) await page.setViewportSize({ width: 360, height: 760 });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    // the faces arrive well after the first paint, as on the live site (the frame's heading was painted first in the stand-in serif there)
    if (r.request().url().endsWith(".woff2")) return new Promise((ok) => setTimeout(ok, 1500)).then(() => r.fallback());
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8 });
  await page.addInitScript(() => {
    type W = { __lcp: { t: number; size: number; boot: boolean; tag: string }[]; __cls: { t: number; v: number; who: string[] }[]; __faces: number };
    const w = window as unknown as W;
    w.__lcp = []; w.__cls = []; w.__faces = -1;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { startTime: number; size: number; element?: Element }[])
        w.__lcp.push({ t: Math.round(e.startTime), size: e.size, boot: !!e.element?.closest("[data-boot]"), tag: e.element ? `${e.element.tagName}.${e.element.className}` : "" });
    }).observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { hadRecentInput: boolean; value: number; startTime: number; sources?: { node?: Node }[] }[])
        if (!e.hadRecentInput) w.__cls.push({ t: Math.round(e.startTime), v: e.value, who: (e.sources ?? []).map((s) => { const n = s.node as Element | undefined; return n ? `${n.nodeName}.${(n as Element).className ?? ""}` : "?"; }) });
    }).observe({ type: "layout-shift", buffered: true });
    // when the hero's words were let paint (the document timeline: the clock LCP's times are on, which the test clock leaves alone)
    new MutationObserver(() => { if (w.__faces < 0 && document.documentElement.hasAttribute("data-faces")) w.__faces = Math.round(Number(document.timeline.currentTime)); })
      .observe(document, { attributes: true, subtree: true, attributeFilter: ["data-faces"] });      // (no <html> yet when this runs)
  });
  await page.goto("/");
  await expect(page.locator("section.lp-hero h1")).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(2500);
  const m = await page.evaluate(() => {
    const w = window as unknown as { __lcp: { t: number; size: number; boot: boolean; tag: string }[]; __cls: { t: number; v: number; who: string[] }[]; __faces: number };
    return { lcp: w.__lcp, cls: w.__cls, faces: w.__faces };
  });
  const cls = m.cls.reduce((a, b) => a + b.v, 0);
  console.log(`${page.viewportSize()!.width}px faces let paint at ${m.faces} ms; LCP ${JSON.stringify(m.lcp)}; CLS ${cls.toFixed(4)} ${JSON.stringify(m.cls)}`);
  const last = m.lcp[m.lcp.length - 1];
  expect(m.faces, "the hero's words wait for their faces, then paint").toBeGreaterThan(0);
  expect(last.size, "the largest paint is the hero's heading or lede").toBeGreaterThan(20000);
  // one paint of the hero, when its faces came: the app's hero drawn later, the same words in the same place, is no larger paint
  expect(last.t, `the largest paint is the hero's first, not a later redraw: ${JSON.stringify(m.lcp)}`).toBeLessThanOrEqual(m.faces + 250);
  expect(cls, `nothing on the landing moves: ${JSON.stringify(m.cls)}`).toBeLessThan(0.01);
});
