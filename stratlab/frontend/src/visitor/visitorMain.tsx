import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, useLocation } from "react-router-dom";
import { LoadGuard } from "../components/LoadGuard";
import { pageview } from "../lib/analytics";
import { isPublicForAll, wantsAccount } from "../lib/entry";
import { VisitorApp } from "./VisitorApp";

/* The public half of the site, on its own: no sign-in library, no account state, no menu. A page load for someone with no
 * saved sign-in runs this. If the person signs in meanwhile (in another tab) or follows a link into the app, the page
 * loads again as a whole so the app starts. */

/** Whether this browser now has what the app needs (a saved sign-in). */
const signedInNow = () => wantsAccount({ supabaseUrl: window.STRATLAB_CONFIG?.SUPABASE_URL, storage: localStorage });

function Watch() {
  const { pathname } = useLocation();
  useEffect(() => { pageview(pathname); }, [pathname]);          // usage analytics: off without a key
  // a link from a policy page to an address inside the app, for someone who is signed in: load the whole app
  useEffect(() => { if (!isPublicForAll(pathname) && signedInNow()) location.reload(); }, [pathname]);
  useEffect(() => {
    const on = () => { if (signedInNow() && !isPublicForAll(location.pathname)) location.reload(); };
    window.addEventListener("storage", on);                      // signed in from another tab
    return () => window.removeEventListener("storage", on);
  }, []);
  return null;
}

export function startVisitor(root: HTMLElement) {
  createRoot(root).render(
    <StrictMode>
      <LoadGuard>
        <BrowserRouter>
          <Watch />
          <VisitorApp />
        </BrowserRouter>
      </LoadGuard>
    </StrictMode>,
  );
}
