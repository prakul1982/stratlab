import type { ReactNode } from "react";
import { Disclosure } from "./Disclosure";

/** A card's method, source and long explanatory notes (owner, 18 Nov: "hide these type of information in a drop down … everything this just
 *  clutters the pages"): one fold at the card's foot, closed until asked, "About these figures" unless the card says otherwise. A one-line
 *  date or as-of label stays outside it, where it is seen. Each child is a note: a string or a paragraph. */
export function CardNote({ children, summary = "About these figures", testId }: { children: ReactNode; summary?: string; testId?: string }) {
  return (
    <Disclosure className="k-cardnote" summary={summary} testId={testId}>
      <div className="k-cardnote-body">{children}</div>
    </Disclosure>
  );
}
