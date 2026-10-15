// Review 7a on the options pages: the flat line on an exchange holiday, old saved drafts, the legs table's keys after a
// re-centre, the STT note, and the leg stop and re-centre help. Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const { blankOptions, flatLine, mergeDraft, STT_NOTE } = await import("../src/lib/options.ts");
const { HELP } = await import("../src/lib/help.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

const IN = { id: "IN", name: "IN", venues: "", currency: "INR", symbol: "₹", tz: "Asia/Kolkata",
  hours: { open: "09:15", close: "15:30", days: "Mon–Fri", fo_close: "15:40" }, what: "", costs: "", brokerage: 0, status: "live",
  max_days: null, holidays: ["2026-10-20"] };
const at = (iso) => new Date(`${iso}+05:30`);
const snap = { status: "running", strategy: blankOptions(), account: { halted: false, entries_today: 0, cool_until: null, next_entry: null } };

test("a flat session on an exchange holiday says the market is closed for it", () => {
  const line = flatLine(snap, 0, IN, at("2026-10-20T11:00:00"));                  // Tuesday 20 Oct, a holiday
  assert.equal(line, "No trades today. The market is closed today for a holiday; next entry 09:30 on the next market day.");
  assert.doesNotMatch(line, /Entries open until/);
  assert.equal(flatLine(snap, 0, IN, at("2026-10-19T11:00:00")), "No trades today. Entries open until 14:45.");   // a normal day
  assert.match(read("src/pages/OptionsSession.tsx"), /flatLine\(snap, today\.length, optionsMarket\(markets, s\.exchange\)\)/);
});

test("an old saved draft keeps the defaults of nested fields it doesn't have", () => {
  const old = { name: "Mine", risk: { stopType: "amount", stop: 4000 }, sizing: { mode: "margin" }, legs: [{ side: "sell", opt: "CE", offset: 1, lots: 1 }] };
  const d = mergeDraft(blankOptions(), old);
  assert.equal(d.name, "Mine");
  assert.equal(d.risk.stop, 4000);
  assert.equal(d.risk.legStopPct, 0);                     // missing in the draft: the default, not undefined
  assert.equal(d.sizing.mode, "margin");
  assert.equal(d.sizing.safety, 0.98);
  assert.deepEqual(d.recenter, blankOptions().recenter);
  assert.deepEqual(d.legs, old.legs);                     // the legs are taken whole
  const page = read("src/pages/OptionsPage.tsx");
  assert.doesNotMatch(page, /\{ \.\.\.blankOptions\(\), \.\.\./);
  assert.match(page, /mergeDraft\(blankOptions\(\), JSON\.parse\(raw\)\)/);
});

test("the legs table's keys stay unique when a re-centre reopens the same contract at the same price", () => {
  const src = read("src/pages/OptionsSession.tsx");
  const m = src.match(/label="Open legs".*? rowKey=\{(.*?)\} rowAttrs=/);
  assert.ok(m, "the open legs table has a rowKey");
  const key = new Function(`return ${m[1]}`)();
  const leg = { sym: "NIFTY25000CE", side: "sell", entry: 100 };
  const rows = [leg, { ...leg }];                         // the closed leg and the reopened one
  assert.equal(new Set(rows.map((l, i) => key(l, i))).size, 2);
});

test("the costs on both pages say STT on exercise isn't included", () => {
  assert.equal(STT_NOTE, "STT on options exercised at expiry is not included.");
  assert.match(read("src/pages/OptionsSession.tsx"), /\{STT_NOTE\}/);
  assert.match(read("src/pages/OptionsPage.tsx"), /Rates as of \{asOf\(c\.rates_as_of\)\}\. \{STT_NOTE\}/);
});

test("the leg stop and re-centre help say a stopped leg isn't reopened", () => {
  assert.match(HELP.optLegStop, /A stopped leg stays closed: a re-centre doesn't reopen it\./);
  assert.match(HELP.optRecenter, /a sold leg the leg stop closed stays closed/);
});

test("the builder shows the note when margin sizing falls back to 1 unit", () => {
  assert.match(read("src/pages/OptionsPage.tsx"), /preview\?\.sizing_note && preview\.units !== 0 && <Notice>\{preview\.sizing_note\}<\/Notice>/);
});
