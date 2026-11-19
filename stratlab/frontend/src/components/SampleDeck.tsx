import { useEffect, useState } from "react";
import { CFG } from "../lib/config";
import { publicGet } from "../lib/http";

type Sample = { theme: string; id: string | null } | null;
let asked: Promise<Sample | undefined> | undefined;

/** The server's sample deck, read once per page load and shared: null when it has none to give (LIVE15A-003: the words that promise one
 * are left out then), undefined until known or when the read failed (asked again next time). */
export function useSampleDeck(): Sample | undefined {
  const [got, setGot] = useState<Sample | undefined>(undefined);
  useEffect(() => {
    let live = true;
    asked ??= publicGet<{ available: boolean; theme: string | null; id?: string | null }>("/pricing/sample-deck/info")
      .then((r) => (r.available ? { theme: r.theme ?? "", id: r.id ?? null } : null), () => { asked = undefined; return undefined; });
    void asked.then((s) => { if (live) setGot(s); });
    return () => { live = false; };
  }, []);
  return got;
}

/** FREE-TIER: the sample deck, for Free and visitors (Free has no slide decks of its own): one theme deck already kept on the server
 * (backend app/sample_deck.py), downloaded as it was made; nothing is counted. Drawn only when the server has one to give. */
export function SampleDeckLink({ label = "Download a sample deck (PDF)", className = "link" }: { label?: string; className?: string }) {
  const s = useSampleDeck();
  if (!s || !CFG.API_BASE) return null;
  const { theme, id } = s;
  // the deck the label names, by its id (LIVE12B-021: "Cement" downloaded the Oil and gas deck kept after the page read which one it was)
  return (
    <a className={className} href={`${CFG.API_BASE}/pricing/sample-deck${id ? `?id=${encodeURIComponent(id)}` : ""}`} download data-testid="sample-deck"
      title={theme ? `A real theme deck: ${theme}` : undefined}>{label}{theme ? `: ${theme}` : ""}</a>
  );
}
