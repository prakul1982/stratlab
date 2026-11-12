import { useState } from "react";
import { useApp } from "../lib/app";
import { shareLink } from "../lib/share";
import { sharedNote, type ShareMade } from "../lib/researchShare";
import { researchShareApi } from "../lib/researchShareApi";
import type { Region } from "../lib/research";
import { track } from "../lib/analytics";
import { Share } from "./Icons";

/** "Share link" on a deep dive or a theme: the server keeps a dated public teaser of it at /r/<token> (no account details in it),
 *  then the phone's share sheet or, on a computer, the link copied. Counted against the plan's share links a month; over the
 *  limit the page's own upgrade message shows (fail). */
export function ShareResearchButton({ kind, region, target, label }: { kind: "deep" | "theme"; region: Region; target: string; label: string }) {
  const { notify, fail } = useApp();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const out: ShareMade = kind === "deep" ? await researchShareApi.deep(region, target) : await researchShareApi.theme(region, target);
      const r = await shareLink({ url: out.url, title: `${out.title} on StratLab`, text: `${out.title}: a snapshot from StratLab.` });
      if (r !== "cancelled") track("research shared", { kind, region, channel: r });
      if (r === "copied") notify(sharedNote(kind));
      else if (r === "shown") notify(`Your link: ${out.url}`);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <button type="button" className="btn quiet sm" onClick={() => void run()} disabled={busy} data-testid="share-research"
      title={`A public link to a dated snapshot of ${label}: the headline facts and a way into StratLab`}>
      <Share size={16} /> {busy ? "Making the link…" : "Share link"}
    </button>
  );
}
