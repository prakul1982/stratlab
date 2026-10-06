import { useRef, type ReactNode } from "react";
import { Upload } from "../Icons";

/** The one button that picks a file: an upload icon and its words, and a hidden file box behind it. `onFiles` gets the
 * chosen files and a `reset` that empties the box (so the same file can be picked again). `quiet` for a secondary one. */
export function UploadButton({ label, busyLabel = "Reading…", busy, accept, multiple, ariaLabel, quiet, onFiles }: {
  label: ReactNode; busyLabel?: string; busy?: boolean; accept: string; multiple?: boolean; ariaLabel: string; quiet?: boolean;
  onFiles: (files: FileList | null, reset: () => void) => void;
}) {
  const box = useRef<HTMLInputElement>(null);
  const reset = () => { if (box.current) box.current.value = ""; };
  return (
    <label className={`btn${quiet ? " quiet" : ""}${busy ? " disabled" : ""} k-upload`}>
      <Upload size={18} />{busy ? busyLabel : label}
      <input ref={box} type="file" accept={accept} multiple={multiple} hidden disabled={busy} aria-label={ariaLabel} onChange={(e) => onFiles(e.target.files, reset)} />
    </label>
  );
}
