import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { SourceChip } from "./kit/SourceChip";

type Inbox = { ready: boolean; address: string | null; last: { at: string; via: string } | null };

/** "u-…@in.stratlab.studio": the address, short, for a chip (the whole of it in its title, and copied whole). */
export const shortAddress = (a: string) => a.replace(/^([^@]{2})[^@]+@/, "$1…@");

/** Beside a statement upload (Mutual funds): the statement inbox of Settings → Connected accounts, so the statement can arrive by
 * itself instead of being uploaded each time (owner, 5 Nov: "why don't we add the option we made for automating it"). On, one chip
 * (R15 #6, owner 7 Nov: "same compact style"): "● Inbox on · u-…@in.stratlab.studio", then Copy and Settings. Off, one muted line with
 * the way to set it up. Says nothing while it loads, when the inbox isn't open on this server, or when it can't be read: the upload
 * beside it works either way. */
export function InboxNote({ what = "statement" }: { what?: string }) {
  const { notify } = useApp();
  const [box, setBox] = useState<Inbox | null>(null);
  useEffect(() => { api<{ inbox: Inbox }>("/connect").then((c) => setBox(c.inbox)).catch(() => setBox(null)); }, []);
  if (!box?.ready) return null;
  const address = box.address;
  if (!address) {
    return (
      <p className="k-note k-inbox-note" data-testid="inbox-note">
        Or let it arrive by itself: forward the {what} email from CAMS, KFintech or MF Central to a private StratLab address, once.{" "}
        <Link className="link" to="/settings#inbox">Set up the inbox</Link>
      </p>
    );
  }
  const copy = async () => {
    try { await navigator.clipboard.writeText(address); notify("Address copied."); } catch { notify("Select the address in Settings and copy it."); }
  };
  return (
    <div className="k-inbox-note" data-testid="inbox-note">
      <span className="sr-only">Statement inbox is on: forward the {what} email from CAMS, KFintech or MF Central to {address} and it is read when it arrives.</span>
      <SourceChip name="Inbox on" when={<span aria-hidden="true">{shortAddress(address)}</span>}
        title={`Forward the ${what} email from CAMS, KFintech or MF Central to ${address} and it is read when it arrives${box.last ? `; the last came ${dateOnly(box.last.at)}` : ""}.`}>
        <button type="button" className="btn quiet sm" onClick={() => void copy()} aria-label="Copy the inbox address">Copy</button>
        <Link className="btn quiet sm" to="/settings#inbox" aria-label="Inbox settings">Settings</Link>
      </SourceChip>
    </div>
  );
}
