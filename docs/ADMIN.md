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
| **Data and jobs** | The background jobs (status, last run, schedule, a log), the India broker data login, exchange holidays, the blog and storage |
| **Quality** | The data audits, strategies people reported, and rates and rules |
| **System** | Recent server errors, alert channels, which build each host runs, the AI providers' status and **Check every feature** |
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

Pull requests merge once the tests pass; the hosts then deploy the new build. Run **Admin → System → Check every
feature** after a deploy.
