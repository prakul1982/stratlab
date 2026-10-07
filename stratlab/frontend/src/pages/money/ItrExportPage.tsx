import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { Download } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { Card, CardHead, DataTable, EmptyState, Field, FormGrid, Notice, PageHeader, PlanNote, Select, Skeleton, Stat, StatRow, type Column } from "../../components/kit";
import { rememberFy, savedFy } from "../../lib/fy";

/* /money/itr: the year's figures from the tax report, tax tools and US stocks, laid out as the ITR-2 and ITR-3 schedules,
 * to download as a workbook, CSV files or a PDF pack for a CA. Built from the kit (components/kit). */

type Cell = string | number | null;
type Sheet = { key: string; title: string; count: number; columns?: string[]; rows?: Cell[][]; notes?: string[] };
type View = {
  fy: number; label: string; ay: string; label_text: string; check: string; locked: boolean; plan: string; summary: { label: string; value: string }[];
  sources: string[]; assumptions: string[]; years: number[]; tables: Sheet[];
};
type Format = "xlsx" | "zip" | "pdf";

const FORMATS: [Format, string, string][] = [
  ["xlsx", "Excel workbook", "Every schedule on its own sheet"], ["zip", "CSV files (ZIP)", "One file per schedule, with the 112A upload layout"],
  ["pdf", "PDF pack for your CA", "Summary, schedules, workings, assumptions and sources"],
];
const fyLabel = (y: number) => `FY ${y}-${String(y + 1).slice(2)}`;
const cell = (v: Cell) => (v == null ? "" : typeof v === "number" ? v.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : v);

/** A schedule's table: the columns the server names, numbers on the right, the first column naming the row. */
function Schedule({ t }: { t: Sheet }) {
  const columns: Column<{ i: number; r: Cell[] }>[] = (t.columns ?? []).map((c, i) => ({
    key: String(i), header: c, numeric: i > 0 && (t.rows ?? []).some((r) => typeof r[i] === "number"), rowHeader: i === 0, cell: (x) => cell(x.r[i] ?? null),
  }));
  return <DataTable label={t.title} columns={columns} rows={(t.rows ?? []).map((r, i) => ({ i, r }))} rowKey={(x) => String(x.i)} />;
}

export function ItrExportPage() {
  const { fail } = useApp();
  const [v, setV] = useState<View | null>(null);
  const [getting, setGetting] = useState<Format | null>(null);
  const [open, setOpen] = useState<string | null>("112a");

  const load = useCallback((fy?: number) => {
    setV(null);
    api<View>(`/money/itr${fy ? `?fy=${fy}` : ""}`).then(setV).catch(fail);
  }, [fail]);
  useEffect(() => { load(savedFy() ?? undefined); }, [load]);     // the Money pages' shared year, when one was picked

  const download = async (f: Format) => {
    if (!v) return;
    setGetting(f);
    try {
      const r = await api<Response>(`/money/itr/export?fy=${v.fy}&format=${f}`, { raw: true });
      const a = document.createElement("a");
      const base = `stratlab-ITR-FY-${v.fy}-${String(v.fy + 1).slice(2)}`;
      a.href = URL.createObjectURL(await r.blob()); a.download = f === "pdf" ? `${base}-CA-pack.pdf` : f === "zip" ? `${base}-schedules.zip` : `${base}-schedules.xlsx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      track("itr export", { format: f });
    } catch (e) { fail(e); } finally { setGetting(null); }
  };

  return (
    <div className="k-page">
      <PageHeader eyebrow="Money · Tax" title="Your year, laid out for the return"
        lede={<>The figures from your <Link className="link" to="/tax-report">tax report</Link>, <Link className="link" to="/money/tax-tools">tax tools</Link> and <Link className="link" to="/money/us-tax">US stocks</Link>, shaped like the ITR-2 and ITR-3 schedules, to download as a spreadsheet or one PDF for your CA.</>}
        info="Schedule 112A scrip by scrip, Schedule CG, dividends, intraday and F&O turnover, tax paid, foreign income and Schedule FA. Only you can see these figures." infoLabel="What is in the schedules" />
      <Notice label="Not a filed return"><b>Not a filed return.</b> {v?.label_text ?? "Prepared by StratLab from your files to help you or your CA fill the return. This is not a filed return, and StratLab files nothing for you."} {v?.check}</Notice>

      <FormGrid label="Choose the year">
        <Field label="Financial year">{(id) => (
          <Select id={id} value={v?.fy ?? ""} disabled={!v} onChange={(x) => { rememberFy(Number(x)); load(Number(x)); }}
            options={(v?.years ?? []).map((y) => ({ value: y, label: `${fyLabel(y)} (AY ${y + 1}-${String(y + 2).slice(2)})` }))} />
        )}</Field>
      </FormGrid>

      {!v && <Card><Skeleton label="Laying out your schedules" /></Card>}
      {v && (
        <>
          <Card>
            <CardHead title={`Download for ${v.label} (AY ${v.ay})`} />
            {v.locked && <PlanNote>The downloads and the full schedules are on the {v.plan} plan. Below is what each schedule would hold.</PlanNote>}
            <div className="k-downloads">
              {FORMATS.map(([f, label, hint]) => (
                <button key={f} type="button" className={`btn${f === "pdf" ? "" : " quiet"}`} disabled={v.locked || !!getting} onClick={() => download(f)}>
                  <Download size={16} /><span>{getting === f ? "Making it…" : label}<small>{hint}</small></span>
                </button>
              ))}
            </div>
            <StatRow>{v.summary.map((s) => <Stat key={s.label} label={s.label} value={/^[−+-]?[₹$\d]/.test(s.value) && s.value.length < 18 ? s.value : <span className="k-stat-text">{s.value}</span>} />)}</StatRow>
          </Card>

          <section className="k-page" aria-label="Schedules">
            {v.tables.map((t) => (
              <Card key={t.key}>
                <button type="button" className="k-fold" aria-expanded={open === t.key} onClick={() => setOpen(open === t.key ? null : t.key)}>
                  <span className="k-card-title">{t.title}</span>
                  <span className="k-note">{t.count ? `${t.count} line${t.count === 1 ? "" : "s"}` : "nothing this year"}</span>
                </button>
                {open === t.key && !v.locked && t.columns && (
                  <>
                    {t.rows && t.rows.length > 0 ? <Schedule t={t} />
                      : <EmptyState title={`Nothing to report in ${v.label}`}>Nothing in this schedule from your files for the year. Upload trades on the <Link className="link" to="/tax-report">tax report</Link> to fill it.</EmptyState>}
                    {!!t.notes?.length && <ul className="k-list muted">{t.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
                  </>
                )}
                {open === t.key && v.locked && <p className="k-small k-muted">The full table is on the {v.plan} plan.</p>}
              </Card>
            ))}
          </section>

          <Card>
            <CardHead title="Where the figures come from" />
            <ul className="k-list" aria-label="Sources">{v.sources.map((s, i) => <li key={i}>{s}</li>)}</ul>
            <h3 className="k-sub">Assumptions</h3>
            <ul className="k-list muted">{v.assumptions.map((s, i) => <li key={i}>{s}</li>)}</ul>
            <p className="k-note">StratLab doesn't file returns: filing on someone's behalf needs registration as an e-return intermediary with the Income Tax Department. Upload or type these figures into the return yourself, or hand the pack to your CA.</p>
          </Card>
        </>
      )}
    </div>
  );
}
