import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { dateOnly } from "../lib/format";

type Inbox = { ready: boolean; address: string | null; last: { at: string; via: string } | null };

/** Beside a statement upload (Mutual funds): the statement inbox of Settings → Connected accounts, so the statement can arrive by
 * itself instead of being uploaded each time (owner, 5 Nov: "why don't we add the option we made for automating it"). Off, it says
 * what it does and links to setting it up; on, it shows the person's own address. Says nothing while it loads, when the inbox
 * isn't open on this server, or when it can't be read: the upload beside it works either way. */
export function InboxNote({ what = "statement" }: { what?: string }) {
  const [box, setBox] = useState<Inbox | null>(null);
  useEffect(() => { api<{ inbox: Inbox }>("/connect").then((c) => setBox(c.inbox)).catch(() => setBox(null)); }, []);
  if (!box?.ready) return null;
  return (
    <div className="k-line-row k-inbox-note stack-narrow" data-testid="inbox-note">
      {box.address ? (
        <span className="k-line-text">
          <b>Statement inbox is on</b>
          <span className="k-sub-line">Forward the {what} email from CAMS, KFintech or MF Central to <code className="k-address">{box.address}</code> and it is read when it arrives{box.last ? `; the last came ${dateOnly(box.last.at)}` : ""}.</span>
        </span>
      ) : (
        <span className="k-line-text">
          <b>Or let it arrive by itself</b>
          <span className="k-sub-line">Forward the {what} email from CAMS, KFintech or MF Central to a private StratLab address, once, and each one is read when it arrives.</span>
        </span>
      )}
      <Link className="btn quiet sm" to="/settings#inbox">{box.address ? "Inbox settings" : "Set up the inbox"}</Link>
    </div>
  );
}
