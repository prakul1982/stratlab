import { expect, test, type Page } from "@playwright/test";
import { sessionAs, open, API } from "./pages-kit";

// The REVIEW lane (Wed 4 Nov): Instinct's UI items and the overlay layering. Each test signs in as its own fake Pro account per
// project (review-N in tests/fake_db.py), so nothing saved here meets another spec or the other project's run.

const as = (n: number, phone: boolean) => { const i = n * 2 + (phone ? 1 : 0); return { token: `review-${i}`, id: `u-review-${i}`, email: `review${i}@example.com` }; };
type Who = ReturnType<typeof as>;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });
const signIn = (page: Page, u: Who, path: string, ready: string) => open(page, path, ready, sessionAs(u.token, u.id, u.email));

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

/** What is drawn on top at the middle of `el`: inside `el` itself, or what covers it. */
const onTop = (page: Page, sel: string) => page.evaluate((s) => {
  const el = document.querySelector(s);
  if (!el) return "missing";
  const r = el.getBoundingClientRect();
  const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return top && (el === top || el.contains(top)) ? "self" : (top?.className || top?.tagName || "nothing").toString();
}, sel);

test("Instinct #3: one Slides (PDF) click makes one file, once (and PowerPoint once)", async ({ page }, info) => {
  const u = as(0, info.project.name === "phone");
  // the probe Instinct asked for: every blob address the page makes, with the file's size and type
  await page.addInitScript(() => {
    const made: { size: number; type: string }[] = [];
    (window as unknown as { __blobs: typeof made }).__blobs = made;
    const real = URL.createObjectURL.bind(URL);
    URL.createObjectURL = (o: Blob | MediaSource) => { if (o instanceof Blob) made.push({ size: o.size, type: o.type }); return real(o); };
  });
  const decks: string[] = [];
  page.on("request", (r) => { if (/\/research\/deep\/TCS\/deck/.test(r.url())) decks.push(new URL(r.url()).searchParams.get("format") ?? ""); });
  const errors = await signIn(page, u, "/research/IN/TCS/deep", "business, capex and growth");
  const blobs = () => page.evaluate(() => (window as unknown as { __blobs: { size: number; type: string }[] }).__blobs);
  const before = (await blobs()).length;

  const pdf = page.getByRole("button", { name: "Slides (PDF)" });
  const [file] = await Promise.all([page.waitForEvent("download"), pdf.click()]);
  expect(file.suggestedFilename()).toBe("TCS-deep-dive.pdf");
  await expect(pdf).toBeEnabled();
  await page.waitForTimeout(1500);              // a loop would go on making addresses after the first file
  const afterPdf = (await blobs()).slice(before);
  expect(afterPdf.length, "blob addresses made by one PDF click").toBe(1);
  expect(afterPdf[0].type).toBe("application/pdf");
  expect(afterPdf[0].size).toBeGreaterThan(1000);
  expect(decks).toEqual(["pdf"]);

  const [deck] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Slides (PowerPoint)" }).click()]);
  expect(deck.suggestedFilename()).toBe("TCS-deep-dive.pptx");
  await page.waitForTimeout(1000);
  expect((await blobs()).length - before).toBe(2);
  expect(decks).toEqual(["pdf", "pptx"]);
  expect(errors).toEqual([]);
});

