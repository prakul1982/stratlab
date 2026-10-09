/* Why an AI read is missing, in plain words, and whether asking again can help. Plain functions (no React), so the words
 * can be tested alone. */

/** The daily cap on fresh AI reads is the reason (the server's research_ai_limit message). */
export function aiLimited(message: string | null): boolean {
  return !!message && /fresh AI reads|used \d+|allowance/i.test(message);
}

/** Why an AI read is missing, as the words that follow "No AI read right now": a few plain words, never the message
 * itself, which can be long or name an internal step. When the cause isn't one worth naming, nothing is said of it. */
export function aiReason(message: string | null): string {
  if (message && /hasn't updated|haven't updated|previous session/i.test(message)) return `: ${message.replace(/\.?\s*Ask again in a minute\.?$/i, "")}. Ask again in a minute.`;
  if (message && /busy|overloaded|try again in/i.test(message)) return ": the AI service is busy. Ask again in a minute.";
  // the cap: no "Ask again" beside it (aiLimited), and when it comes back (R8O-002)
  if (aiLimited(message) || (message && /limit|tomorrow/i.test(message)))
    return ": today's fresh AI reads on your plan are used up. Reads already written still open, and the count starts again at midnight India time.";
  if (message && /plan|upgrade/i.test(message)) return ": it isn't on your plan.";
  return ". Ask again in a moment.";
}

/** Account's line for the cap: "3 of 60 (starts again at midnight India time)", or "3 (no daily cap on Pro)". */
export function aiReadsUse(used: number, limit: number | null, capFor: string | null): string {
  if (limit == null) return `${used.toLocaleString("en-IN")} (no daily cap${capFor === "admin" ? " for the site's admins" : " on Pro"})`;
  return `${used.toLocaleString("en-IN")} of ${limit.toLocaleString("en-IN")} (starts again at midnight India time)`;
}
