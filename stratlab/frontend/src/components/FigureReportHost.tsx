import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { importWithRetry } from "../lib/lazyRetry";
import { FIGURE_REPORT, type FigureDetail } from "./kit/ReportFigure";

/* "Report an error in this figure" in the signed-in app (owner, 12 Nov): the flag beside a figure (kit/ReportFigure) asks for the dialog,
 * downloaded only when someone opens it; and a note the person hasn't seen, that a figure they reported was fixed, is said once in the
 * app's message line and then marked as shown. */
const FigureReportDialog = lazy(() => importWithRetry(() => import("./FigureReportDialog")));

export function FigureReports() {
  const { me, notify } = useApp();
  const [detail, setDetail] = useState<FigureDetail | null>(null);
  useEffect(() => {
    const on = (e: Event) => setDetail((e as CustomEvent<FigureDetail>).detail);
    window.addEventListener(FIGURE_REPORT, on);
    return () => window.removeEventListener(FIGURE_REPORT, on);
  }, []);
  const told = useRef<string>("");
  const notes = me?.notes ?? [];
  const key = notes.map((n) => n.id).join(",");
  useEffect(() => {
    if (!key || told.current === key) return;
    told.current = key;
    notify(notes.length === 1 ? notes[0].text : `${notes.length} figures you reported were fixed. Thanks for telling us.`);
    void api("/feedback/notes/seen", { method: "POST", body: { ids: notes.map((n) => n.id) } }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return detail ? <Suspense fallback={null}><FigureReportDialog detail={detail} signedIn={!!me} onClose={() => setDetail(null)} notify={notify} /></Suspense> : null;
}
