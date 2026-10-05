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
| **Services** | Market data: the broker login state, **Log in**, **Run the automatic login now**. Other services: Telegram, email (**Send a test email**), phone notifications, Sentry, the option-chain recorder, the newsletters, and **Send this week's summary now** (the owner's Monday 9:00 IST email). **AI**: each provider's state, quota and models in use (success rate, median time, last problem), the order each kind of job asks them in, **Test every provider**, **Re-rank models**, **Pin** and **Block**, and the free providers not set up yet with where to get a key (see [AI providers](#ai-providers)) |
| **Data checks** | **Check every feature**, **Rates and rules**, **Market breadth** (**Run now** per market), **Fund costs (TER)** (**Read now**), **Storage**, the **Data audit**, the **Whole market** audits for India and the US, **Exchange holidays** for every market, and **Save real prices** (the price snapshot the tests run on) |
| **Users** | Every user with plan, join date, experiments, AI builds, invites and free months earned; **Change plan** grants Basic or Pro for 30 days, 90 days, a year or with no end. **Invite rewards** shows rewards given and sign-ups waiting for review. **Paper trading now** lists every running session with **Stop**. **Reported in the library** holds strategy-library entries people reported |
| **Billing** | The **Launch offer**, payments status and **Check payments**, **Prices** per currency, and **Invoices** (the seller's GST details and every invoice) |

### Check every feature (platform check)

`backend/app/platform_check.py`, shown on **Data checks**. Runs each part of StratLab once on the live server with live
data and compares what came back with what it should be: prices in every market and how fresh they are, a two-year
backtest per market, the NIFTY 50 and US scans, sector rotation, the NIFTY option chain, exchange filings, insider
trades, surveillance lists, BSE filings, company pages, news, the database and how full it is (**Database space**), the
holiday calendar of every market (a warning under 60 days known), **Rates and rules last reviewed**, and **Fund costs
(TER)** (see [Fund costs](#fund-costs-ter)). No AI is used,
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
- **Refreshes:** the results calendar, corporate actions, surveillance lists and F&O contract changes run on their own
  schedules; each has an admin refresh route (`/admin/results/refresh`, `/admin/corp-actions/refresh`,
  `/admin/surveillance/refresh`, `/admin/fo-changes/refresh`) for after an outage. There are no buttons for these:
  call them signed in as an admin (see [F&O contract changes](#fo-contract-changes)).

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

### Fund costs (TER)

`backend/app/money_mf_ter.py` reads the fund industry body's public monthly TER disclosure for **Mutual funds → Fund
costs**: the current and previous month at most every 12 hours (started when someone opens the page and the copy is
due), then one older month a run until two years are stored, with a pause between requests. It's kept market-wide in
`app_settings`; nothing in it is per user.

- **The panel** (Data checks → **Fund costs (TER)**): the last good read (when, how many schemes, which month), how many
  schemes and months are stored, the last error, and the check's verdict. The check passes when the last good read had
  500 or more schemes and is at most 45 days old, warns when it's older or smaller, and fails when nothing was ever read.
- **Read now** reads the disclosure at once in the background, whatever the age of the stored copy (a second press while
  it runs is refused). Press it on a new server, or when the check warns.
- While the very first read runs, users see "Costs are being read; check back shortly." The same is
  `GET /admin/ter` (status) and `POST /admin/ter/read`.

### F&O contract changes

`backend/app/fo_changes.py` keeps the dated list behind **Trade → F&O changes**: the exchange's F&O market lots file and
its F&O circulars (exits, entries, lot sizes, expiry days and sessions), read twice a trading day at 08:15 and 19:50
IST, and at once on a new server. A new change that touches a user's watchlist or running paper sessions is sent to
those who turned the alert on (Basic and up), once each.

- **No panel.** After an outage, or to see what the sources answer, call `POST /admin/fo-changes/refresh` signed in as
  an admin: it reads both sources now and returns what was added, any problems and each source's state. It sends no
  alerts; the next scheduled run sends any due.
- Expiry dates come from the listed contracts once the day's broker login is done, else from the exchange's rule.

### ETF price against NAV

`backend/app/etf_nav.py` reads the exchange's ETF list (price, indicative NAV) every few minutes while India's market is
open, records each ETF's close after the close with that day's NAV once the NAV file has it, and keeps 30 trading days.
It runs by itself and has no admin panel; a new server reads the list at once.

### Option-chain recorder (`OPTION_SNAPSHOTS`)

The recorder (Services → the option-chain recorder; Overview flags a problem) saves the chains named in
`OPTION_SNAPSHOTS` every `OPTION_SNAPSHOT_MINUTES` (5) in market hours and keeps `OPTION_SNAPSHOT_KEEP_DAYS` (120). The
default is all five: `NFO:NIFTY,NFO:BANKNIFTY,NFO:FINNIFTY,NFO:MIDCPNIFTY,BFO:SENSEX`.

- **Check Railway once:** a value set in **Railway → Variables** replaces the default. If `OPTION_SNAPSHOTS` is there
  from before FINNIFTY and MIDCPNIFTY were added (for example `NFO:NIFTY,NFO:BANKNIFTY,BFO:SENSEX`), delete it to use
  the default, or add the two, then redeploy. Without them, those indices get no chain facts or history on Positioning.
- An empty value turns recording off. Options backtesting and the Positioning chain history are built from these
  recordings, which can't be fetched again later, so keep it on.
- The option chain on the Options builder, with its IV and Greeks, is read live and doesn't depend on the recorder.

## AI providers

The idea builder, the ask bar, the research reads and the long-document reads (deep dive, report card) all go through
one AI layer (`backend/app/ai_providers.py`). It needs at least one key; two or three free ones from different
companies make it hard to take down. Each provider below is optional and skipped while its variables are empty. After
adding a key in **Railway → Variables**, redeploy, then press **Re-rank models** in **Admin → Services → AI**.

| Provider | Free allowance (checked October 2026) | Production use on the free tier | Get a key | Railway variables |
| --- | --- | --- | --- | --- |
| Groq | About 30 requests a minute and 1,000 a day per model; the big models also have a daily token cap | Yes | [console.groq.com/keys](https://console.groq.com/keys) | `GROQ_API_KEY` (`GROQ_MODEL`) |
| Google Gemini | Flash models: a few hundred to a thousand requests a day each; Gemma models many more | Yes. Free-tier prompts may be used by Google to improve its products | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `GEMINI_API_KEY` (`GEMINI_MODEL`) |
| Mistral | "Experiment" plan: about 1 request a second and a large monthly token allowance (phone check at sign-up) | Allowed, but prompts may be used to train Mistral's models | [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys) | `MISTRAL_API_KEY` (`MISTRAL_MODEL`) |
| Cerebras | About 1 million tokens a day (some new accounts get trial credit instead) | Yes | [cloud.cerebras.ai](https://cloud.cerebras.ai) | `CEREBRAS_API_KEY` (`CEREBRAS_MODEL`) |
| SambaNova | A few requests a minute per model | Yes | [cloud.sambanova.ai/apis](https://cloud.sambanova.ai/apis) | `SAMBANOVA_API_KEY` (`SAMBANOVA_MODEL`) |
| OpenRouter | Models marked `:free` only: 20 a minute, 50 a day (1,000 a day once $10 of credit was ever bought) | Yes; some free models' hosts log prompts | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) | `OPENROUTER_API_KEY` (`OPENROUTER_MODEL`) |
| Cloudflare Workers AI | 10,000 "neurons" a day (a few hundred short answers), reset at 00:00 UTC | Yes | [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens): use the "Workers AI" token template; the account id is on the dashboard's overview | `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` (`CLOUDFLARE_MODEL`) |
| Z.ai (GLM Flash) | The GLM Flash models cost nothing; about one request at a time | No clear statement either way: check z.ai's terms before relying on it. China-based | [z.ai/manage-apikey/apikey-list](https://z.ai/manage-apikey/apikey-list) | `ZAI_API_KEY` (`ZAI_MODEL`) |
| Hugging Face | $0.10 of credit a month (about a hundred short answers); $2 with a PRO account | Yes (it's their paid service with a small free credit) | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens): a fine-grained token with "Make calls to Inference Providers" | `HF_TOKEN` (`HUGGINGFACE_MODEL`) |
| Vercel AI Gateway | $5 of credit every 30 days on a set of free-tier models; buying credit ends the monthly $5 | **Flagged:** fine on a Vercel Pro team; Vercel's Hobby plan is for personal, non-commercial use. Asked after the production-ready providers | [vercel.com/dashboard/ai-gateway](https://vercel.com/dashboard/ai-gateway) | `AI_GATEWAY_API_KEY` (`AI_GATEWAY_MODEL`) |
| GitHub Models | 50 to 150 requests a day per model; 8,000 tokens in and 4,000 out per request | **Flagged: prototyping tier.** GitHub describes free use as for prototyping. Asked only after every other free provider, and never for long documents | [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new): a fine-grained token with the "Models" (read) permission | `GITHUB_MODELS_TOKEN` (`GITHUB_MODEL`) |
| NVIDIA API catalog | About 40 requests a minute | **Flagged: development and testing only** under NVIDIA's terms. Asked only after every other free provider | [build.nvidia.com/settings/api-keys](https://build.nvidia.com/settings/api-keys) | `NVIDIA_API_KEY` (`NVIDIA_MODEL`) |
| Anthropic | None (paid) | Yes | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) | `ANTHROPIC_API_KEY` (`ANTHROPIC_MODEL`) |

Left out on purpose: **Chutes** (its free API tier ended on 30 September 2026), **Cohere** (the free trial key is for
non-commercial use only) and anonymous gateways such as LLM7 and Pollinations (no account, no terms to rely on, and
prompts pass through a third party). Free limits change often: the **Test** and **Re-rank** buttons show what actually
works today.

**Suggested set-up:** Groq, Google Gemini and Mistral first (production-ready, generous), then Cloudflare and Cerebras.
The flagged ones add resilience but are asked last.

### How it picks models

- **Measured, not listed.** Every 6 hours (every 12 on Cloudflare, 24 on GitHub and 72 on Hugging Face, where measuring spends scarce credit; Anthropic only on demand), when you press **Re-rank models**, and
  when every model a provider was using stops working, each provider's model list is read and filtered
  (`backend/app/ai_catalog.py`, with a comment per rule): no speech, image, embedding, safety-filter or search models,
  no code or maths specialists, no models built for another language (such as ALLaM, which is Arabic-first), nothing
  under about 8B parameters when the name says its size, and no slow reasoners (R1 and its distills). Up to six of the
  rest are each asked two small questions: a JSON object with exact values, and a one-sentence English answer about
  revenue plus a one-word finance term. The ones that answer correctly are ranked by success rate, then speed, and the
  best three per provider are used. Results are stored in `app_settings` (`ai:rank:<provider>`), so a restart keeps
  them; before the first measurement each provider's known-good models (`defaults` in `ai_catalog.py`) are used.
- **Every real request counts too:** each model's recent successes, failures and times feed the same score.
- **By job:** quick jobs (idea builder, ask bar) put fast models first; research reads and long documents put strong
  ones first and skip models whose context window the document wouldn't fit. The prototyping-tier providers come after
  every production-ready one, and Anthropic (paid) is always last. The order each job uses right now is shown in the
  panel. `AI_PROVIDERS` (and `AI_PROVIDERS_RESEARCH` for research and long reads) can still fix the order of providers
  by hand; measurement then only orders each provider's own models.
- **Reasoning models** (gpt-oss, Qwen 3, GLM, MiniMax, Gemma 4, o-series…) are asked to think little or not at all in
  whichever way the provider accepts (`reasoning_effort`, `enable_thinking`, `thinking.type`, `/no_think`, Gemini's
  thinking budget), get extra room for the answer, and their `<think>` blocks are stripped. A reply that holds only
  reasoning is used only when the final answer is clearly marked. A setting a provider rejects is removed and the
  request sent again.
- **Every reply is checked:** not empty, not cut off, and a JSON object. An empty or cut-off reply gets one more try
  with more room; anything else moves straight to the next model.
- **Breakers and quotas:** a model that fails twice in a row is skipped for 2 minutes, doubling up to 6 hours; a
  provider erroring 3 times in a row is paused for a minute, doubling up to 15. A rate limit (429) pauses the model or
  the provider until the reset time it sends (`Retry-After`, the `x-ratelimit-reset-*` headers, Google's
  `retryDelay`), and a provider that says it has no requests left is not asked until its reset. A rejected key pauses
  the provider for 30 minutes; an unknown or retired model is skipped for 6 hours.
- **Time budgets:** a whole request takes at most 30 s for quick jobs, 60 s for research reads and 120 s for long
  documents (`BUDGET` in `ai_providers.py`), however many models are tried.
- **Cache:** the same question for the same job is answered from memory for 6 hours (quick), 1 hour (research) or 12
  hours (long), so a repeat doesn't spend free quota.
- **Errors users see never name a provider**; the details (each model's error) are on the Admin page.

### The AI panel (Admin → Services)

Per provider: its state (OK, Check, Problem, Not tested), the free limit and terms, the quota left and when it resets,
when it was last measured and what was left out, and each model in use with its success rate, median time and last
problem. **Test every provider** sends a tiny request to each now; **Re-rank models** (or **Re-rank** on one provider)
measures again in the background; **Pin** uses only that model for its provider (until **Unpin**; a
`<NAME>_MODEL` in Railway pins too); **Block** never uses a model again (until **Unblock**). Providers without a key are
listed with what they offer, a **Get a key** link and the Railway variables to set. The API behind it is
`GET /admin/ai`, `POST /admin/ai/test`, `POST /admin/ai/rerank` (`{"provider"}` optional), `POST /admin/ai/pin`
(`{"provider", "model"}`, `null` to unpin) and `POST /admin/ai/block` (`{"provider", "model", "blocked"}`).

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
