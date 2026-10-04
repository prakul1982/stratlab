import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly } from "../lib/format";

type RegionStatus = { ran_at?: string; started_at?: string; as_of?: string; stocks?: number; loaded?: number; failed?: number;
  last_error?: string | null; failed_at?: string };
type State = { status: Record<string, RegionStatus>; running: string | null };

const NAMES: Record<string, string> = { IN: "India", US: "US" };

/** Admin: market breadth's last run per market, and a button to work it out now instead of waiting for the evening job. */
export function BreadthAdminPanel() {
  const { fail } = useApp();
  const [s, setS] = useState<State | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const load = useCallback(async () => { try { setS(await api<State>("/admin/breadth")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!s?.running) return;
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [s?.running, load]);
  const run = async (region: string) => {
    setNote(null);
    try {
      await api(`/admin/breadth/run?region=${region}&full=true`, { method: "POST" });
      setNote(`${NAMES[region]} started. The first run reads about two years of prices: a few minutes for the US, 20–25 minutes for India (it needs the day's broker login; use "Log in now" in Services if it isn't done).`);
      load();
    } catch (e) { fail(e); }
  };

  return (
    <section className="card stack" style={{ gap: 10 }} aria-label="Market breadth">
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2">Market breadth</h2>
        {s?.running && <span className="badge running">Running: {NAMES[s.running] ?? s.running}</span>}
      </div>
      <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>
        Worked out by itself after each market's close. Run it now to fill it in without waiting (the whole two years).
      </p>
      {!s ? <p className="small muted">Loading…</p> : (
        <div className="stack" style={{ gap: 8 }}>
          {["IN", "US"].map((r) => {
            const st = s.status?.[r] || {};
            const failedLast = st.failed_at && (!st.ran_at || st.failed_at > st.ran_at);
            return (
              <div key={r} className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
                <div className="small">
                  <b>{NAMES[r]}</b>{" · "}
                  {st.ran_at ? <>last run {ago(st.ran_at)}{st.as_of && <> · prices to {dateOnly(st.as_of)}</>}
                    {st.loaded != null && <> · {st.loaded.toLocaleString("en-IN")} stocks read{st.failed ? `, ${st.failed} failed` : ""}</>}</> : "not run yet"}
                  {failedLast && st.last_error && <div className="small" style={{ color: "var(--red-ink, #b42318)" }}>Last try failed: {st.last_error}</div>}
                </div>
                <button className="btn sm" disabled={!!s.running} onClick={() => run(r)} aria-label={`Run market breadth for ${NAMES[r]} now`}>
                  {s.running === r ? "Running…" : "Run now"}
                </button>
              </div>
            );
          })}
        </div>
      )}
      {note && <p className="small muted" role="status" style={{ margin: 0 }}>{note}</p>}
    </section>
  );
}
