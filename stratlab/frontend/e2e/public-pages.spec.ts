import { expect, test, type Page } from "@playwright/test";

// PUB-1: the pages the API draws (company pages, /stocks and its directories, the 404 page, the blog) are checked in a real browser at
// a phone's 390 px and at 1440 px, light and dark: no sideways scroll, no text under 12 px, a 44 px tap target on a phone for every button, link
// in a list and form control, body text at 4.5:1 or better against what it sits on; and the share-price chart a person can use: a range switch,
// the change above it, a crosshair with the date and the close (a tap on a phone), axis labels, and the figures as text.
// The pages' fonts are the site's, served by the web server (/fonts), as the host does.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const PAGES = ["/stocks", "/stocks/in", "/stocks/in/RELIANCE", "/stocks/us/AAPL", "/stocks/in/browse/r", "/stocks/in/index/nifty-50", "/stocks/in/NOSUCHCO", "/blog", "/blog/briefs"];

async function open(page: Page, path: string, web: string) {
  // fetched and handed back rather than continued to another origin: Chromium blocks a continued request whose host changes
  // (net::ERR_BLOCKED_BY_CLIENT in CI)
  await page.route("**/fonts/**", async (r) => {
    try { await r.fulfill({ response: await r.fetch({ url: web + new URL(r.request().url()).pathname }) }); }
    catch { /* the page was closed while a font was still on its way: nothing left to hand it to */ }
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(API + path, { waitUntil: "networkidle" });
  return errors;
}

/** The drawn page measured: sideways scroll, text under 12 px, tap targets under 44 px, and the lowest text contrast. */
async function measure(page: Page) {
  return page.evaluate(() => {
    const lum = (c: number[]) => { const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
    const parse = (s: string) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).map(Number); return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }; };
    const under = (el: Element) => { for (let e: Element | null = el; e; e = e.parentElement) { const b = parse(getComputedStyle(e).backgroundColor); if (b && b.a > 0.9) return b.rgb; } return [255, 255, 255]; };
    const shown = (el: Element) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && +s.opacity > 0.01; };
    const small: string[] = [], tiny: string[] = [], low: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const el = n.parentElement!;
      if (!n.textContent!.trim() || !shown(el) || el.closest("script,style,noscript,[hidden],.sr-only,.skip")) continue;
      const s = getComputedStyle(el), px = parseFloat(s.fontSize);
      if (px < 12) small.push(`${el.tagName}.${el.className} ${px}px "${n.textContent!.trim().slice(0, 30)}"`);
      const fg = parse(s.color), bg = under(el);
      if (fg) {
        const a = lum(fg.rgb) + 0.05, b = lum(bg) + 0.05, ratio = Math.max(a, b) / Math.min(a, b);
        if (ratio < 4.5) low.push(`${ratio.toFixed(2)} ${el.tagName}.${el.className} "${n.textContent!.trim().slice(0, 30)}"`);
      }
    }
    // what a finger taps: buttons, the menu and form controls, the nav and the footer's links, chips and list links (a link inside a sentence is exempt)
    for (const el of Array.from(document.querySelectorAll("button, summary, input, select, .btn, .nav a, footer a, .links a, ul.dir a, .tabs a, .pager a, .more a, a.post, .seg button"))) {
      if (!shown(el) || el.closest("[hidden]")) continue;
      const r = el.getBoundingClientRect();
      if (r.height < 43.5) tiny.push(`${el.tagName}.${(el as HTMLElement).className} ${Math.round(r.height)}px "${(el.textContent || "").trim().slice(0, 25)}"`);
    }
    return { sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth, small, tiny, low };
  });
}

for (const scheme of ["light", "dark"] as const) {
  test(`public pages: no sideways scroll, no small text, 44 px taps, readable contrast, on a phone (${scheme})`, async ({ browser, baseURL }, info) => {
    test.skip(info.project.name !== "desktop", "makes its own 390 px window");
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, colorScheme: scheme });
    const problems: string[] = [];
    for (const path of PAGES) {
      const page = await ctx.newPage();
      const errors = await open(page, path, baseURL!);
      const m = await measure(page);
      if (m.sideways > 0) problems.push(`${path}: scrolls sideways by ${m.sideways}px`);
      for (const x of m.small) problems.push(`${path}: text under 12px: ${x}`);
      for (const x of m.tiny) problems.push(`${path}: tap target under 44px: ${x}`);
      for (const x of m.low) problems.push(`${path}: contrast under 4.5: ${x}`);
      for (const x of errors.filter((e) => !(path.includes("NOSUCHCO") && /status of 404/.test(e)))) problems.push(`${path}: browser error: ${x}`);     // the 404 page is a 404
      await page.close();
    }
    await ctx.close();
    expect(problems).toEqual([]);
  });

  test(`public pages: the same on a desktop (${scheme})`, async ({ browser, baseURL }, info) => {
    test.skip(info.project.name !== "desktop", "one desktop pass");
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme });
    const problems: string[] = [];
    for (const path of PAGES) {
      const page = await ctx.newPage();
      await open(page, path, baseURL!);
      const m = await measure(page);
      if (m.sideways > 0) problems.push(`${path}: scrolls sideways by ${m.sideways}px`);
      for (const x of [...m.small, ...m.low]) problems.push(`${path}: ${x}`);
      await page.close();
    }
    await ctx.close();
    expect(problems).toEqual([]);
  });
}

