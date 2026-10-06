import { useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { Badge, Card, CardHead, ConfirmDialog, EmptyState, Seg } from "../../components/kit";
import { useAdmin, type ReportedRow } from "./AdminContext";
import { AuditPanel, MarketAuditPanel, type Region } from "./AuditPanel";
import { RulesPanel } from "./RulesPanel";

/** Admin → Quality: the India and US audits and whole-market check, strategies users reported, and the rates and rules. */
export function QualitySection() {
  const { notify, fail } = useApp();
  const { reported, reload } = useAdmin();
  const [region, setRegion] = useState<Region>("IN");
  const [busy, setBusy] = useState<string | null>(null);
  const [asking, setAsking] = useState<ReportedRow | null>(null);

  const moderate = async (r: ReportedRow, action: "hide" | "restore" | "delete") => {
    setBusy(r.id);
    try {
      await api(`/admin/library/${r.id}`, { method: "POST", body: { action } });
      notify(action === "restore" ? "Back in the library, reports cleared." : action === "hide" ? "Hidden." : "Deleted.");
      setAsking(null); await reload();
    } catch (e) { fail(e); } finally { setBusy(null); }
  };
  const entries = reported?.entries ?? [];

  return (
    <>
      <div className="k-toolbar">
        <Seg label="Market" value={region} onChange={(v) => setRegion(v as Region)} options={[{ value: "IN", label: "India" }, { value: "US", label: "US" }]} />
      </div>
      <AuditPanel region={region} />
      <MarketAuditPanel region={region} />

      <Card label="Reported strategies">
        <CardHead title={`Reported strategies (${entries.length})`} info="An entry is hidden by itself after 3 reports from different people, until you look at it here." />
        {!entries.length ? <EmptyState title="Nothing reported">Library strategies that users report show up here.</EmptyState> : (
          <div className="k-stack">{entries.map((r) => (
            <div key={r.id} className="k-stack adm-reported">
              <div className="k-spread">
                <b>{r.name} <span className="k-small k-muted">by {r.author}{r.email ? ` (${r.email})` : ""}</span></b>
                {r.hidden ? <Badge tone="warn">Hidden{r.hidden_by === "admin" ? " by you" : " by reports"}</Badge> : <Badge>Showing</Badge>}
              </div>
              {r.description && <p className="k-small k-muted">{r.description}</p>}
              <span className="k-small">{r.reports} report{r.reports === 1 ? "" : "s"}{r.reports ? ": " + Object.entries(r.reasons).map(([k, n]) => `${reported?.reasons[k] ?? k} (${n})`).join(", ") : ""}</span>
              <div className="k-row">
                <button type="button" className="btn quiet sm" disabled={busy === r.id} onClick={() => moderate(r, "restore")}>{r.hidden ? "Restore" : "Keep, clear reports"}</button>
                {!r.hidden && <button type="button" className="btn quiet sm" disabled={busy === r.id} onClick={() => moderate(r, "hide")}>Hide</button>}
                <button type="button" className="btn quiet sm danger" disabled={busy === r.id} onClick={() => setAsking(r)}>Delete</button>
              </div>
            </div>
          ))}</div>
        )}
      </Card>

      <RulesPanel />
      {asking && <ConfirmDialog title={`Delete "${asking.name}"?`} confirmLabel="Delete for good" busy={busy === asking.id} onConfirm={() => moderate(asking, "delete")} onClose={() => setAsking(null)}>It leaves the library for good.</ConfirmDialog>}
    </>
  );
}
