import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// site85 (Release 85) on the fake world. Every start-up check holds the app's code back on purpose (2.5 s), so the page's own HTML frame is
// on screen long enough to be measured on any machine: the frame must be right, not merely short.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
// S85_SHOTS=<folder>: also save the frames (the lane's before/after; never in CI)
const SHOTS = process.env.S85_SHOTS;

async function signedIn(page: Page, token: string, theme?: "light" | "dark") {
  const known: Record<string, [string, string]> = { "free-token": ["u-free", "free@example.com"], "pro-token": ["u-pro", "u-pro@example.com"] };
  const [id, email] = known[token] ?? [`u-${token}`, `${token.replace("-", "")}@example.com`];
  const user = { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} };
  await page.addInitScript(([t, u, th]) => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: t, token_type: "bearer", expires_in: 3600, expires_at: 4102444800, refresh_token: "r", user: u }));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab.consent.v1", "no");
      if (th) localStorage.setItem("stratlab-theme", th);
    } catch { /* none */ }
  }, [token, user, theme ?? ""] as const);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
}

/** An address as production serves it: the build's own page (dist/<path>/index.html), which vite preview serves only with the slash. */
async function servedAsLive(page: Page, p: string) {
  await page.route((u) => u.pathname === p, (r) => r.request().resourceType() === "document"
    ? r.fulfill({ status: 200, contentType: "text/html", body: readFileSync(new URL(`../dist${p}/index.html`, import.meta.url), "utf8") })
    : r.fallback());
}

/** What the page shows now, for the start-up frame's checks. */
const frame = (page: Page) => page.evaluate(() => {
  const seen = (el: Element | null) => { if (!el) return false; const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0; };
  const signIn = [...document.querySelectorAll("a, button")].filter((b) => /^\s*Sign in\s*$/.test((b as HTMLElement).innerText || b.textContent || "") && seen(b)).length;
  const landingH1 = [...document.querySelectorAll("h1")].filter((h) => /skill or luck/i.test(h.textContent || "")).length;
  const publicHead = document.querySelectorAll("[data-boot-head], .lp-nav, .boot-head").length;
  const shell = document.querySelector(".boot-shell");
  const appShell = document.querySelector(".shell:not(.boot-shell)");
  const load = shell?.querySelector(".k-loading") as HTMLElement | null;
  const col = shell?.querySelector("main") as HTMLElement | null;
  let off = null as number | null, font = "", text = "";
  if (load && col && seen(load)) {
    // the words' own box (a range), against the page column's centre
    const range = document.createRange(); range.selectNodeContents(load);
    const r = range.getBoundingClientRect(), c = col.getBoundingClientRect();
    off = Math.round(Math.abs((r.left + r.right) / 2 - (c.left + c.right) / 2));
    font = getComputedStyle(load).fontFamily; text = load.innerText.trim();
  }
  const side = shell?.querySelector(".sidebar"), top = shell?.querySelector(".topbar");
  return { signIn, landingH1, publicHead, shell: seen(shell), appShell: !!appShell, off, font, text, sidebar: seen(side ?? null), topbar: seen(top ?? null),
    // the logo, its mark's gradients its own (a fill naming another copy's, in a hidden top bar, is drawn empty)
    logo: !!shell?.querySelector(".logo") && [...(shell?.querySelectorAll('[fill^="url(#"]') ?? [])].every((el) => {
      const id = (el.getAttribute("fill") || "").slice(5, -1);
      const def = document.getElementById(id);
      return !!def && def.closest("svg") === el.closest("svg");
    }), paper: getComputedStyle(document.body).backgroundColor, h1s: document.querySelectorAll("h1").length };
});

