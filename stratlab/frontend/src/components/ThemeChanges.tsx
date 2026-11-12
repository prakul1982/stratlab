import { useState } from "react";
import { Badge, Card, CardHead, DataTable, PlanNote, Working, type Column } from "./kit";
import { Download } from "./Icons";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { deckDay } from "../lib/deckName";
import { deckWhenReady } from "../lib/deckReady";
import { fmtDate } from "../lib/format";
import { REGION_NAME, type Region } from "../lib/research";
import { download } from "../lib/share";
import type { Dive } from "../lib/theme";
import { CAUSE_WORDS, changeRows, changesLockLine, countsLine, type ChangeLog, type ChangeRow } from "../lib/themeChanges";

/* f4: a theme's change log ("What changed", theme_changes.py) and its Excel workbook (theme_workbook.py), beside the deck downloads.
 * Basic and up see every entry; Free the latest refresh's counts and its first 5 changes, with the plan note for the rest. */

const COLS: Column<ChangeRow>[] = [
  { key: "c", header: "Change", cell: (x) => x.change },
  { key: "co", header: "Company", rowHeader: true, wrap: true, cell: (x) => (x.company ? <b>{x.company}</b> : "–") },
  { key: "d", header: "Detail", wrap: true, cell: (x) => x.detail },
];

export function ChangesCard({ dive }: { dive: Dive & { changes?: ChangeLog } }) {
  const log = dive.changes;
  if (!log) return null;
  const unit = dive.unit ?? (dive.region === "IN" ? "₹ crore" : "$ million");
  return (
    <Card id="theme-changes" testId="theme-changes">
      <CardHead title="What changed" actions={!log.full ? <Badge tone="plain">Latest refresh</Badge> : undefined} />
      <p className="k-small k-muted">Each time this theme's figures are stored again (a Refresh, a new map, a re-check under new placement rules, or the companies' own figures updated), they are set against the read before: companies added, removed with the reason, moved between layers; layers renamed, split or merged; latest-year revenue moved by more than 2% or a margin by more than a point for the same year.</p>
      {log.entries.length === 0 ? (
        <p className="k-small" data-testid="theme-changes-empty">{log.since ? `No change recorded since ${fmtDate(log.since)}.` : "Changes are recorded from the next time this theme's figures are stored again."}</p>
      ) : log.entries.map((e, i) => {
        const rows = changeRows(e, unit);
        return (
          <section key={`${e.at}-${i}`} className="k-stack" data-testid="theme-change-entry" aria-label={`Changes on ${fmtDate(e.d)}`}>
            <h3 className="k-sub">{fmtDate(e.d)} · {CAUSE_WORDS[e.cause] ?? e.cause}</h3>
            <p className="k-small">{countsLine(e.counts)}.</p>
            {rows.length > 0 && <DataTable label={`What changed on ${fmtDate(e.d)}`} columns={COLS} rows={rows} rowKey={(x) => x.key} />}
            {(e.hidden ?? 0) > 0 && log.full && <p className="k-note">{e.hidden} more not kept in this list; the counts above are whole.</p>}
          </section>
        );
      })}
      {!log.full && log.entries.length > 0 && <PlanNote plan="basic">{changesLockLine(log)}</PlanNote>}
    </Card>
  );
}

/** "Workbook (XLSX)" beside the deck downloads: Basic and up, counted as the theme's deck of the month (its PDF, PowerPoint and workbook are one deck). */
export function WorkbookButton({ region, theme, dive }: { region: Region; theme: string; dive: Dive | null }) {
  const { me, fail, refreshMe } = useApp();
  const [making, setMaking] = useState(false);
  const [preparing, setPreparing] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const off = (me?.plan_info.features as Record<string, boolean> | undefined)?.theme_workbook === false;
  const go = async () => {
    if (off) { setLocked(true); return; }
    setMaking(true);
    try {
      const url = `/research/theme-dive/workbook?region=${region}&q=${encodeURIComponent(theme)}`;
      const blob = await deckWhenReady(() => api<Response>(url, { raw: true }), { onWait: (t) => setPreparing(t.replace("deck", "workbook")) });
      download(blob, `StratLab - ${`${theme} theme (${REGION_NAME[region]})`.normalize("NFKD").replace(/[^\x20-\x7e]+/g, " ").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 120)} - ${deckDay()}.xlsx`);
      void refreshMe();
    } catch (e) { fail(e); } finally { setMaking(false); setPreparing(null); }
  };
  return (
    <>
      <button type="button" className="btn quiet sm" disabled={making || !dive} onClick={go} aria-describedby={locked ? "theme-workbook-lock" : undefined}
        title="Every table of this theme as an Excel workbook: the companies with their layers and figures, layer medians, peers, valuation, operating figures, what changed, and the sources and method">
        <Download size={16} />{making ? "Making the workbook…" : "Workbook (XLSX)"}
      </button>
      {preparing && <Working small label={preparing} />}
      {locked && <div id="theme-workbook-lock" className="theme-wb-lock" data-testid="theme-workbook-lock"><PlanNote plan="basic">A theme's workbook (Excel) is on the Basic plan; it counts as the theme's deck of the month.</PlanNote></div>}
    </>
  );
}

/** Release 43: every company in the theme as a CSV, made by the server (GET /research/theme-dive/companies.csv): a download, so Basic and
 * up with the theme's workbook; Free sees the same companies on the page, and the plan note here. Not counted as a deck. */
export function ThemeCsvButton({ region, theme, dive }: { region: Region; theme: string; dive: Dive | null }) {
  const { me, fail } = useApp();
  const [making, setMaking] = useState(false);
  const [locked, setLocked] = useState(false);
  const off = (me?.plan_info.features as Record<string, boolean> | undefined)?.theme_workbook === false;
  const go = async () => {
    if (off) { setLocked(true); return; }
    setMaking(true);
    try {
      const url = `/research/theme-dive/companies.csv?region=${region}&q=${encodeURIComponent(theme)}`;
      const blob = await deckWhenReady(() => api<Response>(url, { raw: true }), {});
      download(blob, `StratLab - ${`${theme} theme companies (${REGION_NAME[region]})`.normalize("NFKD").replace(/[^\x20-\x7e]+/g, " ").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 120)} - ${deckDay()}.csv`);
    } catch (e) { fail(e); } finally { setMaking(false); }
  };
  return (
    <>
      <button type="button" className="btn quiet sm" disabled={making || !dive} onClick={go} aria-describedby={locked ? "theme-csv-lock" : undefined}
        data-csv="theme companies" aria-label="CSV: every company in this theme" title="Every company in this theme as a CSV file, to open in a spreadsheet">
        <Download size={16} />{making ? "Making the CSV…" : "CSV"}
      </button>
      {locked && <div id="theme-csv-lock" className="theme-wb-lock" data-testid="theme-csv-lock"><PlanNote plan="basic">Downloading a theme's companies as a CSV is on the Basic plan; every company is listed on this page.</PlanNote></div>}
    </>
  );
}
