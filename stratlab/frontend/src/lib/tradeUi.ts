import type { CheckStatus } from "./types";

/** The class for a gain or a loss in the kit's colours (green up, red down, nothing at zero or when unknown). */
export const upDown = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) || v === 0 ? "" : v > 0 ? "k-up" : "k-down");

/** The kit Badge tone for a check's status. */
/** Every verdict runs the same four checks (unseen data, nearby settings, bad-luck drawdown, enough trades). */
export const CHECKS = 4;

/** "3 of 4 checks passed · 1 not run": counted out of the same four everywhere (a check can be skipped, say nearby
 * settings on a group of stocks, but it is still one of the four). `run` is how many weren't skipped. */
export function checksLine(passed: number, run: number): string {
  const skipped = Math.max(0, CHECKS - run);
  return `${passed} of ${CHECKS} checks passed${skipped ? ` · ${skipped} not run` : ""}`;
}

export const checkTone =(s: CheckStatus | "pass" | "warn" | "fail" | "skip"): "ok" | "warn" | "plain" => (s === "pass" ? "ok" : s === "fail" ? "warn" : "plain");
