import { expect, test, type Page } from "@playwright/test";

// The Admin page's AI panel, on desktop and phone: each provider's state, the models in use with their numbers,
// quota and its reset, the computed routing order, the missing keys with where to get them, and the buttons (test,
// re-rank, pin, block). Signed in as the fake database's site owner.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string, ready: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
}

async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

const now = () => Date.now() / 1000;
const model = (id: string, rank: number | null, extra: Record<string, unknown> = {}) => ({
  id, in_use: rank != null, rank, success: 96, tries: 25, median_ms: 1200, probe: { ok: 2, tries: 2, at: now() - 3600, error: null },
  last_error: null, last_error_at: null, open_until: null, open_reason: null, blocked: false, pinned: false, ctx: 128000, thinks: false, ...extra });
const provider = (name: string, label: string, extra: Record<string, unknown> = {}) => ({
  name, label, configured: true, missing: [], key_url: `https://example.com/${name}`, free: "Free: plenty.", terms: "ok", note: "",
  variables: [`${name.toUpperCase()}_API_KEY`], model_variable: `${name.toUpperCase()}_MODEL`, state: "ok", state_text: "Working.",
  quota: { limited: false, reset_at: null, remaining: { requests: 980, tokens: 11000 }, remaining_at: now() - 60 },
  last_ok: now() - 60, last_error: null, last_used_model: "llama-3.3-70b-versatile", pinned: null, pinned_by: null,
  ranked_at: now() - 7200, rank_error: null, discovered: 19, skipped: { "not a chat model": 6, "not English-first": 1, "too small": 2 }, probing: false,
  models: [], blocked: [], ...extra });

function view(pinned: string | null, blocked: string[]) {
  const groqModels = [model("llama-3.3-70b-versatile", 1), model("openai/gpt-oss-120b", 2, { thinks: true, success: 88 }),
    model("qwen/qwen3-32b", null, { last_error: "empty reply (qwen/qwen3-32b)", success: 40 })]
    .map((m) => ({ ...m, pinned: m.id === pinned, blocked: blocked.includes(m.id) }));
  return {
    providers: [
      provider("groq", "Groq", { models: groqModels, pinned, pinned_by: pinned ? "admin" : null, blocked }),
      provider("mistral", "Mistral", { state: "warn", state_text: "Free quota used up for now; it resets on its own.",
        quota: { limited: true, reset_at: now() + 3 * 3600, remaining: null, remaining_at: null },
        models: [model("mistral-small-latest", 1, { open_until: now() + 3 * 3600, open_reason: "rate limited (daily free quota)" })] }),
      provider("github", "GitHub Models", { configured: false, missing: ["GITHUB_MODELS_TOKEN"], terms: "prototype", state: "off",
        state_text: "No key yet.", free: "Free: 50 to 150 requests a day per model.", note: "Asked only after every other free provider.",
        key_url: "https://github.com/settings/personal-access-tokens/new", models: [] }),
      provider("cloudflare", "Cloudflare Workers AI", { configured: false, missing: ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"],
        state: "off", state_text: "No key yet.", key_url: "https://dash.cloudflare.com/profile/api-tokens", models: [] }),
    ],
    routes: {
      quick: { label: "Idea builder and quick answers", budget_s: 30, steps: [
        { provider: "groq", label: "Groq", model: pinned ?? "llama-3.3-70b-versatile", ready: true },
        { provider: "mistral", label: "Mistral", model: "mistral-small-latest", ready: false }] },
      research: { label: "Research reads", budget_s: 60, steps: [{ provider: "groq", label: "Groq", model: "openai/gpt-oss-120b", ready: true }] },
      long: { label: "Long documents", budget_s: 120, steps: [] },
    },
    cache: { entries: 12, hits: 30, misses: 70 }, rerank_every_hours: 6,
    last_failure: { at: now() - 600, task: "research", detail: "No AI model could answer. Groq · openai/gpt-oss-120b: timed out" },
  };
}

