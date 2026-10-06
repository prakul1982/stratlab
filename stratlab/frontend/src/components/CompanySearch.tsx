import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { useRotating } from "../lib/rotating";
import { researchApi, type Region } from "../lib/research";
import { Search } from "./Icons";

/** The company search box. In its own file so the home page can show it without loading the research pages. */
export function CompanySearch({ region, autoFocus, onPick, placeholder }: {
  region: Region; autoFocus?: boolean; onPick?: (symbol: string) => void; placeholder?: string;
}) {
  const example = useRotating(region === "IN" ? ["Apollo Hospitals", "HDFC Bank", "Titan", "Tata Motors", "Polycab", "Dixon"]
    : ["Nvidia", "Apple", "Costco", "Vertiv", "Eli Lilly"], 3200);
  const nav = useNavigate();
  const { fail } = useApp();
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<{ symbol: string; name: string; exchange: string }[] | null>(null);
  const [active, setActive] = useState(0);
  const timer = useRef<number>(undefined);
  useEffect(() => { setQ(""); setRows(null); }, [region]);
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (q.trim().length < 1) { setRows(null); return; }
    timer.current = window.setTimeout(async () => {
      try { setRows(await researchApi.search(region, q.trim())); setActive(0); } catch (e) { fail(e); }
    }, 250);
  }, [q, region, fail]);
  const pick = (sym: string) => {
    setQ(""); setRows(null);
    if (onPick) onPick(sym); else nav(`/research/${region}/${encodeURIComponent(sym)}`);
  };
  const submit = () => {
    if (rows?.length) pick(rows[active]?.symbol ?? rows[0].symbol);
    else if (q.trim()) pick(q.trim().toUpperCase());
  };
  return (
    <label className="search-box">
      <Search />
      <span className="sr-only">Search companies</span>
      <input autoFocus={autoFocus} value={q} onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); submit(); }
          else if (e.key === "Escape") setQ("");
          else if (e.key === "ArrowDown" && rows) { e.preventDefault(); setActive((a) => Math.min(rows.length - 1, a + 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
        }}
        placeholder={placeholder ?? `Try “${example}”`} aria-label={region === "IN" ? "Search any company listed in India (NSE or BSE)" : "Search any US company"} />
      {rows && (
        <div className="results">
          {rows.length === 0 && <p className="small muted results-none">No matches. Press Enter to try "{q.toUpperCase()}" as a ticker.</p>}
          {rows.map((r, i) => (
            <button key={r.symbol} type="button" className={i === active ? "on" : undefined} onClick={() => pick(r.symbol)}>
              <span><b>{r.symbol}</b> <span className="small muted">{r.name}</span></span>
              <span className="small muted">{r.exchange}</span>
            </button>
          ))}
        </div>
      )}
    </label>
  );
}
