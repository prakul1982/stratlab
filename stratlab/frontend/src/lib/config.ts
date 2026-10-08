/* What /config.js (a static file next to index.html) says: where the server is, the sign-in project and who runs the
 * site. Kept apart from lib/api.ts so a page that only reads it (the policies, the landing page) doesn't download the
 * sign-in library. */

import { sessionKeyFor } from "./entry";

declare global {
  interface Window {
    STRATLAB_CONFIG?: { API_BASE: string; SUPABASE_URL: string; SUPABASE_ANON_KEY: string; SENTRY_DSN?: string;
      BUSINESS_NAME?: string; CONTACT_EMAIL?: string; PRIVACY_EMAIL?: string; BILLING_EMAIL?: string; BUSINESS_ADDRESS?: string;
      BUSINESS_GSTIN?: string; POSTHOG_KEY?: string; POSTHOG_HOST?: string };
    Razorpay?: any;
  }
}

export type Config = NonNullable<Window["STRATLAB_CONFIG"]>;

export const CFG: Config = window.STRATLAB_CONFIG ?? { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" };

/** Where the saved login lives in localStorage (the sign-in library's own key for this project). */
export const sessionKey = (supabaseUrl = CFG.SUPABASE_URL): string => sessionKeyFor(supabaseUrl);
