// The browser tests' clock (CLOCK, owner 31 Oct: "the PR fails are a real issue"). The fake world (backend/tests/visual_server.py)
// runs at one fixed moment, E2E_NOW, not the machine's clock (backend/tests/e2e_clock.py), and every browser context here starts at
// the world's time now, read from /e2e/now: a page and the API agree on the day, the hour and whether a market is open, whatever
// day CI runs on. The clock runs on from there (page.clock.install: timers still fire); a spec that sets its own clock
// (a11y, live-refresh, stale...) still does, its call coming after this one.
//
// Every spec gets this without importing it: e2e/tsconfig.json maps "@playwright/test" to this file (playwright.config.ts names
// that tsconfig), and this file takes Playwright itself from "playwright/test", the package "@playwright/test" re-exports.
//
//   test.use({ moment: "closed" })   the shut-market moment (Sun 1 Nov 2026, 15:00 IST): its own world, built at that moment and
//                                    started the first time a test asks; `api` is its address, and the page's config points there
import { test as base, type BrowserContext } from "playwright/test";

export * from "playwright/test";

// the two named moments, as backend/tests/e2e_clock.py has them (frontend/unit/review-clock.test.mjs keeps them equal)
export const E2E_NOW = "2026-10-28T11:00:00+05:30";            // Wed: India mid-session, no holiday within two weeks
export const E2E_NOW_CLOSED = "2026-11-01T15:00:00+05:30";     // Sun, a month's first day: every market shut
const OPEN_API = process.env.E2E_API ?? "http://127.0.0.1:8765";

// the world's time now; null when the server runs on the machine's clock (E2E_NOW=real) or is an older one without the route
async function worldNow(api: string): Promise<number | null> {
  const r = await fetch(`${api}/e2e/now`).catch(() => null);
  if (!r?.ok) return null;
  const j = await r.json() as { now: string; fixed: boolean };
  return j.fixed ? Date.parse(j.now) : null;
}

async function setClock(context: BrowserContext, api: string) {
  const now = await worldNow(api);
  if (now !== null) await context.clock.install({ time: now });
}

// the closed world's address, once per worker: the first ask starts it (about a minute's build), later ones find it running
let closed: Promise<string> | undefined;
function closedWorld(): Promise<string> {
  closed ??= (async () => {
    const r = await fetch(`${OPEN_API}/e2e/closed`, { method: "POST" });
    if (!r.ok) throw new Error(`the fake world can't start its closed moment: ${r.status}`);
    const { api } = await r.json() as { api: string };
    for (const until = Date.now() + 360_000; Date.now() < until; await new Promise((ok) => setTimeout(ok, 2000)))
      if (await worldNow(api) !== null) return api;
    throw new Error(`the closed world at ${api} didn't start in 6 minutes`);
  })();
  return closed;
}

export const test = base.extend<{ moment: "open" | "closed"; api: string }>({
  moment: ["open", { option: true }],
  // the fake API's address at the test's moment (a spec's own API constant is the open world's)
  api: [async ({ moment }, use) => { await use(moment === "closed" ? await closedWorld() : OPEN_API); }, { timeout: 400_000 }],
  // contexts a spec opens itself (browser.newContext, browser.newPage) start at the open world's time too
  browser: [async ({ browser }, use) => {
    const newContext = browser.newContext.bind(browser);
    browser.newContext = async (options) => {
      const context = await newContext(options);
      await setClock(context, OPEN_API);
      return context;
    };
    await use(browser);
  }, { scope: "worker" }],
  context: async ({ context, api }, use) => {
    if (api !== OPEN_API) {
      await setClock(context, api);
      // the built app's config (e2e/config.mjs) names the open world's API: at the closed moment the page talks to the closed one
      await context.route("**/config.js", async (route) => {
        const res = await route.fetch();
        await route.fulfill({ response: res, body: (await res.text()).replace(OPEN_API, api) });
      });
    }
    await use(context);
  },
});
