import { expect, test, type Page } from "@playwright/test";

// fix12: speed of the main pages on the fake world (LIVE10A-010, CX2 #8): the time from the start of the visit to the page's heading, and to
// the page holding still with no "loading" placeholder left. Each test sets its own width, so it is the same on the desktop and phone projects.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function timings(page: Page, path: string): Promise<{ h1: number; settled: number; left: string[]; last: string }> {
  const t0 = Date.now();
  await page.goto(path, { waitUntil: "commit" });
  await page.locator("h1").first().waitFor({ state: "visible", timeout: 20_000 });
  const h1 = Date.now() - t0;
  // settled: no placeholder (role=status aria-busy) on the page for half a second running, at most 20 s
  let quietSince = 0;
  let left: string[] = [], last = "";
  while (Date.now() - t0 < 20_000) {
    left = await page.locator('[aria-busy="true"][aria-label]').evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""));
    if (left.length) last = left.join(", ");
    if (!left.length) { if (!quietSince) quietSince = Date.now(); if (Date.now() - quietSince >= 500) break; }
    else quietSince = 0;
    await page.waitForTimeout(100);
  }
  return { h1, settled: (quietSince || Date.now()) - t0, left, last };
}

test("the main pages show their heading within 3 s and hold no placeholder past 6 s on the fake world (LIVE10A-010, CX2)", async ({ browser }, info) => {
  test.skip(info.project.name === "phone", "measured once, at the reviewer's 1440 desktop");
  test.setTimeout(240_000);
  const out: string[] = [], slow: string[] = [];
  const pages: [string, boolean][] = [["/", false], ["/mine", true], ["/research/pulse", true], ["/research/IN/TCS", true], ["/research/results", true],
    ["/trade/signals", true], ["/invest/breadth", true]];
  for (const [path, signedIn] of pages) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    if (signedIn) await ctx.addInitScript((s) => { try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ } }, session);
    const p = await ctx.newPage();
    const cold = await timings(p, path);    // the first visit warms the server's caches (as any earlier visitor would)
    const t = await timings(p, path);
    out.push(`${path}: heading ${t.h1} ms, settled ${t.settled} ms${t.left.length ? ` (still loading: ${t.left.join(", ")})` : ""}`
      + ` · first visit ${cold.h1} / ${cold.settled} ms · last placeholder: ${t.last || cold.last || "none"}`);
    if (t.h1 > 3000 || t.settled > 6000) slow.push(out[out.length - 1]);
    await ctx.close();
  }
  console.log(out.join("\n"));
  expect(slow, slow.join("\n")).toEqual([]);
});