test("company page: the share-price chart has a range switch, the change, a crosshair with the date and the close, and axis labels", async ({ browser, baseURL }, info) => {
  test.skip(info.project.name !== "desktop", "makes its own windows");
  for (const [w, h, touch] of [[1440, 900, false], [390, 844, true]] as const) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, hasTouch: touch });
    const page = await ctx.newPage();
    const errors = await open(page, "/stocks/in/RELIANCE", baseURL!);
    const card = page.locator("[data-chart]");
    // nothing is asked for until the chart is about to be seen (on a phone it is a long way down)
    if (touch) expect(await page.evaluate(() => performance.getEntriesByType("resource").filter((r) => r.name.includes("prices.json")).length)).toBe(0);
    await card.scrollIntoViewIfNeeded();
    await expect(card).toHaveAttribute("data-ready", "1", { timeout: 15_000 });
    const svg = card.locator(".plot svg");
    await expect(svg).toBeVisible();
    // the card's text before and after: the change above the chart, with its range
    await expect(card.locator("[data-change]")).toHaveText(/^(Up|Down) \d+\.\d%$|^Unchanged$/);
    await expect(card.locator("[data-change-note]")).toContainText("over 1 year");
    await expect(card.locator('.seg [aria-pressed="true"]')).toHaveText("1Y");
    // labelled axes: money on the left, dates along the bottom, at 12 px or more
    const ticks = await svg.locator("text").allTextContents();
    expect(ticks.filter((t) => /^[\d,.]+$/.test(t)).length).toBeGreaterThanOrEqual(3);
    expect(ticks.filter((t) => /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/.test(t)).length).toBeGreaterThanOrEqual(2);
    expect(await svg.locator("text").evaluateAll((els) => els.every((e) => parseFloat(getComputedStyle(e).fontSize) >= 12))).toBe(true);
    expect(await svg.getAttribute("aria-label")).toMatch(/^Share price over 1 year\. The close was ₹[\d,.]+ on \d+ \w+ \d{4} and ₹[\d,.]+ on \d+ \w+ 2026\. Highest close/);
    // the chart fits its card
    const [bw, cw] = await Promise.all([svg.boundingBox(), card.boundingBox()]);
    expect(bw!.width).toBeLessThanOrEqual(cw!.width);
    // a crosshair: a mouse over it, or a tap on a phone, shows the day and its close
    const at = { x: bw!.x + bw!.width * 0.6, y: bw!.y + bw!.height / 2 };
    if (touch) await page.touchscreen.tap(at.x, at.y); else await page.mouse.move(at.x, at.y);
    const tip = card.locator(".tip");
    await expect(tip).toBeVisible();
    await expect(tip).toContainText(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d+ \w+ \d{4}₹[\d,]+\.\d\d$/);
    const [tb, pb] = [await tip.boundingBox(), await card.locator(".plot").boundingBox()];
    expect(tb!.x).toBeGreaterThanOrEqual(pb!.x - 1);
    expect(tb!.x + tb!.width).toBeLessThanOrEqual(pb!.x + pb!.width + 1);               // the label stays inside the chart
    // the range switch redraws it, the change note follows, and 5 years is there
    for (const [r, words] of [["1m", "1 month"], ["6m", "6 months"], ["5y", "5 years"]] as const) {
      const before = await svg.getAttribute("aria-label");
      await card.locator(`.seg [data-r="${r}"]`).click();
      await expect(card.locator("[data-change-note]")).toContainText(`over ${words}`);
      await expect(card.locator('.seg [aria-pressed="true"]')).toHaveAttribute("data-r", r);
      expect(await card.locator(".plot svg").getAttribute("aria-label")).not.toBe(before);
      if (touch) expect((await card.locator(`.seg [data-r="${r}"]`).boundingBox())!.height).toBeGreaterThanOrEqual(43.5);
    }
    // the same closes as a table, and as words that don't need the picture
    await card.locator("summary").click();
    expect(await card.locator("[data-table] tbody tr").count()).toBeGreaterThanOrEqual(10);
    await expect(card.locator("[data-summary]")).toContainText("Highest close");
    // nothing said about the future
    expect((await card.innerText()).match(/\b(buy|sell|target|forecast|predict\w*|expected)\b/gi)).toBeNull();
    expect(errors).toEqual([]);
    await ctx.close();
  }
});

test("company page: revenue and profit columns show their figures on hover and focus, and the page has no script but its chart", async ({ browser, baseURL }, info) => {
  test.skip(info.project.name !== "desktop", "makes its own window");
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await open(page, "/stocks/in/RELIANCE", baseURL!);
  const cols = page.locator(".by-col");
  expect(await cols.count()).toBe(5);
  await expect(cols.nth(4).locator(".by-tip")).toBeHidden();
  await cols.nth(4).focus();
  await expect(cols.nth(4).locator(".by-tip")).toBeVisible();
  await expect(cols.nth(4).locator(".by-tip")).toContainText("Revenue");
  await expect(cols.nth(4).locator(".by-tip")).toContainText("9,64,693");
  expect(await page.locator("script[src]").evaluateAll((s) => s.map((x) => (x as HTMLScriptElement).getAttribute("src")!.split("?")[0]))).toEqual(["/stocks/chart.js"]);
  expect(await page.locator("script:not([src]):not([type='application/ld+json'])").count()).toBe(0);
  await ctx.close();
});
