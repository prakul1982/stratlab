import { createContext, useContext, useMemo, type ReactNode } from "react";

/* "Report an error in this figure" (owner, 12 Nov). A part of a page whose figures come from StratLab's data (a company's Key numbers,
 * its financial tables, a theme's layers, the results rows, the heatmap's table) is wrapped in a ReportScope that says what it is and
 * where its figures come from; every DataTable row and Stat inside it then carries a small flag that opens the report dialog filled in
 * with the page, the figure, its value, its period and its source (components/FigureReportHost.tsx draws the dialog, downloaded only
 * once someone opens it). A table or card outside a scope (your own holdings, a form) has no flag. Tiny on purpose: the public pages'
 * kit carries it. */

export type FigureScope = { section: string; source?: string; period?: string };
/** What the dialog opens with: the scope, the figure's name and value, and for a row of several figures (a table of periods) each
 * column's name and figure, to pick which one is wrong. */
export type FigureDetail = FigureScope & { label: string; value?: string; choices?: [string, string][] };

export const FIGURE_REPORT = "stratlab:figure-report";
const Scope = createContext<FigureScope | null>(null);

export function ReportScope({ section, source, period, children }: FigureScope & { children: ReactNode }) {
  const value = useMemo(() => ({ section, source, period }), [section, source, period]);
  return <Scope.Provider value={value}>{children}</Scope.Provider>;
}

export const useReportScope = () => useContext(Scope);

export function openFigureReport(detail: FigureDetail) {
  window.dispatchEvent(new CustomEvent<FigureDetail>(FIGURE_REPORT, { detail }));
}

/** The flag beside a figure (inside a ReportScope only). `choices` is read when it is pressed, not on every draw. */
export function ReportFigure({ label, value, choices }: { label: string; value?: string; choices?: () => [string, string][] }) {
  const scope = useReportScope();
  if (!scope || !label.trim()) return null;
  const name = label.trim().slice(0, 160);
  return (
    <button type="button" className="k-report" aria-label={`Report an error in ${name}`} title="Report an error in this figure"
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); openFigureReport({ ...scope, label: name, value, choices: choices?.() }); }}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 21V4M5 4h11l-2 4 2 4H5" /></svg>
    </button>
  );
}
