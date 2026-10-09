// Round 11 review of the live site (9 Oct 2026): the app's side, each on the reviewer's example. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

test("R11P-005: Razorpay's window carries the renewal line in its description", async () => {
  const { checkoutDescription } = await import("../src/lib/offer.ts");
  assert.equal(checkoutDescription("Basic", "month"), "Basic, monthly · renews every month");
  assert.equal(checkoutDescription("Pro", "year"), "Pro, yearly · renews every year");
  assert.match(read("src/pages/PlansPage.tsx"), /description: checkoutDescription\(plan === "pro" \? "Pro" : "Basic", period\)/);
});

test("R11P-006: Admin counts only the holidays the owner added by hand as added by the owner", async () => {
  const { holidaysSaved } = await import("../src/pages/admin/holidays.ts");
  assert.equal(holidaysSaved(20, 0), "20 saved, all from the exchange.");
  assert.equal(holidaysSaved(20, 2), "20 saved: 18 from the exchange, 2 added by you.");
  assert.equal(holidaysSaved(3, 3), "3 saved, all added by you.");
  assert.equal(holidaysSaved(20, null), "20 saved.");                      // an older server that does not say
  assert.equal(holidaysSaved(0, 0), "");
  assert.equal(holidaysSaved(5, 9), "5 saved, all added by you.");         // never more by hand than saved
  const panel = read("src/pages/admin/HolidaysPanel.tsx");
  assert.match(panel, /holidaysSaved\(status\.added\.length, status\.by_hand \? status\.by_hand\.length : null\)/);
  assert.doesNotMatch(panel, /added by you\./);
});

test("R11P-007: a long link in a provider's error is cut to its address on System, and whole sentences are kept", async () => {
  const { shortLinks, oneLine } = await import("../src/pages/admin/attention.ts");
  const url = "https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai%3Fmodal%3Dadd-credit-card%26x%3D" + "a".repeat(100);
  const said = `403: AI Gateway requires a valid credit card on file. Visit ${url} to add one.`;
  const out = shortLinks(said);
  assert.ok(out.text.length < 140 && out.text.includes("https://vercel.com/d?to=") && out.text.includes("…"));
  assert.ok(out.text.endsWith(" to add one.") && out.text.includes("Visit "));       // the sentences around it stay
  assert.equal(out.full, said);
  assert.deepEqual(shortLinks("Free quota used up for now; it resets on its own."), { text: "Free quota used up for now; it resets on its own." });
  assert.deepEqual(shortLinks(null), { text: "" });
  // the Overview's one-line cut (PR 178) already covers a raw link: it is cut at 120 characters
  assert.ok(oneLine(url).text.length <= 120);
  const panel = read("src/pages/admin/AIPanel.tsx");
  assert.match(panel, /<Said text=\{p\.state_text\} \/>/);
  assert.match(panel, /<Said text=\{m\.last_error\} \/>/);
  assert.match(panel, /out_of_credit/);
  assert.match(panel, /\(out of credit\)/);
});

test("R11P-009: the journal's strength-of-evidence dots are an image with its label", () => {
  assert.match(read("src/pages/trade/JournalPage.tsx"), /<div className="dots" role="img" aria-label=\{checksLine\(v\.passed, v\.total\)\}>/);
  assert.match(read("src/pages/ExperimentPage.tsx"), /<div className="dots" role="img" aria-label=/);       // the other use of the same dots
});

test("R11P-010: a change that rounds to zero is flat, not up", async () => {
  const { changeDir, pct } = await import("../src/lib/format.ts");
  assert.equal(changeDir(0.0012, pct(0.0012, 2)), "flat");                  // USD/INR 96.76 "▲ Up 0.00%"
  assert.equal(changeDir(-0.0012, pct(-0.0012, 2)), "flat");
  assert.equal(changeDir(0, "0.00%"), "flat");
  assert.equal(changeDir(null), "flat");
  assert.equal(changeDir(0.4, "+0.40%"), "up");
  assert.equal(changeDir(-3.6, "3.6%"), "down");
  assert.equal(changeDir(296, "₹296 cr"), "up");
  assert.equal(changeDir(0.004, "+₹0 cr"), "flat");
  assert.equal(changeDir(2.3, "+2.30 (0.00%)"), "up");                      // the first figure is the one that decides
  assert.equal(changeDir(0.05), "up");                                      // without text, the sign
  const stat = read("src/components/kit/Stat.tsx");
  assert.match(stat, /const dir = changeDir\(value, textOf\(children\)\)/);
  assert.match(stat, /"Unchanged "/);
});
