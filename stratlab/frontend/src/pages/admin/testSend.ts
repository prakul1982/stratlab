/** Admin → Email previews → "Send me a test": the line that stays under the button after each press (R23-009: the
 * 4.5 s toast was the only answer, and a press that repeated the last toast's words looked like no answer at all). The
 * time makes each press's line its own. */

const two = (n: number) => String(n).padStart(2, "0");

export function clock(at: Date): string {
  return `${two(at.getHours())}:${two(at.getMinutes())}:${two(at.getSeconds())}`;
}

export function sentLine(subject: string, to: string, at: Date): string {
  return `"${subject}" sent to ${to} at ${clock(at)}. Check your inbox (and spam).`;
}

export function sendErrorLine(e: unknown, at: Date, fallback = "The test email couldn't be sent. Try again."): string {
  const msg = (e as { message?: unknown } | null)?.message;
  const why = typeof msg === "string" && msg.trim() ? msg.trim().replace(/\.?$/, ".") : fallback;
  return `Not sent (${clock(at)}): ${why}`;
}

/** Admin → System → "Send a test error": the line under the row after a press, with the time, saying whether it went to Sentry. */
export function sentryTestLine(r: { sentry_on: boolean; message: string }, at: Date): string {
  return r.sentry_on
    ? `Test error sent to Sentry at ${clock(at)}: "${r.message}". It should show in Sentry's Issues in a minute.`
    : `Not sent (${clock(at)}): Sentry is off on the server. Add SENTRY_DSN in Railway and restart to turn it on.`;
}
