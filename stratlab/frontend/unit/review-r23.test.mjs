// Round 23 (emails and reliability): "Send me a test" in Admin → Email previews answers every press with a line that stays.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { sentLine, sendErrorLine, clock } = await import("../src/pages/admin/testSend.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("R23-009: each press's line names the email, the address and the time, so two presses read differently", () => {
  const a = new Date(2026, 9, 15, 9, 5, 7), b = new Date(2026, 9, 15, 9, 5, 19);
  assert.equal(clock(a), "09:05:07");
  assert.equal(sentLine("[Test] Welcome to StratLab", "owner@example.com", a),
    '"[Test] Welcome to StratLab" sent to owner@example.com at 09:05:07. Check your inbox (and spam).');
  assert.notEqual(sentLine("s", "t", a), sentLine("s", "t", b));
  assert.equal(sendErrorLine({ message: "You've sent 5 test emails this hour. Try again later" }, a),
    "Not sent (09:05:07): You've sent 5 test emails this hour. Try again later.");
  assert.equal(sendErrorLine(null, a), "Not sent (09:05:07): The test email couldn't be sent. Try again.");
});

test("R23-009: the button is disabled while sending, a second press does nothing, and the answer stays on the page", () => {
  const src = read("src/pages/admin/EmailSection.tsx");
  assert.match(src, /if \(sending\.current\) return;/);
  assert.match(src, /disabled=\{busy\} aria-busy=\{busy\}/);
  assert.match(src, /setResult\(\{ ok: true, text: line \}\)/);
  assert.match(src, /setResult\(\{ ok: false, text: sendErrorLine\(e, new Date\(\)\) \}\)/);
  assert.match(src, /role=\{result\.ok \? "status" : "alert"\} data-testid="test-send-result"/);
  assert.match(src, /finally \{ sending\.current = false; setBusy\(false\); \}/);
});
