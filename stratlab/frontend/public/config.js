// The anon/publishable key is safe to expose; never put the service_role key here.
window.STRATLAB_CONFIG = {
  API_BASE: "https://stratlab-production-ca25.up.railway.app",
  SUPABASE_URL: "https://enxrxhikzzfualjzqibf.supabase.co",
  // SENTRY_DSN: "https://…@….ingest.sentry.io/…",   // optional: browser error alerts
  SUPABASE_ANON_KEY: "sb_publishable_31v3Fc59LUCl_aMZpyulbA_SXtDV4cs",
  // Usage analytics (optional): PostHog's "Project API key" (phc_…, public by design). Off while empty: nothing loads.
  // The project is on PostHog's US cloud; the CSP in vercel.json allows that host.
  POSTHOG_KEY: "phc_yjniCAedaF52gysc4635oJtJk6BVSbLASMqVUqjUrMCH",
  POSTHOG_HOST: "https://us.i.posthog.com",
  // Shown on the Terms, Privacy, Refunds and Contact pages (Razorpay checks these before going live).
  // Add BUSINESS_ADDRESS: "Street, City, State PIN, India" if you want an address listed.
  BUSINESS_NAME: "StratLab",
  CONTACT_EMAIL: "support@stratlab.studio",   // contact and help
  BILLING_EMAIL: "billing@stratlab.studio",   // payments, invoices and refunds
  PRIVACY_EMAIL: "privacy@stratlab.studio",   // privacy requests and grievances (DPDP Act)
};
