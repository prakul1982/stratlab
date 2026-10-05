// Chart replay: the page's running simulation against the server's own answers (fixtures/replay.json, written by
// stratlab/backend/tests/test_replay.py from app/replay.py). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as R from "../src/lib/replay.ts";

const fx = JSON.parse(readFileSync(new URL("./fixtures/replay.json", import.meta.url), "utf8"));
const close = (got, want, what) => assert.ok(Math.abs(got - want) <= Math.max(1e-6, 1e-9 * Math.abs(want)), `${what}: ${got} vs ${want}`);

for (const c of fx.cases) {
  test(`${c.name}${c.close_at_end ? "" : " (left open)"} matches the server`, () => {
    const got = R.simulate(c.bars, c.orders, c.first, c.cursor, c.kind, c.rates, c.step, c.close_at_end);
    assert.equal(got.trades.length, c.want.trades.length, "trades");
    got.trades.forEach((t, i) => {
      const w = c.want.trades[i];
      for (const k of ["side", "why", "entry_i", "exit_i", "entry_t", "exit_t", "fills"]) assert.equal(t[k], w[k], `trade ${i} ${k}`);
      for (const k of ["qty", "entry", "exit", "gross", "charges", "net"]) close(t[k], w[k], `trade ${i} ${k}`);
    });
    assert.deepEqual(got.skipped.map((s) => s.why), c.want.skipped);
    if (!c.want.position) assert.equal(got.position, null);
    else {
      for (const k of ["side", "stop", "target"]) assert.equal(got.position[k], c.want.position[k], `position ${k}`);
      for (const k of ["qty", "avg", "mark", "unrealised"]) close(got.position[k], c.want.position[k], `position ${k}`);
    }
  });
}

test("quantities round down to the step like the server's", () => {
  assert.equal(R.floorTo(140, 65), 130);
  assert.equal(R.floorTo(0.30000000000000004, 0.1), 0.3);
  assert.equal(R.floorTo(-1, 1), 0);
});
