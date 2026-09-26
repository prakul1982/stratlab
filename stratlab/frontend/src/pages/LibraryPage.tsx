import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { pct, signClass, TF_NAME } from "../lib/format";
import { opSay, refName } from "../lib/rules";
import type { Cond, Strategy, VerdictKind } from "../lib/types";
import { Search } from "../components/Icons";
import { Info, Loading, VerdictBadge } from "../components/ui";

export interface LibEntry {
  id: string; name: string; question: string; description: string; author: string; market: string;
  instrument: { symbol: string; name?: string } | null; group: { name: string; members?: unknown[] } | null;
  tf: string; side: string; range: { from: string; to: string } | null; strategy: Strategy;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number };
  stats: { ret: number | null; buy_hold: number | null; mdd: number | null; trades: number | null; unseen: number | null };
  published_at: string; copies: number; mine: boolean; reported?: boolean; hidden?: boolean;
}

const VERDICTS: [string, string][] = [["", "Any verdict"], ["edge", "Likely a real edge"], ["mixed", "Mixed evidence"], ["not_enough", "Not enough evidence"], ["luck", "Probably luck"], ["no_edge", "No edge here"]];
const line = (c: Cond) => `${refName(c.l)} ${opSay(c.op)} ${refName(c.r)}`;

function Rules({ s }: { s: Strategy }) {
  const parts: [string, Cond[]][] = [["Buy when", s.entry], ["Sell when", s.exit], ["Short when", s.shortEntry ?? []], ["Cover when", s.shortExit ?? []]];
  return (
    <div className="stack small" style={{ gap: 3 }}>
      {parts.filter(([, cs]) => cs?.length).map(([label, cs]) => (
        <span key={label}><b>{label}</b> {cs.map(line).join(s.entryJoin === "any" && label !== "Sell when" ? " or " : " and ")}</span>
      ))}
      {s.risk?.sl ? <span className="muted">Stop {s.risk.sl}{s.risk.stopType === "points" ? " points" : s.risk.stopType === "atr" ? "× ATR" : "%"}{s.risk.tgt ? ` · target ${s.risk.tgt}${s.risk.tgtType === "r" ? "R" : s.risk.tgtType === "points" ? " points" : "%"}` : ""}</span> : null}
    </div>
  );
}

