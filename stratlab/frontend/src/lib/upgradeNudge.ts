/* A gentle upgrade prompt (conv101, P8; funnel 27 Nov: no moment ever asked a free user to pay). A Free account that has used 3 of its 5
 * backtests, or 3 of its 5 AI strategy builds, this month is told so once, with what Basic gives, beside the plan's own lock at the limit
 * (the server's 402, lib/app.tsx `fail`). The limits are the plan's own (from /me and lib/planCore): nothing here changes them. Once per
 * feature per month on this browser; never during the launch offer (every account is on Pro then) or while the owner views as a plan. */

export type NudgeUsage = { backtests_used?: number; backtests_limit?: number | null; ai_used?: number; ai_limit?: number | null };
export type Nudge = { key: string; kind: "backtests" | "ai"; text: string };

/** At this share of a monthly limit (and below the limit itself), the prompt is shown: 3 of 5. */
const SHARE = 0.6;

const FEATURES: { kind: Nudge["kind"]; used: keyof NudgeUsage; limit: keyof NudgeUsage; words: string; basic: (n: number | null) => string }[] = [
  { kind: "backtests", used: "backtests_used", limit: "backtests_limit", words: "free backtests", basic: (n) => (n == null ? "Basic has no limit" : `Basic gives ${n} a month`) },
  { kind: "ai", used: "ai_used", limit: "ai_limit", words: "free AI strategy builds", basic: (n) => (n == null ? "Basic has no limit" : `Basic gives ${n} a month`) },
];

/** The month as India counts it (the server's usage month): "2026-11". */
export function istMonth(now = Date.now()): string {
  return new Date(now + 5.5 * 3600_000).toISOString().slice(0, 7);
}

/** The prompt due now for this account, or null. `basic`: Basic's own limits ({backtests, ai}); `seen`: whether a key was shown already. */
export function nudgeFor(o: { plan?: string | null; viewAs?: string | null; usage?: NudgeUsage | null; basic: { backtests: number | null; ai: number | null };
  seen: (key: string) => boolean; now?: number }): Nudge | null {
  if (o.plan !== "free" || o.viewAs || !o.usage) return null;
  const month = istMonth(o.now);
  for (const f of FEATURES) {
    const used = o.usage[f.used], limit = o.usage[f.limit];
    if (typeof used !== "number" || typeof limit !== "number" || limit < 2) continue;
    if (used < Math.ceil(limit * SHARE) || used >= limit) continue;
    const key = `stratlab.nudge.${f.kind}.${month}`;
    if (o.seen(key)) continue;
    const left = limit - used;
    const text = `You've used ${used} of your ${limit} ${f.words} this month (${left} left). ${f.basic(f.kind === "backtests" ? o.basic.backtests : o.basic.ai)}.`;
    return { key, kind: f.kind, text };
  }
  return null;
}

/** Whether this browser has shown a prompt (storage off: shown at most once a page load, kept in memory). */
const memory = new Set<string>();
export function nudgeSeen(key: string): boolean {
  if (memory.has(key)) return true;
  try { return localStorage.getItem(key) === "1"; } catch { return false; }
}
export function markNudge(key: string): void {
  memory.add(key);
  try { localStorage.setItem(key, "1"); } catch { /* storage off: this page load only */ }
}
