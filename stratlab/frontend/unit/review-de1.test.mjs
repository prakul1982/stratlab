// Deep audit DE (24 Oct 2026): the scan and market-view pages — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("DE-001/DE-002: a scan read on the last close says so, and an offline answer offers no pointless Try again", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /st2\.last_close && <p className="k-note" data-testid="scan-last-close">/);
  assert.match(s, /setScanOffline\(\(err as Error & \{ code\?: string \}\)\.code === "data_offline"\)/);
  assert.match(s, /action=\{scanOffline \? undefined : \{ label: "Try again"/);
});

test("DE-003: every group's Stage 2 + Supertrend scan shows the same stats, with the stocks checked", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /<Stat label="Stocks checked"/);
  assert.match(s, /st2\.counts\.stage2 != null && <Stat label="In Stage 2 only"/);
});

test("DE-004/DE-035: on a phone the scan's and the red flags' rows are cards that lead with the signal or the flag", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /\{ key: "sg", header: "Signal", lead: true,/);
  assert.match(s, /\{ key: "f", header: "Flag", wrap: true, lead: true,/);
  assert.match(s, /<DataTable stack label="Red-flag filings, newest first"/);
  assert.match(s, /<DataTable stack phonePage=\{25\} label=\{`\$\{st2\.name\}: stage and Supertrend`\}/);
  const css = read("src/styles.css");
  assert.match(css, /\.k-tbl-wrap\.stack\.has-lead \.k-table td\.k-lead \{ order: -1; grid-column: 1 \/ -1; \}/);
  assert.match(read("src/components/kit/DataTable.tsx"), /c\.lead && "k-lead"/);
});

test("DE-007/DE-008: the group picker spans the row; the alert switch confirms and warns when nothing reaches you", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /<Field label="Group to scan" wide>/);
  assert.match(s, /Set up a phone, Telegram or a confirmed email in Settings for it to reach you/);
  assert.match(s, /data-testid="scan-alert-nowhere"/);
});

test("DE-010/DE-011/DE-012: an impossible range is said, the filtered column shows, the boxes line up", () => {
  const s = read("src/pages/Screens.tsx");
  assert.match(s, /bad\.add\(`\$\{k\}\.order`\)/);
  assert.match(s, /"At least" is above "at most": no company can meet this\./);
  assert.match(s, /setError\(\(e as Error\)\.message\); setOut\(null\); setRows\(\[\]\);/);
  assert.match(s, /c\.key === sort \|\| filtered\.has\(c\.key\)/);
  assert.match(s, /placeholder="Like: Low debt"/);
  assert.match(s, /data-testid="screens-no-value"/);
  assert.match(read("src/styles-invest.css"), /grid-template-columns: minmax\(0, 1fr\) minmax\(0, 1fr\) 2\.75rem/);
});

test("DE-013: the theme page names no unlisted company and shows the exchange's list for the industries", () => {
  const s = read("src/pages/Research.tsx");
  assert.doesNotMatch(s, /\(not listed\)/);
  assert.match(s, /On the exchange's list for these industries/);
  assert.match(s, /with no figures: there's no source here to check a budget, size or growth rate against/);
});

test("DE-017: index cards show the level to two decimals and keep the 52-week phrase on one line; repeats say so", () => {
  const s = read("src/pages/Research.tsx");
  assert.match(s, /minimumFractionDigits: 2, maximumFractionDigits: 2/);
  assert.match(s, /<span className="nowrap">\{i\.from_high_pct > -0\.5/);
  assert.match(read("src/components/Research.tsx"), /n\.similar \? `\$\{n\.similar\} similar/);
});

test("DE-018/DE-019/DE-020/DE-021: rotation's weeks, its units, its heading and its phone labels", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /useAnimate\(out \? Math\.max\(1, \.\.\.out\.rows\.map\(\(r\) => r\.points\.length\)\) : tail\)/);
  assert.match(s, /not 2\.79% stronger/);
  assert.match(s, /Heading is the way its dot moved in the last \{unit\}/);
  const r = read("src/components/Rotation.tsx");
  assert.doesNotMatch(r, /if \(phone && h\.id !== first\) continue;/);
  assert.match(r, /const name = phone && h\.id !== first \? shortName\(h\.name\) : h\.name;/);
});

test("DE-022: one Table switch per breadth chart, a zoom hint on every zoomable chart, and a capped TRIN spike", async () => {
  const s = read("src/pages/BreadthPage.tsx");
  assert.equal((s.match(/<PairBars [^>]*table=\{false\}/g) || []).length, 2);
  assert.match(read("src/components/chart/XYChart.tsx"), /p\.table !== false \|\| zoomable;/);
  const { spikeCap } = await import("../src/lib/breadth.ts");
  const trin = [...Array(60)].map((_, i) => 0.8 + (i % 5) * 0.1);
  assert.equal(spikeCap(trin), null);                                 // nothing stands out: drawn as it is
  const cap = spikeCap([...trin, 9.8]);
  assert.ok(cap != null && cap >= 3 && cap < 9.8, String(cap));
});

test("DE-023/DE-024: the headline card's notes, the sector table's small sectors and the alert level's reason", () => {
  const s = read("src/pages/BreadthPage.tsx");
  assert.match(s, /20\\u2011day/);
  assert.match(s, /: the same \$\{count\(x\.prev\)\}/);
  assert.match(s, /An earlier day's count was revised/);
  assert.match(s, /data-testid="breadth-small-sectors"/);
  assert.match(s, /data-testid="breadth-alert-why"/);
  assert.match(s, /read its direction, not its level against another group's/);
});

test("DE-026/DE-027: results are listed day by day with each day's count, and a long day opens in full", () => {
  const s = read("src/pages/ResultsPage.tsx");
  assert.match(s, /export function dayHeading/);
  assert.match(s, /onClick=\{\(\) => setOpenDay\(d\)\}>Show all/);
  assert.doesNotMatch(s, /And \{data\.more\} more\./);
});

test("DE-028/DE-029/DE-031: dividends ahead in the US, a distribution's parts, the ex-date said once", () => {
  const p = read("src/pages/CorpActionsPage.tsx");
  assert.doesNotMatch(p, /Only ex-dates that have already happened are available for the US/);
  assert.doesNotMatch(p, /in India it's also the record date/);
  assert.match(p, /<ActionLine key=\{r\.id\} a=\{r\} showEx=\{false\} \/>/);
  assert.match(p, /placeholder=\{region === "IN" \? "Like TCS or Infosys" : "Like AAPL or Apple"\}/);
  assert.match(read("src/components/CorpActions.tsx"), /dividend: "Dividends and distributions"/);
});

test("DE-032/DE-036: red flags from the evening's read for a company that didn't answer, one tab name in both markets", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /r\.stored && <Badge tone="plain">From the evening's read/);
  assert.match(s, /window\.setTimeout\(\(\) => setTries\(\(n\) => n \+ 1\), FILINGS_REREAD_MS\)/);
  assert.match(s, /options=\{\[\{ value: "mine", label: "Your stocks" \}, \{ value: "all", label: "All companies" \}\]\}/);
  assert.match(read("src/components/Filings.tsx"), /from the evening's read of every company's filings/);
});
