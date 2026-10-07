import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { pct, TF_NAME } from "../lib/format";
import { opSay, refName } from "../lib/rules";
import { checksLine } from "../lib/tradeUi";
import type { Cond, Strategy, VerdictKind } from "../lib/types";
import { Search } from "../components/Icons";
import { VerdictBadge } from "../components/ui";
import { Badge, Card, CardHead, ConfirmDialog, DataTable, Disclosure, EmptyState, ErrorState, PageHeader, Seg, Select, Skeleton, Stat, type Column } from "../components/kit";
import { usePersisted } from "../lib/persist";
import "./trade/trade.css";

export interface LibEntry {
  id: string; name: string; question: string; description: string; author: string; market: string;
  instrument: { symbol: string; name?: string } | null; group: { name: string; members?: unknown[] } | null;
  tf: string; side: string; range: { from: string; to: string } | null; strategy: Strategy;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number };
  stats: { ret: number | null; buy_hold: number | null; mdd: number | null; trades: number | null; unseen: number | null };
  published_at: string; copies: number; mine: boolean; reported?: boolean; hidden?: boolean;
  /** StratLab's own entries: run by StratLab through its own backtest and verdict. */
  official?: boolean; badge?: string;
}

const VERDICTS: [string, string][] = [["", "Any verdict"], ["edge", "Likely a real edge"], ["mixed", "Mixed evidence"], ["not_enough", "Not enough evidence"], ["luck", "Probably luck"], ["no_edge", "No edge here"]];
const line = (c: Cond) => `${refName(c.l)} ${opSay(c.op)} ${refName(c.r)}`;

function Rules({ s }: { s: Strategy }) {
  const parts: [string, Cond[]][] = [["Buy when", s.entry], ["Sell when", s.exit], ["Short when", s.shortEntry ?? []], ["Cover when", s.shortExit ?? []]];
  return (
    <div className="k-stack k-tight k-small">
      {parts.filter(([, cs]) => cs?.length).map(([label, cs]) => (
        <span key={label}><b>{label}</b> {cs.map(line).join(s.entryJoin === "any" && label !== "Sell when" ? " or " : " and ")}</span>
      ))}
      {s.risk?.sl ? <span className="k-muted">Stop {s.risk.sl}{s.risk.stopType === "points" ? " points" : s.risk.stopType === "atr" ? "× ATR" : "%"}{s.risk.tgt ? ` · target ${s.risk.tgt}${s.risk.tgtType === "r" ? "R" : s.risk.tgtType === "points" ? " points" : "%"}` : ""}</span> : null}
    </div>
  );
}

