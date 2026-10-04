import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly } from "../lib/format";

type Status = { last_try?: number; last_ok?: number; error?: string | null; schemes?: number; month?: string; running: boolean;
  stored: number; months: number; newest: string | null };
type State = { status: Status; check: { state: "pass" | "warn" | "fail"; detail: string } };

const iso = (t?: number) => (t ? new Date(t * 1000).toISOString() : null);

/** Admin: how the TER disclosure reads for fund costs have gone, and a button to read it now. */
export function TerAdminPanel() {
  const { fail } = useApp();
  const [s, setS] = useState<State | null>(null);
  const load = useCallback(async () => { try { setS(await api<State>("/admin/ter")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!s?.status.running) return;
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, [s?.status.running, load]);
  const read = async () => {
    try { await api("/admin/ter/read", { method: "POST" }); load(); } catch (e) { fail(e); }
  };
  const st = s?.status;
  return (
    <section className="card stack" style={{ gap: 10 }} aria-label="Fund costs (TER)">
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2">Fund costs (TER)</h2>
        {s && <span className={`badge ${s.check.state === "pass" ? "next" : "skip"}`}>{s.check.state === "pass" ? "OK" : s.check.state === "warn" ? "Warning" : "Failing"}</span>}
      </div>
      <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>The public TER disclosure behind Mutual funds → What your funds cost. Read by itself every 12 hours when someone opens the page, and checked every day.</p>
      {!st ? <p className="small muted">Loading…</p> : (
        <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
          <div className="small">
            {st.last_ok ? <>Last good read {ago(iso(st.last_ok)!)} · {st.schemes ?? 0} schemes for {st.month}</> : "Never read"}
            {" · "}{st.stored.toLocaleString("en-IN")} schemes stored over {st.months} months{st.newest ? `, newest TER ${dateOnly(st.newest)}` : ""}
            {st.error && <div className="small" style={{ color: "var(--red-ink, #b42318)" }}>Last error{st.last_try ? ` (${ago(iso(st.last_try)!)})` : ""}: {st.error}</div>}
            <div className="tiny muted">{s!.check.detail}</div>
          </div>
          <button className="btn sm" disabled={st.running} onClick={read}>{st.running ? "Reading…" : "Read now"}</button>
        </div>
      )}
    </section>
  );
}
