import { expect, test, type Page } from "@playwright/test";

// RC-7, the third round of the main review: the account, errors and phone side, and the investor figures that said one fact two
// ways. Each flow that broke, driven in the browser.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const who = (n: number, phone: boolean) => { const i = n + (phone ? 1 : 0); return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` }; };
type Who = ReturnType<typeof who>;

async function signIn(page: Page, u: Who, path: string, tour = true) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: u.token, user: { id: u.id, aud: "authenticated", email: u.email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript(([s, t]) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); if (t) localStorage.setItem("stratlab.tour.v1", "1"); }, [session, tour] as const);
  await page.goto(path);
  return errors;
}

/** A colour string ("rgb(…)" or "rgba(…)") as [r, g, b]. */
const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
const lum = ([r, g, b]: number[]) => { const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
const contrast = (a: string, b: string) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

for (const scheme of ["dark", "light"] as const) {
  test(`RC7-001: when the app's files fail to load, the shell's error card is on-brand and readable (${scheme} device)`, async ({ browser }) => {
    const ctx = await browser.newContext({ colorScheme: scheme, viewport: { width: 390, height: 800 } });
    const page = await ctx.newPage();
    await page.route("**/assets/**", (r) => r.abort());
    await page.goto("/");
    const card = page.locator(".boot-now");
    await expect(card).toBeVisible({ timeout: 40_000 });
    await expect(card.getByRole("heading", { name: "Couldn't load StratLab." })).toBeVisible();
    await expect(card.getByRole("button", { name: "Reload" })).toBeVisible();
    const m = await page.evaluate(() => {
      const cs = (e: Element, p: string) => getComputedStyle(e).getPropertyValue(p);
      const card = document.querySelector(".boot-now")!, h = card.querySelector("h1")!, p = card.querySelector("p")!, b = card.querySelector("button")!;
      const r = card.getBoundingClientRect();
      return { page: cs(document.body, "background-color"), html: cs(document.documentElement, "background-color"), card: cs(card, "background-color"), h: cs(h, "color"), p: cs(p, "color"), b: cs(b, "background-color"), bt: cs(b, "color"), left: r.left, right: innerWidth - r.right, logo: !!card.querySelector("img") };
    });
    expect(m.html, "the page has the paper colour, not the browser's white").toBe(scheme === "dark" ? "rgb(20, 19, 17)" : "rgb(245, 241, 232)");
    expect(contrast(m.h, m.card), "the heading reads on the card").toBeGreaterThan(7);
    expect(contrast(m.p, m.card), "the sentence reads on the card").toBeGreaterThan(4.5);
    expect(contrast(m.bt, m.b), "the button's words read on the button").toBeGreaterThan(7);
    expect(m.left, "a gutter on a phone").toBeGreaterThanOrEqual(16);
    expect(m.right).toBeGreaterThanOrEqual(16);
    expect(m.logo).toBe(true);
    await ctx.close();
  });
}

test("RC7-002: the welcome question shows all four choices on a 360 x 640 phone with no scroll, and the optional level question comes after them", async ({ page }, info) => {
  const u = who(270, info.project.name === "phone");
  await page.setViewportSize({ width: 360, height: 640 });
  const errors = await signIn(page, u, "/", false);
  const dialog = page.getByRole("dialog", { name: "What brings you here?" });
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  const choices = dialog.locator("[data-focus]");
  await expect(choices).toHaveCount(4);
  await expect(dialog.getByText("How much have you done? · optional")).toBeAttached();
  const vh = 640;
  for (const f of ["trade", "invest", "money", "both"]) {
    const box = await dialog.locator(`[data-focus="${f}"]`).boundingBox();
    expect(box && box.y >= 0 && box.y + box.height <= vh, `the ${f} choice is fully on screen at 360 x 640 (${JSON.stringify(box)})`).toBe(true);
  }
  // the owner's words are all still there, in the dialog's own text
  const text = await dialog.innerText();
  for (const w of ["StratLab is a lab for testing trading ideas", "We'll open the one you pick.", "Manage my money", "How much have you done? · optional"]) expect(text).toContain(w);
  // the level question is after the choices, in the page's order and in the drawn order
  const [last, level] = [await dialog.locator('[data-focus="both"]').boundingBox(), await dialog.getByText("How much have you done? · optional").boundingBox()];
  expect(level!.y).toBeGreaterThan(last!.y);
  expect(errors).toEqual([]);
});