/** True on a phone-width screen: the library cards then show the headline and keep the rest behind "Rules and all figures". */
function usePhone(): boolean {
  const q = "(max-width: 640px)";
  const [phone, setPhone] = useState(() => typeof matchMedia === "function" && matchMedia(q).matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const m = matchMedia(q), on = () => setPhone(m.matches);
    on();
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return phone;
}

/* /library: rules people published with the verdict they earned, luck included. Copy any of them and re-test it
 * yourself. Built from the kit (components/kit). */
export function LibraryPage() {
  const { markets, fail, notify, refreshNotebooks } = useApp();
  const nav = useNavigate();
  const [rows, setRows] = useState<LibEntry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState(() => new URLSearchParams(location.search).get("q") ?? "");
  const [market, setMarket] = useState("");
  const [verdict, setVerdict] = useState("");
  const [sort, setSort] = useState("best");
  const [official, setOfficial] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [reporting, setReporting] = useState<{ id: string; reason: string } | null>(null);
  const [taking, setTaking] = useState<LibEntry | null>(null);
  const [again, setAgain] = useState(0);
  const phone = usePhone();
  // a dense table to scan many at once, or the cards; remembered on this device (R1-026)
  const [layout, setLayout] = usePersisted<"cards" | "table">("stratlab.library.view", "cards");

  useEffect(() => {
    const t = window.setTimeout(() => {
      const p = new URLSearchParams({ q, market, verdict, sort, ...(official ? { official: "true" } : {}) });
      setFailed(false);
      api<{ entries: LibEntry[]; total: number; reasons?: Record<string, string> }>(`/library?${p}`)
        .then((r) => { setRows(r.entries); setTotal(r.total); if (r.reasons) setReasons(r.reasons); }).catch((e) => { setRows([]); setFailed(true); fail(e); });
    }, 200);
    return () => window.clearTimeout(t);
  }, [q, market, verdict, sort, official, fail, again]);

  const copy = async (e: LibEntry) => {
    setBusy(e.id);
    try {
      const nb = await api<{ id: string }>(`/library/${e.id}/copy`, { method: "POST" });
      await refreshNotebooks();
      notify("Copied into a new notebook. Run an experiment to test it yourself.");
      nav(`/n/${nb.id}`);
    } catch (x) { fail(x); } finally { setBusy(null); }
  };
  const takeDown = async () => {
    const e = taking;
    if (!e) return;
    setTaking(null);
    try { await api(`/library/${e.id}`, { method: "DELETE" }); setRows((r) => r?.filter((x) => x.id !== e.id) ?? r); notify("Taken down."); } catch (x) { fail(x); }
  };
  const sendReport = async () => {
    if (!reporting) return;
    setBusy(reporting.id);
    try {
      const r = await api<{ hidden: boolean }>(`/library/${reporting.id}/report`, { method: "POST", body: { reason: reporting.reason } });
      const id = reporting.id;
      setRows((rs) => r.hidden ? rs?.filter((x) => x.id !== id) ?? rs : rs?.map((x) => x.id === id ? { ...x, reported: true } : x) ?? rs);
      setReporting(null);
      notify(r.hidden ? "Thanks. It's hidden while the site owner takes a look." : "Thanks. The site owner will take a look.");
    } catch (x) { fail(x); } finally { setBusy(null); }
  };
  const live = markets.filter((m) => m.status !== "soon" && m.id !== "CSV");
  const signedPct = (n: number | null) => (n == null ? "–" : <span className={n > 0 ? "k-up" : n < 0 ? "k-down" : undefined}>{pct(n)}</span>);
  const tableCols: Column<LibEntry>[] = [
    { key: "name", header: "Strategy", rowHeader: true, wrap: true, cell: (e) => <><b>{e.name}</b><span className="k-sub-line">{e.group ? e.group.name : e.instrument?.symbol ?? e.market} · {TF_NAME[e.tf] ?? e.tf} · by {e.author}</span></> },
    { key: "verdict", header: "Verdict", cell: (e) => <><VerdictBadge v={e.verdict.verdict} /><span className="k-sub-line">{checksLine(e.verdict.passed, e.verdict.total)}</span></> },
    { key: "ret", header: "After costs", numeric: true, cell: (e) => signedPct(e.stats.ret) },
    { key: "bh", header: "Buy and hold", numeric: true, cell: (e) => signedPct(e.stats.buy_hold) },
    { key: "unseen", header: "Unseen years", numeric: true, cell: (e) => signedPct(e.stats.unseen) },
    { key: "mdd", header: "Worst fall", numeric: true, cell: (e) => signedPct(e.stats.mdd) },
    { key: "copy", header: "", action: true, cell: (e) => <button type="button" className="btn quiet sm" disabled={busy === e.id} onClick={() => copy(e)} aria-label={`Copy and re-test ${e.name}`}>{busy === e.id ? "Copying…" : "Copy"}</button> },
  ];
  const filtered = !!(q || market || verdict || official);

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Strategy library"
        lede="Real rules with honest verdicts, published by other traders and by StratLab itself. Copy one and test it yourself: a verdict here describes the past, not what comes next."
        info="Strategies people published from their own experiments, each with the verdict it earned: the lucky ones are shown as plainly as the real edges. Copy any of them into a notebook of your own and re-test it on your market and dates. Publish yours from a verdict: Share verdict → Publish to the library." infoLabel="About the library" />
      <Card label="Find a strategy">
        <div className="k-toolbar">
          <label className="k-search"><Search size={18} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: RSI, BANKNIFTY, breakout" aria-label="Search the library" /></label>
          <Select label="Market" value={market} onChange={setMarket} options={[{ value: "", label: "Every market" }, ...live.map((m) => ({ value: m.id, label: m.name }))]} />
          <Select label="Verdict" value={verdict} onChange={setVerdict} options={VERDICTS.map(([value, label]) => ({ value, label }))} />
          <Seg label="Whose" options={[{ value: "all", label: "Everyone's" }, { value: "official", label: "StratLab's own" }]} value={official ? "official" : "all"} onChange={(v) => setOfficial(v === "official")} />
          <Seg label="Sort" options={[{ value: "best", label: "Best verdict" }, { value: "new", label: "Newest" }, { value: "copied", label: "Most copied" }]} value={sort} onChange={setSort} />
          {!phone && <Seg label="View" options={[{ value: "cards", label: "Cards" }, { value: "table", label: "Table" }]} value={layout} onChange={(v) => setLayout(v as "cards" | "table")} />}
        </div>
      </Card>
      {rows === null ? <Card><Skeleton label="Opening the library" /></Card>
        : failed ? <ErrorState title="The library couldn't be opened" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>Your connection or ours dropped for a moment. Nothing was lost.</ErrorState>
        : rows.length === 0 ? (
          <EmptyState title={filtered ? "Nothing matches that yet." : "The library is empty so far."}>
            Be the first: run an experiment, then on its verdict choose Share verdict → Publish to the library.
          </EmptyState>
        ) : (
          <>
            <span className="k-small k-muted">{total} strateg{total === 1 ? "y" : "ies"}</span>
            {layout === "table" && !phone ? (
              <Card label="Strategies">
                <DataTable label="Strategies" rows={rows} rowKey={(e) => e.id} columns={tableCols} />
              </Card>
            ) : (
            <div className="k-cards">
              {rows.map((e) => (
                <Card key={e.id} label={e.name}>
                  {(() => {
                    const eyebrow = <span className="k-eyebrow">{e.group ? `${e.group.name} (${e.group.members?.length ?? "group"})` : e.instrument?.symbol ?? e.market} · {TF_NAME[e.tf] ?? e.tf} candles{e.side !== "long" ? ` · ${e.side === "both" ? "long and short" : "short"}` : ""}</span>;
                    const stats = ([["After costs", e.stats.ret], ["Buy and hold", e.stats.buy_hold], ["Unseen years", e.stats.unseen], ["Worst fall", e.stats.mdd]] as [string, number | null][])
                      .filter(([k]) => !phone || k !== "Buy and hold");
                    const miniStats = (list: [string, number | null][]) => (
                      <div className="k-mini-stats">
                        {list.map(([k, n]) => <Stat key={k} label={k} value={n == null ? "–" : pct(n)} tone={n == null || n === 0 ? undefined : n > 0 ? "up" : "down"} />)}
                      </div>);
                    return (
                      <>
                        <div className="k-stack k-tight">
                          {!phone && eyebrow}
                          <CardHead title={e.name} />
                          <span className="k-note k-row">{e.official && <Badge tone="ok" dot={false}>{e.badge ?? "StratLab"}</Badge>}<span>by {e.author}{e.copies ? ` · copied ${e.copies} time${e.copies === 1 ? "" : "s"}` : ""}</span></span>
                        </div>
                        <div className="k-row"><VerdictBadge v={e.verdict.verdict} /><span className="k-note">{checksLine(e.verdict.passed, e.verdict.total)}</span></div>
                        {/* two lines of the description; the rest is a tap away in its title, so a card isn't a wall of text */}
                        {e.description && <p className={`k-small ${phone ? "lib-oneline" : "lib-clamp"}`} title={e.description}>{e.description}</p>}
                        {phone ? (
                          <>
                            {miniStats(stats.filter(([k]) => k !== "Worst fall"))}
                            <Disclosure summary="Rules and all figures">
                              <div className="k-stack">
                                {eyebrow}
                                <Rules s={e.strategy} />
                                {miniStats([["Buy and hold", e.stats.buy_hold], ["Worst fall", e.stats.mdd]])}
                              </div>
                            </Disclosure>
                          </>
                        ) : (
                          <>
                            {miniStats(stats)}
                            <Disclosure summary="The rules"><Rules s={e.strategy} /></Disclosure>
                          </>
                        )}
                      </>
                    );
                  })()}
                  {e.mine && e.hidden && <p className="k-small k-down">Hidden from others after reports. The site owner will review it; editing and publishing again won't bring it back sooner.</p>}
                  {reporting?.id === e.id ? (
                    <div className="k-row k-push">
                      <Select label="Why are you reporting this?" small value={reporting.reason} onChange={(v) => setReporting({ id: e.id, reason: v })} options={Object.entries(reasons).map(([k, n]) => ({ value: k, label: n }))} />
                      <button type="button" className="btn sm" disabled={busy === e.id} onClick={sendReport}>{busy === e.id ? "Sending…" : "Send report"}</button>
                      <button type="button" className="btn quiet sm" onClick={() => setReporting(null)}>Cancel</button>
                    </div>
                  ) : (
                    <div className="k-row k-push">
                      <button type="button" className="btn sm" disabled={busy === e.id} onClick={() => copy(e)}>{busy === e.id ? "Copying…" : "Copy and re-test"}</button>
                      {e.mine && <button type="button" className="btn quiet sm danger" onClick={() => setTaking(e)}>Take down</button>}
                      {!e.mine && (e.reported
                        ? <span className="k-note k-end">Reported</span>
                        : <button type="button" className="btn quiet sm k-end" onClick={() => setReporting({ id: e.id, reason: "spam" })}>Report</button>)}
                    </div>
                  )}
                </Card>
              ))}
            </div>
            )}
          </>
        )}
      <p className="k-note">Published by StratLab users for research and paper trading. Past results don't predict future returns, and nothing here is investment advice.</p>
      {taking && (
        <ConfirmDialog title={`Take "${taking.name}" out of the library?`} confirmLabel="Take it down" onConfirm={takeDown} onClose={() => setTaking(null)}>
          Copies people already made stay theirs.
        </ConfirmDialog>
      )}
    </div>
  );
}
