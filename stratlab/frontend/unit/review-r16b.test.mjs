import test from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

const { indexWhen, SETTLING } = await import("../src/lib/research.ts");
const { pulseLede } = await import("../src/lib/researchFormat.ts");

test("R16B-002: Pulse says the close is settling as the stock pages do", () => {
  const day = (d) => "14 Oct";
  assert.equal(indexWhen({ day: "2026-10-14", live: false, stale: false, settling: true }, day), "14 Oct · closing prints still settling");
  assert.match(pulseLede(null, "14 Oct", true), new RegExp(`^${SETTLING} · 14 Oct: index levels`));
  assert.match(pulseLede(null, "14 Oct", false), /^Last close, 14 Oct: index levels/);
});
