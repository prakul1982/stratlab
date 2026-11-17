// LIVE10A (17 Nov 2026): the scored live review of Release 60. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10A-001: a market-hours mood copy served after the close says it was read during the session", () => {
  assert.match(read("src/pages/PulseMood.tsx"), /Read \{readAt\}\{m\.during \? ", during the session" : ""\}/);
  assert.match(read("src/lib/research.ts"), /during\?: boolean;/);
});

test("LIVE10A-010: while the newer session trades, the note says its figures so far are being read", async () => {
  const { moodBehindNote } = await import("../src/lib/pulseMood.ts");
  const dayText = (d) => (d === "2026-11-16" ? "16 Nov" : "17 Nov");
  assert.equal(moodBehindNote({ session: "2026-11-16", behind: "2026-11-17", is_open: true }, null, dayText),
    "These figures are of the 16 Nov session; the 17 Nov session's figures so far are being read.");
  assert.equal(moodBehindNote({ session: "2026-11-16", behind: "2026-11-17", is_open: false }, "2026-11-17", dayText),
    "These figures are of the 16 Nov session; the 17 Nov session's are being read.");
});
