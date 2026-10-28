// 25 Oct 2026, the deep audit of search, navigation, My space, the tour, Help, Get the app and the briefs (DI-001 .. DI-033):
// Indian companies found with the feed off, companies above "Do it", page names matched as words with room for a typo, one
// home for "What you see first", one current page in the menu, Help with a way in, My space in the chosen order and on the
// account, and the briefs' own pages.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const rank = await import("../src/lib/paletteRank.ts");
const { match, oneTypo, OWN_PAGES } = await import("../src/lib/features.ts");
const { slotSpans, cleanLayout } = await import("../src/lib/mineLayout.ts");
const { resultsLine } = await import("../src/lib/mineLayout.ts");
const { startView, homeOf } = await import("../src/lib/spaces.ts");
const nav = await import("../src/lib/nav.ts");

test("DI-001: the box's companies come from the live search and the company directory, one row each, best match first", () => {
  // the feed off: the instrument search has only the US listings; the directory has the NSE company
  const insts = [{ symbol: "RS", name: "Reliance, Inc.", market: "US", type: "EQ" }, { symbol: "EZRA", name: "Reliance Global Group", market: "US", type: "EQ" }];
  const sugg = [{ symbol: "RELIANCE", id: "RELIANCE", name: "Reliance Industries Ltd", exchange: "NSE", market: "IN", match: 0 }];
  const hits = rank.companyHits(insts, sugg);
  assert.equal(hits[0].symbol, "RELIANCE");
  assert.equal(hits[0].to, "/research/IN/RELIANCE");
  assert.equal(hits.length, 3);
  // the same company from both lists is one row, with the better of the two matches
  const twice = rank.companyHits([{ symbol: "TCS", market: "IN", type: "EQ", match: 2 }], [{ symbol: "TCS", id: "TCS", name: "Tata Consultancy Services", exchange: "NSE", market: "IN", match: 0 }]);
  assert.equal(twice.length, 1);
  assert.equal(twice[0].match, 0);
  assert.equal(twice[0].name, "Tata Consultancy Services");
  // a company only on BSE opens by its code; indices, coins and contracts are not companies
  assert.equal(rank.companyHits([], [{ symbol: "TINYCO", id: "543210", name: "Tiny Co", exchange: "BSE", market: "IN", match: 1 }])[0].to, "/research/IN/543210");
  assert.equal(rank.companyHits([{ symbol: "NIFTY 50", market: "IN", type: "INDEX" }, { symbol: "TCS26OCTFUT", market: "IN", type: "FUT", fno: true }], []).length, 0);
  const pal = read("src/components/SearchPalette.tsx");
  assert.match(pal, /\/suggest\/companies\?ranked=true&q=/);
  assert.match(pal, /void suggestCompanies\(lookup\)\.then\(\(r\) => \{ if \(n === asked\.current\) setSuggested\(r\); \}\);/);
  // deep dive and compare fall back to the directory too
  assert.match(pal, /const s = \(await suggestCompanies\(name\)\)\[0\];/);
});

test("DI-002: a company found is put before the AI's Do it", () => {
  const co = [{ key: "IN:INFY", symbol: "INFY", market: "IN", match: 9, to: "/research/IN/INFY" }];
  assert.equal(rank.companyFirst({ companies: co, words: 1, firstGroup: "Do", intent: false }), true);
  assert.equal(rank.companyFirst({ companies: co, words: 4, firstGroup: "Do", intent: false }), false);         // a sentence: the AI first
  assert.equal(rank.companyFirst({ companies: [{ ...co[0], match: 1 }], words: 4, firstGroup: "Do", intent: false }), true);
  assert.equal(rank.companyFirst({ companies: co, words: 1, firstGroup: "Features", intent: false }), false);  // a page named first stays first
  assert.equal(rank.companyFirst({ companies: co, words: 1, firstGroup: "Do", intent: true }), false);
  assert.equal(rank.companyFirst({ companies: [], words: 1, firstGroup: "Do", intent: false }), false);
  assert.match(read("src/components/SearchPalette.tsx"), /if \(lead !== "ai" && companyFirst\(\{ companies, words, firstGroup: out\[0\]\?\.group, intent: !!intent \}\)\) first\("Companies"\);/);
});

