import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { serious } from "./a11y-kit";
import { open, sane, session } from "./pages-kit";

// The Heatmap (L4), on desktop and phone against the fake world: the daily breadth run there stores each stock's changes, so the page
// draws real tiles. Every setting changes the picture without leaving the page; a tile opens its company; the Table view lists every
// company; a theme opens its own heatmap grouped by layer; before the first daily run the page says so plainly; light and dark.
const SHOTS = process.env.E2E_SHOTS;
const ADVICE = /\b(buy|sell|hold|accumulate|avoid|cheap|expensive|bullish|bearish|should)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|nseindia/i;
const THEME = "India steel and mining";

const tiles = (page: Page) => page.locator(".hm-map .hm-tile");
const controls = (page: Page) => page.getByTestId("hm-controls");
const seg = (page: Page, group: string, choice: string) => controls(page).getByRole("radiogroup", { name: group }).getByRole("radio", { name: choice, exact: true });

/** Every tile inside the map, none on top of another (the drawing is geometry: check it as drawn). */
async function tidy(page: Page) {
  const bad = await page.evaluate(() => {
    const map = document.querySelector(".hm-map")!.getBoundingClientRect();
    const boxes = Array.from(document.querySelectorAll(".hm-map .hm-tile")).map((el) => el.getBoundingClientRect());
    const out: string[] = [];
    boxes.forEach((b, i) => {
      if (b.left < map.left - 1 || b.top < map.top - 1 || b.right > map.right + 1 || b.bottom > map.bottom + 1) out.push(`tile ${i} outside the map`);
      for (let j = i + 1; j < boxes.length; j++) {
        const c = boxes[j];
        if (Math.min(b.right, c.right) - Math.max(b.left, c.left) > 1 && Math.min(b.bottom, c.bottom) - Math.max(b.top, c.top) > 1) out.push(`tiles ${i} and ${j} overlap`);
      }
    });
    return out.slice(0, 5);
  });
  expect(bad, "the map's tiles").toEqual([]);
}

