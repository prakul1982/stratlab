// Round 7, mail, payments, broker and reliability (9 Oct 2026): frontend side, each on the reviewer's real example.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const server = (extra = {}) => ({ server: { kite_ready: true, kite_token_day: null, feed_connected: false, live_sessions: 0, india_sessions: 0,
  auto_login: { at: null, ok: true, message: "ok" }, auto_login_configured: true, billing_enabled: true, ai: [], research: { finnhub: true },
  recent_errors: [], server_started_at: "2026-10-09T01:00:00+05:30", ...extra }, stats: {} });

test("Invoice seller details empty: a warning on Overview and Money; the Plans words follow the invoice (R7M-001)", async () => {
  const { attention, invoiceWarning } = await import("../src/pages/admin/attention.ts");
  const empty = { complete: false, missing: ["legal name", "address", "state", "GSTIN"], gst: false };
  const warning = invoiceWarning(empty);
  assert.match(warning, /^The invoice seller details are empty\. Until the GSTIN is set, every invoice is a plain one that says the supplier isn't registered under GST/);
  assert.equal(invoiceWarning({ complete: true, missing: [], gst: true }), null);
  assert.equal(invoiceWarning(undefined), null);                                   // an older server says nothing
  assert.match(invoiceWarning({ complete: false, missing: ["legal name", "address"], gst: true }), /missing the legal name, address\. Invoices carry GST, but are incomplete/);
  const items = attention(server({ invoice_seller: empty }), null, []);
  const item = items.find((x) => x.text === warning);
  assert.ok(item && item.to === "/admin/money" && item.bad, "Overview lists it as something to fix while payments are on");
  assert.equal(attention(server({ invoice_seller: empty, billing_enabled: false }), null, []).find((x) => x.text === warning).bad, false);
  assert.ok(!attention(server({ invoice_seller: { complete: true, missing: [], gst: true } }), null, []).some((x) => /invoice seller/.test(x.text)));
  const money = read("src/pages/admin/MoneySection.tsx");
  assert.match(money, /invoiceWarning\(ov\?\.server\.invoice_seller\)/);
  assert.match(money, /<Notice tone="warn"[^>]*label="Invoice seller details"/);
  assert.match(read("src/pages/admin/InvoiceAdminPanel.tsx"), /notify\("Invoice details saved\."\); void reload\(\)/);   // Overview learns of the save
});

test("Plans and the confirm step say nothing of GST while the invoice carries none, and the stale window sentence is gone (R7M-001, R6V-009)", async () => {
  const { finePrint, paymentWindowLine, rupeeCharge, viewingPlansNote } = await import("../src/lib/offer.ts");
  assert.equal(rupeeCharge(699, true), "₹699 incl. 18% GST");
  assert.equal(rupeeCharge(19999, false), "₹19,999");
  const live = { mode: "paid", payments: true, yearly: true };
  const x = { currency: "INR", inRupees: false, inRupeesYear: false };
  assert.deepEqual(finePrint(live, { ...x, gst: true }).slice(0, 1), ["Rupee prices include 18% GST, and every payment gets a GST invoice."]);
  assert.deepEqual(finePrint(live, x).slice(0, 1), ["Rupee prices include 18% GST, and every payment gets a GST invoice."]);       // not told: as before
  const none = finePrint(live, { ...x, gst: false }).join(" ");
  assert.match(none, /^Every payment gets an invoice in Account\./);
  assert.doesNotMatch(none, /GST/);
  const abroad = finePrint(live, { currency: "SAR", inRupees: true, inRupeesYear: true, charged: { basic: "₹699", pro: "₹1,999" }, gst: false }).join(" ");
  assert.match(abroad, /a card is charged ₹699 \(Basic\) or ₹1,999 \(Pro\) a month, and your bank converts it/);
  assert.doesNotMatch(abroad, /GST/);
  assert.equal(paymentWindowLine("Basic", "month"), 'The payment window that opens next is headed "StratLab · Basic, monthly" and shows the amount in rupees.');
  assert.match(paymentWindowLine("Pro", "year"), /StratLab · Pro, yearly/);
  const plans = read("src/pages/PlansPage.tsx");
  assert.doesNotMatch(plans, /shows the amount only/);
  assert.match(plans, /paymentWindowLine\(planName\(switching\), period\)/);
  assert.match(plans, /const gst = pricing\?\.invoice\?\.gst === true/);
  assert.match(plans, /\{price\.inr && gst && <span className="k-note">incl\. GST<\/span>\}/);
  assert.doesNotMatch(read("src/content/seo.ts"), /include 18% GST/);
  assert.match(read("src/pages/Login.tsx"), /const gst = pricing\?\.invoice\?\.gst === true/);
  assert.match(viewingPlansNote("Free"), /^You're viewing as Free\./);
});

test("Plans: the upgrade buttons are off under View as, with the reason, not a click into a refusal (R7M-010)", () => {
  const plans = read("src/pages/PlansPage.tsx");
  assert.match(plans, /disabled=\{!!busy \|\| !!viewAs\}/);
  assert.match(plans, /title=\{viewAs \? viewingPlansNote\(planName\(viewAs\)\) : undefined\}/);
  assert.match(plans, /\{viewAs && billing && <div id="plans-viewas" data-testid="plans-viewas">/);
});

test("Admin: the AI tile counts what worked last, not what is configured: 5 of 12 working, 6 out of credit (R7M-008)", async () => {
  const { aiTile } = await import("../src/pages/admin/attention.ts");
  const row = (label, result, extra = {}) => ({ label, configured: true, in_use: true, model: "m", last_error: null, answering: result === "working", result, ...extra });
  const ai = [...["Groq", "Gemini", "OpenRouter", "Cloudflare", "NVIDIA"].map((n) => row(n, "working")),
    ...["Cerebras", "SambaNova", "Z.ai", "Vercel AI Gateway", "Hugging Face", "GitHub Models"].map((n) => row(n, "quota")), row("Mistral", "untested")];
  const t = aiTile(ai);
  assert.equal(t.detail, "5 of 12 working · 6 out of credit · 1 not tried yet");
  assert.equal(t.state, "warn");
  assert.equal(aiTile([row("Groq", "working"), row("Gemini", "failed")]).detail, "1 of 2 working · 1 failing");
  assert.equal(aiTile([row("Groq", "working"), row("HF", "paused", { answering: false })]).detail, "1 of 2 working · 1 paused");
  assert.equal(aiTile([row("Groq", "working"), row("Gemini", "working")]).state, "ok");
  assert.equal(aiTile([row("Groq", "working", { paused_models: 1 })]).state, "warn");           // a paused model is never "all working"
  assert.equal(aiTile([row("Mistral", "untested")]).detail, "0 of 1 working · 1 not tried yet");
  assert.equal(aiTile([row("Groq", "failed", { answering: false })]).state, "bad");
  // an older server sends no last result: the wording it had stays (unit/review-r6o.test.mjs)
  assert.equal(aiTile([{ label: "Groq", configured: true, in_use: true, model: "m", last_error: null, answering: true }]).detail, "1 of 1 answering");
  assert.match(read("src/pages/admin/AIPanel.tsx"), /\{m\.name \?\? m\.id\}/);                 // Cloudflare's models by name
});

test("Admin: the currencies without an exchange rate are named, and the 'last rate kept' note is only for those that had one (R7M-003)", async () => {
  const { noRate, rateNote } = await import("../src/pages/admin/prices.ts");
  const rows = { NOK: { no_rate: true }, SAR: { no_rate: false }, QAR: {}, AUD: {} };
  assert.deepEqual(noRate(rows), ["NOK"]);
  assert.equal(rateNote(["NOK: no rate", "AUD: down"], rows),
    "Couldn't read: AUD (last rate kept). No exchange rate yet for NOK: it isn't shown to visitors until one is read. Fix a price here to show one anyway.");
  assert.match(rateNote(["SAR: x", "NOK: x", "QAR: x"], { SAR: { no_rate: true }, NOK: { no_rate: true }, QAR: { no_rate: true } }), /^No exchange rate yet for SAR, NOK, QAR: they aren't shown/);
  assert.equal(rateNote([], rows).includes("last rate kept"), false);
  assert.equal(rateNote(["AUD: down"], {}), "Couldn't read: AUD (last rate kept).");
  assert.match(read("src/pages/admin/PricesPanel.tsx"), /No rate: not shown to visitors/);
});

test("System: Loading, not the all-clear, while the status comes (R7M-007)", () => {
  const sys = read("src/pages/admin/SystemSection.tsx");
  assert.match(sys, /\{!sv \? <Skeleton label="Loading the server errors" lines=\{2\} \/> : !errors\.length \? <EmptyState/);
  assert.match(sys, /title=\{sv \? `Server errors \(/);
});

test("Zerodha connected with nothing: Holdings says so with the time, and the card drops 'tap to refresh tomorrow' (R7M-009)", async () => {
  const { zerodhaEmpty, zerodhaLine } = await import("../src/lib/zerodha.ts");
  const now = new Date("2026-10-09T01:00:00+00:00");                                 // 06:30 IST
  assert.equal(zerodhaEmpty({ count: 0, read_at: "2026-10-09T00:41:00+00:00" }, now), "Zerodha is connected; it returned 0 holdings at 06:11 IST.");
  assert.equal(zerodhaEmpty({ count: 0, read_at: "2026-10-08T09:59:00+00:00" }, now), "Zerodha is connected; it returned 0 holdings at 8 Oct, 15:29 IST.");
  assert.equal(zerodhaEmpty({ count: 3, read_at: "2026-10-09T00:41:00+00:00" }, now), null);
  assert.equal(zerodhaEmpty(null, now), null);
  assert.equal(zerodhaEmpty({ count: null, read_at: null }, now), null);
  assert.equal(zerodhaLine({ live: true, refreshed_label: "yesterday 23:00", count: 0 }), "Connected · last read yesterday 23:00 IST · 0 holdings");
  assert.equal(zerodhaLine({ live: true, refreshed_label: "today 06:11", count: 1 }), "Connected · last read today 06:11 IST · 1 holding");
  assert.equal(zerodhaLine({ live: false, refreshed_label: "08 Oct 09:12", count: 4 }), "Today's login has ended · last read 08 Oct 09:12 IST · log in again to read your holdings");
  for (const s of [zerodhaLine({ live: true, refreshed_label: "x", count: 0 }), zerodhaLine({ live: false, refreshed_label: null, count: null })]) assert.doesNotMatch(s, /tap to refresh|refreshed/);
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /<EmptyState title=\{zerodhaEmpty\(view\.zerodha\) \?\? "Zerodha is connected; it returned 0 holdings"\}>/);
  assert.match(page, /view\?\.zerodha\s*\?\s*<p className="k-note">Zerodha is connected\./);        // not "Connect Zerodha once" to someone who has
});

test("Trade journal: why its numbers differ from the tax report, and no promise it does not keep (R7M-013)", async () => {
  const { JOURNAL_LEDE, journalVsTax } = await import("../src/lib/journalTax.ts");
  const withFno = journalVsTax(true).join(" ");
  assert.match(withFno, /one round trip per position closed/);
  assert.match(withFno, /every sale line on its own/);
  assert.match(withFno, /one total for each financial year/);
  assert.match(withFno, /Upload the tax P&L's trade-by-trade files to count them here/);
  assert.doesNotMatch(journalVsTax(false).join(" "), /card below the trades/);
  assert.match(JOURNAL_LEDE, /equity from a tradebook or your tax report, F&O, commodity and currency from a tradebook or the tax P&L's trade-by-trade files/);
  assert.doesNotMatch(JOURNAL_LEDE, /Your broker's trades, equity, F&O, commodity and currency,/);
  const page = read("src/pages/trade/JournalPage.tsx");
  assert.match(page, /summary="Why these numbers differ from your tax report"/);
  assert.match(page, /lede=\{JOURNAL_LEDE\}/);
});

test("Net worth: a leftover snapshot is said and can be removed with nothing entered (R7M-012)", () => {
  const page = read("src/pages/money/NetWorthPage.tsx");
  assert.match(page, /\{empty && view\.history_allowed && hist\.length > 0 && \(\s*<Notice tone="warn" role="status" label="Kept history">/);
  assert.match(page, /data-testid="nw-snapshots" open=\{empty \|\| undefined\}/);
});

test("Email previews say the briefs are real; the unsubscribe page and the newsletter note point at Settings (R7M-004, R7M-005)", () => {
  const ctx = read("src/pages/admin/AdminContext.tsx");
  assert.match(ctx, /lede: "Every email StratLab sends, as a reader gets it\. The market briefs are the newest real issues; the rest use made-up details\./);
  assert.doesNotMatch(ctx, /Every email StratLab sends, with made-up details/);
  assert.match(read("src/pages/admin/EmailSection.tsx"), /The market briefs show the newest issue actually built/);
  assert.match(read("src/components/NewslettersCard.tsx"), /If you turn one on after that, the first one comes after the next close\./);
});