test("/tour opens the tour on Home (it was Page not found)", async ({ page }, info) => {
  const u = as(1, info.project.name === "phone");
  const errors = await signIn(page, u, "/tour", "");
  const note = page.locator(".k-coach-note");
  await expect(note).toBeVisible({ timeout: 30_000 });
  await expect(note).toContainText("Four spaces");
  await expect(page).not.toHaveURL(/\/tour$/);
  await expect(page.getByText("Page not found")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("/tour signed out asks to sign in to see the tour, not Page not found", async ({ page }) => {
  await page.goto("/tour");
  await expect(page.getByText(/Sign in to see the tour/i).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Page not found")).toHaveCount(0);
});

/** Opens Market Watch's panel as this device keeps it: open, docked (a sheet on a phone, floating under 1600 px), on `list`. */
const panelOpen = (page: Page, u: Who, list: string | null = null) => page.addInitScript(([id, l]) => {
  localStorage.setItem(`stratlab.watch.layout.${id}`, JSON.stringify({ open: true, mode: "dock", w: 380, h: 560, x: null, y: null, list: l, sort: "custom", chart: null }));
}, [u.id, list] as const);

/** A dialog drawn over everything: at the end of the page (not inside what opened it), its dimmed page the whole window, and
 * its buttons the thing a click at their middle lands on, also where Market Watch's panel is. */
async function onTopOfAll(page: Page, name: string | RegExp, buttons: string[]) {
  const ask = page.getByRole("dialog", { name });
  await expect(ask).toBeVisible();
  const where = await ask.evaluate((d) => {
    const back = d.parentElement!;
    const r = back.getBoundingClientRect();
    const mw = document.querySelector("[data-testid=market-watch]")?.getBoundingClientRect();
    const hit = mw ? document.elementFromPoint(mw.left + mw.width / 2, mw.top + Math.min(40, mw.height / 2)) : null;
    return { parent: back.parentElement === document.body, full: r.width >= innerWidth - 1 && r.height >= innerHeight - 1,
      panel: mw ? (hit === back || back.contains(hit) ? "covered" : "on top") : "none" };
  });
  expect(where).toEqual({ parent: true, full: true, panel: expect.stringMatching(/covered|none/) });
  for (const b of buttons) {
    await ask.getByRole("button", { name: b, exact: true }).evaluate((el) => el.setAttribute("data-probe", "1"));
    expect(await onTop(page, "[data-probe='1']"), `${b} is the thing clicked`).toBe("self");
    await page.evaluate(() => document.querySelector("[data-probe='1']")?.removeAttribute("data-probe"));
  }
  return ask;
}

test("Instinct #11: the delete-confirm opened in Market Watch's panel is over the whole page, not held inside the panel", async ({ page, request }, info) => {
  const u = as(2, info.project.name === "phone");
  const got = await (await request.get(`${API}/watch/lists`, { headers: auth(u) })).json();
  for (const l of got.lists) if (!l.default) await request.delete(`${API}/watch/lists/${l.id}`, { headers: auth(u) });
  const made = await (await request.post(`${API}/watch/lists`, { headers: auth(u), data: { name: "R test layers" } })).json();
  const id = (made.lists ?? []).find((l: { name: string }) => l.name === "R test layers")?.id ?? made.id;
  expect(id).toBeTruthy();
  await panelOpen(page, u, id);
  const errors = await signIn(page, u, "/alerts", "Your alerts");
  // a phone never opens the sheet by itself on a page load: the top bar's Markets button does
  if (info.project.name === "phone") await page.getByRole("button", { name: "Markets", exact: true }).click();
  const mw = page.getByTestId("market-watch");
  await expect(mw).toBeVisible({ timeout: 30_000 });
  await mw.getByRole("button", { name: "Actions for the list R test layers" }).click();
  await mw.getByRole("menuitem", { name: "Delete the list" }).click();
  const ask = await onTopOfAll(page, "Delete the list R test layers?", ["Delete the list", "Cancel"]);
  await ask.getByRole("button", { name: "Delete the list" }).click();
  await expect(ask).toHaveCount(0);
  await expect.poll(async () => (await (await request.get(`${API}/watch/lists`, { headers: auth(u) })).json()).lists.length).toBe(1);
  expect(errors).toEqual([]);
});

test("Instinct #11: with the panel open, New alert and the assistant key's Revoke confirm take their own clicks", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  test.skip(phone, "on a phone the panel is a full-window sheet the person closes first");
  const u = as(3, phone);
  await page.setViewportSize({ width: 1280, height: 720 });       // a laptop: under 1600 px the panel floats over the page's corner
  const keys = await (await request.get(`${API}/me/assistant`, { headers: auth(u) })).json().catch(() => ({ keys: [] }));
  for (const k of keys.keys ?? []) if (!k.revoked_at) await request.delete(`${API}/me/assistant/keys/${k.id}`, { headers: auth(u) });
  expect((await request.post(`${API}/me/assistant/keys`, { headers: auth(u), data: { name: "R test layers", paper: false } })).ok()).toBeTruthy();
  await panelOpen(page, u);
  const errors = await signIn(page, u, "/alerts", "Your alerts");
  await expect(page.getByTestId("market-watch")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "New alert" }).click();
  const add = page.getByRole("dialog", { name: /New alert|Your alerts are full/ });
  await expect(add).toBeVisible();
  expect(await add.evaluate((d) => d.parentElement!.parentElement === document.body)).toBe(true);
  await add.getByRole("button", { name: "Close" }).click();
  await page.goto("/assistant");
  await page.getByRole("button", { name: "Revoke" }).first().click();
  const ask = await onTopOfAll(page, 'Revoke "R test layers"?', ["Revoke key", "Cancel"]);
  await ask.getByRole("button", { name: "Revoke key" }).click();
  await expect(ask).toHaveCount(0);
  await expect(page.getByText(/Revoked keys/)).toBeVisible();
  expect(errors).toEqual([]);
});
