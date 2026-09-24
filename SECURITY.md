# Security policy

StratLab handles sign-ins, broker credentials and payments, so security reports are welcome.

## Reporting a problem

Please report it privately through [GitHub's security advisories](https://github.com/prakul1982/stratlab/security/advisories/new), not as a public issue. Include what you found, how to reproduce it, and what an attacker could do with it. You'll get a reply within a few days.

## How secrets are kept

- Every secret (the Supabase service key, Kite API secret, Kite password and TOTP secret, Razorpay keys, AI and Finnhub keys) lives only in the backend's environment variables. None are committed, and none reach the browser.
- The browser talks only to the backend API, authenticated with the user's Supabase token. Database tables use row-level security.
- Razorpay webhooks are verified with their signature before anything changes.

## Known advisory

`kiteconnect` pins `autobahn==19.11.2`, which has published advisories. StratLab uses it only for the outgoing connection to Zerodha's price feed, not to serve anything. See "Known limits" in the [setup guide](stratlab/README.md).
