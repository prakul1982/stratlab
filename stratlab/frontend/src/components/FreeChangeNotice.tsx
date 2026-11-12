import { useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { CHANGE_KEEPS, changeLines, changeSeenKey, changeTitle } from "../lib/freeChange";

/** FREE-TIER: the one-time notice on Account and My space for an account in its grace (me.free_change): when its Free counts change
 * and each change, old and new. "Got it" hides it on both pages for good (on this device); nothing is emailed. */
export function FreeChangeNotice() {
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
  return (
    <div className="k-notice warn" role="status" aria-label={changeTitle(fc)} data-testid="free-change">
      <span>
        <b>{changeTitle(fc)}.</b> Your account keeps the Free plan's old limits until then:
        <ul className="k-list">{changeLines(fc).map((l) => <li key={l}>{l}</li>)}</ul>
        {CHANGE_KEEPS} <Link className="link" to="/plans">See plans</Link>
      </span>
      <span className="k-row"><button type="button" className="btn sm" onClick={done}>Got it</button></span>
    </div>
  );
}
