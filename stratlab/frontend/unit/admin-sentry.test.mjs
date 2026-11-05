// Admin → System: "Error alerts (Sentry): on / off" from the server's SDK, and "Send a test error" with its answer kept on the card (owner, 4 Nov).
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { sentryTestLine, sendErrorLine } = await import("../src/pages/admin/testSend.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("the test error's line says whether it went to Sentry, with the time", () => {
  const at = new Date(2026, 10, 4, 14, 5, 9);
  const msg = "StratLab test error from Admin, 04 Nov 2026 14:05:09 IST";
  assert.equal(sentryTestLine({ sentry_on: true, message: msg }, at), `Test error sent to Sentry at 14:05:09: "${msg}". It should show in Sentry's Issues in a minute.`);
  assert.equal(sentryTestLine({ sentry_on: false, message: msg }, at), "Not sent (14:05:09): Sentry is off on the server. Add SENTRY_DSN in Railway and restart to turn it on.");
  // the throttle's 429 words, or a fallback of its own (not the email's)
  assert.equal(sendErrorLine({ message: "You've sent 3 test errors this hour. Try again later." }, at, "x"), "Not sent (14:05:09): You've sent 3 test errors this hour. Try again later.");
  assert.equal(sendErrorLine(null, at, "The test error couldn't be sent. Try again."), "Not sent (14:05:09): The test error couldn't be sent. Try again.");
  assert.equal(sendErrorLine(null, at), "Not sent (14:05:09): The test email couldn't be sent. Try again.");      // the email's own answer is unchanged
});

test("System's Other services card has the Sentry row (On/Off from the server) and the button posts to the admin route", () => {
  const src = read("src/pages/admin/SystemSection.tsx");
  assert.match(src, /label="Error alerts \(Sentry\)"/);
  assert.match(src, /word=\{sv\.sentry \? "On" : "Off"\}/);
  assert.match(src, /api<\{ sentry_on: boolean; message: string \}>\("\/admin\/sentry\/test", \{ method: "POST" \}\)/);
  assert.match(src, /data-testid="sentry-sent"/);
  assert.match(read("src/pages/admin/AdminContext.tsx"), /sentry\?: boolean;/);
  const main = readFileSync(new URL("../../backend/app/main.py", import.meta.url), "utf8");
  assert.match(main, /"sentry": error_alerts\.enabled\(\)/);
  assert.match(main, /@app\.post\("\/admin\/sentry\/test"\)\ndef admin_sentry_test\(profile=Depends\(admin\.admin_profile\)\):/);
});
