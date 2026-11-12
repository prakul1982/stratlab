# Lane c-p1 report: a tighter Free tier (Free is a teaser; Basic and Pro unchanged)

Branch `p1`, built on `lane/c-p1-freetier` (77f96ce, 21cd812, 2650ab9) with `rel7` merged in, so the Refresh rule matches the
merged lane that made a Refresh one fresh AI read (LIVE7B-002). Not pushed; no pull request.

## Limits, old to new (Free only)

| Limit | Free before | Free now | Basic | Pro |
|---|---|---|---|---|
| Fresh AI reads a day (`ai_reads_per_day`) | 60 | 5 | 60 (`RESEARCH_AI_PER_DAY`) | Unlimited |
| Refresh of a stored read (each Refresh is one fresh AI read) | yes, held to the 60 | none | yes, held to the 60 | yes |
| AI answers in the search box a day (`search_ai_per_day`) | 40 | 10 | 40 | 40 |
| New themes mapped a month (`themes_per_month`; themes already in the library open on every plan) | no limit | 1 | 10 | Unlimited |
| Slide decks a month (`decks_per_month`) | 1 | 0, with a sample deck to download | 5 | Unlimited |
| Company deep dives a month | 2 | 1 | 15 | Unlimited |
| Backtests a month | 10 | 5 | 100 | Unlimited |
| AI strategy builds a month | 10 | 5 | 100 | Unlimited |
| Instruments in a group test | 10 | 5 | 25 | 50 |
| Stock alerts on at once | 5 | 3 | 25 | 100 |
| Saved screens | 2 | 1 | 10 | 25 |
| The tax report's CSV and PDF downloads (`tax_export`) | yes | Basic | yes | yes |

Reads already written still open for everyone. A Free reader's company read is the shared Basic/Pro copy (`company_read_key`). An older
Free copy is used only when no shared copy exists. A Free reader's fresh read is written as the shared copy.

## Rollout

- `FREE_TIER_CHANGE_AT` (config, default `2026-11-16T00:00:00+05:30`). Accounts made after it get the new counts at once.
- Accounts made before it keep the old Free counts (`plans.FREE_BEFORE`) and the tax downloads for 14 days after it (`free_grace_until`).
  This includes Refresh.
- The notice is shown once on Account and My space (`me.free_change`, `FreeChangeNotice`). It lists each count, old and new, plus what
  moves to Basic (Refresh, tax downloads). "Got it" hides it on both pages. No email is sent.

## Finished in this pass (after the cloud builder stopped)

- **Refresh, matched to the merged rule.** A Refresh is one fresh AI read, and the separate refresh count is gone (LIVE7B-002).
  `REFRESHES_PER_DAY`/`refreshes_per_day` are removed. The new `plans.refreshes_allowed(plan, profile)` allows Basic, Pro, and Free only
  in its grace.
  - `computed.refresh_gate` gives Free the stored read with state "capped". The new `plan_held` argument leaves the market mood, which
    no one's count holds, open to everyone. `intel/routes.ai_call` applies it to counted company reads.
  - `/me/usage` carries `refresh_off`, and the Refresh note reads it: "On Basic", "Refreshing a stored read is on Basic and Pro". Before,
    it read a "refresh" row that no longer exists.
  - The grace notice lists the Refresh move. The Plans row says "Fresh AI reads a day, refreshes included (Free has no refreshes; ...)".
  - README's row is now "Refresh of a stored result … None / ✓ / ✓". FEATURES.md's Themes row is updated.
- **Merge conflicts with rel7 resolved:** computed.py, main.py (`/me/usage`), plans.py, plans.ts, test_r19_library, test_research_api.
- **Tour (rel7's new intro):** the tax report step carries `tax_export`, so it says the downloads are on Basic. The company step's Free
  line now reads "On Free: 1 deep dive a month; slide decks are on Basic." (was "1 deep dives and 0 slide download a month").
- **Test isolation fixed:** seven test edits from the branch set the signed-in person with `monkeypatch.setitem` on
  `app.dependency_overrides`. That restored the api fixture's profile after the fixture had cleared it, so a profile leaked into later
  tests in the same worker and 26 tests failed in a full run. They now set it directly, and the api fixture clears it.

## Tests

- New or updated (each marked "(updated on purpose)" with the reason):
  - `test_free_tier.py`: Free has no Refresh, while the market mood stays open. Basic's Refresh is held to its 60. The grace Refresh is
    held to the old 60. New: `/me/usage` `refresh_off` per account.
  - `test_plan_copy.py`: the README refresh row.
  - `test_r19_library.py`: the Refresh cases run on Basic.
  - `test_research_api.py`: a Free Refresh gives the stored read, "capped", with no AI call.
  - Frontend unit tests: `free-tier.test.mjs` (refresh_off) and `intro.test.mjs` (tax step lock, Free line).
  - e2e: `r19-library.spec.ts` (the user there is Free: 5 reads, `refresh_off`).
- Totals are in the session report.
