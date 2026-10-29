import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../../lib/http";
import { Upload } from "../Icons";

/** The one button that picks a file: an upload icon and its words, and a hidden file box behind it. `onFiles` gets the
 * chosen files and a `reset` that empties the box (so the same file can be picked again). `quiet` for a secondary one. */
export function UploadButton({ label, busyLabel = "Reading…", busy, accept, multiple, ariaLabel, quiet, onFiles }: {
  label: ReactNode; busyLabel?: string; busy?: boolean; accept: string; multiple?: boolean; ariaLabel: string; quiet?: boolean;
  onFiles: (files: FileList | null, reset: () => void) => void;
}) {
  const box = useRef<HTMLInputElement>(null);
  const reset = () => { if (box.current) box.current.value = ""; };
  // LIVE1B-001: a first read of the day took 13 s with "Reading…" and nothing else, which looked hung; after a few seconds the
  // button says it is still working
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    setSlow(false);
    if (!busy) return;
    const t = window.setTimeout(() => setSlow(true), SLOW_READ_MS);
    return () => window.clearTimeout(t);
  }, [busy]);
  return (
    <>
      <label className={`btn${quiet ? " quiet" : ""}${busy ? " disabled" : ""} k-upload`}>
        <Upload size={18} />{busy ? busyLabel : label}
        <input ref={box} type="file" accept={accept} multiple={multiple} hidden disabled={busy} aria-label={ariaLabel} onChange={(e) => onFiles(e.target.files, reset)} />
      </label>
      {busy && slow && <span className="k-note" role="status" data-testid="upload-slow">Still reading. The first file after a quiet spell can take a few seconds.</span>}
    </>
  );
}

/** How long a file read may take before the page says it is still at it. */
export const SLOW_READ_MS = 4000;

/** A refused file's explanation, kept on the page beside its upload until the next try (RC6-010: a long reason such as "We couldn't
 * find the holdings in that file. It needs a column for the stock..." was a toast, gone in seconds, over the form's fields).
 * `refused(e)` takes the error of a failed upload: when the server turned the file down (400 or 422) it keeps the words and says
 * so (true); any other failure (no connection, a limit, a server error) is left to the toast (false). */
export function useUploadProblem() {
  const [problem, setProblem] = useState<string | null>(null);
  const refused = (e: unknown): boolean => {
    if (e instanceof ApiError && (e.status === 400 || e.status === 422) && e.message) { setProblem(e.message); return true; }
    return false;
  };
  /** A refusal of the page's own (a file over the size limit), kept the same way as the server's (LIVE1B-002). */
  const reject = (message: string) => setProblem(message);
  return { problem, clear: () => setProblem(null), refused, reject };
}

/** The kept explanation of a refused file, under the upload it belongs to. */
export function UploadProblem({ problem }: { problem: string | null }) {
  return problem ? <p className="k-small k-down" role="alert" data-testid="upload-problem">{problem}</p> : null;
}
