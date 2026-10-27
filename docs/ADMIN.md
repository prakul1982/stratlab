# Running StratLab: admin operations

[← Back to the project overview](../README.md) · [Setup guide](../stratlab/README.md)

Everything the site owner does after deploy: the Admin page, the checks and jobs that run by themselves, email,
analytics, error alerts, memory, storage and backups. Setting up the services the first time (Supabase, the broker data API,
Razorpay, AI keys) is in the [setup guide](../stratlab/README.md).

## Who is an admin

Set `ADMIN_EMAILS` on the backend to one or more Google addresses, comma-separated, and redeploy. Signed in with one
of them (Google-verified, and the current sign-in address), you get **Admin** in the account menu (your initials at the
foot of the menu). Everyone else gets a 403 from every `/admin` route and never sees the link.

## The Admin page

Admin is its own area with a left menu of seven sections. **Refresh** at the top re-reads the page. Old links such as
`/admin?tab=services` open the section that took over.

| Section | What's on it |
| --- | --- |
| **Overview** | **Needs your attention**, worst first (the broker not logged in or its automatic login failing, the live price feed, AI providers down, email not set up, server errors, library entries users reported, a data job that failed or needs a look, holidays running out, rate or rule sources that changed, whole-market audit mismatches, invoice details missing, payments not connected). **Today's numbers** (sign-ups, revenue, server errors since the last restart), **Money, use and limits** (30-day revenue, active users, emails sent today against the email service's daily limit, links to the bills StratLab can't read), **Services** (one light each for the live price feed, AI providers, the broker login, the automatic login, alert emails, US company data, payments and exchange holidays), **Data feeds** (a light per background job), **This month** with a link to the PostHog dashboard once a key is set, and **View as a plan** (see [View as](#view-as-a-plan)) |
| **Users and growth** | **Plans ending and sign-ins without a profile**; **Invite rewards** (given, and waiting for review); **Users** (search by email, filter by plan, experiments and AI builds this month, invites and free months earned; **Change plan** grants Basic or Pro for 30 days, 90 days, a year or with no end, and **Delete data** removes one person's app data behind a confirmation); the **Launch offer**; **Paper trading now** lists every running session with **Stop** |
| **Money** | **Payments** (Razorpay connected, the webhook secret, international cards; **Check payments setup**), **Subscriptions and payments** (the newest 50 of each, refunds and failed payments, revenue by month), **Prices outside India** and **Invoice details** with every invoice |
| **Data and jobs** | **Background jobs**: every job with its status, last run, schedule and a **Run now** where it has one, and a **Log** of what it reported; **India broker data** (the broker login state, **Log in to the broker**, **Run the automatic login now**); **Exchange holidays** for every market; **Storage** (see [Storage](#storage)) |
| **Quality** | The **Data audit** and the **Whole market** audit for India or the US, **Reported strategies** (strategy-library entries people reported: **Restore**, **Hide** or **Delete**), and **Rates and rules** |
| **System** | **Server errors** (the last 25 unexpected errors with the request, the error, the line of code and the ref code the user saw, kept across restarts), **Other services** (alert channels, US company data, alert email with **Send a test email**, **Email a reviewer sign-in link** and **Send this week's summary now**, the exchange filings feed with **Check filings feed**), **Build** (which commit each host runs), the **AI providers** (see [AI providers](#ai-providers)), **Check every feature** and **Real prices for testing** |
| **Email previews** | Every email StratLab sends, as a reader gets it, at desktop or phone width or as text. The market briefs are the newest real issues; the rest use made-up details and say so. Nothing here is sent except **Send me a test** to your own address |

### Background jobs (Data and jobs)

One row per job (`backend/app/admin_jobs.py`): market breadth, the quarter-hour breadth rounds, red flags across
companies, newsletters, positioning, ETF price against NAV, fund costs (TER), exchange holidays, the results calendar,
corporate actions, market events, IPOs, F&O contract changes, surveillance lists, the closing auction, India VIX
history, option chain recording, company pages' prices, the daily Interactive Brokers read, the statement inbox
reminder and the library seed. Each row says when the job runs next (its own clock, in IST or New York time), when it
last ran and how that went:

- **OK**, **Check** or **Problem**. **Problem** is a failed run. **Check** is something to look at that isn't a failure:
  a job that reads several sources and got some of them (the row says which source was missed, what that leaves out,
  and whether the fault looks like the source's site), a feed waiting for a file the exchange hasn't published, or an IPO
  filing no exchange lists yet.
- **Run now** starts the job at once where it has a manual trigger (a job without a button runs on its clock only); a
  second press while it runs is refused. **Log** shows what the last run reported and what you ran from the page.
- A job's last status is kept in the database, so a row doesn't read "Not run yet" only because the server restarted.

### Check every feature (platform check)

`backend/app/platform_check.py`, shown on **System**. Runs each part of StratLab once on the live server with live
data and compares what came back with what it should be: prices in every market and how fresh they are, a two-year
backtest per market, the NIFTY 50 and US scans, sector rotation, the NIFTY option chain, exchange filings, insider
trades, surveillance lists, BSE filings, company pages, news, the database and how full it is (**Database space**), the
holiday calendar of every market (a warning under 60 days known), **Rates and rules last reviewed**, and **Fund costs
(TER)** (see [Fund costs](#fund-costs-ter)). No AI is used,
so it costs no allowance.

- **By itself:** every day at 4:50 pm IST. Anything that fails is tried again two minutes later; whatever still fails is
  emailed to the admins (and sent by phone notification or Telegram when set up in Settings).
- **By hand:** **Run checks** (about a minute). Run it after every deploy.
- The last runs show as a row of ticks and crosses, with the time of the last failure.

### Data audit (companies)

`backend/app/audit.py`, the **Data audit** panel on **Quality**. Runs every company in a set through the deep dive on the live server:
the numbers, prices, industry, valuation, checklist and documents, each compared with its source. **Mismatches** are
numbers that disagree with the source; **gaps** are things a user would still have to look up elsewhere. No AI is used;
about 3 to 10 seconds a company.

- Pick India or the US and a set: a ready-made group, every sector's main stocks, or (India) a whole NSE index such as
  the NIFTY 500. **Run audit**, **Stop**, and **Download CSV** of the findings.
- **Whole market (India / US):** reads the list of every listed company every six hours (NSE and BSE-only; US common
  stock only, no preferred shares, warrants, units or rights) and puts each new listing through the same checks the day
  it appears and again on each day of its first 10 days. Every company gets a **full check on the 1st of each month**
  (India time), the ones never checked first, then the problems still standing, then whoever was checked longest ago; the
  month's run is marked in the database so a restart doesn't repeat it. **Start** / **Pause** (with why it's paused), a
  progress bar with the rate and the time left, **Reset and check everything again**, **Re-check the N not checked
  yet**, **Read the list now**, **Re-check** on each company, and a **Full re-check on the 1st of each month**
  switch (on by default; off means only new listings until you reset). When BSE refuses the server, the panel says so
  and how many companies wait for their documents.
- **Why it's paused:** **off** (switched off; press **Start**), **busy** (a Data audit above is running; it carries on
  when that ends), **offline** (India only: the broker's market data login isn't done today, so prices can't be read;
  it carries on by itself once you log in), **cooling** (a source is turning every company away, so it waits between
  companies, up to half an hour, until it answers again).
- **Log in before the India audit.** The broker's login lasts one day. Each day, **Log in to the broker** on Data and jobs (or let the
  automatic login run) before the India whole-market audit is due; until then it waits as **offline** rather than
  marking every company "not checked yet".
- **Clearing "not checked yet" rows:** a check a source turned away is tried again by itself, 20 an hour, backing off
  to a day while the source keeps refusing. To retry them all at once, press **Re-check the N not checked yet**: it
  re-checks only those rows, not the whole list.
- **What the India checks treat as facts, not gaps:** a company that holds only one-on-one meetings with investors
  (earnings calls are counted apart; a call with no transcript stays a gap) or files no investor presentation; for a
  company with no sales in the years compared, "N checks can't be judged without sales"; a margin above 100% explained
  by nil or negative sales or costs written back; new or untraded listings and DVR shares. ETFs and trusts in the
  broker's list are not checked as companies. When the company page has no P/E it is worked out from market value
  and trailing profit (or the reason is given: a loss, no market value, no balance sheet), and capex the balance
  sheet can't estimate is read from the fixed assets bought in the cash flow breakdown.
- A failed read of the stored results after a restart never overwrites them: nothing is checked or saved until they
  have been read (the panel says it's reading).
- Stored findings are re-read with today's rules, so a fix shows up without re-running everything.

### Other admin jobs

- **Launch offer** (Users and growth): every user gets every Pro feature free for N days, starting now. Users see a banner and a
  countdown; Plans and Account still show what they actually pay for. It ends by itself, or press **End now**.
- **Invite rewards** (Users and growth): more than 5 sign-ups through one link in a day wait here for review; the sign-ups
  themselves go through. Approve or reject each reward. A daily check from 6 am IST gives rewards and closes invites
  whose 14 days ran out. The Given table's **Reward** column says how the inviter earned: **Use** (the friend used
  StratLab on 3 days in their first 2 weeks; 2 a rolling year), **Payment** (the friend's first real Razorpay charge
  within 90 days of joining; 2 a rolling year), **Payment (25% of a month)** (8 days of free time after that; 8 a year;
  the percentage is `INVITE_EXTRA_PCT` in `invite_rewards.py`), **Waiting to subscribe**, or **Taken back (refund)**.
  For refunds and disputes to take a payment-based reward back, tick `refund.created`, `refund.processed` and
  `payment.dispute.created` in Razorpay's webhook settings, next to the subscription events.
- **Prices** (Money): rupee prices are set in `plans.py` only. Every other currency (18 of them, in `pricing.py`) has
  its own fixed price, set from the rupee price at 24 October's rates and rounded; it doesn't move with the exchange rate
  and changing the rupee price doesn't change it. Any price can be overridden here, and cleared to go back to the set
  price. **Read today's rates** only refreshes the "about ₹…" notes. No Razorpay plan is needed to show a price: without
  one in that currency, visitors pay the rupee price and their card converts it.
- **Invoices** (Money): the seller's legal name, address, state, GSTIN and LUT ARN. Every payment gets a GST invoice
  (CGST and SGST within the state, IGST across states, exports zero-rated under the LUT).
- **Exchange holidays** (Data and jobs): a row per market with where its holidays come from (the calendar package or
  the exchange's own list), how far ahead they're known, the next holiday and a status with a hint. For India, add a
  holiday by hand or refresh from the exchange here.
- **Library seed** (Data and jobs): StratLab's own library strategies are run through the app's own backtest and verdict on the
  standard groups of every market the backtester reads (India, the US, UK, Europe, Japan, crypto, forex, Indian commodities,
  Indian currency futures and global commodities). A start-up run publishes only the entries the library lacks, so a market
  added later is seeded once and nothing already there is run again; **Run now** refreshes them all (`/admin/library/seed`).
  Markets on the broker's feed wait for the daily login.
- **Closed accounts:** a user can delete their own account (Account → Your data → Delete my account). It erases every store's
  data and the sign-in account at once, and keeps invoices and the payment records behind them. It refuses while a plan would
  still be billed (the user cancels first) and for the owner's account, which is closed from the sign-in service, not from here.
- **Layout checker:** every change is measured page by page in CI ([UI_CHECKER.md](UI_CHECKER.md)); a failing run keeps its report
  and screenshots on the run's page.
- **Refreshes:** the results calendar, corporate actions, surveillance lists, market events, IPOs and F&O contract
  changes run on their own schedules, and each has a **Run now** in **Data and jobs** (the routes behind them are
  `/admin/results/refresh`, `/admin/corp-actions/refresh`, `/admin/surveillance/refresh`, `/admin/events/refresh`,
  `/admin/ipos/refresh` and `/admin/fo-changes/refresh`) for after an outage. Corporate actions also has **Read the whole
  US universe**.

### Rates and rules

`backend/app/rules.py` lists every hard-coded rate and rule (tax slabs, STT, exchange and SEC fees, freeze limits,
interest rates, due dates) with its official source and the day each area was last checked; the **Rates and rules**
panel on **Quality** shows them. An area asks for a review after 90 days, or when a day it is known to change has passed (1 April, each
quarter's small-savings rates, the SEC's fiscal year). Every morning at 07:40 IST `rules_watch.py` reads the official
sources a program can read (NSE's freeze limits, lot sizes and circulars, the SEC's fee rate, the PPF rate), emails the
admins about a change and shows it here until you press **Mark seen**; **Read the sources now** runs it at once.
Nothing is applied by itself: a changed rate is changed in the code, with a test.

### Market breadth

`backend/app/breadth.py` counts, for each group (all NSE stocks, NIFTY 50, NIFTY 500, Midcap 150, Smallcap 250, US large
caps), how many stocks rose or fell, sit above their averages and made new highs or lows. It runs by itself after each
close (18:30 IST for India, 16:55 New York for the US, in by about 5:05 PM there), and the first run on a new server
reads about two years. The **Market breadth** row in **Data and jobs** shows each market's last run (when, prices up to
which day, stocks read and any that failed, and the last error), and **Run India** and **Run US** work the whole two
years out at once: a few minutes for the US, 20 to 25 for India, which needs the day's broker login (**Log in to the
broker** on Data and jobs). The same is `POST /admin/breadth/run?region=IN&full=true`; `GET /admin/breadth` is the
status.

While India's market is open, `backend/app/breadth_live.py` also works the same measures out from the live prices every
quarter hour (09:15 to 15:30 IST) for the Indian groups, a few requests a round whatever the number of stocks. The
**Intraday breadth rounds** row shows the last round (its time and how many stocks it read) and says **Late** when the
newest round is more than 20 minutes old.

### Positioning

`backend/app/positioning.py` reads the exchange's participant-wise open interest and volume files and its provisional
FII/DII cash numbers each trading evening from 18:40 IST, trying every 20 minutes until 21:30. At other times a
catch-up every 20 minutes reads whatever an evening run missed (a restart, a server started on a weekend): the cash
numbers and the last 10 days' participant files. On a new server it walks the archives back a year, 25 days a run, a
second and a half between files; five days missing in a row count as the archive refusing and are tried again later.
The option-chain facts and their history come from the recorded chains (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY and
SENSEX; `OPTION_SNAPSHOTS`). The **Positioning** row in **Data and jobs** has **Run now**, which reads the newest
trading day (the row is a **Check** while a file isn't out yet); `GET /admin/positioning` shows the archive walk and each
part's state, and `POST /admin/positioning/run?backfill=true` takes the next step back through the archives. When a
number is missing, the page says why in words.

### Fund costs (TER)

`backend/app/money_mf_ter.py` reads the fund industry body's public monthly TER disclosure for **Mutual funds → Fund
costs**: the current and previous month at most every 12 hours (started when someone opens the page and the copy is
due), then one older month a run until two years are stored, with a pause between requests. It's kept market-wide in
`app_settings`; nothing in it is per user.

- **The row** (**Data and jobs** → **Fund costs (TER)**): the last good read (when, how many schemes, which month), how
  many schemes and months are stored and the last error. **Check every feature** has a **Fund costs (TER)** check that
  passes when the last good read had 500 or more schemes and is at most 45 days old, warns when it's older or smaller,
  and fails when nothing was ever read.
- **Read now** reads the disclosure at once in the background, whatever the age of the stored copy (a second press while
  it runs is refused). Press it on a new server, or when the check warns.
- While the very first read runs, users see "Costs are being read; check back shortly." The same is
  `GET /admin/ter` (status) and `POST /admin/ter/read`.

### F&O contract changes

`backend/app/fo_changes.py` keeps the dated list behind **Trade → F&O changes**: the exchange's F&O market lots file and
its F&O circulars (exits, entries, lot sizes, expiry days and sessions), read twice a trading day at 08:15 and 19:50
IST, and at once on a new server. A new change that touches a user's watchlist or running paper sessions is sent to
those who turned the alert on (Basic and up), once each.

- **The row** (**Data and jobs** → **F&O contract changes**) shows the last run and each source's state, and **Run now**
  reads both sources at once and sends no alerts; the next scheduled run sends any due. After an outage, or to see what
  the sources answer, `POST /admin/fo-changes/refresh` returns what was added, any problems and each source's state.
- Expiry dates come from the listed contracts once the day's broker login is done, else from the exchange's rule.

### ETF price against NAV

`backend/app/etf_nav.py` reads the exchange's ETF list (price and the last published NAV; it gives no indicative NAV)
every 4 minutes while India's market is open, takes each ETF's ISIN from the exchange's ETF securities file (once a
day) to match it in the NAV file, records each ETF's close after 3:45 PM IST with that day's NAV once the NAV file has
it, and keeps 30 trading days. It runs by itself; a new server reads the list at once. The **ETF price against NAV**
row in **Data and jobs** has **Read now**.

### IPOs

`backend/app/ipo.py` keeps the lists behind **Invest → IPOs**, one stored row per issue. India is read at 7:40 AM and
8:10 PM IST (NSE's and BSE's public-issue pages, and every page of SEBI's draft and red herring prospectus lists) and the US at 8:30 AM and 9:30 PM IST (the public IPO calendar and the SEC's S-1,
F-1 and prospectus filings). While an Indian issue is open its bids are read every 15 minutes from 9:55 AM to 5:30 PM
IST, and the final bids after 7:20 PM. Between the reads the offer documents are fetched and the summaries written a few
at a time; the alerts go at 8:00 AM IST (India) and 7:00 PM IST (the US dates). **Data and jobs → IPOs** has **Run now**
and the log.

- **The completeness check.** After each read the lists are compared with the exchanges' and regulators' own: an issue
  on NSE's or BSE's list that ours lacks, or has without dates, or one BSE says is listed that ours doesn't, is a
  **Problem**. A red herring prospectus filed with SEBI that no exchange lists yet, or a US final prospectus not yet
  confirmed as a company's first offering, is a **Check** ("To check"), looked for again every day: it is usually an
  issue that hasn't been announced yet, not a gap in StratLab.
- Issues the exchange names withdrawn, postponed or cancelled are kept in their own list with that word, with no alerts,
  and Social Stock Exchange fund raises are labelled as not IPOs.
- The offer-document summaries use the AI layer: each document is summarised once, for everyone, up to 120 a day; a
  statement is kept only when its quote is found in the document.

### Option-chain recorder (`OPTION_SNAPSHOTS`)

The recorder (**Data and jobs → Option chain recording**: when it last saved, how many chains today, any problem) saves the chains named in
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
adding a key in **Railway → Variables**, redeploy, then press **Re-rank models** in **Admin → System → AI providers**.

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
| NVIDIA API catalog | About 40 requests a minute | **Flagged: development and testing only** under NVIDIA's terms. Asked only after every other free provider | [build.nvidia.com/settings/api-keys](https://build.nvidia.com/settings/api-keys) | `NVIDIA_API_KEY` (`NVIDIA_MODEL`) |
| Anthropic | None (paid) | Yes | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) | `ANTHROPIC_API_KEY` (`ANTHROPIC_MODEL`) |

Left out on purpose: **GitHub Models** (GitHub retired it on 30 July 2026), **Chutes** (its free API tier ended on
30 September 2026), **Cohere** (the free trial key is for non-commercial use only) and anonymous gateways such as LLM7
and Pollinations (no account, no terms to rely on, and prompts pass through a third party). Free limits change often:
the **Test** and **Re-rank** buttons show what actually works today.

**Suggested set-up:** Groq, Google Gemini and Mistral first (production-ready, generous), then Cloudflare and Cerebras.
The flagged ones add resilience but are asked last.

### How it picks models

- **Measured, not listed.** Every 6 hours (every 12 on Cloudflare and 72 on Hugging Face, where measuring spends scarce credit; Anthropic only on demand), when you press **Re-rank models**, and
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

### The AI panel (Admin → System)

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

`ALERT_FROM_EMAIL` sets the sender. Until one channel is set, Settings doesn't offer email, and alerts go by
phone notification or Telegram instead.

- **Admin → System → Other services → Send a test email** sends one to you and shows the exact reason when it can't.
- Alert, scan and newsletter email goes only to an address the user confirmed from a link. Every email carries a signed
  one-click unsubscribe link (and the `List-Unsubscribe` headers); the unsubscribe page asks first, so mail scanners
  opening links don't unsubscribe anyone.
- Links in emails point at the backend itself: set `PUBLIC_API_URL` (on Railway it defaults to the service's public
  domain). `MAIL_TOKEN_SECRET` signs those links; without it one is derived from the Supabase service key.
- What goes out: trade alerts and the daily report, stock, results, corporate-action, red-flag, scan, market breadth,
  F&O change, ETF gap, IPO, business update and named holder alerts, market event, advance tax and money calendar
  reminders, the newsletters (`backend/app/newsletter/`), the weekly screen email, lifecycle emails (welcome, first test,
  trial and offer reminders, what's new, receipts, invite rewards), and the owner's Monday summary. **Admin → Email
  previews** shows each one as a reader gets it.

## India broker login

Indian prices, F&O, MCX, live ticks, India paper trading, India market breadth and the India audit need the broker's
market data login every day: its tokens end each morning at about 6 am.

- **By hand:** **Admin → Data and jobs → India broker data → Log in to the broker** opens the broker's login in a new tab.
  After it, the server restarts itself (live sessions are saved first and resume), because the live feed can't switch to
  a new token inside a running process.
- **Automatically:** with `KITE_USER_ID`, `KITE_PASSWORD` and `KITE_TOTP_SECRET` set, the server logs in by itself every
  day from `KITE_AUTO_LOGIN_AT` (IST, 08:00 unless set). **Run the automatic login now** tests it and shows the result. A
  rejected password is not retried that day; a rejected 2FA code gets one more try with the next code; a network error is
  retried every 5 minutes, up to 6 attempts a day. When it gives up it tells the admin (Overview, and Telegram when
  `ADMIN_TELEGRAM_CHAT_ID` is set).
- **A CAPTCHA on Zerodha's login page.** Repeated failed logins can make Zerodha ask for a CAPTCHA, which the automatic
  login can't answer. Log in once by hand on kite.zerodha.com in a browser to clear it, then press **Run the automatic
  login now**. Keep the password and the 2FA secret right (and `KITE_AUTO_LOGIN_AT` away from any other program's
  login on the same account) so the failures don't repeat.
- Give StratLab its own API app. A new login to the same app cancels the previous token, so a bot sharing the key would
  knock StratLab out; StratLab notices, goes offline with a message and does not log in again by itself.

## View as a plan

**Overview → View as a plan** (or **View as:** in the account menu) with Free, Basic, Pro or Off: the app reads as that
plan's user would see it, on the live site, with its locks, upgrade prompts and monthly limits; the launch offer and free
Basic time are left out. A banner on every page says "Viewing as Free. Your real plan is unchanged." with a **Turn off**
button, and the choice stays on that device across reloads. The page sends it as an `X-View-As` header, which the server
honours for a Google-verified admin only; your stored plan, billing and Admin access are never touched, and
subscribing, verifying and cancelling are refused while it is on.

## Connect once (Settings → Connected accounts)

Four things a user connects once so their numbers keep updating. Each shows "Not set up yet" (or "Not open yet") until the
settings below are in place; nothing here invents a value. Every password and token a user hands over is encrypted at
rest with `CONNECT_SECRET_KEY`, never written to a log (`backend/app/connect/redact.py` masks them), never sent back to
the page, and deleted when the user disconnects.

### 1. The encryption key (needed for everything below)

Make a key once and add it as `CONNECT_SECRET_KEY` in Railway → Variables:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep a copy somewhere safe: if it is lost or changed, stored statement passwords and broker tokens can't be opened and users
have to enter them again. To rotate, set `CONNECT_SECRET_KEY` to `<new key>,<old key>` (the first encrypts, all decrypt).

### 2. Statement inbox (a private address per user)

Each user gets `u-<20 random letters and digits>@<INBOUND_DOMAIN>`. Their email filter forwards the monthly NSDL, CDSL, CAMS,
KFintech and MF Central statements there; the server opens the PDF in memory with the user's stored password, saves the
holdings and funds through the same code as an upload, and keeps nothing of the PDF. Brevo (already the app's mail
service) does the receiving. Steps for the owner:

1. Pick a receiving subdomain that has no other mail, for example `in.stratlab.studio`. It must not be a domain or
   subdomain that already receives your own mail.
2. In your DNS (wherever `stratlab.studio` is managed) add two MX records on that subdomain, as Brevo's inbound parsing
   guide says (https://developers.brevo.com/docs/inbound-parse-webhooks):

   | Host | Type | Priority | Value |
   |---|---|---|---|
   | `in.stratlab.studio` | MX | 10 | `inbound1.sendinblue.com.` |
   | `in.stratlab.studio` | MX | 20 | `inbound2.sendinblue.com.` |

3. In Railway → Variables add `INBOUND_DOMAIN=in.stratlab.studio`, `INBOUND_PROVIDER=brevo`, and `INBOUND_WEBHOOK_SECRET=` a
   long random string (for example the output of `openssl rand -hex 24`), and keep `BREVO_API_KEY` set (it is also used to
   download the attachments). Redeploy.
4. Register the webhook with Brevo, once:

   ```
   curl -X POST https://api.brevo.com/v3/webhooks \
     -H "api-key: $BREVO_API_KEY" -H "content-type: application/json" \
     -d '{"type":"inbound","events":["inboundEmailProcessed"],"domain":"in.stratlab.studio",
          "url":"https://<your API host>/inbound/email/brevo?k=<INBOUND_WEBHOOK_SECRET>","description":"StratLab statements"}'
   ```

   Brevo doesn't sign its webhooks, so the secret `k` in the address is the check (compared in constant time); a wrong or
   missing one gets 401. Treat the address as a password.
5. Test: sign in, Settings → Connected accounts → Statement inbox → Set up my inbox, then send a mail with a made-up PDF
   to the address and watch "Last received" change.

Not using Brevo? `INBOUND_PROVIDER=signed` takes any forwarder that posts JSON signed with HMAC-SHA256 to
`/inbound/email/signed` with the header `X-StratLab-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>." + body, key
INBOUND_WEBHOOK_SECRET>`; body `{"to": [...], "from", "subject", "text", "message_id", "attachments": [{"name",
"content_type", "data_b64"}]}` (for example an email worker on a Cloudflare-routed domain). Another provider is one
adapter class in `backend/app/connect/inbound.py`.

Behaviour worth knowing: unknown addresses get the same 200 as real ones (so addresses can't be guessed); at most 30 mails
a day per address and 120 posts a minute overall; Gmail's forwarding-confirmation mail is recognised and its code is
shown on the user's card; a user with no statement for 40 days gets a reminder through their usual notifications. The
background job `connect-once` does the reminders, the daily Interactive Brokers read and the owner's own Zerodha read.

### 3. Zerodha login for every user

Built and switched off. Until Zerodha approves a multi-user Kite Connect app, only admins (`ADMIN_EMAILS`) can connect their
own Zerodha; for everyone else the card says "Not open yet" (`KITE_MULTIUSER_APPROVED` is `false`). Zerodha's terms for apps serving many users need their
approval: ask through the Kite Connect forum (https://kite.trade) or Zerodha support. Once approved:

1. In the Kite developer console (https://developers.kite.trade/apps) set the app's **redirect URL** to
   `https://<your API host>/connect/kite/callback`. (If you keep using the existing app, its `/admin/kite/callback`
   address also works: it hands user logins over by their state.) A separate multi-user app can be used by setting
   `KITE_CONNECT_API_KEY` and `KITE_CONNECT_API_SECRET`; otherwise `KITE_API_KEY` and `KITE_API_SECRET` are used.
2. Set `KITE_MULTIUSER_APPROVED=true` in Railway and redeploy.

Zerodha ends every login at about 6 am, so users tap once a day ("Connected · refreshed today 09:12 · tap to refresh
tomorrow"); there is no way around that daily step.

### 4. Interactive Brokers (US stocks)

Nothing to set beyond `CONNECT_SECRET_KEY`. Each user pastes their own Flex token and query id; a daily job (from 07:00 India
time) reads their positions into My Holdings (US) and closed trades into the trade journal (US).

### 5. EPF, NPS and AIS uploads

No setup. The file is looked at in memory, the figures found are shown to the user, and only what they confirm is saved.

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

**Admin → Data and jobs → Storage** shows how full the main database is against Supabase's free 500 MB (`DB_LIMIT_MB`
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
  again to carry on if it stops). Users' own data and payments stay in Supabase until they're moved too (*Users'
  data on Railway*, below). Supabase hands the space back after
  `vacuum full public.option_snapshots, public.app_settings;` in its SQL Editor.
- With the second database, older option chains can be kept longer: raise `OPTION_SNAPSHOT_KEEP_DAYS` (120 by default;
  120 days of all five indices is a few hundred MB).
- The second database isn't in the nightly backup. Most of it is rebuilt by the server's own jobs; what can't be
  fetched again is the recorded option chains (and the daily chain facts made from them) and the FII/DII cash history,
  which the exchange only publishes for the latest day. Keep that database for as long as you want those.

### Users' data on Railway

Supabase's free plan counts every byte the server reads from it (its *egress*, 5 GB a month), and the server reads
users' data all day: profiles, paper sessions, notebooks, settings. In October 2026 that went past the limit more
than twice. Moving users' data to the Railway Postgres (the same one as `MARKET_DATABASE_URL`, in its own `app`
schema) puts it next to the server on Railway's private network, so none of it counts. Supabase then only checks
sign-ins.

- **Admin → Data and jobs → Storage → Move users' data to Railway.** The server saves the running paper sessions,
  restarts, and before it answers anyone copies every table (profiles, notebooks, paper sessions and orders, usage,
  settings) in one transaction, checks each table's row count, and marks the move done. The site is away for about a
  minute. If anything fails, nothing is kept on Railway, the panel shows the error and the server carries on with
  Supabase; pressing the button again tries again (`app/maindb.py`).
- After the move, add the repository secret `APP_DB_URL` (Railway → the Postgres → **Connect** → the *public*
  connection URL) so the nightly backup copies Railway instead of Supabase (below).
- The way back, in an emergency: set `MAIN_DATABASE=supabase` on the backend. Supabase then serves its copy from the
  moment of the move; anything written on Railway since isn't in it.

## Memory

The server's cost is its memory (one process holds the live paper sessions, the tick feed and the jobs), so
`backend/app/memguard.py` keeps it low without cutting a feature:

- **Heavy jobs take turns.** The whole-market audits, the screens index, the company pages' price refresh, market
  breadth (daily and quarter-hour), the evening exchange files, positioning, the library seed, IPO offer documents,
  business updates, named holders and the corporate-action reads each build their big structures inside one fair lock, so
  two jobs' peaks never stack, and each hands its memory back when it is through. A job that waits longer than
  `HEAVY_JOB_WAIT` (45 minutes by default) runs anyway.
- **The caches share one budget,** `CACHE_BUDGET_MB` (256 by default): the least recently used entries of the fattest
  cache go first, expired entries are swept out, a source's last good copy is capped at 16 MB, and the mutual fund
  histories kept in memory are the latest 80 schemes.
- **malloc gives memory back:** it is told to keep two arenas and to serve blocks of 1 MB and more from their own
  mappings. `MALLOC_TUNE=0` leaves malloc's settings alone.
- **Python's small objects live in malloc's heap,** not in its own 1 MB arenas: the start command sets
  `PYTHONMALLOC=malloc` (a Railway variable of the same name overrides it; `pymalloc` goes back). An arena returns to the
  system only when every object in it is gone, and a few long-lived cache entries between the temporary ones kept ~300 MB
  after each day's peaks; malloc returns what is free in pages. On a replay of the day's jobs, freeing the caches gave
  back 75 MB with Python's arenas and 220 MB with malloc (with every cache full it is about 4% higher, 709 against 681 MB,
  and parsing takes about 5% more CPU), so the gain is memory handed back when entries expire and jobs finish, which is what
  the bill follows. jemalloc was measured too and did not beat it.
- **Looking at it:** there is no panel. `GET /admin/memory` (signed in as an admin) returns the process's resident memory
  (`rss_mb`), which heavy job has the turn (`running`, `since`) and how many wait, and the caches' size against the budget.
  `GET /admin/memory?detail=true` adds a census of the heap by type (object counts and bytes of the 25 biggest types) and
  the largest module-level collections: take it twice an hour apart and the type or collection that grew is what is
  growing between them. It takes about a second and keeps nothing. The census counts only what the garbage collector
  tracks (containers; not the strings, numbers and bytes inside them, which are most of the data: 10 MB counted for 66 MB
  held on a test page set), so read it with the rest of that answer: `allocators` (which malloc, whether Python's
  arenas are in use), `python_heap` (arenas taken, in live objects, wasted: only with Python's arenas), `rss_split`
  (anonymous against file-backed memory) and `caches` (each cache by name, its items and its size against the budget).
- Backtests run in worker processes (`BACKTEST_PROCESSES`, 2 by default; 0 runs them in the server process) and
  `HEAVY_SLOTS` (2) caps heavy requests running at once.

## Backups

Every night at 02:10 IST a GitHub Action (`.github/workflows/backup.yml`) copies the main database, encrypts it, and
keeps it on the repository's **Actions** page → *Database backup* → the run → *Artifacts*. A nightly copy holds the
app's tables without the recorded option chains' rows and is kept 7 days. The weekly one (Monday 02:10 IST, which is
still Sunday in UTC) and any run by hand (*Run workflow*) hold everything, the option chains too until they move to the
second database; they're named `…-full` and kept 28 days. Each copy has the app's tables (`app.dump`, the whole
`public` schema) and the sign-ins (`auth.dump`: `auth.users` and `auth.identities`; if those can't be copied, the run
warns and keeps the rest). A run with the secrets missing fails and says which to add.

Once users' data is on Railway (above) and `APP_DB_URL` is set, `app.dump` is copied from Railway instead: the `app`
schema (users' data) every night, and on full days the `public` schema too (the market data, with the recorded option
chains and the FII/DII history that can't be fetched again). Supabase is then read only for the sign-ins, so the
backup no longer counts against its egress. Until the move is done the run keeps copying Supabase, even with
`APP_DB_URL` set.

Setup, once, in GitHub → Settings → Secrets and variables → Actions → New repository secret:

- `SUPABASE_DB_URL`: Supabase → **Connect** → *Session pooler* connection string, with your database password filled in.
- `APP_DB_URL` (after the move): Railway → the Postgres → **Connect** → the public connection URL.
- `BACKUP_PASSPHRASE`: a long random passphrase. Keep it in your password manager: without it a backup can't be opened.

A copy from Railway restores into any Postgres with `pg_restore -d "$NEW_DB_URL" --no-owner --clean --if-exists app.dump`
(it holds the `app` schema, and `public` on full days); it doesn't refer to `auth.users`.

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
