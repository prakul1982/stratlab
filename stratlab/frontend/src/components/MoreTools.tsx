import type { MouseEvent, ReactNode } from "react";
import { Link } from "react-router-dom";
import { DataTable, FoldCard, usePhone, type Column } from "./kit";

/** One tool in a space's "More" list: its name (the link), one short line, and the menu entry it lives under. */
export type ToolRow = {
  id: string; title: string; line: string; to: string; group: string; groupId: string;
  /** under the name: the plan it needs, "Starts with a notebook" */
  tag?: ReactNode;
  /** attributes on the link (data-money) */
  attrs?: Record<string, string>;
  onClick?: (e: MouseEvent<HTMLAnchorElement>) => void;
};

/** The rest of a space's tools at the foot of its home (My space, Trade, Invest, Money, the notebooks): one row, closed, that says how
 * many tools are in it, and opened, one calm table of name, line and menu entry (owner, 5 Nov: "More in Money" was "very weird and
 * very filled", a wall of cards; "make it like a dropdown everywhere"). The menu entry is said on its first row only, so the table reads
 * in groups. `children`: more under the table (Explore's "Elsewhere in StratLab"). */
export function MoreTools({ title, rows, children, id }: { title: string; rows: ToolRow[]; children?: ReactNode; id?: string }) {
  const phone = usePhone();
  const firstOf = new Set(rows.filter((r, i) => i === 0 || rows[i - 1].groupId !== r.groupId).map((r) => r.id));
  const cols: Column<ToolRow>[] = [
    { key: "tool", header: "Tool", rowHeader: true, cell: (r) => (
      <span className="k-more-go">
        <Link className="link k-more-link" to={r.to} onClick={r.onClick} {...r.attrs}>{r.title}</Link>
        {r.tag}
      </span>) },
    { key: "what", header: "What it is", wrap: true, lead: true, cell: (r) => <span className="k-muted">{r.line}</span> },
    // a phone's cards are the name and its line only: a "Menu entry" row on each made the list twice as long
    ...(phone ? [] : [{ key: "in", header: "Menu entry", cell: (r: ToolRow) => (firstOf.has(r.id) ? r.group : "") }]),
  ];
  return (
    <FoldCard id={id} className="k-more-tools" title={title} meta={`${rows.length} tool${rows.length === 1 ? "" : "s"}`} testId="more-tools">
      <DataTable stack label={title} columns={cols} rows={rows} rowKey={(r) => r.id} rowAttrs={(r) => ({ "data-entry": r.groupId })} />
      {children}
    </FoldCard>
  );
}