test("DI-003: pages are matched by their words, with room for a typo; Contact, Help, Theme and Sign out are found; no ideas for a page", () => {
  assert.equal(match("sign out", 5)[0].title, "Sign out");
  assert.ok(!match("sign out", 5).some((f) => /signal/i.test(f.title)), "sign is not signal");
  assert.equal(match("dark mode", 5)[0].id, "theme");
  assert.equal(match("contact", 5)[0].id, "contact");
  assert.equal(match("help", 5)[0].id, "help");
  assert.equal(match("setings", 5)[0].title, "Settings");
  assert.equal(match("invoice", 5)[0].title, "Account");
  assert.equal(match("walk forward", 1)[0].id, "walkforward");
  assert.ok(oneTypo("relaince", "reliance") && oneTypo("setings", "settings") && !oneTypo("signal", "sign"));
  assert.ok(OWN_PAGES.includes("settings") && OWN_PAGES.includes("signout"));
  assert.equal(rank.offerIdeas("settings", { features: 1, companies: 0, helps: 0, intent: false, page: true }), false);
  assert.equal(rank.offerIdeas("momentum", { features: 2, companies: 0, helps: 0, intent: false, page: false }), true);
  const pal = read("src/components/SearchPalette.tsx");
  assert.match(pal, /if \(f\.to === "@signout"\)/);
  assert.match(read("src/pages/SettingsPage.tsx"), /theme: "experience"/);         // /settings#theme opens the theme
});

