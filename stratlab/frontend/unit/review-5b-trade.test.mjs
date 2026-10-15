// Review 5b: the Trade space frontend. A failed notebook save, rules rebuilt from words, options on a notebook's signal,
// signal sessions (paused, test buttons, polling), missing options sessions, plan locks, the strike step, the compare
// page, currencies, imports, a stopped session's day, and the rule editor's number boxes. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const backend = (p) => readFileSync(new URL(`../../backend/app/${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

const rules = await import("../src/lib/rules.ts");
const options = await import("../src/lib/options.ts");
const tradeUi = await import("../src/lib/tradeUi.ts");
const compare = await import("../src/lib/compare.ts");
const { makeSaver } = await import("../src/lib/notebookSave.ts");

/* ---------- 1. a failed save ---------- */

test("R5B-001: a failed notebook save keeps the edit (under newer ones), says Not saved, and Retry sends it", async () => {
  const sent = [], states = [];
  let down = true;
  const s = makeSaver(async (body) => { if (down) throw new Error("offline"); sent.push(body); }, { state: (x) => states.push(x) });
  s.add({ strategy: { v: 1 }, notes: "a" });
  assert.equal(await s.flush(true), false);                         // the caller hears it failed
  assert.deepEqual(s.pending(), { strategy: { v: 1 }, notes: "a" });  // ...and the edit is still there
  assert.equal(states.at(-1), "failed");
  s.add({ notes: "b" });                                            // an edit made after the failure wins over the old one
  down = false;
  assert.equal(await s.flush(), true);
  assert.deepEqual(sent, [{ strategy: { v: 1 }, notes: "b" }]);
  assert.deepEqual(s.pending(), {});
  assert.equal(states.at(-1), "saved");
});

test("R5B-001: a flush waits for the save already on its way, so Run never goes ahead on rules still being saved", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const s = makeSaver(async () => { await gate; throw new Error("500"); }, { state: () => {} });
  s.add({ strategy: { v: 2 } });
  const first = s.flush();               // the autosave
  const run = s.flush(true);             // Run, while it is in flight: nothing pending of its own
  release();
  assert.equal(await first, false);
  assert.equal(await run, false);        // it tried the kept edit again, and says the save failed
  assert.deepEqual(s.pending(), { strategy: { v: 2 } });
});

