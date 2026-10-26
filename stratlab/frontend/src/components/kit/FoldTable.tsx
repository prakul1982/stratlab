import { useState, type ReactNode } from "react";
import { Info } from "../ui";
import { textOf } from "./Card";
import { minusNode } from "../../lib/format";
import type { Column } from "./DataTable";

const head = (c: { header?: ReactNode; info?: ReactNode }) => <Info label={`About ${typeof c.header === "string" ? c.header.toLowerCase() : "this column"}`}>{c.info}</Info>;

/** A list where each thing is said once: one row of its main figures, and the rest of what there is to know about it folded
 * under that row (MF-1, RC2B-047). The first column names the row; the others are its figures, under a header row on a
 * wide screen and each under its own name on a phone (a card, never a sideways table). `detail` is drawn only once a row is
 * opened; `openWhen` opens the rows that need something done. The summary is the whole row's tap target (44 px). */
export function FoldTable<R>({ label, columns, rows, rowKey, detail, openWhen, testId }: {
  label: string; columns: Column<R>[]; rows: R[]; rowKey: (row: R) => string; detail: (row: R) => ReactNode; openWhen?: (row: R) => boolean; testId?: string;
}) {
  const [name, ...figures] = columns;
  // the name takes the room; a column of words (`wrap`) a little more than a column of figures
  const cols = `minmax(0, 2.2fr) ${figures.map((c) => (c.wrap ? "minmax(0, 1.7fr)" : "minmax(0, 1fr)")).join(" ")}`;
  return (
    <div className="k-fold-list" data-testid={testId} style={{ ["--fold-cols" as string]: cols }}>
      <div className="k-fold-head">
        <span aria-hidden="true">{name.header}</span>
        {figures.map((c) => (
          <span key={c.key} className={c.numeric ? "k-num" : undefined}>
            {c.numeric && c.info && head(c)}<span aria-hidden="true">{c.header}</span>{!c.numeric && c.info && head(c)}
          </span>
        ))}
      </div>
      <ul className="k-fold-rows" aria-label={label}>
        {rows.map((r) => <FoldRow key={rowKey(r)} row={r} name={name} figures={figures} detail={detail} open={openWhen?.(r) ?? false} />)}
      </ul>
    </div>
  );
}

function FoldRow<R>({ row, name, figures, detail, open }: { row: R; name: Column<R>; figures: Column<R>[]; detail: (row: R) => ReactNode; open: boolean }) {
  const [shown, setShown] = useState(open);
  return (
    <li>
      <details className="k-fold" open={shown} onToggle={(e) => setShown(e.currentTarget.open)}>
        <summary className="k-fold-sum">
          <span className="k-fold-name">{minusNode(name.cell(row))}</span>
          {figures.map((c) => {
            const label = c.cardLabel ?? (typeof c.header === "string" ? c.header : textOf(c.header).trim());
            return (
              <span key={c.key} className={`k-fold-cell${c.numeric ? " k-num" : ""}${c.wrap ? " k-fold-wide" : ""}`}>
                <span className="k-fold-k">{label}</span>
                <span className="k-fold-v">{minusNode(c.cell(row))}</span>
              </span>
            );
          })}
        </summary>
        {shown && <div className="k-fold-body">{detail(row)}</div>}
      </details>
    </li>
  );
}
