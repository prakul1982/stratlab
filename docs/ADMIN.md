# Running StratLab

[← Back to the project overview](../README.md) · [Setup guide](../stratlab/README.md)

A short overview for the site's operator. Setting up the services the first time is in the [setup guide](../stratlab/README.md);
every setting the backend reads is listed by name in `stratlab/backend/.env.example`.

## Who is an admin

Set `ADMIN_EMAILS` on the backend to one or more Google addresses, comma-separated, and redeploy. Signed in with one of
them, you get **Admin** in the account menu. Nobody else sees it or can use it.

## The Admin page

Admin has a left menu of sections:

| Section | What it's for |
| --- | --- |
| **Overview** | What needs your attention, worst first; today's numbers; one light per service and data feed |
| **Users and growth** | Users, plans, invite rewards and the paper trading sessions running now |
| **Money** | Payments, subscriptions, prices outside India and invoices |
| **Data and jobs** | The background jobs (status, last run, schedule, a log), the India broker data login, exchange holidays, the blog (each post's state, and a theme post whose figures were worked out under older theme rules) and storage |
| **Quality** | The data audits, strategies people reported, and rates and rules |
| **System** | Recent server errors, alert channels, which build each host runs, the AI providers' status and **Check every feature** |
| **Library** | Everything worked out once and kept for every user (theme reads, theme figures and decks, AI reads): how often each was served, its size and date, **Refresh now** and **Remove**; each kept theme deck with its publication check; a row no longer served (kept under older rules, or an earlier day's deck) says so |
| **Feedback** | What people sent from the Feedback button; each new one is also emailed to you |
| **Email previews** | Every email StratLab sends, as a reader gets it |

## Checks that run by themselves

- **Check every feature** runs every day and can be run from Admin → System after a deploy; anything that fails shows
  on the Overview.
- The **data audit** checks the company figures the app shows against the companies' own filings; new listings are
  checked as they arrive.

## Services

- **AI:** the AI builder and research summaries use the AI providers whose keys are set. Admin → System shows whether
  each is answering.
- **Email and alerts:** set the email and Telegram keys to send alert emails and messages; Admin → System has **Send a
  test email**.
- **Usage and errors:** PostHog and Sentry are optional; set their keys to turn them on.

## Storage

Users' data and the market data live in Postgres on Railway; sign-ins live in Supabase. Admin → Data and jobs → Storage
shows how much each holds.

## Backups

The database is backed up by Railway: **Railway → the Postgres service → Backups**, on a daily and a weekly schedule.
Sign-ins are backed up by Supabase.

To restore: open **Railway → the Postgres service → Backups**, pick the backup by its date and choose **Restore**. Railway
restores it into the volume (check the data after it comes back up, then run **Check every feature** from Admin → System).

## Deploys

Pull requests merge once the tests pass; the hosts then deploy the new build (the backend from its Dockerfile). Run
**Admin → System → Check every feature** after a deploy.

A deploy that changes the theme rules, a theme dive's sentences or the theme deck's version needs nothing by hand: kept
theme reads, figures and decks are keyed by those versions and are worked out again when next asked for, and the blog's
theme posts whose figures came from older rules are worked out again from the theme library's read at the next newsletter
check (or at the theme's next read).

## Ads (Google AdSense)

Ads are off until the switch is on: `ADS_ENABLED=true` with the publisher ID `ADSENSE_CLIENT` (ca-pub-…) and the ad unit's
`ADSENSE_SLOT_PUBLIC` on the backend (the pages the server draws), and the same names in `config.js` (or `VITE_…` at build) for the
app. `ads.txt` and the `google-adsense-account` tag already carry the publisher ID. A visitor is asked first; nothing from Google
loads before "Allow ads". Never on money, tax, holdings, account, admin, sign-in or payment pages, and never in emails.

**Which pages may carry an ad (AdSense: no ads on auto-generated pages or pages with little to no original content).** A page
carries its one ad only when its main content holds at least **300 words of its own text**. Counted: the words inside `<main>`.
Not counted: navigation, the header and footer, forms, tables, charts, buttons, link text, the ad itself, anything marked
`data-shared`, and numbers and dates (a word has a letter in it). The server's pages use `ads.original_words` /
`ads.enough_content` (`MIN_ORIGINAL_WORDS`, backend/app/ads.py); the app's slot uses the same rule and number
(frontend/src/lib/adContent.ts). Pages that are one template filled in with figures carry `data-shared` on their `<main>`, so
they never qualify: every company page, every market brief and every theme post. A research post written for its one subject,
the landing page, the FAQ and the policies are counted as written.

**Which company pages search engines are offered.** A company page is indexed and listed in the sitemap only when it shows both
reported numbers and a recent share price (`stock_pages.indexable`). One with only one of them is `noindex` and left out of the
sitemap; a visitor who opens it still reads what there is. The sitemap lists public pages only: the site's own pages (with
`/about`), company pages that pass that rule, the A-Z and index lists, the blog's indexable posts and the theme pages offered to
search. A link from a public page into the app (an address that asks for sign-in) says "(needs sign-in)" and is `nofollow`.

Before pressing **Resubmit** in AdSense: open AdSense → **Policy center** and read the reason it names; wait until this release
is live (the company pages' cache keeps a copy up to a day); then check `https://stratlab.studio/ads.txt`, `/about` and
`/sitemap.xml` load.
