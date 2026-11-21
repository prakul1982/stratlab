import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { API, MF, open, session, sessionAs, settle } from "./pages-kit";

// Centre alignment (owner, 20 Nov: "this is still not centre aligned, I told you to get everything centre aligned", Money > Mutual funds
// with a scheme open): every cell of a table row or a fold row sits on its row's vertical centre, a header over its column, and a fold's
// opened body has equal insets left and right, its tables as wide as the row above and ending at its right edge. Measured, so it holds on
// any machine and any fonts. ALIGN_SHOTS=<folder> also saves the pictures (the lane's before/after; never in CI).
const SHOTS = process.env.ALIGN_SHOTS;

/** What is off on the page now: one line per cell, row or body that misses by more than 2 px. */
export async function misaligned(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const TOL = 2;
    const name = (el: Element) => `${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/)[0] : el.tagName.toLowerCase()} "${(el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 30)}"`;
    const box = (el: Element) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 ? r : null; };
    const px = (v: string) => parseFloat(v) || 0;
    // the block a cell's contents make (their line boxes, as the cell centres them), not the cell's own box: a table cell is always the row's
    // height. Measured by wrapping them in a block for a moment (a range's box is the glyphs' only: a small note in a taller line read as off)
    const inner = (el: Element) => {
      const wrap = document.createElement("div");
      const kids = [...el.childNodes];
      kids.forEach((k) => wrap.appendChild(k));
      el.appendChild(wrap);
      const r = wrap.getBoundingClientRect();
      kids.forEach((k) => el.insertBefore(k, wrap));
      wrap.remove();
      return r.height > 0 ? r : null;
    };
    const shown = (el: Element) => { const s = getComputedStyle(el); return s.visibility !== "hidden" && s.display !== "none"; };

    // 1. fold rows and the fold header: cells side by side (their boxes overlap top to bottom) share one vertical centre
    for (const row of document.querySelectorAll(".k-fold-sum, .k-fold-head")) {
      if (!box(row) || !shown(row)) continue;
      const cells = [...row.children].filter((c) => shown(c) && box(c)).map((c) => ({ c, r: box(c)! }));
      for (let i = 0; i < cells.length; i++) {
        for (let j = i + 1; j < cells.length; j++) {
          const a = cells[i].r, b = cells[j].r;
          if (a.bottom <= b.top || b.bottom <= a.top) continue;                 // one under the other (a phone's second line): no pair
          const d = Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2);
          if (d > TOL) out.push(`fold row: ${name(cells[i].c)} and ${name(cells[j].c)} centres ${d.toFixed(1)} px apart`);
        }
      }
      // the chevron (the summary's ::after) on the row's centre
      if (row.classList.contains("k-fold-sum")) {
        const s = getComputedStyle(row, "::after");
        if (s.content && s.content !== "none" && s.position !== "absolute" && s.alignSelf !== "center") out.push(`fold row: chevron not centred (align-self ${s.alignSelf}) in ${name(row)}`);
        if (s.content && s.content !== "none" && s.position === "absolute") {
          const r = box(row)!;
          const h = px(s.height) + px(s.borderBottomWidth);
          const mid = px(s.top) + h / 2;
          if (Math.abs(mid - r.height / 2) > TOL) out.push(`fold row: chevron centre ${mid.toFixed(1)} px vs row centre ${(r.height / 2).toFixed(1)} px in ${name(row)}`);
        }
      }
    }
    // 2. table rows: each cell's contents on the cell's centre (allowing for unequal padding), header cells too
    for (const cell of document.querySelectorAll(".k-table tr > td, .k-table tr > th")) {
      if (!shown(cell) || cell.closest(".stack")) continue;                        // a phone's stacked card is a column, not a row
      const r = box(cell); const c = inner(cell);
      if (!r || !c || !(cell.textContent || "").trim()) continue;
      const s = getComputedStyle(cell);
      const mid = r.top + px(s.borderTopWidth) + px(s.paddingTop) + (r.height - px(s.borderTopWidth) - px(s.borderBottomWidth) - px(s.paddingTop) - px(s.paddingBottom)) / 2;
      const d = Math.abs((c.top + c.bottom) / 2 - mid);
      if (d > TOL) out.push(`table cell: ${name(cell)} ${d.toFixed(1)} px off its row's centre`);
    }
    // 3. a fold's opened body: equal insets, and its tables as wide as the row above it, ending at the same right edge
    for (const body of document.querySelectorAll(".k-fold-body")) {
      const det = body.closest("details"); const sum = det?.querySelector(":scope > summary");
      const b = box(body); const d = det && box(det); const sm = sum && box(sum);
      if (!b || !d || !sm || !sum) continue;
      const bs = getComputedStyle(body), ss = getComputedStyle(sum);
      const left = b.left + px(bs.paddingLeft) - d.left, right = d.right - (b.right - px(bs.paddingRight));
      if (Math.abs(left - right) > TOL) out.push(`fold body: insets ${left.toFixed(1)} px left, ${right.toFixed(1)} px right`);
      const rowL = sm.left + px(ss.paddingLeft), rowR = sm.right - px(ss.paddingRight);
      if (getComputedStyle(sum, "::after").position === "absolute") continue;      // a phone's card keeps room for its chevron at the right
      for (const t of body.querySelectorAll(".k-tbl-wrap")) {
        const tr = box(t);
        if (!tr || t.parentElement?.closest(".k-tbl-wrap")) continue;
        if (Math.abs(tr.left - rowL) > TOL || Math.abs(tr.right - rowR) > TOL) out.push(`fold body: table ${tr.left.toFixed(0)}-${tr.right.toFixed(0)} vs the row above ${rowL.toFixed(0)}-${rowR.toFixed(0)}`);
      }
    }
    // 4. (owner, 20 Nov) a table never wider than its box at a desktop width: no sideways scroll and no column cut off (Mutual funds'
    // "Redemptions matched to purchases" and the capital gains "Kind" table at 1000px); a grid read across on purpose (data-grid) is left out
    if (document.documentElement.clientWidth > 720) {
      for (const w of document.querySelectorAll("main .k-tbl-wrap")) {
        if (!box(w) || !shown(w) || w.hasAttribute("data-grid") || w.closest("details:not([open]) > :not(summary)")) continue;
        const he = w as HTMLElement;
        if (he.scrollWidth > he.clientWidth + 1) out.push(`table wider than its box: "${(w.querySelector("table")?.getAttribute("aria-label") || w.getAttribute("aria-label") || "").slice(0, 40)}" ${he.scrollWidth} in ${he.clientWidth} px`);
      }
    }
    return out;
  });
}

