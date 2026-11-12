import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { download as saveFile } from "../lib/share";
import { cellText, downloadPath, yearLabel, type Region, type StatementRow, type Statements } from "../lib/companyTables";
import { Card, CardHead, ChipBar, DataTable, ErrorState, PlanNote, Seg, Skeleton, type Column } from "./kit";
import "./companyTables.css";

/* Financial statements (lane c-f2): profit and loss, balance sheet, cash flow and ratios by year (as many as are stored, up to 12) and the
 * last 12 quarters, standalone and consolidated where both are kept. A figure a period doesn't have is "–", never filled in. Free: the latest
 * 3 years of profit and loss; Basic: everything; Pro: Excel and CSV. */

const BASIS: Record<string, string> = { consolidated: "Consolidated", standalone: "Standalone" };

export function StatementsCard({ region, symbol, id = "co-statements" }: { region: Region; symbol: string; id?: string }) {
  const { fail } = useApp();
  const [basis, setBasis] = useState<string | null>(null);
  const [v, setV] = useState<Statements | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [view, setView] = useState<string>("pl");
  const [getting, setGetting] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    api<Statements>(`/research/company/${region}/${encodeURIComponent(symbol)}/statements${basis ? `?basis=${basis}` : ""}`)
      .then((x) => { if (live) setV(x); })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "The statements couldn't be read."); });
    return () => { live = false; };
  }, [region, symbol, basis, tries]);
  useEffect(() => { setV(null); setBasis(null); setView("pl"); }, [region, symbol]);

  const file = async (what: "statements.xlsx" | "statements.csv") => {
    setGetting(what);
    try {
      const r = await api<Response>(downloadPath(region, symbol, what, v?.basis), { raw: true });
      saveFile(await r.blob(), `stratlab-${symbol}-statements-${v?.basis ?? "consolidated"}.${what.split(".")[1]}`);
    } catch (e) { fail(e); } finally { setGetting(null); }
  };

  const info = "The company's reported figures by financial year and by quarter, as filed. Ratios marked with a dot are worked out from two figures of the same year (net margin is net profit over sales). A figure a period doesn't have shows as –.";
  if (error && !v) return <Card id={id}><CardHead title="Financial statements" info={info} /><ErrorState title="The statements couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState></Card>;
  if (!v) return <Card id={id}><CardHead title="Financial statements" info={info} /><Skeleton label="Reading the statements" lines={6} /></Card>;
  if (!v.sections.length) return <Card id={id}><CardHead title="Financial statements" info={info} /><p className="k-small k-muted">No statements are stored for this company yet.</p></Card>;

  const options = [...v.sections.map((s) => ({ value: s.key, label: s.key === "pl" ? "Profit and loss" : s.title, short: s.key === "pl" ? "P&L" : undefined })),
    ...(v.quarters ? [{ value: "quarters", label: "Quarters" }] : [])];
  const shown = options.some((o) => o.value === view) ? view : "pl";
  const quarters = shown === "quarters" && v.quarters;
  const cols = quarters ? v.quarters!.cols : v.cols;
  const rows: StatementRow[] = quarters ? v.quarters!.rows : (v.sections.find((s) => s.key === shown)?.rows ?? []);
  const columns: Column<StatementRow>[] = [
    { key: "label", header: quarters ? "Quarter" : "Year", rowHeader: true, wrap: true,
      cell: (r) => <>{r.label}{r.worked && <span className="ct-worked" title="Worked out from the figures above">{" "}·<span className="sr-only"> worked out from the figures above</span></span>}</> },
    ...cols.map((c, i): Column<StatementRow> => ({ key: `c${i}`, header: quarters ? c : yearLabel(c, region), numeric: true,
      cell: (r) => cellText(r.values[i], r.kind, region), csvHeader: c })),
  ];
  const actions = <>
    {v.bases.length > 1 && v.full && <Seg label="Accounts" options={v.bases.map((b) => ({ value: b, label: BASIS[b] ?? b }))} value={v.basis} onChange={setBasis} />}
    {v.can_export && <>
      <button type="button" className="btn quiet sm" disabled={!!getting} onClick={() => void file("statements.xlsx")}>{getting === "statements.xlsx" ? "Preparing…" : "Excel"}</button>
      <button type="button" className="btn quiet sm" disabled={!!getting} onClick={() => void file("statements.csv")}>{getting === "statements.csv" ? "Preparing…" : "CSV"}</button>
    </>}
  </>;
  const what = quarters ? "quarter" : region === "IN" ? "financial year" : "fiscal year";
  return (
    <Card id={id}>
      <CardHead title="Financial statements" info={info} actions={actions} />
      {options.length > 1 && <ChipBar label="Statement" options={options} value={shown} onChange={setView} wrap />}
      <p className="k-small k-muted">{BASIS[v.basis] ?? v.basis} figures in {v.unit}, by {what}{v.full ? `; ${v.years_stored} year${v.years_stored === 1 ? "" : "s"} stored` : ""}.{v.basis_note ? ` ${v.basis_note}` : ""}</p>
      <div className="ct-statement" data-view={shown}>
        <DataTable label={`${v.name}: ${options.find((o) => o.value === shown)?.label ?? ""}`} rows={rows} rowKey={(r) => r.label} columns={columns} stack={false} scrollEnd />
      </div>
      {v.notes.map((n) => <p key={n} className="k-note">{n}</p>)}
      {v.locked && <PlanNote plan={v.locked.plan}>{v.locked.message}</PlanNote>}
      {v.export_locked && <p className="k-note">{v.export_locked.message}</p>}
    </Card>
  );
}
