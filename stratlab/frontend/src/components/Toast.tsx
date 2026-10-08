import { useApp } from "../lib/app";

/** The short message at the bottom of the screen (lib/app's `notify`). Kept out of components/ui.tsx so the pages that
 * need no account don't download the sign-in code with it. */
export function Toast() {
  const { toast } = useApp();
  if (!toast) return null;
  return (
    <div className="toast" role="status">
      <span>{toast.msg}</span>
      {toast.action && <button onClick={toast.action.run}>{toast.action.label}</button>}
    </div>
  );
}
