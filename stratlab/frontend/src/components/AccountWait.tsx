import { useEffect, useState } from "react";
import { useApp } from "../lib/app";
import { ErrorState, Skeleton } from "./kit";
import { LoadFailed, OPEN_TIMEOUT_MS } from "./LoadGuard";

/** What a page shows while it waits for the account (`/me`). While it loads: a skeleton. When it failed: what happened
 * and a Retry button, never a spinner that waits forever (R5O-002). */
export function AccountWait({ label }: { label: string }) {
  const { meError, refreshMe } = useApp();
  const [busy, setBusy] = useState(false);
  const [stuck, setStuck] = useState(false);
  // still nothing after OPEN_TIMEOUT_MS and no error: say so with Reload, not a skeleton for ever (R29B-003)
  useEffect(() => { const t = window.setTimeout(() => setStuck(true), OPEN_TIMEOUT_MS); return () => window.clearTimeout(t); }, []);
  if (!meError && stuck) return <LoadFailed what="this page" />;
  if (!meError) return <Skeleton label={label} />;
  const retry = () => { setBusy(true); void refreshMe().finally(() => setBusy(false)); };
  return (
    <ErrorState title="Your account didn't load" action={{ label: busy ? "Trying again…" : "Retry", onClick: busy ? undefined : retry }}>
      {meError}
    </ErrorState>
  );
}

/** The Retry button beside the "couldn't load your account" line at the top of every page. */
export function AccountRetry() {
  const { refreshMe } = useApp();
  const [busy, setBusy] = useState(false);
  return (
    <button type="button" className="btn sm quiet account-retry" disabled={busy}
      onClick={() => { setBusy(true); void refreshMe().finally(() => setBusy(false)); }}>
      {busy ? "Trying again…" : "Retry"}
    </button>
  );
}
