import type { CheckStatus } from "./types";
import { signCls } from "./format";

/** The class for a gain or a loss in the kit's colours (green up, red down, nothing at zero or when unknown). */
export const upDown = (v: number | null | undefined): string => signCls(v);

/** The kit Badge tone for a check's status. */
/** Every verdict runs the same four checks (unseen data, nearby settings, bad-luck drawdown, enough trades). */
export const CHECKS = 4;

/** "3 of 4 checks passed · 1 not run": counted out of the same four everywhere (a check can be skipped, say nearby
 * settings on a group of stocks, but it is still one of the four). `run` is how many weren't skipped. */
export function checksLine(passed: number, run: number, notRun?: string[]): string {
  const skipped = Math.max(0, CHECKS - run);
  // with the names of the checks that didn't run, say which (R5O-014: "1 not run" alone left people guessing)
  const which = notRun?.length === skipped && skipped ? ` · ${notRun.join(" and ")} not run` : skipped ? ` · ${skipped} not run` : "";
  return `${passed} of ${CHECKS} checks passed${which}`;
}

/** The checks' plain names, for "nearby settings not run". */
export const CHECK_NAMES: Record<string, string> = { unseen: "unseen years", nearby: "nearby settings", shuffle: "bad-luck fall", sample: "enough trades" };

export const checkTone =(s: CheckStatus | "pass" | "warn" | "fail" | "skip"): "ok" | "warn" | "plain" => (s === "pass" ? "ok" : s === "fail" ? "warn" : "plain");
