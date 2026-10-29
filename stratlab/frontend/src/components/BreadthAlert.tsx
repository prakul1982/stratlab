import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { breadthApi, shortDay, type BreadthAlerts, type Group } from "../lib/breadth";
import { DataTable, Dialog, Field, FormActions, FormGrid } from "./kit";
import { Bell } from "./Icons";

/* "Alert me" on the table's Above 50-day average row (MOOD-1, owner: "why is the alerts here": it was a full-width card between the
 * figures and the charts). The same alert as before (the same API, the same plan rules and limit): a message after the close when the
 * share of a group's stocks above their 50-day average crosses a level. The row's button says the level when one is set. */
export function BreadthAlertButton({ group }: { group: Group }) {
  const { fail, notify } = useApp();
  const [alerts, setAlerts] = useState<BreadthAlerts | null>(null);
  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState("60");
  const [busy, setBusy] = useState(false);
  useEffect(() => { breadthApi.alerts().then(setAlerts).catch(() => setAlerts(null)); }, []);
  const n = Number(level);
  const ok = level.trim() !== "" && Number.isFinite(n) && n >= 1 && n <= 99;
  // DE-024: a level the alert can't take says why, not only a greyed-out button
  const why = level.trim() === "" ? "Enter a level from 1 to 99%." : !ok ? "The level is a share of stocks: a number from 1 to 99." : null;
  const mine = alerts?.items ?? [];
  const here = mine.filter((a) => a.group === group.id);
  const name = (id: string) => (id === group.id ? group.name : id);
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ok) return;
    setBusy(true);
    try {
      setAlerts(await breadthApi.addAlert(group.id, n));
      notify(`You'll get a message after the close when ${group.name}'s share above the 50-day average crosses ${n}%.`);
    } catch (err) { fail(err); } finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    try { setAlerts(await breadthApi.deleteAlert(id)); } catch (e) { fail(e); }
  };
  return (
    <>
      <button type="button" className="btn quiet sm" data-testid="breadth-alert-open" onClick={() => setOpen(true)}
        aria-label={here.length ? `Alert at ${here.map((a) => `${a.level}%`).join(" and ")} on ${group.name}'s share above the 50-day average` : `Alert me when ${group.name}'s share above the 50-day average crosses a level`}>
        <Bell size={17} />{here.length ? `Alert at ${here.map((a) => `${a.level}%`).join(", ")}` : "Alert me"}
      </button>
      {open && (
        <Dialog title="Alert on the share above the 50-day average" onClose={() => setOpen(false)}>
          <div className="k-stack" data-testid="breadth-alerts">
            <p className="k-small">Checked once a day, after the counts for the close are in. You get one message each time the share moves from one side of your level to the other, by phone notification, Telegram or email, whichever you set up in <Link className="link" to="/settings#notifications">Settings</Link>. Up to {alerts?.limit ?? 5}.</p>
            <FormGrid label="New breadth alert" onSubmit={add} inline>
              <Field label="Alert level" unit="%" inputMode="decimal" value={level} onChange={(e) => setLevel(e.target.value)} aria-invalid={!ok}
                aria-label={`Alert me when the share of ${group.name} stocks above their 50-day average crosses`} />
              {why && <p className="k-note k-down k-field wide" role="alert" data-testid="breadth-alert-why">{why}</p>}
              {ok && alerts && mine.length >= alerts.limit && <p className="k-note k-field wide">You have the {alerts.limit} alerts a plan keeps: delete one to add another.</p>}
              <FormActions>
                <button className="btn" disabled={!ok || busy || (alerts ? mine.length >= alerts.limit : false)}>Add alert</button>
              </FormActions>
            </FormGrid>
            {mine.length > 0 && (
              <DataTable stack label="Your breadth alerts" rows={mine} rowKey={(a) => a.id}
                columns={[{ key: "g", header: "Group", rowHeader: true, cell: (a) => name(a.group) },
                  { key: "l", header: "Crosses", numeric: true, cell: (a) => `${a.level}%` },
                  { key: "s", header: "Now", cell: (a) => a.side ?? "–" },
                  { key: "f", header: "Last sent", cell: (a) => (a.fired_at ? shortDay(a.fired_at.slice(0, 10)) : "–") },
                  { key: "x", header: "", action: true, cell: (a) => <button className="btn quiet sm" aria-label={`Delete the alert at ${a.level}% on ${name(a.group)}`} onClick={() => remove(a.id)}>Delete</button> }]} />
            )}
            {alerts && !alerts.channels.length && <p className="k-note">Set up a phone, Telegram or a confirmed email in <Link className="link" to="/settings#notifications">Settings</Link> for alerts to reach you.</p>}
          </div>
        </Dialog>
      )}
    </>
  );
}
