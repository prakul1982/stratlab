import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { Loading } from "../../components/ui";
import { Download } from "../../components/Icons";
import { track } from "../../lib/analytics";

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

export function ItrExportPage() {
  const { fail } = useApp();
  const [v, setV] = useState<View | null>(null);
  const [getting, setGetting] = useState<Format | null>(null);
  const [open, setOpen] = useState<string | null>("112a");

  const load = useCallback((fy?: number) => {
    setV(null);
    api<View>(`/money/itr${fy ? `?fy=${fy}` : ""}`).then(setV).catch(fail);
  }, [fail]);
  useEffect(() => { load(); }, [load]);

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
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Money · ITR-ready export</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Your year, laid out for the return</h1>
        <p className="page-sub">The figures from your <Link className="link" to="/tax-report">tax report</Link>, <Link className="link" to="/money/tax-tools">tax tools</Link> and <Link className="link" to="/money/us-tax">US stocks</Link>, shaped like the ITR-2 and ITR-3 schedules: Schedule 112A scrip by scrip, Schedule CG, dividends, intraday and F&amp;O turnover, tax paid, foreign income and Schedule FA. Download them as a spreadsheet or one PDF for your CA.</p>
      </div>
      <div className="banner tax-note" role="note"><span><b>Not a filed return.</b> {v?.label_text ?? "Prepared by StratLab from your files to help you or your CA fill the return. This is not a filed return, and StratLab files nothing for you."} {v?.check}</span></div>

      <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="field" style={{ minWidth: 220 }}>Financial year
          <select value={v?.fy ?? ""} onChange={(e) => load(Number(e.target.value))} aria-label="Financial year" disabled={!v}>
            {(v?.years ?? []).map((y) => <option key={y} value={y}>{fyLabel(y)} (AY {y + 1}-{String(y + 2).slice(2)})</option>)}
          </select>
        </label>
      </div>

      {!v && <Loading label="Laying out your schedules" />}
      {v && (
        <>
          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">Download for {v.label} (AY {v.ay})</h2>
            {v.locked && <div className="banner" role="note"><span>The downloads and the full schedules are on the {v.plan} plan. Below is what each schedule would hold. <Link className="link" to="/plans">See plans</Link></span></div>}
            <div className="itr-downloads">
              {FORMATS.map(([f, label, hint]) => (
                <button key={f} className={`btn${f === "pdf" ? "" : " quiet"}`} disabled={v.locked || !!getting} onClick={() => download(f)}>
                  <Download size={16} /><span className="stack" style={{ gap: 0, alignItems: "flex-start", textAlign: "left" }}>
                    <span>{getting === f ? "Making it…" : label}</span><span className="tiny" style={{ opacity: 0.75, fontWeight: 400 }}>{hint}</span></span>
                </button>
              ))}
            </div>
            <dl className="itr-summary" aria-label="Summary">
              {v.summary.map((s) => <div key={s.label}><dt className="tiny muted">{s.label}</dt><dd className="num">{s.value}</dd></div>)}
            </dl>
          </section>

          <section className="stack" style={{ gap: 12 }} aria-label="Schedules">
            {v.tables.map((t) => (
              <div key={t.key} className="card stack" style={{ gap: 10 }}>
                <button className="spread itr-head" aria-expanded={open === t.key} onClick={() => setOpen(open === t.key ? null : t.key)}>
                  <span className="h2" style={{ textAlign: "left" }}>{t.title}</span>
                  <span className="tiny muted">{t.count ? `${t.count} line${t.count === 1 ? "" : "s"}` : "nothing this year"}</span>
                </button>
                {open === t.key && !v.locked && t.columns && (
                  <>
                    {t.rows && t.rows.length > 0 ? (
                      <div className="table-wrap">
                        <table aria-label={t.title}>
                          <thead><tr>{t.columns.map((c, i) => <th key={i} style={i === 0 ? { textAlign: "left" } : undefined}>{c}</th>)}</tr></thead>
                          <tbody>{t.rows.map((r, i) => (
                            <tr key={i}>{r.map((x, j) => <td key={j} className={typeof x === "number" ? "num" : undefined} style={j === 0 ? { textAlign: "left" } : undefined}>{cell(x)}</td>)}</tr>
                          ))}</tbody>
                        </table>
                      </div>
                    ) : <p className="small muted" style={{ margin: 0 }}>Nothing to report in {v.label} from your files.</p>}
                    {!!t.notes?.length && <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{t.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
                  </>
                )}
                {open === t.key && v.locked && <p className="small muted" style={{ margin: 0 }}>The full table is on the {v.plan} plan.</p>}
              </div>
            ))}
          </section>

          <section className="card stack" style={{ gap: 10 }}>
            <h2 className="h2">Where the figures come from</h2>
            <ul className="small" style={{ margin: 0, paddingLeft: 20 }} aria-label="Sources">{v.sources.map((s, i) => <li key={i}>{s}</li>)}</ul>
            <h3 className="small" style={{ margin: "6px 0 0" }}>Assumptions</h3>
            <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{v.assumptions.map((s, i) => <li key={i}>{s}</li>)}</ul>
            <p className="tiny muted" style={{ margin: 0 }}>StratLab doesn't file returns: filing on someone's behalf needs registration as an e-return intermediary with the Income Tax Department. Upload or type these figures into the return yourself, or hand the pack to your CA.</p>
          </section>
        </>
      )}
    </div>
  );
}
