// The anon/publishable key is safe to expose; never put the service_role key here.
window.STRATLAB_CONFIG = {
  API_BASE: "https://stratlab-production-ca25.up.railway.app",
  SUPABASE_URL: "https://enxrxhikzzfualjzqibf.supabase.co",
  // SENTRY_DSN: "https://…@….ingest.sentry.io/…",   // optional: browser error alerts
  SUPABASE_ANON_KEY: "sb_publishable_31v3Fc59LUCl_aMZpyulbA_SXtDV4cs",
  // Usage analytics (optional): PostHog's "Project API key" (phc_…, public by design). Off while empty: nothing loads.
  // POSTHOG_HOST defaults to the EU cloud; for a US project use "https://us.i.posthog.com" and update the CSP to match.
  POSTHOG_KEY: "",
  // POSTHOG_HOST: "https://eu.i.posthog.com",
  // Shown on the Terms, Privacy, Refunds and Contact pages (Razorpay checks these before going live).
  // Add BUSINESS_ADDRESS: "Street, City, State PIN, India" if you want an address listed.
  BUSINESS_NAME: "StratLab",
  CONTACT_EMAIL: "prakul828@gmail.com",
};
