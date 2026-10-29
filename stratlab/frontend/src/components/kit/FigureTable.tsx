import type { ReactNode } from "react";
import { DataTable, type Column } from "./DataTable";

export interface Figure { key?: string; label: ReactNode; value: ReactNode; note?: ReactNode; /** "up", "down" or a sign class ("k-up", "pos", "neg"): the figure in the kit's green or red, its sign still in the text */ tone?: string }
const toneClass = (t?: string) => (!t ? undefined : /\bup\b|\bpos\b|\bk-up\b/.test(t) ? "k-up" : /\bdown\b|\bneg\b|\bk-down\b/.test(t) ? "k-down" : undefined);

/** Several figures as a table (TABLES EVERYWHERE): what it is, its value (right-aligned) and, when there is one, what it counts or how it
 * changed. For a block of three or more label and value pairs; a single headline figure stays a `Stat`. `valueHeader` and `noteHeader`
 * name the two columns where "Now" and "What it counts" do not fit. */
export function FigureTable({ label, rows, header = "Figure", valueHeader = "Now", noteHeader = "What it counts" }: {
  label: string; rows: Figure[]; header?: string; valueHeader?: string; noteHeader?: string | null;
}) {
  const withNote = noteHeader != null && rows.some((r) => r.note != null && r.note !== "");
  const columns: Column<Figure>[] = [
    { key: "k", header, rowHeader: true, wrap: true, cell: (r) => r.label },
    { key: "v", header: valueHeader, numeric: true, cell: (r) => <span className={toneClass(r.tone)}>{r.value}</span> },
    ...(withNote ? [{ key: "n", header: noteHeader as string, wrap: true, cell: (r: Figure) => <span className="k-note k-muted">{r.note}</span> } as Column<Figure>] : []),
  ];
  return <DataTable label={label} rows={rows} rowKey={(r, i) => r.key ?? `${i}`} columns={columns} />;
}