/** The page column's gutters beside the menu (desktop): [left, right] in px. */
async function gutters(page: Page): Promise<[number, number]> {
  return page.evaluate(() => {
    const main = document.querySelector("main")!;
    const side = document.querySelector(".side, aside, nav[aria-label='Pages']");
    const col = [...main.querySelectorAll(":scope > *")].map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0).sort((a, b) => b.width - a.width)[0];
    const from = side ? side.getBoundingClientRect().right : 0;
    return [Math.round(col.left - from), Math.round(document.documentElement.clientWidth - col.right)];
  });
}

async function shot(page: Page, file: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: `${SHOTS}/${file}.png`, fullPage: true });
}

test.describe("centre alignment", () => {
  test("Mutual funds with a scheme open: fold rows centred, the body's insets equal, its tables the row's width", async ({ page, request }, info) => {
    test.setTimeout(150_000);
    const phone = info.project.name === "phone";
    const [token, id, email] = phone ? ["site83-1", "u-site83-1", "site831@example.com"] : ["site83-0", "u-site83-0", "site830@example.com"];
    expect((await request.delete(`${API}/money/mutual-funds`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
    if (!phone) await page.setViewportSize({ width: 1000, height: 900 });        // the owner's Safari window
    await open(page, "/money/mutual-funds", "Your mutual funds, in one place", sessionAs(token, id, email));
    await settle(page);
    await page.locator("input[type=file]").setInputFiles(MF + "synthetic_cas.pdf");
    await page.getByLabel("PDF password").fill("ABCDE1234F");
    await page.getByRole("button", { name: "Read my funds" }).click();
    await expect(page.getByText(/transactions and .* stamp duty or tax lines added/)).toBeVisible({ timeout: 60_000 });
    const fold = page.getByRole("button", { name: /^Your schemes/ });
    if ((await fold.getAttribute("aria-expanded")) === "false") await fold.click();
    const flexi = page.getByRole("list", { name: "Schemes" }).getByRole("listitem").filter({ hasText: "Example Flexi Cap Fund" });
    await flexi.locator("summary").click();
    await expect(flexi.getByText("What you hold")).toBeVisible();
    await page.waitForTimeout(800);
    await flexi.scrollIntoViewIfNeeded();
    await shot(page, `mutual-funds-${info.project.name}`);
    expect(await misaligned(page)).toEqual([]);
    if (!phone) {
      for (const w of [1000, 1280, 1600]) {
        await page.setViewportSize({ width: w, height: 900 });
        await page.waitForTimeout(300);
        expect(await misaligned(page), `at ${w}px`).toEqual([]);
        const [l, r] = await gutters(page);
        expect(Math.abs(l - r), `the page column's gutters beside the menu at ${w}px: ${l} and ${r}`).toBeLessThanOrEqual(2);
      }
    }
  });

  // LIVE21B-012 (site85): the check above missed the tax report's sales live (738 px in a 548 px box at 1000 px; "Bought" cut at 1280 with More
  // columns on) because it measured only at 1280, with the owner's short symbols, and never with More columns turned the other way. This is
  // exactly the reviewer's case: a fund's long name, at 1000, 1280 and 1600 px, More columns on and off; nothing wider than its box, nothing cut.
  test("tax report: the sales fit their card at 1000, 1280 and 1600 px, More columns on and off, with a fund's long name", async ({ page, request }, info) => {
    test.skip(info.project.name === "phone", "desktop widths");
    test.setTimeout(150_000);
    const token = "site85-0", h = { Authorization: `Bearer ${token}` };
    expect((await request.delete(`${API}/tax`, { headers: h })).ok()).toBeTruthy();
    const csv = ["Date,Symbol,Type,Quantity,Price",
      "2023-04-10,PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN - GROWTH,BUY,1250,52.35", "2025-05-10,PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN - GROWTH,SELL,1250,84.6",
      "2024-01-10,RELIANCE,BUY,40,1210.5", "2025-06-10,RELIANCE,SELL,40,1488.2",
      "2025-01-02,ICICIBANK,BUY,120,1270", "2025-08-01,ICICIBANK,SELL,120,1431.75"].join("\n") + "\n";
    const r = await request.post(`${API}/tax/import?filename=trades.csv`, { headers: { ...h, "Content-Type": "application/octet-stream" }, data: Buffer.from(csv) });
    expect(r.ok()).toBeTruthy();
    await page.setViewportSize({ width: 1000, height: 900 });
    await open(page, "/tax-report", "Capital gains on your shares", sessionAs(token, "u-site85-0", "site850@example.com"));
    await settle(page);
    await page.getByRole("combobox", { name: "Financial year" }).selectOption("2025");
    const sales = page.locator(".k-tbl-wrap").filter({ has: page.getByRole("table", { name: "Realised sales" }) });
    await expect(sales.getByText(/PARAG PARIKH/)).toBeVisible();
    const more = page.getByTestId("cols-tax-sales");
    const cut = () => sales.evaluate((w) => {
      const box = w.getBoundingClientRect(), out: string[] = [];
      if (w.scrollWidth > w.clientWidth + 1) out.push(`table ${w.scrollWidth} px in its ${w.clientWidth} px box`);
      for (const c of w.querySelectorAll("th, td")) {
        const r = c.getBoundingClientRect();
        if (r.width && (r.right > box.right + 1 || r.left < box.left - 1)) out.push(`"${(c.textContent || "").trim().slice(0, 20)}" runs ${Math.round(r.left)}-${Math.round(r.right)} past ${Math.round(box.left)}-${Math.round(box.right)}`);
      }
      // the long name: two lines at most, and all of it in its title
      const n = w.querySelector(".tax-name") as HTMLElement | null;
      if (!n || !/PARAG PARIKH FLEXI CAP FUND/.test(n.title)) out.push("the name's title");
      else if (n.getBoundingClientRect().height > 2 * parseFloat(getComputedStyle(n).lineHeight) + 1) out.push(`the name takes ${Math.round(n.getBoundingClientRect().height)} px`);
      return out;
    });
    for (const w of [1000, 1280, 1600]) {
      await page.setViewportSize({ width: w, height: 900 });
      for (const on of [false, true]) {
        if ((await more.getAttribute("aria-pressed")) !== String(on)) await more.click();
        await page.waitForTimeout(400);
        await sales.scrollIntoViewIfNeeded();
        await shot(page, `tax-sales-${w}-${on ? "more" : "fewer"}`);
        expect(await cut(), `at ${w}px, More columns ${on ? "on" : "off"}`).toEqual([]);
        expect(await misaligned(page), `at ${w}px, More columns ${on ? "on" : "off"}`).toEqual([]);
      }
    }
    // every figure still there: the purchase day under the sale's with More columns on, the cost under the sale amount
    await expect(sales.getByText("bought 10 Apr 2023")).toBeVisible();
    await expect(sales.getByText(/^cost ₹65,4\d\d/)).toBeVisible();
  });

  for (const [path, ready, file] of [["/holdings", "My Holdings", "holdings"], ["/money/net-worth", "Net worth", "net-worth"], ["/tax-report", "Capital gains on your shares", "tax-report"]] as const) {
    test(`${file}: every table row and fold row centred`, async ({ page }, info) => {
      if (info.project.name !== "phone") await page.setViewportSize({ width: 1280, height: 900 });
      await open(page, path, ready, session);
      await settle(page);
      await page.waitForTimeout(1500);
      await shot(page, `${file}-${info.project.name}`);
      expect(await misaligned(page)).toEqual([]);
    });
  }
});
