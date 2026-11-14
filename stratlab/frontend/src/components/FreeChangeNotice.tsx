import { useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { CHANGE_KEEPS, changeDay, changeRows, changeSeenKey, changeTitle } from "../lib/freeChange";

/** FREE-TIER: the one-time notice for an account in its grace (me.free_change): when its Free counts change and each change, old and
 * new. Account has it in full, as a Limit / Now / From table (LIVE8B-006: twelve sentences in a box, twice); My space has one line
 * linking to it, so its cards stay on the first screen. "Got it" hides it on both pages for good (on this device); nothing is emailed. */
export function FreeChangeNotice({ line = false }: { line?: boolean }) {
  const { me } = useApp();
  const fc = me?.free_change ?? null;
  const key = fc ? changeSeenKey(fc) : "";
  const [seen, setSeen] = useState(() => {
    try { return !!key && localStorage.getItem(key) === "1"; } catch { return false; }
  });
  if (!fc || seen) return null;
  const done = () => {
    try { localStorage.setItem(key, "1"); } catch { /* private window: hidden for this visit */ }
    setSeen(true);
  };
  const got = <button type="button" className="btn sm" onClick={done}>Got it</button>;
  if (line) {
    return (
      <div className="k-notice warn free-change-line" role="status" aria-label={changeTitle(fc)} data-testid="free-change">
        <span><b>{changeTitle(fc)}.</b> <Link className="link" to="/account#free-change">See what changes</Link></span>{got}
      </div>
    );
  }
  const day = changeDay(fc.on);
  return (
    <section className="k-notice warn free-change" id="free-change" role="status" aria-label={changeTitle(fc)} data-testid="free-change">
      <div className="free-change-head"><b>{changeTitle(fc)}.</b>{got}</div>
      <p>Your account keeps the Free plan's old limits until then.</p>
      <div className="k-tbl-wrap"><table className="k-table">
        <thead><tr><th scope="col">Limit</th><th scope="col" className="k-num">Now</th><th scope="col" className="k-num">From {day}</th></tr></thead>
        <tbody>{changeRows(fc).map(([label, now, after]) => <tr key={label}><th scope="row">{label}</th><td className="k-num">{now}</td><td className="k-num">{after}</td></tr>)}</tbody>
      </table></div>
      {fc.moves.length + (fc.over?.length ?? 0) > 0 && <ul className="k-list">{fc.moves.map((m) => <li key={m}>{m}, from {day}</li>)}{(fc.over ?? []).map((m) => <li key={m}>{m}</li>)}</ul>}
      <p>{CHANGE_KEEPS} <Link className="link" to="/plans">See plans</Link></p>
    </section>
  );
}
