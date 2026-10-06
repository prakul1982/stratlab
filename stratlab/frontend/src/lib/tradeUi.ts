import type { CheckStatus } from "./types";

/** The class for a gain or a loss in the kit's colours (green up, red down, nothing at zero or when unknown). */
export const upDown = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) || v === 0 ? "" : v > 0 ? "k-up" : "k-down");

/** The kit Badge tone for a check's status. */
export const checkTone = (s: CheckStatus | "pass" | "warn" | "fail" | "skip"): "ok" | "warn" | "plain" => (s === "pass" ? "ok" : s === "fail" ? "warn" : "plain");
