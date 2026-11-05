// R11 (owner, 5 Nov): Upstox and Dhan beside Zerodha on Settings -> Connected accounts, said the same way for each.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const B = await import("../src/lib/brokers.ts");
const base = { key: "upstox", name: "Upstox", configured: true, available: true, connected: true, live: true, refreshed_label: "today 09:12", count: 4, detail: null, ends_at: null };

test("a broker's badge: not set up, not open, not connected, connected, log in again", () => {
  assert.deepEqual(B.brokerBadge({ ...base, configured: false, available: false }), { tone: "plain", text: "Not set up yet" });
  assert.deepEqual(B.brokerBadge({ ...base, available: false }), { tone: "plain", text: "Not open yet" });
  assert.deepEqual(B.brokerBadge({ ...base, connected: false }), { tone: "plain", text: "Not connected" });
  assert.deepEqual(B.brokerBadge(base), { tone: "ok", text: "Connected" });
  assert.deepEqual(B.brokerBadge({ ...base, live: false }), { tone: "warn", text: "Log in again" });
});

test("a broker's line names the last read, the holdings and when the broker ends the login, as Zerodha's does", () => {
  const now = new Date("2026-11-05T10:00:00+05:30");
  assert.equal(B.brokerLine({ ...base, ends_at: "2026-11-06T03:30+05:30" }, now), "Connected · last read today 09:12 IST · 4 holdings · this login ends on 6 Nov, 03:30 IST");
  assert.equal(B.brokerLine({ ...base, count: 1, ends_at: "2026-11-05T23:59+05:30" }, now), "Connected · last read today 09:12 IST · 1 holding · this login ends at 23:59 IST");
  assert.equal(B.brokerLine({ ...base, live: false }, now), "This login has ended · last read today 09:12 IST · log in again to read your holdings");
  assert.equal(B.brokerLine({ ...base, refreshed_label: null, count: null }, now), "Connected · not read yet");
  assert.equal(B.brokerLine({ ...base, connected: false }, now), "");
  assert.equal(B.brokerLine({ ...base, available: false }, now), "");
});

test("the names a page offers", () => {
  assert.equal(B.orList([]), "");
  assert.equal(B.orList(["Zerodha"]), "Zerodha");
  assert.equal(B.orList(["Zerodha", "your statement inbox"]), "Zerodha or your statement inbox");
  assert.equal(B.orList(["Zerodha", "Upstox", "Dhan", "your statement inbox"]), "Zerodha, Upstox, Dhan or your statement inbox");
});

test("Settings lists every broker in one table, a row each; Holdings reads them again and names the ones open", async () => {
  const c = read("src/components/ConnectedAccounts.tsx");
  assert.match(c, /<DataTable label="Broker logins" columns=\{columns\} rows=\{rows\}/);
  assert.match(c, /rowAttrs=\{\(b\) => \(\{ id: b\.id, "data-testid": `broker-\$\{b\.key\}` \}\)\}/);
  assert.match(c, /\/connect\/\$\{key\}\/confirm/);
  assert.match(c, /r === "refused" \? `\$\{name\} didn't allow this login yet\. Upload your holdings file or forward your statement instead\.`/);
  const h = read("src/pages/HoldingsPage.tsx");
  assert.match(h, /`\/connect\/\$\{b\.key\}\/refresh`/);
  assert.match(h, /data-testid="connect-offer"/);
  const { syncedNote } = await import("../src/lib/holdingsEdit.ts");
  assert.match(syncedNote("dhan"), /^Synced from Dhan\./);
  const { sourceWords } = await import("../src/lib/format.ts");
  assert.equal(sourceWords("Dhan login"), "your Dhan login");
  assert.equal(sourceWords("Upstox"), "your Upstox file");
});

test("Pick your broker: the list, Other last, and each broker's ways in order", async () => {
  const G = await import("../src/lib/brokerGuide.ts");
  const names = G.GUIDE_BROKERS.map((b) => b.name);
  assert.deepEqual(names, ["Zerodha", "Groww", "Upstox", "Angel One", "Dhan", "ICICI Direct", "HDFC Sky / HDFC Securities", "Kotak Neo", "Paytm Money", "Motilal Oswal", "Other"]);
  assert.equal(new Set(G.GUIDE_BROKERS.map((b) => b.id)).size, names.length);
  for (const b of G.GUIDE_BROKERS) assert.match(b.id, /^[a-z0-9]{2,20}$/);          // what the server keeps as the pick
  // a live connection only where StratLab has one; Groww has none (nothing said about one)
  assert.deepEqual(G.GUIDE_BROKERS.filter((b) => b.connect).map((b) => [b.id, b.connect]), [["zerodha", "kite"], ["upstox", "upstox"], ["dhan", "dhan"]]);
  assert.deepEqual(G.waysFor(G.guideFor("upstox")), ["connect", "file", "email"]);
  assert.deepEqual(G.waysFor(G.guideFor("groww")), ["file", "email"]);
  assert.deepEqual(G.waysFor(G.guideFor("angelone")), ["file", "email"]);          // owner, 5 Nov: no Angel One connection
  assert.deepEqual(G.waysFor(G.guideFor("other")), ["file", "email"]);
  assert.equal(G.guideFor("nope"), null);
  assert.equal(G.guideFor(null), null);
  for (const b of G.GUIDE_BROKERS) {
    assert.ok(b.file.steps.length >= 2, b.id);
    // steps that name menus come from the broker's own help page, on its own site
    if (b.file.help) assert.match(b.file.help, /^https:\/\/(support\.zerodha\.com|groww\.in|upstox\.com|www\.angelone\.in|dhan\.co|www\.kotakneo\.com|www\.paytmmoney\.com)\//, b.id);
    assert.ok(G.readLine(b).length > 20);
  }
  assert.match(G.guideFor("zerodha").file.steps.join(" "), /Console.*Portfolio, then Holdings.*XLSX beside Download/);
  assert.match(G.guideFor("groww").file.steps.join(" "), /profile, then Reports/);
  assert.match(G.readLine(G.guideFor("groww")), /recognises Groww's file/);
  assert.match(G.readLine(G.guideFor("other")), /Symbol \(or ISIN\), Quantity and Average price/);
  assert.match(G.guideFor("paytm").file.steps[0], /PDF, which can't be read here/);
  assert.match(G.EMAIL_STEPS.join(" "), /NSDL or CDSL.*every broker.*CAMS or KFintech/);
});
