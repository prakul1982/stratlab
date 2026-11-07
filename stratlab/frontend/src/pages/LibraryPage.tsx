import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { COPY_ANY_PLAN, copyNeeds } from "../lib/rules";
import { LIMITS } from "../lib/plans";
import { LibraryTable, libMeta, marketChoices, strategyName, trails, VERDICTS, type LibEntry, CHECKS_NOT_HOLD } from "../components/LibraryBits";
import { Search } from "../components/Icons";
import { Card, ChipBar, ConfirmDialog, EmptyState, ErrorState, PageHeader, Seg, Select, Skeleton } from "../components/kit";
import { LIBRARY_DATES } from "../lib/libraryText";
import "./trade/trade.css";


/** How many strategies a phone shows before "Show 12 more" (VR6-024): the table's own phone paging (LibraryBits PHONE_ROWS). */
export { PHONE_ROWS as PHONE_CARDS } from "../components/LibraryBits";

/* /library: rules people published with the verdict they earned, luck included. Copy any of them and re-test it
 * yourself. Built from the kit (components/kit). */
export function LibraryPage() {
  const { fail, notify, refreshNotebooks, me, allIndicators } = useApp();
  // what a copy would need that the plan lacks, said on the card before the copy (DP1-008)
  const needs = (e: LibEntry) => me ? copyNeeds(e.strategy, e.group?.members?.length ?? 0,
    { allIndicators, groupCap: me.plan_info.group_size, basicCap: LIMITS.basic.group_size, proCap: LIMITS.pro.group_size }) : null;
  const nav = useNavigate();
  const [rows, setRows] = useState<LibEntry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [total, setTotal] = useState(0);
  // how many strategies each market has, so the market filter offers only those that have some (MO-5b)
  const [counts, setCounts] = useState<Record<string, number> | undefined>(undefined);
  const [q, setQ] = useState(() => new URLSearchParams(location.search).get("q") ?? "");
  const [market, setMarket] = useState("");
  const [verdict, setVerdict] = useState("");
  // furthest ahead of buy and hold first by default: by checks alone, a strategy 108.5 points behind it led the list (DA-037)
  const [sort, setSort] = useState("hold");
  // whose strategies: StratLab's own (first, so the list isn't empty while few people have published), or only those people published
  // ("Everyone's", owner R15: "in everyone don't show stratlab ones"). No "All" (owner, 7 Nov: "remove the all option")
  const [whose, setWhose] = useState<"users" | "official">("official");
  const [busy, setBusy] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [reporting, setReporting] = useState<{ id: string; reason: string } | null>(null);
  const [taking, setTaking] = useState<LibEntry | null>(null);
  const [again, setAgain] = useState(0);

  useEffect(() => {
    let live = true;       // a slower answer for an earlier search must not replace the one for the search now on screen
    const t = window.setTimeout(() => {
      const p = new URLSearchParams({ q, market, verdict, sort, whose });
      setFailed(false);
      api<{ entries: LibEntry[]; total: number; reasons?: Record<string, string>; markets?: Record<string, number> }>(`/library?${p}`)
        .then((r) => { if (!live) return; setRows(r.entries); setTotal(r.total); setCounts(r.markets); if (r.reasons) setReasons(r.reasons); }).catch((e) => { if (!live) return; setRows([]); setFailed(true); fail(e); });
    }, 200);
    return () => { live = false; window.clearTimeout(t); };
  }, [q, market, verdict, sort, whose, fail, again]);

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
  const choices = marketChoices(counts, rows ?? [], market);
  const filtered = !!(q || market || verdict);
  // the intro says whose rules are listed: StratLab's own, or what people published (never promising other people's rules on
  // StratLab's own list, R5O-014)
  const ours = whose === "official";

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Strategies" title="Strategy library"
        lede={ours ? "Rules StratLab tested itself, each with the result of its checks and its return beside buying and holding. Publish your own from a verdict, and copy any rule to test it yourself: a result here describes the past, not what comes next." : "Rules people using StratLab published from their own experiments, each with the result of its checks and its return beside buying and holding. Copy one and test it yourself: a result here describes the past, not what comes next."}
        info="Rules published from experiments, each with the result its checks gave: the ones that failed are shown as plainly as the ones that passed. Copy any of them into a notebook of your own and re-test it on your market and dates. Publish yours from a verdict: Share verdict → Publish to the library." infoLabel="About the library" />
      <Card label="Find a strategy">
        <div className="k-toolbar">
          <label className="k-search"><Search size={18} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: RSI, BANKNIFTY, breakout" aria-label="Search the library" /></label>
          <Select label="Verdict" value={verdict} onChange={setVerdict} options={VERDICTS.map(([value, label]) => ({ value, label }))} />
          <Seg label="Whose" options={[{ value: "official", label: "StratLab's own" }, { value: "users", label: "Everyone's" }]} value={whose} onChange={(v) => setWhose(v as typeof whose)} />
          <Seg label="Sort" options={[{ value: "hold", label: "Ahead of buy and hold", short: "Vs hold" }, { value: "best", label: "Most checks passed", short: "Checks" },
            { value: "new", label: "Newest" }, { value: "copied", label: "Most copied", short: "Copied" }]} value={sort} onChange={setSort} />
        </div>
        {/* only the markets that have strategies, each with how many; wrapped on a phone too, so none is cut off at the edge (MO-5b, VR1-181) */}
        {choices.length > 2 && <ChipBar label="Market" options={choices} value={market} onChange={setMarket} wrap />}
      </Card>
      {rows === null ? <Card><Skeleton label="Opening the library" page /></Card>
        : failed ? <ErrorState title="The library couldn't be opened" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>Your connection or ours dropped for a moment. Nothing was lost.</ErrorState>
        : rows.length === 0 ? (
          <EmptyState title={filtered ? "Nothing matches that yet." : ours ? "The library is empty so far." : "Nobody has published a strategy yet."}>
            Be the first: run an experiment, then on its verdict choose Share verdict → Publish to the library.
          </EmptyState>
        ) : (
          <>
            <span className="k-small k-muted">{total} strateg{total === 1 ? "y" : "ies"}</span>
            {/* said once for the list, not on every card (DA-037), and why a copy's figures can differ from its card (DA-038) */}
            <p className="k-note" data-testid="lib-list-notes">
              {rows.some(trails) && <>{CHECKS_NOT_HOLD} </>}{LIBRARY_DATES}{rows.some((e) => needs(e)) && <> {COPY_ANY_PLAN}</>}
            </p>
            {/* one table on every screen (TABLES EVERYWHERE, owner 4 Nov): the figures in sortable columns, the rules under each row */}
            <LibraryTable key={`${q}|${market}|${verdict}|${sort}|${whose}`} rows={rows}
              actions={(e) => (
                <div className="k-row lib-buttons">
                  <button type="button" className="btn sm" disabled={busy === e.id} onClick={() => copy(e)} aria-label={`Copy and re-test ${strategyName(e)}, ${libMeta(e)}`}>{busy === e.id ? "Copying…" : "Copy"}</button>
                </div>)}
              extra={(e) => (
                <>
                  {e.mine && e.hidden && <p className="k-small k-down">Hidden from others after reports. The site owner will review it; editing and publishing again won't bring it back sooner.</p>}
                  {needs(e) && <span className="k-note" data-testid="lib-needs">{needs(e)}</span>}
                  {reporting?.id === e.id ? (
                    <div className="k-row">
                      <Select label="Why are you reporting this?" small value={reporting.reason} onChange={(v) => setReporting({ id: e.id, reason: v })} options={Object.entries(reasons).map(([k, n]) => ({ value: k, label: n }))} />
                      <button type="button" className="btn sm" disabled={busy === e.id} onClick={sendReport}>{busy === e.id ? "Sending…" : "Send report"}</button>
                      <button type="button" className="btn quiet sm" onClick={() => setReporting(null)}>Cancel</button>
                    </div>
                  ) : (
                    <div className="k-row">
                      {e.mine && <button type="button" className="btn quiet sm danger" onClick={() => setTaking(e)}>Take down</button>}
                      {!e.mine && (e.reported
                        ? <span className="k-note">Reported</span>
                        : <button type="button" className="btn quiet sm" onClick={() => setReporting({ id: e.id, reason: "spam" })}>Report</button>)}
                    </div>
                  )}
                </>)} />
          </>
        )}
      <p className="k-note">Published by StratLab and its users for research and paper trading. Past results don't predict future returns, and nothing here is investment advice.</p>
      {taking && (
        <ConfirmDialog title={`Take "${taking.name}" out of the library?`} confirmLabel="Take it down" onConfirm={takeDown} onClose={() => setTaking(null)}>
          Copies people already made stay theirs.
        </ConfirmDialog>
      )}
    </div>
  );
}
