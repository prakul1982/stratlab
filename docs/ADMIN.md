# Running StratLab: admin operations

[← Back to the project overview](../README.md) · [Setup guide](../stratlab/README.md)

Everything the site owner does after deploy: the Admin page, the checks and jobs that run by themselves, email,
analytics, error alerts, storage and backups. Setting up the services the first time (Supabase, the broker data API,
Razorpay, AI keys) is in the [setup guide](../stratlab/README.md).

## Who is an admin

Set `ADMIN_EMAILS` on the backend to one or more Google addresses, comma-separated, and redeploy. Signed in with one
of them (Google-verified, and the current sign-in address), you get **Admin** in the sidebar. Everyone else gets a 403
from every `/admin` route and never sees the link.

## The Admin page

Admin is split into five tabs.

| Tab | What's on it |
| --- | --- |
| **Overview** | **Needs your attention**, worst first (the broker not logged in or its automatic login failing, AI providers down, email not set up, server errors, reported library entries, the option-chain recorder, holidays running out, payments not connected), usage at a glance, a link to the PostHog dashboard once a key is set, and **Recent server errors**: the last 25 unexpected errors with the request, the error, the line of code and the ref code the user saw, kept across restarts |
| **Services** | Market data: the broker login state, **Log in**, **Run the automatic login now**. Other services: Telegram, email (**Send a test email**), phone notifications, Sentry, the option-chain recorder, the newsletters, and **Send this week's summary now** (the owner's Monday 9:00 IST email). AI: a live test of every provider, the order each kind of job uses, and which keys are missing |
| **Data checks** | **Check every feature**, **Rates and rules**, **Market breadth** (**Run now** per market), **Storage**, the **Data audit**, the **Whole market** audits for India and the US, **Exchange holidays** for every market, and **Save real prices** (the price snapshot the tests run on) |
| **Users** | Every user with plan, join date, experiments, AI builds, invites and free months earned; **Change plan** grants Basic or Pro for 30 days, 90 days, a year or with no end. **Invite rewards** shows rewards given and sign-ups waiting for review. **Paper trading now** lists every running session with **Stop**. **Reported in the library** holds strategy-library entries people reported |
| **Billing** | The **Launch offer**, payments status and **Check payments**, **Prices** per currency, and **Invoices** (the seller's GST details and every invoice) |

### Check every feature (platform check)

`backend/app/platform_check.py`, shown on **Data checks**. Runs each part of StratLab once on the live server with live
data and compares what came back with what it should be: prices in every market and how fresh they are, a two-year
backtest per market, the NIFTY 50 and US scans, sector rotation, the NIFTY option chain, exchange filings, insider
trades, surveillance lists, BSE filings, company pages, news, the database and how full it is (**Database space**), the
holiday calendar of every market (a warning under 60 days known), and **Rates and rules last reviewed**. No AI is used,
so it costs no allowance.

- **By itself:** every day at 4:50 pm IST. Anything that fails is tried again two minutes later; whatever still fails is
  emailed to the admins (and sent by phone notification or Telegram when set up in Account).
- **By hand:** **Run checks** (about a minute). Run it after every deploy.
- The last runs show as a row of ticks and crosses, with the time of the last failure.

### Data audit (companies)

`backend/app/audit.py`, the **Data audit** panel. Runs every company in a set through the deep dive on the live server:
the numbers, prices, industry, valuation, checklist and documents, each compared with its source. **Mismatches** are
numbers that disagree with the source; **gaps** are things a user would still have to look up elsewhere. No AI is used;
about 3 to 10 seconds a company.

- Pick India or the US and a set: a ready-made group, every sector's main stocks, or (India) a whole NSE index such as
  the NIFTY 500. **Run audit**, **Stop**, and **Download CSV** of the findings.
- **Whole market (India / US):** reads the list of every listed company daily (NSE and BSE-only; US common stock
  only, no preferred shares, warrants, units or rights) and puts each new listing through the same checks as it
  appears. **Start** / **Pause** (with why it's paused), a progress bar with the rate and the time left, **Reset and
  check everything again**, **Re-check the N not checked yet**, **Re-check** on each company, and **Full re-check on the
  1st of each month** (on by default; off means only new listings until you reset). A check a source turned away is
  tried again in small batches every hour, backing off to a day while the source keeps refusing. When BSE refuses the
  server, the panel says so and how many companies wait for their documents.
- A failed read of the stored results after a restart never overwrites them: nothing is checked or saved until they
  have been read (the panel says it's reading).
- Stored findings are re-read with today's rules, so a fix shows up without re-running everything.

### Other admin jobs

- **Launch offer** (Billing): every user gets every Pro feature free for N days, starting now. Users see a banner and a
  countdown; Plans and Account still show what they actually pay for. It ends by itself, or press **End now**.
- **Invite rewards** (Users): more than 5 sign-ups through one link in a day wait here for review; the sign-ups
  themselves go through. Approve or reject each reward. A daily check from 6 am IST gives rewards and closes invites
  whose 14 days ran out. The Given table's **Reward** column says how the inviter earned: **Use** (the friend used
  StratLab on 3 days in their first 2 weeks; 2 a rolling year), **Payment** (the friend's first real Razorpay charge
  within 90 days of joining; 2 a rolling year), **Payment (25% of a month)** (8 days of free time after that; 8 a year;
  the percentage is `INVITE_EXTRA_PCT` in `invite_rewards.py`), **Waiting to subscribe**, or **Taken back (refund)**.
  For refunds and disputes to take a payment-based reward back, tick `refund.created`, `refund.processed` and
  `payment.dispute.created` in Razorpay's webhook settings, next to the subscription events.
- **Prices** (Billing): rupee prices are set in `plans.py` only. US dollars, euros and pounds have their own prices
  (`pricing.py`); every other currency follows the rupee price at the day's exchange rate. Any price can be overridden
  here, and cleared to go back to the default.
- **Invoices** (Billing): the seller's legal name, address, state, GSTIN and LUT ARN. Every payment gets a GST invoice
  (CGST and SGST within the state, IGST across states, exports zero-rated under the LUT).
- **Exchange holidays** (Data checks): a row per market with where its holidays come from (the calendar package or
  the exchange's own list), how far ahead they're known, the next holiday and a status with a hint. For India, add a
  holiday by hand or refresh from the exchange here.
- **Refreshes:** the results calendar, corporate actions and surveillance lists run on their own schedules; each has an
  admin refresh route (`/admin/results/refresh`, `/admin/corp-actions/refresh`, `/admin/surveillance/refresh`) for
  after an outage.

### Rates and rules

`backend/app/rules.py` lists every hard-coded rate and rule (tax slabs, STT, exchange and SEC fees, freeze limits,
interest rates, due dates) with its official source and the day each area was last checked; the **Rates and rules**
panel shows them. An area asks for a review after 90 days, or when a day it is known to change has passed (1 April, each
quarter's small-savings rates, the SEC's fiscal year). Every morning at 07:40 IST `rules_watch.py` reads the official
sources a program can read (NSE's freeze limits, lot sizes and circulars, the SEC's fee rate, the PPF rate), emails the
admins about a change and shows it here until you press **Mark seen**; **Read the sources now** runs it at once.
Nothing is applied by itself: a changed rate is changed in the code, with a test.

### Market breadth

`backend/app/breadth.py` counts, for each group (all NSE stocks, NIFTY 50, NIFTY 500, Midcap 150, Smallcap 250, US large
caps), how many stocks rose or fell, sit above their averages and made new highs or lows. It runs by itself after each
close (18:30 IST for India, 17:45 New York for the US), and the first run on a new server reads about two years. The
**Market breadth** panel shows each market's last run (when, prices up to which day, stocks read and any that failed,
and the last error), and **Run now** works the whole two years out at once: a few minutes for the US, 20 to 25 for India,
which needs the day's broker login (**Log in** on Services). The same is `POST /admin/breadth/run?region=IN&full=true`;
`GET /admin/breadth` is the status.

### Positioning

`backend/app/positioning.py` reads the exchange's participant-wise open interest and volume files and its provisional
FII/DII cash numbers each trading evening from 18:40 IST, trying every 20 minutes until 21:30. At other times a
catch-up every 20 minutes reads whatever an evening run missed (a restart, a server started on a weekend): the cash
numbers and the last 10 days' participant files. On a new server it walks the archives back a year, 25 days a run, a
second and a half between files; five days missing in a row count as the archive refusing and are tried again later.
The option-chain facts and their history come from the recorded chains (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY and
SENSEX; `OPTION_SNAPSHOTS`). There's no panel: `GET /admin/positioning` shows the job, the archive walk and each part's
state, `POST /admin/positioning/run` reads the newest trading day now, and `POST /admin/positioning/run?backfill=true`
takes the next step back through the archives. When a number is missing, the page says why in words.

## Email

The server tries, in order:

1. `BREVO_API_KEY`: over HTTPS. In Brevo, verify the sender address, and if Brevo blocks the server's IP, turn off the
   IP blocking under your name (top right) → **Security → Authorized IPs** (the test email's error says where).
2. `RESEND_API_KEY`: over HTTPS; verify the sending domain in Resend.
3. SMTP: `SMTP_HOST`, `SMTP_PORT` (465 SSL, 587 STARTTLS), `SMTP_USER`, `SMTP_PASSWORD`. Railway blocks outgoing mail
   ports, so on Railway use Brevo or Resend.

`ALERT_FROM_EMAIL` sets the sender. Until one channel is set, the Account page doesn't offer email, and alerts go by
phone notification or Telegram instead.

- **Admin → Services → Send a test email** sends one to you and shows the exact reason when it can't.
- Alert, scan and newsletter email goes only to an address the user confirmed from a link. Every email carries a signed
  one-click unsubscribe link (and the `List-Unsubscribe` headers); the unsubscribe page asks first, so mail scanners
  opening links don't unsubscribe anyone.
- Links in emails point at the backend itself: set `PUBLIC_API_URL` (on Railway it defaults to the service's public
  domain). `MAIL_TOKEN_SECRET` signs those links; without it one is derived from the Supabase service key.
- What goes out: trade alerts and the daily report, stock, results, corporate-action, red-flag, scan and market breadth
  alerts, advance tax and money calendar reminders, the newsletters (`backend/app/newsletter/`), the weekly screen
  email, lifecycle emails (welcome, first test, trial and offer reminders, what's new, receipts, invite rewards), and
  the owner's Monday summary.

## Usage analytics (PostHog)

Off until a key is set: with no key nothing is downloaded and nothing is sent.

- **Frontend:** `POSTHOG_KEY` (the project API key, `phc_…`, public by design) and `POSTHOG_HOST` in
  `frontend/public/config.js`, or `VITE_POSTHOG_KEY` / `VITE_POSTHOG_HOST` at build time. The production project is on
  PostHog's US cloud (`https://us.i.posthog.com`), which is also the default; for an EU project set the host and change
  the PostHog host in the CSP in `vercel.json`.
- **Backend:** the same key as `POSTHOG_KEY` (and `POSTHOG_HOST`) on Railway, so a completed payment is counted from the
  server, once per payment, where an ad blocker or a closed tab can't lose it.
- **What's sent:** page views (addresses with ids, tokens and queries masked) and a fixed list of funnel events, from
  "signed up" to "payment completed", all through `track()` in `frontend/src/lib/analytics.ts`. Tied to the internal
  user id only: no emails, names, symbols held or amounts, no session recording and no autocapture. Browsers sending
  Do Not Track are skipped. The privacy page says so.
- In PostHog's project settings, turn on "Discard client IP data".
- **Admin → Overview** links to the dashboard once a key is set.

## Error alerts (Sentry)

Optional. `SENTRY_DSN` on the backend (`SENTRY_ENV` defaults to `production`) sends every server error tagged with the
ref code users see, plus errors in the paper trading loop and failed broker logins. `SENTRY_DSN` in
`frontend/public/config.js` does the same for browsers; the Sentry code only downloads when a DSN is set. Nothing
personal is sent.

## Storage

Admin → Data checks → **Storage** shows how full the main database is against Supabase's free 500 MB (`DB_LIMIT_MB`
sets another limit), its biggest tables and the biggest kinds of stored data. **Check every feature**'s **Database
space** row warns at 80% and fails at 95%, and says what to do.

- **First time:** the panel shows a short SQL snippet. Paste it into Supabase → SQL Editor → New query and press Run
  (it only reads sizes; it's also in `stratlab/supabase/schema.sql`).
- **When it gets near the limit:** add a second database on Railway (New → Database → PostgreSQL), then on the backend
  service add the variable `MARKET_DATABASE_URL` = `${{Postgres.DATABASE_URL}}`. After the redeploy, new market data
  is saved there: whole-market checks, stored company reads, breadth and positioning history, corporate actions, deals,
  the results and surveillance lists, the screens index, fund NAVs, exchange rates, holidays read from the exchange and
  the recorded option chains (`MARKET_PREFIXES` in `market_store.py`). It's read there first, and anything not moved yet
  is still read from Supabase, so nothing is lost. **Move market data now** moves what's already in Supabase (run it
  again to carry on if it stops). Users' own data and payments stay in Supabase. Supabase hands the space back after
  `vacuum full public.option_snapshots, public.app_settings;` in its SQL Editor.
- With the second database, older option chains can be kept longer: raise `OPTION_SNAPSHOT_KEEP_DAYS` (120 by default;
  120 days of all five indices is a few hundred MB).
- The second database isn't in the nightly backup. Most of it is rebuilt by the server's own jobs; what can't be
  fetched again is the recorded option chains (and the daily chain facts made from them) and the FII/DII cash history,
  which the exchange only publishes for the latest day. Keep that database for as long as you want those.

## Backups

Every night at 02:10 IST a GitHub Action (`.github/workflows/backup.yml`) copies the main database, encrypts it, and
keeps it on the repository's **Actions** page → *Database backup* → the run → *Artifacts*. A nightly copy holds the
app's tables without the recorded option chains' rows and is kept 7 days. The weekly one (Monday 02:10 IST, which is
still Sunday in UTC) and any run by hand (*Run workflow*) hold everything, the option chains too until they move to the
second database; they're named `…-full` and kept 28 days. Each copy has the app's tables (`app.dump`, the whole
`public` schema) and the sign-ins (`auth.dump`: `auth.users` and `auth.identities`; if those can't be copied, the run
warns and keeps the rest). A run with the secrets missing fails and says which to add.

Setup, once, in GitHub → Settings → Secrets and variables → Actions → New repository secret:

- `SUPABASE_DB_URL`: Supabase → **Connect** → *Session pooler* connection string, with your database password filled in.
- `BACKUP_PASSPHRASE`: a long random passphrase. Keep it in your password manager: without it a backup can't be opened.

Restoring (to a new Supabase project, or to check a copy). Download the artifact (a .zip) and use PostgreSQL 17's
client tools, as the copy is made with `pg_dump` 17:

```bash
unzip stratlab-db-2026-10-05.zip                           # the artifact holds the encrypted file
gpg -d stratlab-db-2026-10-05.tar.gpg | tar -xf -          # asks for BACKUP_PASSPHRASE; gives app.dump and auth.dump
pg_restore -d "$NEW_DB_URL" --no-owner --data-only auth.dump   # the sign-ins first: the app's tables point at them
pg_restore -d "$NEW_DB_URL" --no-owner --clean --if-exists app.dump
psql "$NEW_DB_URL" -f stratlab/supabase/schema.sql         # puts back the sign-up trigger on auth.users
```

The order matters: the app's tables refer to `auth.users`, so loading them before the sign-ins leaves those links
out; and the trigger that gives each new sign-up a profile is attached to `auth.users`, so it isn't in `app.dump`.
`schema.sql` only adds what's missing, so running it again is safe.

## Deploys

- **Backend (Railway):** one process (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, no extra workers). Live
  sessions, the tick feed and the daily login live in memory, so hosts that sleep when idle break paper trading.
- **Frontend (Vercel):** root `stratlab/frontend`; `vercel.json` sets the build, the security headers and CSP, and
  forwards `/v/*`, `/c/*`, `/stocks/*`, `/sitemap.xml` and `/sitemaps/*` to the backend. `public/config.js` holds the
  API address and the public keys, read at runtime.
- Pull requests merge once the backend, frontend and browser tests pass and the preview builds; Railway and Vercel then
  deploy. After a deploy, run **Check every feature**.
