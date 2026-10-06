import { useState, type ReactNode } from "react";
import { Card, CardHead } from "./Card";
import { ChipBar } from "./ChipBar";
import { DataTable, type Column } from "./DataTable";
import { Seg, type Choice } from "./Seg";

/** A chart in its card: the title and (i) on the left, and in the same row the range switch (a Seg for up to four
 * ranges, a ChipBar for more) and a "Table" switch that swaps the chart for the same numbers as a table. Put a StatRow
 * in `stats` to show the headline figures above the chart; `actions` adds a card's own buttons after Table; `footer` is for one line under it. The chart inside should
 * be drawn with its own range buttons and table switch turned off (`ranges={false} table={false}`): this frame has them. */
export function ChartFrame<R>({ title, info, id, label, ranges, range, onRange, table, actions, stats, footer, children }: {
  title: ReactNode; info?: ReactNode; id?: string; label?: string; ranges?: Choice[]; range?: string; onRange?: (v: string) => void; actions?: ReactNode;
  table?: { label: string; columns: Column<R>[]; rows: R[]; rowKey: (r: R) => string; empty?: ReactNode };
  stats?: ReactNode; footer?: ReactNode; children: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const rangeBar = ranges && ranges.length > 1 && range != null && onRange
    ? (ranges.length <= 4 ? <Seg label="Range" options={ranges} value={range} onChange={onRange} /> : <ChipBar label="Range" options={ranges} value={range} onChange={onRange} />) : null;
  return (
    <Card id={id} label={label}>
      <CardHead title={title} info={info} actions={<>
        {rangeBar}
        {table && <button type="button" className="btn quiet sm" aria-pressed={asTable} onClick={() => setAsTable((x) => !x)}>Table</button>}
        {actions}
      </>} />
      {stats}
      <div className="k-chart-body">{asTable && table ? <DataTable {...table} /> : children}</div>
      {footer}
    </Card>
  );
}