/** Rules people published with the verdict they earned, luck included. Copy any of them and re-test it yourself. */
export function LibraryPage() {
  const { markets, fail, notify, refreshNotebooks } = useApp();
  const nav = useNavigate();
  const [rows, setRows] = useState<LibEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState(() => new URLSearchParams(location.search).get("q") ?? "");
  const [market, setMarket] = useState("");
  const [verdict, setVerdict] = useState("");
  const [sort, setSort] = useState("best");
  const [busy, setBusy] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [reporting, setReporting] = useState<{ id: string; reason: string } | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => {
      const p = new URLSearchParams({ q, market, verdict, sort });
      api<{ entries: LibEntry[]; total: number; reasons?: Record<string, string> }>(`/library?${p}`)
        .then((r) => { setRows(r.entries); setTotal(r.total); if (r.reasons) setReasons(r.reasons); }).catch((e) => { setRows([]); fail(e); });
    }, 200);
    return () => window.clearTimeout(t);
  }, [q, market, verdict, sort, fail]);

  const copy = async (e: LibEntry) => {
    setBusy(e.id);
    try {
      const nb = await api<{ id: string }>(`/library/${e.id}/copy`, { method: "POST" });
      await refreshNotebooks();
      notify("Copied into a new notebook. Run an experiment to test it yourself.");
      nav(`/n/${nb.id}`);
    } catch (x) { fail(x); } finally { setBusy(null); }
  };
  const takeDown = async (e: LibEntry) => {
    if (!confirm(`Take "${e.name}" out of the library? Copies people already made stay theirs.`)) return;
    try { await api(`/library/${e.id}`, { method: "DELETE" }); setRows((r) => r?.filter((x) => x.id !== e.id) ?? r); notify("Taken down."); } catch (x) { fail(x); }
  };
  const sendReport = async () => {
    if (!reporting) return;
    setBusy(reporting.id);
    try {
      const r = await api<{ hidden: boolean }>(`/library/${reporting.id}/report`, { method: "POST", body: JSON.stringify({ reason: reporting.reason }) });
      const id = reporting.id;
      setRows((rs) => r.hidden ? rs?.filter((x) => x.id !== id) ?? rs : rs?.map((x) => x.id === id ? { ...x, reported: true } : x) ?? rs);
      setReporting(null);
      notify(r.hidden ? "Thanks. It's hidden while the site owner takes a look." : "Thanks. The site owner will take a look.");
    } catch (x) { fail(x); } finally { setBusy(null); }
  };
  const live = markets.filter((m) => m.status !== "soon" && m.id !== "CSV");

  return (
    <div className="stack" style={{ gap: 22 }}>
      <div className="stack" style={{ gap: 8 }}>
        <h1 className="page-title">Strategy library<Info>{"Strategies people published from their own experiments, each with the verdict it earned: the lucky ones are shown as plainly as the real edges. Copy any of them into a notebook of your own and re-test it on your market and dates. Publish yours from a verdict: Share verdict → Publish to the library."}</Info></h1>
        <p className="page-sub">Real rules with honest verdicts, published by other traders. Copy one and test it yourself: a verdict here is a starting point, not a promise.</p>
      </div>
      <div className="row wrap" style={{ gap: 10 }}>
        <label className="search-box" style={{ flex: "1 1 240px" }}><Search size={18} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name, stock or idea" aria-label="Search the library" /></label>
        <span className="chip-select"><select aria-label="Market" value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="">Every market</option>{live.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></span>
        <span className="chip-select"><select aria-label="Verdict" value={verdict} onChange={(e) => setVerdict(e.target.value)}>
          {VERDICTS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></span>
        <div className="seg" role="radiogroup" aria-label="Sort">
          {([["best", "Best verdict"], ["new", "Newest"], ["copied", "Most copied"]] as const).map(([k, n]) => (
            <button key={k} role="radio" aria-checked={sort === k} aria-pressed={sort === k} onClick={() => setSort(k)}>{n}</button>))}
        </div>
      </div>
      {rows === null ? <Loading label="Opening the library" /> : rows.length === 0 ? (
        <div className="card stack" style={{ gap: 8 }}>
          <b>{q || market || verdict ? "Nothing matches that yet." : "The library is empty so far."}</b>
          <p className="small muted">Be the first: run an experiment, then on its verdict choose <b>Share verdict → Publish to the library</b>.</p>
        </div>
      ) : (
        <>
          <span className="small muted">{total} strateg{total === 1 ? "y" : "ies"}</span>
          <div className="lib-grid">
            {rows.map((e) => (
              <article key={e.id} className="card stack" style={{ gap: 12 }}>
                <div className="stack" style={{ gap: 4 }}>
                  <span className="eyebrow">{e.group ? `${e.group.name} (${e.group.members?.length ?? "group"})` : e.instrument?.symbol ?? e.market} · {TF_NAME[e.tf] ?? e.tf} candles{e.side !== "long" ? ` · ${e.side === "both" ? "long and short" : "short"}` : ""}</span>
                  <h2 className="h3">{e.name}</h2>
                  <span className="small muted">by {e.author}{e.copies ? ` · copied ${e.copies} time${e.copies === 1 ? "" : "s"}` : ""}</span>
                </div>
                <div className="row wrap" style={{ gap: 8, alignItems: "center" }}><VerdictBadge v={e.verdict.verdict} /><span className="small muted">{e.verdict.passed} of {e.verdict.total} checks passed</span></div>
                {e.description && <p className="small">{e.description}</p>}
                <Rules s={e.strategy} />
                <div className="lib-stats">
                  {([["After costs", e.stats.ret], ["Buy and hold", e.stats.buy_hold], ["Unseen years", e.stats.unseen], ["Worst fall", e.stats.mdd]] as [string, number | null][]).map(([k, n]) => (
                    <div key={k}><span className="eyebrow">{k}</span><b className={`mono ${signClass(n)}`}>{n == null ? "–" : pct(n)}</b></div>))}
                </div>
                {e.mine && e.hidden && <p className="small warn-text">Hidden from others after reports. The site owner will review it; editing and publishing again won't bring it back sooner.</p>}
                {reporting?.id === e.id ? (
                  <div className="row wrap" style={{ gap: 8, marginTop: "auto" }}>
                    <span className="chip-select"><select aria-label="Why are you reporting this?" value={reporting.reason} onChange={(x) => setReporting({ id: e.id, reason: x.target.value })}>
                      {Object.entries(reasons).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></span>
                    <button className="btn sm" disabled={busy === e.id} onClick={sendReport}>{busy === e.id ? "Sending…" : "Send report"}</button>
                    <button className="btn quiet sm" onClick={() => setReporting(null)}>Cancel</button>
                  </div>
                ) : (
                  <div className="row wrap" style={{ gap: 8, marginTop: "auto" }}>
                    <button className="btn sm" disabled={busy === e.id} onClick={() => copy(e)}>{busy === e.id ? "Copying…" : "Copy and re-test"}</button>
                    {e.mine && <button className="btn quiet sm danger" onClick={() => takeDown(e)}>Take down</button>}
                    {!e.mine && (e.reported
                      ? <span className="small muted" style={{ marginLeft: "auto" }}>Reported</span>
                      : <button className="btn quiet sm" style={{ marginLeft: "auto" }} onClick={() => setReporting({ id: e.id, reason: "spam" })}>Report</button>)}
                  </div>
                )}
              </article>
            ))}
          </div>
        </>
      )}
      <p className="small muted" style={{ maxWidth: "80ch" }}>Published by StratLab users for research and paper trading. Past results don't predict future returns, and nothing here is investment advice.</p>
    </div>
  );
}