test("DI-004: a phone gets a close button in search and no Ctrl K hint in the menu", () => {
  assert.match(read("src/components/SearchPalette.tsx"), /className="icon-btn palette-x" aria-label="Close search" onClick=\{close\}/);
  const css = read("src/styles.css");
  assert.match(css, /@media \(hover: none\) and \(pointer: coarse\), \(max-width: 640px\) \{\n  \.palette \.palette-x \{ display: inline-flex; \}\n  \.search-btn kbd, \.palette \.esc-hint \{ display: none; \}/);
});

test("DI-005: My space's cards are drawn in the chosen order, each row filled", () => {
  assert.deepEqual(slotSpans(["networth", "pnl", "paper", "markets", "coming", "watch"]), { networth: 4, pnl: 4, paper: 4, markets: 12, coming: 7, watch: 5 });
  // Markets moved up twice: Net worth gets the first row, Markets the next, and P&L and Paper share one
  assert.deepEqual(slotSpans(["networth", "markets", "pnl", "paper", "coming", "watch"]), { networth: 12, markets: 12, pnl: 6, paper: 6, coming: 7, watch: 5 });
  for (const order of [["watch", "networth", "coming"], ["pnl"], ["coming", "pnl", "paper", "networth"]]) {
    const s = slotSpans(order);
    let row = 0;
    for (const id of order) { row += s[id]; if (row === 12) row = 0; assert.ok(row < 12, order.join()); }
    assert.equal(row, 0, `${order.join()} leaves a gap`);
  }
  const css = read("src/styles.css");
  assert.doesNotMatch(css, /\.mine-grid \{[^}]*grid-auto-flow: dense/);
  assert.match(css, /\.mine-slot\[data-span="6"\] \{ grid-column: span 6; \}/);
  assert.match(read("src/pages/MineHome.tsx"), /data-span=\{spans\[id\]\}/);
});

test("DI-006: the layout is kept on the account", () => {
  const mine = read("src/pages/MineHome.tsx");
  assert.match(mine, /const saved = me\?\.prefs\?\.mine;/);
  assert.match(mine, /const change = \(next: Layout\) => \{ setRaw\(next\); void savePrefs\(\{ mine: next \}, true\); \};/);
  assert.match(mine, /It is kept with your account, so your phone and laptop show the same My space\./);
  assert.deepEqual(cleanLayout({ order: ["markets", "x"], hidden: ["watch"] }).order.slice(0, 2), ["markets", "networth"]);
});

test("DI-007: the holdings tile says the prices are missing when the buy prices are there", () => {
  const src = read("src/pages/SpaceHomes.tsx");
  assert.match(src, /if \(t\.priced === 0 && noCost < t\.count\) return "Needs today's prices, not in yet";/);
  assert.match(src, /missing=\{gainMissing\(h\.totals\)\}/);
});

test("DI-009: a results day reads the same whichever calendar it came from, and the rest are counted", () => {
  assert.deepEqual(resultsLine("AAVAS", "Financial Results/Other business matters"), { title: "AAVAS results", detail: "Among your stocks · Other business matters" });
  assert.deepEqual(resultsLine("BHARATCOAL", null, "after market"), { title: "BHARATCOAL results", detail: "Among your stocks · after market" });
  assert.equal(resultsLine("TCS", "Financial Results").detail, "Among your stocks");
  assert.match(read("src/pages/MineHome.tsx"), /\+\{more\} more in the calendar/);
});

test("DI-010, DI-011, DI-012: the markets' period and colours in words, India's date says so, and the polish", () => {
  const mine = read("src/pages/MineHome.tsx");
  assert.match(mine, /Each line is the last month of daily closes/);                   // VR1-002: in the (i), with the colours, not a paragraph under the title
  assert.match(mine, /" in India" : ""/);
  assert.match(mine, /whole\.length >= 3 \? <Spark/);
  assert.match(mine, /<label className="k-check"><input type="checkbox"/);
  assert.ok(mine.indexOf("<CustomisePanel") < mine.indexOf("<PromoCountdown /><FirstSteps />"), "Customise opens above the first steps");
  assert.match(read("src/styles.css"), /\.mine-slot \.k-state \{ border: 0;/);
});

test("DI-013: `/` opens one home: What you see first, else the account's choice, else My space", () => {
  assert.equal(startView("both", "money"), "mine");
  assert.equal(startView("money", "trade"), "money");
  assert.equal(startView(null, "invest"), "invest");
  assert.equal(startView(null, "all"), "mine");
  assert.equal(startView(null, null), "mine");
  assert.equal(homeOf(startView("trade")), "/trade");
  assert.match(read("src/pages/SpaceHomes.tsx"), /<Navigate to=\{homeOf\(startView\(me\?\.prefs\?\.focus, me\?\.prefs\?\.space\)\)\} replace \/>/);
  assert.match(read("src/components/LevelPrompt.tsx"), /"Every space side by side, starting on My space\."/);
});

test("DI-014, DI-022: Help in the account menu opens the Help page, which lists every explanation; the tour is its own item", () => {
  const menu = read("src/components/SideMenus.tsx");
  assert.match(menu, /<Link role="menuitem" to="\/help" onClick=\{done\(onGo\)\}><Help size=\{16\} \/>Help<\/Link>/);
  assert.match(menu, /<Compass size=\{16\} \/>Take the tour<\/button>/);
  assert.match(menu, /<Gear size=\{16\} \/>Settings/);
  assert.match(menu, /<User size=\{16\} \/>Account<\/Link>/);                                // the plan is named once, on Plan
  const help = read("src/pages/AppGates.tsx");
  assert.match(help, /HELP_TOPICS\.filter/);
  assert.match(help, /<summary>\{h\.title\}<\/summary>/);
});

test("DI-015: All features lists the account's pages and each space's home", () => {
  const p = read("src/pages/NavPages.tsx");
  for (const to of ["/settings", "/account", "/plans", "/invite", "/app", "/assistant", "/help", "/contact", "/settings#accounts"]) assert.match(p, new RegExp(`\\{ to: "${to}"`), to);
  assert.match(p, /\{s\.label\} home<\/b>/);
  assert.doesNotMatch(p, /Bring in your broker's file: the stocks you hold\./);
});

test("DI-016: a menu link with its own rule for 'here' is marked by that rule alone", () => {
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /: <Link key=\{to\} to=\{to\} title=\{title\} className=\{active \? "active" : undefined\} aria-current=\{active \? "page" : undefined\}>/);
  assert.doesNotMatch(shell, /"aria-current": active \? "page" as const : false/);
  assert.equal(nav.locate("/research/investor").page.to, "/research/watchlist");
  assert.equal(nav.locate("/research/watchlist").page.to, "/research/watchlist");
});

test("DI-017, DI-018, DI-019: two kinds of alerts named apart; My space's menu has the everyday pages; trails and titles", () => {
  assert.equal(nav.pageAt("/alerts").page.label, "Stock alerts");
  assert.match(read("src/components/AlertSettings.tsx"), /title="Paper-trade alerts and the daily report"/);
  const shell = read("src/components/Shell.tsx");
  for (const t of ['"Watchlist"', '"Stock alerts"', '"Settings"']) assert.ok(shell.includes(t), t);
  assert.match(shell, /me\?\.plan_info\?\.features\?\.assistant !== false && item\("\/assistant"/);
  const crumb = read("src/components/PageBreadcrumb.tsx");
  assert.match(crumb, /"\/plans": "Plans", "\/help": "Help", "\/features": "All features"/);
  assert.match(crumb, /if \(mine && MINE_LINKED\.includes\(page\.to\)\)/);
  assert.match(read("src/lib/title.ts"), /"\/assistant": "Connect an AI assistant"/);
  for (const f of ["src/pages/SettingsPage.tsx", "src/pages/InvitePage.tsx", "src/pages/AppPage.tsx", "src/pages/AssistantPage.tsx"]) assert.doesNotMatch(read(f), /<PageHeader eyebrow=/, f);
});

test("DI-021, DI-023: the phone's top button and the tour follow the space; on a phone the tour opens the menu", () => {
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /aria-label=\{main\.label\} title=\{main\.label\} onClick=\{\(\) => nav\(main\.to\)\}/);
  assert.match(shell, /useDialogFocus\(aside, open && !tourMenu,/);
  const tour = read("src/components/Tour.tsx");
  assert.match(tour, /`\.topbar \[aria-label='\$\{main\}'\]`/);
  assert.match(tour, /\{ title: "Four spaces", at: \[".sidebar .space-switch"\], menu: true,/);
  assert.match(tour, /Dark mode is in Settings → Experience\./);
  assert.doesNotMatch(tour, /your name at the bottom opens your plan, settings and dark mode/);
});

test("DP2-032 / DP1-028: closing the welcome question starts no tour", () => {
  assert.match(read("src/components/LevelPrompt.tsx"), /onClose=\{\(\) => onDone\(savePrefs\(\{ focus: focus \?\? "both", level: lvl \}\), false\)\}/);
  assert.match(read("src/components/Onboarding.tsx"), /setWelcomed\(answered\)/);
});

test("DI-025..028: the briefs page goes to the issue picked, has older issues, the holiday-aware close and short tabs on a phone", () => {
  const p = read("src/pages/NewsPage.tsx");
  assert.match(p, /pane\.current\?\.scrollIntoView\(\{ block: "start", behavior: scrollBehavior\(\) \}\)/);
  assert.match(p, />Show older issues<\/button>/);
  assert.match(p, /day: issue\.close_day \?\? issue\.day/);
  assert.match(p, /\["IN", "Market brief: India", "India"\]/);
  assert.match(read("src/components/kit/Seg.tsx"), /<span className="k-seg-short" aria-hidden="true">\{o\.short\}<\/span>/);
});

test("DI-029, DI-031, DI-033: install steps for every phone and signed out; badges only for what is locked; landing addresses' own headings", async () => {
  const steps = read("src/components/InstallSteps.tsx");
  assert.match(steps, /tap Share/);
  assert.match(steps, /Copy the link/);
  assert.doesNotMatch(read("src/components/PhoneCard.tsx"), /notifications without Telegram/);
  assert.match(read("src/pages/Gate.tsx"), /=== "\/app"\) return \(/);
  const { signedOutTitle } = await import("../src/lib/title.ts");
  assert.equal(signedOutTitle("/app"), "Get the app · StratLab");
  assert.equal(signedOutTitle("/features"), "What StratLab does · StratLab");
  assert.match(read("src/components/PageTags.tsx"), /const tag = got && \(got\.locked \|\| got\.label !== \(plan === "pro" \? "Pro" : "Basic"\)\) \? got : null;/);
  const seo = await import("../src/content/seo.ts");
  assert.equal(seo.landingIntro("/help"), seo.pageMeta("/help").description);
  assert.equal(seo.landingIntro("/"), undefined);
});
