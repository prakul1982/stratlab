import { useEffect, useState } from "react";
import { CFG } from "../lib/config";
import { publicGet } from "../lib/http";

/** FREE-TIER: the sample deck, for Free and visitors (Free has no slide decks of its own): one theme deck already kept on the server
 * (backend app/sample_deck.py), downloaded as it was made; nothing is counted. Drawn only when the server has one to give. */
export function SampleDeckLink({ label = "Download a sample deck (PDF)", className = "link" }: { label?: string; className?: string }) {
  const [theme, setTheme] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    publicGet<{ available: boolean; theme: string | null }>("/pricing/sample-deck/info")
      .then((r) => { if (live && r.available) setTheme(r.theme ?? ""); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  if (theme == null || !CFG.API_BASE) return null;
  return (
    <a className={className} href={`${CFG.API_BASE}/pricing/sample-deck`} download data-testid="sample-deck"
      title={theme ? `A real theme deck: ${theme}` : undefined}>{label}{theme ? `: ${theme}` : ""}</a>
  );
}