test("admin: the AI panel shows each provider's models, quota and routing, and pins, blocks, tests and re-ranks", async ({ page }, info) => {
  const sent: { path: string; body: unknown }[] = [];
  let pinned: string | null = null;
  let blocked: string[] = [];
  await page.route((u) => u.pathname.startsWith("/admin/ai"), async (r) => {
    const req = r.request();
    const path = new URL(req.url()).pathname;
    const body = req.method() === "POST" ? req.postDataJSON() : null;
    if (req.method() === "POST") sent.push({ path, body });
    if (path === "/admin/ai/pin") pinned = body.model;
    if (path === "/admin/ai/block") blocked = body.blocked ? [...blocked, body.model] : blocked.filter((m) => m !== body.model);
    const v = view(pinned, blocked);
    const out = path === "/admin/ai/test" ? { providers: [{ name: "groq", label: "Groq", ok: true, error: null, model: "llama-3.3-70b-versatile", ms: 812, quota: false },
      { name: "mistral", label: "Mistral", ok: false, error: "Free quota used up for now; it resets on its own.", model: null, ms: 300, quota: true }], view: v }
      : path === "/admin/ai/rerank" ? { ...v, started: ["groq", "mistral"] } : v;
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(out) });
  });
  const errors = await open(page, "/admin/system", "Who is asked, in order");
  const panel = page.locator("section[aria-label='AI']");
  const groq = panel.locator(".ai-provider", { hasText: "Groq" });
  await expect(groq.getByText("llama-3.3-70b-versatile").first()).toBeVisible();
  await expect(groq.getByText("96% of 25 answered well").first()).toBeVisible();
  await expect(groq.getByText(/last problem: empty reply/)).toBeVisible();
  await expect(groq.getByText(/left out 6 not chat models, 1 built for another language, 2 too small/)).toBeVisible();
  await expect(groq.getByText(/Left this period: 980 requests/)).toBeVisible();
  const mistral = panel.locator(".ai-provider", { hasText: "Mistral" });
  await expect(mistral.getByText("Check", { exact: true })).toBeVisible();
  await expect(mistral.getByText(/Free quota resets in 3 h/)).toBeVisible();
  await expect(panel.getByText(/Groq · llama-3.3-70b-versatile → Mistral · mistral-small-latest \(paused\)/)).toBeVisible();
  await expect(panel.getByText(/30% of questions since the last restart were answered from the cache/)).toBeVisible();
  await expect(panel.getByText(/Last time nothing could answer/)).toBeVisible();
  // the providers with no key are one click away, not 13 set-up guides on the page
  const more = panel.locator("[aria-label='More free providers']");
  const fold = panel.getByTestId("ai-more-providers");
  await expect(fold).not.toHaveAttribute("open", /.*/);
  await expect(more.getByRole("link", { name: /Get a key/ })).toHaveCount(0);
  await fold.locator("summary").click();
  await expect(more.getByText("Prototyping tier").first()).toBeVisible();
  await expect(more.getByText("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID")).toBeVisible();
  await expect(more.getByRole("link", { name: "Get a key" }).first()).toHaveAttribute("href", "https://github.com/settings/personal-access-tokens/new");
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  await groq.getByRole("button", { name: "Pin openai/gpt-oss-120b" }).click();
  await expect(groq.getByText(/Pinned to openai\/gpt-oss-120b\./)).toBeVisible();
  await groq.getByRole("button", { name: "Block qwen/qwen3-32b" }).click();
  await expect(groq.getByRole("button", { name: "Unblock qwen/qwen3-32b" })).toBeVisible();
  await groq.getByRole("button", { name: "Unpin" }).click();
  await expect(groq.getByText(/Pinned to/)).toHaveCount(0);
  await panel.getByRole("button", { name: "Test every provider" }).click();
  await expect(groq.getByText("Test: answered with llama-3.3-70b-versatile in 0.8 s")).toBeVisible();
  await panel.getByRole("button", { name: "Re-rank models" }).click();
  await groq.getByRole("button", { name: "Re-rank Groq models" }).click();
  await expect.poll(() => sent).toEqual([
    { path: "/admin/ai/pin", body: { provider: "groq", model: "openai/gpt-oss-120b" } },
    { path: "/admin/ai/block", body: { provider: "groq", model: "qwen/qwen3-32b", blocked: true } },
    { path: "/admin/ai/pin", body: { provider: "groq", model: null } },
    { path: "/admin/ai/test", body: null },
    { path: "/admin/ai/rerank", body: {} },
    { path: "/admin/ai/rerank", body: { provider: "groq" } },
  ]);
  await sane(page, errors);
});

test("admin: with no AI keys, the panel says so and lists every free provider with where to get a key", async ({ page }, info) => {
  const errors = await open(page, "/admin/system", "Quickest to set up");
  const panel = page.locator("section[aria-label='AI']");
  await expect(panel.getByText("No AI keys yet")).toBeVisible();
  await expect(panel.getByText("GROQ_API_KEY")).toBeVisible();
  // the two quickest in view; the other eleven one click away
  await expect(panel.getByRole("link", { name: "Get a key" })).toHaveCount(2);
  await expect(panel.getByRole("link", { name: "Get a key: Google Gemini" })).toBeVisible();
  await panel.getByTestId("ai-more-providers").locator("summary").click();
  await expect(panel.getByRole("link", { name: "Get a key" })).toHaveCount(13);
  await expect(panel.getByRole("button", { name: "Test every provider" })).toBeDisabled();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});