test("R5B-001: Run and Make a copy stop when the rules couldn't be saved; the header offers Retry", () => {
  const page = read("src/pages/NotebookPage.tsx");
  const run = page.slice(page.indexOf("const run = async"), page.indexOf("runRef.current = run"));
  assert.match(run, /if \(!\(await flush\(true\)\)\) \{\s*notify\("The rules couldn't be saved, so nothing was run\./);
  assert.ok(run.indexOf("await flush(true)") < run.indexOf("/experiments`"), "the save is checked before the run is asked for");
  assert.match(page, /const duplicate = async[\s\S]*?if \(!\(await flush\(true\)\)\) \{ notify\("The rules couldn't be saved, so no copy was made\."/);
  assert.match(page, />Not saved · Retry<\/button>/);
  assert.match(page, /makeSaver\(/);
  assert.doesNotMatch(page, /pending\.current = \{\};\s*setSaving\("saving"\)/);
});

test("R5B-001: the rule editor stops at the server's 12 rules a list", () => {
  assert.equal(rules.MAX_RULES, 12);
  const models = backend("models.py");
  for (const k of ["entry", "exit", "shortEntry", "shortExit"])
    assert.match(models, new RegExp(`\\n    ${k}: list\\[Cond\\] = Field\\(default_factory=list, max_length=${rules.MAX_RULES}\\)`));
  const card = read("src/components/Rules.tsx");
  assert.match(card, /const full = \(key[^\n]*\.length >= MAX_RULES;/);
  assert.match(card, /const addRule = [^\n]*\{ if \(!full\(key\)\) set\(/);
  assert.match(card, /const addBtn = [^\n]*=> full\(key\) \? fullNote :/);
  assert.match(card, /const exitPick = [^\n]*\{\n\s*if \(full\(key\)\) return fullNote;/);
});

test("R5B-001: switching a 150-point stop to % clears it and says so; a valid one stays", () => {
  const r = { ...rules.blankStrategy().risk, sl: 150, stopType: "points" };
  const x = rules.switchStopUnit(r, "pct");
  assert.deepEqual(x.risk, { stopType: "pct", sl: 0 });
  assert.match(x.note, /under 100%, so the 150-point stop was cleared/);
  assert.deepEqual(rules.switchStopUnit({ ...r, sl: 2 }, "pct"), { risk: { stopType: "pct" }, note: null });
  assert.deepEqual(rules.switchStopUnit({ ...r, sl: 2.5, stopType: "atr" }, "swing").risk, { stopType: "swing", sl: 3 });
  assert.match(read("src/components/Rules.tsx"), /onChange=\{\(v\) => \{ const x = switchStopUnit\(r, v\); setRisk\(x\.risk\); setUnitNote\(x\.note\); \}\}/);
});

/* ---------- 2 and 3. rules rebuilt from words ---------- */

test("R5B-002: Describe the idea again keeps a US notebook's capital and costs unless the words give them", () => {
  const us = { ...rules.riskForCurrency(rules.blankStrategy().risk, "USD"), slippage: 0.1, riskPct: 0.5, sizing: "capital", perTrade: 2500 };
  const built = rules.blankStrategy().risk;                         // what a new build carries: the Indian defaults
  const kept = rules.rebuiltRisk(us, { ...built, sl: 3 }, ["sl"]);
  assert.equal(kept.capital, 10000); assert.equal(kept.brokerage, 0); assert.equal(kept.slippage, 0.1);
  assert.equal(kept.riskPct, 0.5); assert.equal(kept.sizing, "capital"); assert.equal(kept.perTrade, 2500);
  assert.equal(kept.sl, 3);
  const said = rules.rebuiltRisk(us, { ...built, capital: 50000, riskPct: 2 }, ["capital", "riskPct"]);
  assert.equal(said.capital, 50000); assert.equal(said.riskPct, 2);
  const page = read("src/pages/NotebookPage.tsx");
  assert.match(page, /<IdeaComposer busyLabel="Replace the rules" autoFocus byHand=\{false\} market=\{group\?\.market \?\? inst\?\.market\} symbol=\{inst\?\.symbol \?\? null\}/);
  assert.match(page, /const kept = rebuiltRisk\(s\.risk, b\.strategy\.risk, b\.gaps\.mentioned\);/);
  assert.doesNotMatch(page, /patch\(\{ strategy: \{ \.\.\.b\.strategy, name: nb\.name \}/);
});

test("R5B-003: Edit in words takes risk %, sizing, per-trade capital and leverage the words state; the capital stays", () => {
  const words = "Buy when 20 EMA crosses above 50 EMA. Sell when 20 EMA crosses below 50 EMA. Stop loss 2%, risk 2% of capital";
  const p = rules.parseStrategyText(words);
  const old = { ...rules.blankStrategy().risk, capital: 300000 };
  const n = { ...rules.blankStrategy().risk, ...p.risk, capital: 999 };
  const after = rules.rebuiltRisk(old, n, [...rules.statedIn(words), "capital"], true);
  assert.equal(after.riskPct, 2);
  assert.equal(after.capital, 300000);
  const ai = rules.rebuiltRisk(old, { ...n, sizing: "capital", perTrade: 50000, leverage: 5, maxAlloc: 40 }, ["sizing", "perTrade", "leverage", "maxAlloc"], true);
  assert.deepEqual([ai.sizing, ai.perTrade, ai.leverage, ai.maxAlloc], ["capital", 50000, 5, 40]);
  assert.match(read("src/components/Rules.tsx"), /risk: rebuiltRisk\(s\.risk, n\.risk, out\.built\.gaps\.mentioned, true\) \}\);/);
});

/* ---------- 4. options on a notebook's signal ---------- */

test("R5B-004: the notebook's rules are read on opening with ?nb=, again right before Start, and the page says as of when", () => {
  const nb = { id: "n1", name: "RSI dips", strategy: { ...rules.blankStrategy(), tf: "15m", side: "long" } };
  const sig = options.signalFrom(nb, null, "2026-10-15T04:50:00Z");
  assert.deepEqual({ ...sig, rules: undefined }, { rules: undefined, notebook: "n1", name: "RSI dips", short: "none", asOf: "2026-10-15T04:50:00Z" });
  assert.equal(options.signalFrom(nb, { ...sig, short: "mirror" }, "x").short, "mirror");      // the person's choice stays
  assert.equal(options.signalLine(sig), "Rules from RSI dips, as of 15 Oct, 10:20 IST");
  const page = read("src/pages/OptionsPage.tsx");
  const start = page.slice(page.indexOf("const start = async"), page.indexOf("const exportIt"));
  assert.match(start, /if \(s\.signal\?\.notebook\) \{\s*const fresh = await readSignal\(s\.signal\.notebook\);/);
  assert.match(start, /body: \{ strategy \} \}/);
  assert.match(page, /if \(id\) pickRules\(id, false\);/);
  assert.doesNotMatch(page, /if \(id && id !== s\.signal\?\.notebook\) pickRules\(id\)/);
  // the picked notebook stays in the list (picking it again reads its rules again), and a button does the same
  assert.doesNotMatch(page, /\.filter\(\(n\) => n\.id !== s\.signal\?\.notebook\)/);
  assert.match(page, /if \(s\.signal\?\.notebook === id\) \{ patch\(\{ signal \}\);/);
  assert.match(page, />Read them again now<\/button>/);
});

/* ---------- 5, 6, 7. signal sessions ---------- */

test("R5B-005: a paused signal session offers Stop session, then Delete", () => {
  assert.equal(tradeUi.stoppable("paused"), true);
  assert.equal(tradeUi.stoppable("running"), true);
  assert.equal(tradeUi.stoppable("stopped"), false);
  const page = read("src/pages/trade/SignalsPage.tsx");
  assert.match(page, /\{stoppable\(snap\.status\)\s*\? <div className="k-row">[^\n]*onClick=\{\(\) => setAsk\("stop"\)\}>Stop session<\/button>/);
  assert.doesNotMatch(page, /\{running \? <button type="button" className="btn danger sm" onClick=\{\(\) => setAsk\("stop"\)\}>/);
});

test("R5B-006: test signals carry the page's own id and a busy flag; a qty of 0 is refused, never sent as 1", () => {
  assert.deepEqual(tradeUi.testQty("0"), { error: "The test quantity has to be above 0." });
  assert.ok("error" in tradeUi.testQty(""));
  assert.ok("error" in tradeUi.testQty("abc"));
  assert.deepEqual(tradeUi.testQty("2.5"), { qty: 2.5 });
  assert.deepEqual(tradeUi.testQty("1,000"), { qty: 1000 });
  const id = tradeUi.testSignalId(1791192000000, 0.5);
  const ID = new RegExp(backend("signals.py").match(/^ID = re\.compile\(r"(.+)"\)$/m)[1]);
  assert.match(id, ID);
  assert.notEqual(tradeUi.testSignalId(1, 0.1), tradeUi.testSignalId(1, 0.2));
  // the server takes it and treats a second send as a repeat
  const routes = backend("signals_routes.py");
  assert.match(routes, /class TestReq\(BaseModel\):[\s\S]*?id: str \| None = Field\(None, pattern=SG\.ID\.pattern\)/);
  assert.match(routes, /if req\.id:\s*body\["id"\] = req\.id/);
  const page = read("src/pages/trade/SignalsPage.tsx");
  assert.doesNotMatch(page, /Number\(qty\) \|\| 1/);
  assert.match(page, /let body: Record<string, unknown> = \{ action, id: testSignalId\(\) \};/);
  assert.match(page, /disabled=\{sending\} onClick=\{\(\) => void test\(x\)\}/);
  assert.match(page, /if \(inFlight\.current\) return;/);
});

test("R5B-007: the signal session page leaves only on a 404, keeps its snapshot on a refetch, and its gone handler is stable", () => {
  const page = read("src/pages/trade/SignalsPage.tsx");
  const view = page.slice(page.indexOf("function SessionView"), page.indexOf("if (!snap) return <Card><Skeleton"));
  assert.match(view, /const gone = useRef\(onGone\);/);
  assert.match(view, /if \(e instanceof ApiError && e\.status === 404\) \{ fail\(e\); gone\.current\(\); return; \}/);
  assert.match(view, /\}\), \[sid, fail\]\);/);                         // load doesn't change with onGone
  assert.doesNotMatch(view, /setSnap\(null\)/);
  assert.match(page, /const onGone = useCallback\(\(\) => \{ void load\(\); nav\("\/trade\/signals"\); \}, \[load, nav\]\);/);
  assert.match(page, /<SessionView key=\{sid\} sid=\{sid\} onGone=\{onGone\} \/>/);
});

/* ---------- 8. a missing options session ---------- */

test("R5B-008: a missing options or paper session says so, stops polling, and an error is toasted once", () => {
  const opt = read("src/pages/OptionsSession.tsx");
  assert.match(opt, /if \(missing\) \{ window\.clearInterval\(poll\.current\); return; \}/);
  assert.match(opt, /if \(!told\.current\) \{ told\.current = true; fail\(e\); \}/);
  assert.match(opt, /title="Options session not found"/);
  assert.match(opt, /<ErrorState title="The session couldn't be opened"/);
  const paper = read("src/pages/PaperPage.tsx");
  assert.match(paper, /e\.status === 404[^\n]*setMissing\(true\); window\.clearInterval\(poll\.current\); return; \}/);
  assert.match(paper, /if \(!told\.current\) \{ told\.current = true; fail\(e\); \}/);
  assert.doesNotMatch(paper, /catch \(e\) \{ if \(live\(\)\) \{ setError\([^\n]*fail\(e\); \} \}/);
});

/* ---------- 9. plan locks ---------- */

test("R5B-009: plan-locked choices say their plan before Start, with the server's own feature keys", () => {
  const plans = backend("plans.py");
  for (const k of ["options_signal", "fast_entries", "group_live"]) assert.match(plans, new RegExp(`"${k}"`));
  const opt = read("src/pages/OptionsPage.tsx");
  assert.match(opt, /const signalOk = feats \? !!feats\.options_signal : true;/);
  assert.match(opt, /label: `When a notebook's rules say so\$\{signalOk \? "" : " \(Pro\)"\}`, disabled: !signalOk && !ruleMode/);
  assert.match(opt, /disabled=\{starting \|\| !!offline \|\| !canStart \|\| \(ruleMode && \(!s\.signal \|\| !signalOk\)\)\}/);
  const nb = read("src/pages/NotebookPage.tsx");
  assert.match(nb, /const groupOk = feats \? !!feats\.group_live : true, fastOk = feats \? !!feats\.fast_entries : true;/);
  assert.match(nb, /if \(!groupOk\) \{ plansToast\("Paper trading a group is on the Basic plan\."\); return; \}/);
  assert.match(nb, /Paper trade\{group && !groupOk \? " \(Basic\)" : ""\}/);
  assert.match(nb, /<CheckField label=\{<><b>Faster entries<\/b>\{!fastOk && " \(Pro\)"\}<\/>\} checked=\{fast\.ticks\} disabled=\{!fastOk && !fast\.ticks\}/);
  assert.match(nb, /label=\{`Skip if the spread is over\$\{fastOk \? "" : " \(Pro\)"\}`\}[^\n]*disabled=\{!fastOk && !fast\.maxSpreadPct\}/);
});

/* ---------- 10. the strike step ---------- */

test("R5B-010: strikes to points uses the underlying's own step: BANKNIFTY 100, USDINR 0.25, never an assumed 50", () => {
  const condor = options.STRUCTURES.find((s) => s.id === "iron_condor").legs;
  const bn = options.offsetsIn(condor, "points", 100);
  assert.deepEqual(bn.map((l) => l.offset), condor.map((l) => l.offset * 100));
  assert.deepEqual(options.offsetsIn(bn, "strikes", 100).map((l) => l.offset), condor.map((l) => l.offset));
  assert.equal(options.offsetsIn([{ side: "sell", opt: "CE", offset: 4, lots: 1 }], "points", 0.25)[0].offset, 1);
  assert.equal(options.offsetsIn([{ side: "sell", opt: "CE", offset: 3, lots: 1 }], "points", 0.1)[0].offset, 0.3);
  const page = read("src/pages/OptionsPage.tsx");
  assert.doesNotMatch(page, /\?\? 50\)/);
  assert.match(page, /onChange=\{\(v\) => void switchUnit\(v as "strikes" \| "points"\)\}/);
  assert.match(page, /\(await api<OptChain>\(`\/options\/chain\?[^\n]*\)\)\.step \?\? null/);
  assert.match(page, /strike step isn't known yet, so the distances can't be turned into \$\{to\}\. Price it first, then switch\./);
});

/* ---------- 11, 12. the compare page ---------- */

test("R5B-011: picking the same run on both sides keeps the pickers and says to pick two different runs", () => {
  const page = read("src/pages/CompareExperiments.tsx");
  assert.match(page, /if \(!a \|\| !b\) return \(/);
  assert.match(page, /if \(a\.v === b\.v\) return \([\s\S]*?\{pickers\}\s*<Notice tone="warn" role="status">Pick two different runs: v\{a\.v\} is on both sides\.<\/Notice>/);
});

test("R5B-012: stops and targets in their own units, unit changes in words, money in each run's currency", () => {
  const s = rules.blankStrategy();
  const mk = (risk, inst = { symbol: "NIFTY 50", currency: "INR" }) => ({ strategy: { ...s, risk: { ...s.risk, ...risk } }, instrument: inst, days: 365 });
  assert.deepEqual(compare.changes(mk({ sl: 100, stopType: "points" }), mk({ sl: 150, stopType: "points" })), ["Stop loss: 100 points → 150 points"]);
  assert.deepEqual(compare.changes(mk({ sl: 2 }), mk({ sl: 2, stopType: "atr" })), ["Stop loss: 2% → 2 × ATR"]);
  assert.deepEqual(compare.changes(mk({ tgt: 2, tgtType: "r" }), mk({ tgt: 6 })), ["Target: 2R (× the stop distance) → 6%"]);
  assert.deepEqual(compare.changes(mk({ sizing: "risk" }), mk({ sizing: "capital", perTrade: 50000 })), ["Position size: by risk → fixed ₹50,000 a trade"]);
  const aapl = { symbol: "AAPL", currency: "USD" };
  const out = compare.changes(mk({ capital: 500000, brokerage: 20 }), mk({ capital: 10000, brokerage: 0 }, aapl));
  assert.ok(out.includes("Capital: ₹5,00,000 → $10,000"), out.join(" | "));
  assert.ok(out.includes("Brokerage: ₹20.00 → off"), out.join(" | "));
  for (const line of out) assert.doesNotMatch(line, /\b(pct|atr|points?→|capital →|risk →)\b/);
  const page = read("src/pages/CompareExperiments.tsx");
  assert.match(page, /\["Costs paid", \(e\) => money\(e\.costs\.total, e\.instrument\?\.currency\)/);
  assert.doesNotMatch(page, /const cur = b\.instrument\?\.currency;/);
});

/* ---------- 13, 14. currencies on the signal form; imports ---------- */

test("R5B-013: the signal session's capital box is in the instrument's currency, the market's until one is picked", () => {
  assert.deepEqual(tradeUi.capitalField("USD"), { unit: "$", placeholder: "10,000" });
  assert.deepEqual(tradeUi.capitalField("INR"), { unit: "₹", placeholder: "10,00,000" });
  assert.deepEqual(tradeUi.capitalField(null), { unit: "₹", placeholder: "10,00,000" });
  const page = read("src/pages/trade/SignalsPage.tsx");
  assert.match(page, /const cap = capitalField\(inst\?\.currency \|\| market\?\.currency\);/);
  assert.doesNotMatch(page, /unit="₹"/);
});

test("R5B-014: an import (or an idea) clears the box only once the notebook is made", () => {
  const imp = read("src/components/ImportStrategy.tsx");
  assert.match(imp, /const made = await onBuilt\(\{/);
  assert.match(imp, /if \(made !== false\) \{ setText\(""\); setFile\(""\); \}/);
  const home = read("src/pages/Home.tsx");
  assert.match(home, /return async \(b: Built\): Promise<boolean> => \{/);
  assert.match(home, /\} catch \(e\) \{\s*fail\(e\);\s*return false;\s*\}/);
  assert.match(read("src/components/IdeaComposer.tsx"), /if \(\(await onBuilt\(r\.built\)\) !== false\) setText\(""\);/);
});

/* ---------- 15. a stopped session's day ---------- */

test("R5B-015: a stopped or paused session's day figure is never labelled Today", () => {
  assert.deepEqual(tradeUi.dayStat(true, "running", 120, 30), { label: "Today", value: 150, text: null });
  const gone = tradeUi.dayStat(false, "stopped", null, 0);
  assert.equal(gone.value, null);
  assert.equal(gone.text, "None today: the session is stopped");
  assert.doesNotMatch(gone.label, /Today/);
  assert.doesNotMatch(tradeUi.dayStat(false, "paused", 40, 0).label, /^Today/);
  assert.match(read("src/pages/OptionsSession.tsx"), /const d = dayStat\(running, snap\.status, a\.today, p \? p\.net : 0\);/);
  assert.match(read("src/components/GroupSession.tsx"), /const d = dayStat\(running, snap\.status, running \? a\.today : null, 0\);/);
  assert.match(backend("options/session.py"), /if e\.day != today:\s*acct\["today"\] = None/);
});

/* ---------- 16. the rule editor's number boxes ---------- */

test("R5B-016: the rule editor's number boxes keep what is typed and put the rules' value back on leaving", () => {
  const card = read("src/components/Rules.tsx");
  const nf = card.slice(card.indexOf("function NumField"), card.indexOf("function RefEditor"));
  assert.match(nf, /const \[txt, setTxt\] = useState\(String\(value\)\);/);
  assert.match(nf, /value=\{txt\}/);
  assert.match(nf, /onChange=\{\(e\) => \{ setTxt\(e\.target\.value\);/);
  assert.match(nf, /onBlur=\{\(\) => setTxt\(String\(value\)\)\}/);
  assert.doesNotMatch(nf, /value=\{value\}/);
});

/* ---------- the smaller items ---------- */

test("an options stop switched between ₹ and % of premium is converted at the priced premium, or cleared and said", () => {
  assert.deepEqual(options.convertOptLimit(30, "credit_pct", "amount", -4000, "stop").value, 1200);
  assert.equal(options.convertOptLimit(1200, "amount", "credit_pct", 4000, "stop").value, 30);
  const none = options.convertOptLimit(30, "credit_pct", "amount", null, "stop");
  assert.equal(none.value, 0);
  assert.match(none.note, /cleared/);
  assert.deepEqual(options.convertOptLimit(30, "credit_pct", "none", null, "stop"), { value: 30, note: null });
  assert.doesNotMatch(read("src/pages/OptionsPage.tsx"), /onChange=\{\(v\) => setRisk\(\{ stopType: v as OptionStrategy\["risk"\]\["stopType"\] \}\)\}/);
});

test("signal rows on the risk overview are named and open their own page", () => {
  assert.match(read("src/components/RiskOverview.tsx"), /signal: "Signals"/);
  assert.equal(tradeUi.sessionPath({ id: "s1", kind: "signal" }), "/trade/signals/s1");
  assert.match(read("src/pages/PaperPage.tsx"), /<RiskOverview onOpen=\{\(id, kind\) => nav\(sessionPath\(\{ id, kind \}\)\)\} \/>/);
});

test("the group paper dialog's price floor has its currency; session lists write starts in the market's zone, labelled", () => {
  assert.match(read("src/pages/NotebookPage.tsx"), /label="Skip anything cheaper than" unit=\{currencySymbol\(currency\) \|\| undefined\}/);
  assert.match(read("src/pages/PaperPage.tsx"), /started \{fmtDateTime\(r\.started_at, \{ tz: tzOf\(r\.instrument\), year: false, zone: true \}\)\}/);
  assert.match(read("src/pages/OptionsPage.tsx"), /started \{fmtDateTime\(x\.started_at, \{ tz: IST, year: false, zone: true \}\)\}/);
  assert.match(read("src/pages/trade/SignalsPage.tsx"), /started \$\{fmtDateTime\(r\.started_at, \{ tz: tzOf\(\{ market: r\.market \?\? undefined, tz: r\.tz \?\? undefined \}\), year: false, zone: true \}\)\}/);
});

test("the roll preview's premium paid out is a positive amount under its label; an upload keeps its currency", () => {
  assert.match(read("src/components/OptionModel.tsx"), /label=\{`Premium \$\{r\.premium >= 0 \? "taken in" : "paid out"\}`\} value=\{inr\(Math\.abs\(r\.premium\), 2\)\}/);
  assert.match(read("src/pages/NotebookPage.tsx"), /if \(p\.instrumentId\?\.startsWith\("CSV:"\) && p\.instrument && "currency" in p\.instrument && p\.instrument\.currency\) body\.currency = p\.instrument\.currency;/);
});