test("the heatmap draws a market and every setting changes the picture in place", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/heatmap?region=IN", "Closes of");
  await expect(page.getByRole("heading", { level: 1, name: "Heatmap" })).toBeVisible();
  await expect(page.getByTestId("heatmap").getByRole("heading", { name: "NIFTY 500: 1 day" })).toBeVisible();
  const first = await tiles(page).count();
  expect(first, "tiles drawn").toBeGreaterThan(3);
  await tidy(page);
  await expect(page.getByTestId("hm-facts")).toContainText(/\d+ up, \d+ down/);
  await expect(page.locator(".hm-legend-step")).toHaveCount(8);                // seven steps and "no figure"
  await expect(page.locator(".hm-legend-step").first()).toHaveText("−3%");
  // a tile says its symbol and its figure in words, not by colour alone
  await expect(tiles(page).first().locator(".hm-sym")).toBeVisible();
  await expect(tiles(page).first()).toHaveAttribute("aria-label", /, [+−]?\d+\.\d%|, 0\.0%|, –/);
  await sane(page, errors);

  // period: the title, the legend's steps and the address follow, with no reload
  await controls(page).getByRole("button", { name: "1M", exact: true }).click();
  await expect(page.getByTestId("heatmap").getByRole("heading", { name: "NIFTY 500: 1 month" })).toBeVisible();
  await expect(page.locator(".hm-legend-step").first()).toHaveText("−12%");
  expect(new URL(page.url()).searchParams.get("p")).toBe("1m");

  // colour by volume: one blue scale, in multiples of the average
  await seg(page, "Colour by", "Volume").click();
  await expect(page.locator(".hm-legend-step").last()).toHaveText("no figure");
  await expect(page.locator(".hm-legend-step").nth(5)).toHaveText("3× and up");
  await expect(page.locator(".hm-map .hm-tile[class*='hm-u'], .hm-map .hm-tile[class*='hm-d']")).toHaveCount(0);
  await seg(page, "Colour by", "Vs index").click();
  await expect(page.locator(".hm-legend-step").first()).toHaveText("−12 pts");

  // size: equally sized tiles show every company, the ones with no market value on record too
  await seg(page, "Size by", "Equal").click();
  await expect.poll(() => tiles(page).count()).toBeGreaterThanOrEqual(first);
  await tidy(page);

  // grouping: sector name strips, or none
  await expect(page.locator(".hm-group-head").first()).toBeVisible();
  await seg(page, "Group by", "None").click();
  await expect(page.locator(".hm-group-head")).toHaveCount(0);
  await seg(page, "Group by", "Industry").click();
  await tidy(page);

  // search: the matching company stands out, the rest fade
  const symbol = (await page.locator(".hm-map .hm-sym").first().innerText()).trim();
  await page.getByLabel("Find a company").fill(symbol);
  await expect(page.locator(".hm-map .hm-tile.hit").first()).toBeVisible();
  await expect.poll(() => page.locator(".hm-map .hm-tile.off").count()).toBeGreaterThan(0);
  await page.getByLabel("Find a company").fill("");
  await expect(page.locator(".hm-map .hm-tile.off")).toHaveCount(0);

  if (!phone) {            // hover: the tile's own figures beside the pointer
    await tiles(page).first().hover();
    const tip = page.locator(".hm-tip");
    await expect(tip).toBeVisible();
    await expect(tip).toContainText("Last close");
    await expect(tip).toContainText("Market value");
    await page.mouse.move(2, 2);
  }
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
  await sane(page, errors);

  // the table lists every company, sorted by a column, each a link to its page
  await page.getByRole("radiogroup", { name: "Show as" }).getByRole("radio", { name: "Table" }).click();
  await expect(page.locator(".hm-map")).toHaveCount(0);
  const table = page.getByTestId("heatmap").locator("table, .k-tbl-wrap").first();
  await expect(table).toBeVisible();
  await expect(page.getByTestId("heatmap").getByRole("link").first()).toHaveAttribute("href", /^\/research\/IN\//);
  await sane(page, errors);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/heatmap-table-${info.project.name}.png`, fullPage: true });

  // back to the map: a tile opens its company
  await page.getByRole("radiogroup", { name: "Show as" }).getByRole("radio", { name: "Map" }).click();
  const href = await tiles(page).first().getAttribute("href");
  expect(href).toMatch(/^\/research\/IN\/.+/);
  await tiles(page).first().click();
  await expect(page).toHaveURL(new RegExp(href!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "$"));
});

test("the US market, the menu entry and the wait before the first daily run", async ({ page }, info) => {
  const errors = await open(page, "/invest/heatmap?region=US", "Closes of");
  await expect(page.getByTestId("heatmap").getByRole("heading", { name: /^(S&P 500|US large caps): 1 day$/ })).toBeVisible();
  expect(await tiles(page).count()).toBeGreaterThan(3);
  await expect(tiles(page).first()).toHaveAttribute("href", /^\/research\/US\//);
  await tidy(page);
  await sane(page, errors);
  // switching the market keeps the page and reads the other market's own group
  await controls(page).getByRole("radiogroup", { name: "Market" }).getByRole("radio", { name: /India/ }).click();
  await expect(page.getByTestId("heatmap").getByRole("heading", { name: "NIFTY 500: 1 day" })).toBeVisible();
  await expect(tiles(page).first()).toHaveAttribute("href", /^\/research\/IN\//);
  if (info.project.name === "desktop") {
    await expect(page.locator("nav, aside").getByRole("link", { name: /Market today/ }).first()).toBeVisible();
  }
  // before the first daily run has stored a market's rows: one plain sentence, no error and no empty box
  await page.route("**/invest/heatmap?*", async (r) => {
    const res = await r.fetch();
    await r.fulfill({ response: res, json: { ...(await res.json()), pending: true, tiles: [], as_of: null, shown: 0, matching: 0, with_prices: 0 } });
  });
  await page.goto("/invest/heatmap?region=IN");
  await expect(page.getByText("The heatmap fills in after the next market close")).toBeVisible();
  await expect(page.locator(".hm-map")).toHaveCount(0);
  await sane(page, errors);
});

test("a theme opens its own heatmap, its companies grouped by the layers of its chain", async ({ page }, info) => {
  test.setTimeout(120_000);
  const errors = await open(page, "/research/themes?region=IN&q=" + encodeURIComponent(THEME), "Download");
  const link = page.getByTestId("theme-heatmap").getByRole("link", { name: "Heatmap of this theme" });
  await expect(link).toBeVisible({ timeout: 60_000 });
  await link.click();
  await expect(page).toHaveURL(/\/invest\/heatmap\?theme=/);
  await expect(page.getByRole("heading", { level: 1, name: /^Heatmap: / })).toBeVisible({ timeout: 30_000 });
  await expect(controls(page).getByRole("radiogroup", { name: "Group by" }).getByRole("radio", { name: "Layer" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText(/Showing the companies of the theme/)).toBeVisible();
  // either the theme's tiles, or the plain line that none of its companies has stored closes
  const drawn = page.locator(".hm-map .hm-tile").first();
  const none = page.getByText("None of this theme's companies has stored closes yet");
  await expect(drawn.or(none).first()).toBeVisible({ timeout: 30_000 });
  if (await drawn.isVisible()) await tidy(page);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/heatmap-theme-${info.project.name}.png`, fullPage: true });
  await page.getByRole("link", { name: "See the whole market" }).click();
  await expect(page.getByTestId("heatmap").getByRole("heading", { name: "NIFTY 500: 1 day" })).toBeVisible();
  await sane(page, errors);
});

test("the heatmap in light and dark: every tile's words read on its colour, and axe finds nothing serious", async ({ browser }, info) => {
  test.setTimeout(180_000);
  const phone = info.project.name === "phone";
  const found: string[] = [];
  for (const scheme of ["light", "dark"] as const) {
    const ctx = await browser.newContext({ colorScheme: scheme, viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 1000 }, hasTouch: phone, isMobile: phone });
    const page = await ctx.newPage();
    await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
    for (const [name, path] of [["cap", "/invest/heatmap?region=IN"], ["map", "/invest/heatmap?region=IN&s=equal&p=1m"], ["volume", "/invest/heatmap?region=IN&c=volume&s=equal&g=none"]] as const) {
      const errors = await open(page, path, "Closes of");
      await expect(page.locator(".hm-map .hm-tile").first()).toBeVisible();
      // each tile's text against its own fill, as the browser drew it
      const low = await page.evaluate(() => {
        const lum = (c: string) => { const [r, g, b] = c.match(/[\d.]+/g)!.slice(0, 3).map((v) => { const x = Number(v) / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
        return Array.from(document.querySelectorAll(".hm-map .hm-tile, .hm-legend-step")).map((el) => {
          const s = getComputedStyle(el), a = lum(s.color), b = lum(s.backgroundColor);
          return { cls: el.className, ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) };
        }).filter((x) => x.ratio < 4.5).slice(0, 3);
      });
      expect(low, `${scheme}: words too faint on their tile`).toEqual([]);
      await sane(page, errors);
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
      found.push(...serious(r, `${path} [${scheme} ${info.project.name}]`));
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/heatmap-${name}-${scheme}-${info.project.name}.png`, fullPage: true });
    }
    await ctx.close();
  }
  expect(found, found.join("\n")).toEqual([]);
});
