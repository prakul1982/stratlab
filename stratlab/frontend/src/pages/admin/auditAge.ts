import { fmtDate } from "../../lib/format";

export const STALE_DAYS = 7;          // a hand-run audit older than this is shown as history (DJ-028, owner 5 Nov)

/** The day a finished hand-run audit ended ("3 Oct"), when that was more than STALE_DAYS ago, else null (DJ-028). An old audit's results are
 * history, not today's problems (owner, 5 Nov: "why is it still showing mismatches, errors etc" for a 33-day-old run with 403 price errors):
 * the panel folds them, closed, under "Last hand-run audit, 3 Oct (old)" with the counts greyed, and nothing counts them as an issue
 * (the Overview's list reads the whole-market check only: attention.ts). The data is kept; a fresh run replaces it. */
export function oldAudit(finishedAt: string | null | undefined, now = Date.now()): { days: number; day: string } | null {
  const t = finishedAt ? Date.parse(finishedAt) : NaN;
  if (!Number.isFinite(t)) return null;
  const days = Math.floor((now - t) / 86400000);
  return now - t > STALE_DAYS * 86400000 ? { days, day: fmtDate(finishedAt!, { year: false }) } : null;
}
