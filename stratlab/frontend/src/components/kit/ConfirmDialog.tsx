import type { ReactNode } from "react";
import { Dialog as Modal } from "./Dialog";

/** Asking before something is removed, in the page (never the browser's own box). The question is the title, what
 * happens is the body, the button says the action ("Delete my holdings"), and Cancel sits next to it. Esc and a click
 * outside cancel. */
export function ConfirmDialog({ title, children, confirmLabel, onConfirm, onClose, busy, danger = true }: {
  title: string; children?: ReactNode; confirmLabel: string; onConfirm: () => void; onClose: () => void; busy?: boolean; danger?: boolean;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <div className="k-stack">
        {children && <p className="k-small k-muted">{children}</p>}
        <div className="k-row">
          <button type="button" className={`btn${danger ? " danger" : ""}`} disabled={busy} onClick={onConfirm}>{confirmLabel}</button>
          <button type="button" className="btn quiet" data-autofocus={danger || undefined} onClick={onClose}>Cancel</button>
        </div>
      </div>
    </Modal>
  );
}
