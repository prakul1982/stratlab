import { lazy, Suspense, useLayoutEffect, type ComponentType } from "react";
import { useLocation } from "react-router-dom";
import { visitorView } from "../lib/deepLinks";
import { applySeo, seoFor, type SeoKind } from "../lib/seo";
import { NOT_FOUND_TITLE, signedOutTitle } from "../lib/title";
import { Loading } from "../components/ui";

/* What someone without an account sees, at any address: the landing page (at a section, or with a sign-in panel), the
 * policies, a shared verdict, StratLab's own strategy library, "Sign in to see …" on an address inside the app, or "Page
 * not found". The app uses it for the same people (signed out, or in the moment before sign-in is known), and a plain
 * visitor's page load runs only this (visitor/visitorMain.tsx), without the sign-in library. Each page's code loads when
 * it is opened. */

const page = <K extends string>(load: () => Promise<Record<K, any>>, name: K) => lazy(() => load().then((m) => ({ default: m[name] as ComponentType<any> })));
export const loadLogin = () => import("../pages/Login");
export const loadLegal = () => import("../pages/LegalPage");
export const loadGate = () => import("../pages/Gate");
export const loadVerdict = () => import("../pages/PublicVerdict");
export const loadLibrary = () => import("../pages/PublicLibrary");
const Login = page(loadLogin, "Login");
const LegalPage = page(loadLegal, "LegalPage");
const SignInGate = page(loadGate, "SignInGate");
const NotFound = page(loadGate, "NotFound");
const PublicVerdict = page(loadVerdict, "PublicVerdict");
const PublicLibrary = page(loadLibrary, "PublicLibrary");
const PublicLibraryEntry = page(loadLibrary, "PublicLibraryEntry");

/** The first page's code, started at once (in parallel with the rest of the start-up) for an address. */
export function warmVisitorPage(path: string): Promise<unknown> {
  const v = visitorView(path);
  const load = v.kind === "landing" ? loadLogin : v.kind === "legal" ? loadLegal : v.kind === "verdict" ? loadVerdict
    : v.kind === "library" || v.kind === "libraryEntry" ? loadLibrary : loadGate;
  return load().catch(() => undefined);       // only a head start: the page itself reports a failed download
}

export function VisitorApp() {
  const { pathname } = useLocation();
  const view = visitorView(pathname);
  const kind: SeoKind = view.kind === "gate" ? "gate" : view.kind === "notfound" ? "notfound" : view.kind === "verdict" ? "verdict" : "public";
  // the tab's title and what search engines are told, before the page adds anything of its own (a verdict names itself)
  useLayoutEffect(() => {
    const title = view.kind === "notfound" ? NOT_FOUND_TITLE : view.kind === "verdict" ? "Shared verdict · StratLab"
      : view.kind === "libraryEntry" ? "Strategy library · StratLab" : signedOutTitle(pathname);
    document.title = title;
    applySeo(seoFor(pathname, kind, view.kind === "libraryEntry" ? { index: false } : {}), title);
  }, [pathname, kind, view.kind]);

  const wait = <Loading label="Opening StratLab" />;
  return (
    <Suspense fallback={wait}>
      {view.kind === "landing" ? <Login section={view.section} panel={view.panel} />
        : view.kind === "legal" ? <LegalPage />
        : view.kind === "verdict" ? <PublicVerdict token={view.token} />
        : view.kind === "library" ? <PublicLibrary />
        : view.kind === "libraryEntry" ? <PublicLibraryEntry id={view.id} />
        : view.kind === "gate" ? <SignInGate />
        : <NotFound signedIn={false} />}
    </Suspense>
  );
}
