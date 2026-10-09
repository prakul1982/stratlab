import { Component, type ReactNode } from "react";

declare global {
  interface Window { __stratlabRecover?: () => void; __stratlabShowLoadError?: () => void; __stratlabLoadFailed?: boolean }
}

/** A page's code failed to download (a dropped connection, or a deploy that replaced the files while the tab was open):
 * the error says so, or the start-up script saw a file fail just before (a lazily loaded page whose download failed then
 * fails on its empty module, with an error of its own). */
export const isLoadError = (e: unknown) =>
  /dynamically imported module|importing a module script|loading chunk|chunkloaderror|failed to fetch|load failed|networkerror/i.test(`${(e as Error)?.name ?? ""} ${(e as Error)?.message ?? ""}`)
  || (typeof window !== "undefined" && !!window.__stratlabLoadFailed);

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

/** What anyone sees when a page's own code fails while it runs (not a download): honest, with a way on. A reload may not
 * help, so it isn't promised (R7T-011: "A file didn't download… Reload" for a TypeError that a reload can't fix). */
export function PageFailed({ inPage = false }: { inPage?: boolean }) {
  return (
    <div className={inPage ? "k-page" : "boot"} role="alert" data-testid="page-failed">
      {inPage ? <h1>This page ran into a problem</h1> : <h1>StratLab ran into a problem.</h1>}
      <p>Something on this page failed while it was drawn. It has been noted; the rest of StratLab still works.</p>
      <div className="k-row">
        <a className={inPage ? "btn" : "boot-btn"} href="/">Go to the home page</a>
        <button type="button" className={inPage ? "btn quiet" : "boot-btn"} onClick={() => location.reload()}>Try the page again</button>
      </div>
    </div>
  );
}

/** Wraps the whole page. A failed download reloads the page once on its own (public/boot.js keeps the count); a second
 * failure shows `LoadFailed`; any other crash shows `PageFailed`, never a download message. */
export class LoadGuard extends Component<{ children: ReactNode }, { failed: "load" | "crash" | null }> {
  state: { failed: "load" | "crash" | null } = { failed: null };
  static getDerivedStateFromError(error: unknown) { return { failed: isLoadError(error) ? "load" : "crash" }; }
  componentDidCatch(error: unknown) {
    if (isLoadError(error)) window.__stratlabRecover?.();
  }
  render() { return this.state.failed === "load" ? <LoadFailed /> : this.state.failed === "crash" ? <PageFailed /> : this.props.children; }
}

/** Wraps one page inside the app's frame (`at`: the page's address, so going to another page starts clean): a page's code
 * that failed to download is the download message (and the one automatic reload); a page that fails while it runs is that
 * page's own honest message, with the menu still there (R7T-011). */
export class PageBoundary extends Component<{ children: ReactNode; at?: string }, { failed: "load" | "crash" | null }> {
  state: { failed: "load" | "crash" | null } = { failed: null };
  static getDerivedStateFromError(error: unknown) { return { failed: isLoadError(error) ? "load" : "crash" }; }
  componentDidUpdate(before: { at?: string }) {
    if (before.at !== this.props.at && this.state.failed) this.setState({ failed: null });
  }
  componentDidCatch(error: unknown) {
    if (isLoadError(error)) window.__stratlabRecover?.();
    else console.error("page failed:", error);
  }
  render() {
    if (this.state.failed === "load") return <LoadFailed what="this page" />;
    if (this.state.failed === "crash") return <PageFailed inPage />;
    return this.props.children;
  }
}
