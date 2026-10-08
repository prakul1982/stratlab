import { Component, type ReactNode } from "react";

declare global {
  interface Window { __stratlabRecover?: () => void; __stratlabShowLoadError?: () => void }
}

/** A page's code failed to download (a dropped connection, or a deploy that replaced the files while the tab was open). */
export const isLoadError = (e: unknown) =>
  /dynamically imported module|importing a module script|loading chunk|chunkloaderror|failed to fetch|load failed|networkerror/i.test(`${(e as Error)?.name ?? ""} ${(e as Error)?.message ?? ""}`);

/** What anyone sees instead of a blank page when something fails to load: one plain sentence and a Reload button. */
export function LoadFailed({ what = "StratLab" }: { what?: string }) {
  return (
    <div className="boot" role="alert">
      <h1>Couldn't load {what}.</h1>
      <p>A file didn't download, which is usually a dropped connection. Reload to try again.</p>
      <button type="button" className="boot-btn" onClick={() => location.reload()}>Reload</button>
    </div>
  );
}

/** Wraps the whole page. A failed download reloads the page once on its own (public/boot.js keeps the count); a second
 * failure, or any other crash, shows `LoadFailed` instead of an empty page. */
export class LoadGuard extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: unknown) {
    if (isLoadError(error)) window.__stratlabRecover?.();
  }
  render() { return this.state.failed ? <LoadFailed /> : this.props.children; }
}
