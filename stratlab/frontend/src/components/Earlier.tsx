import { useState, type ReactNode } from "react";

/* Finished things (closed trades, old orders, fired alerts, past dates) folded under one line, closed until asked:
 * "Earlier trades (12) · ₹4,200 after costs". What is current goes above it; nothing is deleted, only tucked away. */

/** The calendar day of a moment in a time zone, as 2026-10-04, which compares and sorts as text ("" when unreadable). */
export function dayIn(iso: string, tz: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-CA", { timeZone: tz });
}

/** The viewer's own time zone, for things that happen to them rather than on an exchange. */
export const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata";

/** Items split into today's and earlier ones, by the day each one happened in the time zone. */
export function splitToday<T>(items: T[], at: (x: T) => string, tz: string, now: Date = new Date()) {
  const today = dayIn(now.toISOString(), tz);
  const out = { today: [] as T[], earlier: [] as T[] };
  for (const x of items) (dayIn(at(x), tz) >= today ? out.today : out.earlier).push(x);
  return out;
}

/** The fold itself. Its contents are only drawn once it is opened, so a long history costs nothing until then. */
export function Earlier({ label, count, note, open = false, className = "", children }: {
  label: string; count: number; note?: ReactNode; open?: boolean; className?: string; children: ReactNode;
}) {
  const [shown, setShown] = useState(open);
  if (!count) return null;
  return (
    <details className={`earlier ${className}`.trim()} open={shown} onToggle={(e) => setShown(e.currentTarget.open)}>
      <summary>
        <span className="earlier-label">{label} <span className="muted">({count.toLocaleString("en-IN")})</span></span>
        {note && <span className="earlier-note">{note}</span>}
      </summary>
      {shown && <div className="earlier-body">{children}</div>}
    </details>
  );
}