// LIVE21B-001 (High): a signed-in full load showed the PUBLIC header ("Library … Contact" and a "Sign in" button) and "Opening StratLab…" in an
// unstyled serif against the page's left edge for ~2.9 s, with the landing's heading "Is your trading idea skill or luck?" in the DOM. Now the
// first frame is the app's own: the menu's panel (the top bar on a phone) with the logo, "Opening StratLab…" centred in the page column, in the
// app's own type and the reader's theme, and no landing header, button or heading at any moment.
for (const theme of ["dark", "light"] as const) {
  test(`a signed-in full load never shows the public header or the landing (${theme})`, async ({ page }, info) => {
    const phone = info.project.name === "phone";
    await page.emulateMedia({ colorScheme: theme === "dark" ? "dark" : "light" });
    await signedIn(page, "pro-token", theme);
    // the app's code held back: the page's own HTML frame is what shows meanwhile
    await page.route(/\/assets\/index-[^/]+\.js$/, async (r) => { await new Promise((ok) => setTimeout(ok, 2500)); await r.fallback(); });
    const t0 = Date.now();
    await page.goto("/mine", { waitUntil: "commit" });
    const frames: Awaited<ReturnType<typeof frame>>[] = [];
    for (const at of [200, 600, 1200, 2000]) {
      await page.waitForTimeout(Math.max(0, at - (Date.now() - t0)));
      const f = await frame(page).catch(() => null);
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/${info.project.name}-${theme}-${at}.png` }).catch(() => undefined);
      if (f) frames.push(f);
    }
    expect(frames.length).toBeGreaterThan(2);
    for (const [i, f] of frames.entries()) {
      const at = `frame ${i}`;
      expect(f.signIn, `${at}: no "Sign in" button`).toBe(0);
      expect(f.publicHead, `${at}: no public header`).toBe(0);
      expect(f.landingH1, `${at}: no landing heading in the DOM`).toBe(0);
      if (f.appShell) continue;              // the app has drawn its own Shell
      expect(f.shell, `${at}: the app's frame`).toBe(true);
      expect(f.logo, `${at}: the logo`).toBe(true);
      expect(phone ? f.topbar : f.sidebar, `${at}: ${phone ? "the top bar" : "the menu's panel"}`).toBe(true);
      expect(f.text, `${at}: its words`).toBe("Opening StratLab…");
      expect(f.off ?? 99, `${at}: centred in the page column`).toBeLessThanOrEqual(2);
      expect(f.font, `${at}: the app's type, not a stand-in serif`).toMatch(/IBM Plex Sans/);
      expect(f.font).not.toMatch(/Georgia|(^|,\s*)serif$/);
      expect(f.paper, `${at}: the ${theme} paper`).toBe(theme === "dark" ? "rgb(20, 19, 17)" : "rgb(245, 241, 232)");
      expect(f.h1s, `${at}: one heading`).toBe(1);
    }
    // the HTML frame was really seen (the hold works), and the page then opens as usual
    expect(frames.some((f) => f.shell), "the HTML frame was measured").toBe(true);
    await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("link", { name: /^Sign in$/ })).toHaveCount(0);
  });
}

// the Plans page's own HTML (dist/plans/index.html: the landing's header with its "Sign in" button and the plan cards) and the sign-in page's
test("a signed-in load of /plans or /login starts in the app's frame too", async ({ page }) => {
  await signedIn(page, "pro-token", "dark");
  await page.route(/\/assets\/index-[^/]+\.js$/, async (r) => { await new Promise((ok) => setTimeout(ok, 2500)); await r.fallback(); });
  for (const p of ["/plans", "/login"]) {
    await servedAsLive(page, p);
    await page.goto(p, { waitUntil: "commit" });
    await page.waitForTimeout(700);
    const f = await frame(page);
    expect(f.signIn, `${p}: no "Sign in" button`).toBe(0);
    expect(f.publicHead, `${p}: no public header`).toBe(0);
    expect(f.shell || f.appShell, `${p}: the app's frame`).toBe(true);
    await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
  }
});

// a visitor (nothing saved) keeps the landing's frame, and a signed-in reader's policy page keeps its own words
test("a visitor's load and a policy page are unchanged", async ({ page }) => {
  await page.route(/\/assets\/index-[^/]+\.js$/, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.fallback(); });
  await page.goto("/", { waitUntil: "commit" });
  await page.waitForTimeout(500);
  expect(await page.locator("[data-boot-head]").count()).toBe(1);
  expect(await page.locator(".boot-shell").count()).toBe(0);
  await signedIn(page, "pro-token");
  await servedAsLive(page, "/terms");
  await page.goto("/terms", { waitUntil: "commit" });
  await page.waitForTimeout(500);
  expect(await page.locator(".boot-shell").count()).toBe(0);
});
