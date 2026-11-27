# Bank Bonus Tracker

A checking-account bonus tracker. Offers refresh daily, and signed-in users can refresh them on demand in seconds.

**Live app:** https://lukeonopa.github.io/bank-bonus-tracking/

- Finds the checking bonuses you qualify for (state, direct deposit, cash on hand), with requirements, safe-to-close dates and churn rules.
- Tracks the accounts you've applied for, opened, been paid on, closed or been denied for.
- Shows which transfers count as direct deposits at each bank and your approval odds from your ChexSystems inquiries (you can upload your ChexSystems PDF).
- Your data stays in your own browser, or sign in with a free account (email and password) to sync it across devices. **Add & back up → Copy backup** still works without an account.

## How the daily refresh works

`.github/workflows/refresh.yml` runs daily (and when changes are merged):

1. `scripts/scrape.py` reads Doctor of Credit's "Best Bank Account Bonuses" page and Fat Stacks Academy's checking-bonus list.
2. It merges them with the hand-researched list in `data/curated.json`: updates bonus amounts, fills in missing churn rules and expiry dates, records when each offer was last listed, and adds offers it hasn't seen before (marked "Auto-collected — verify details").
3. It deploys the app (`index.html`) plus a fresh `data/offers.json` to GitHub Pages. Nothing is committed, so the repo history stays clean.

**Where the details come from.** The banks' own pages and the federal lists come first; the roundup sites are a reference:
- Cards link only to the bank: its offer page (from the roundup article's "Open account" / "Direct link to offer" button), or its homepage. Never to the roundup article.
- Availability is the bank's branch states from FDIC BankFind or NCUA (`scripts/locate.py`). The article's "Availability" line is compared with it, and the card shows when they agree or what the article says instead. If an article says nationwide, the offer stays nationwide. If the bank can't be matched in the federal lists, the article's list is used and the card says so.
- Bonus amounts are checked on the bank's offer page. End dates from articles fill gaps; a recently passed one is flagged (`scripts/reference.py`).
- `scripts/discover.py` also crawls banks' and credit unions' own sites in MN, WI, IA, ND and SD for bonuses the roundups don't list.

If a site is down or changes its layout, that source is skipped for the run and the last good data is kept. The app's header shows when offers were last checked and whether any source failed. Offers that drop off both sites for 7 days are hidden as possibly ended.

## Accounts (Supabase)

Free accounts use Supabase for sign-in and storage. The site talks to Supabase's web API directly, with no extra library.

- `SB_URL` and `SB_KEY` near the top of the account code in `index.html` hold the project URL and the publishable key. The publishable key is meant to be public. If `SB_URL` is blank, the Sign in button stays hidden and the site works as before.
- `supabase/setup.sql` creates the `user_data` table (one row per user) with row-level security, so each user can only read and write their own data.
- In Supabase under **Authentication → URL Configuration**, the Site URL and redirect URLs must include the live app address, or confirmation and password-reset emails will link to the wrong place.
- Sync merges by timestamp per entry, so two devices editing at once don't overwrite each other's newer changes.

## Refresh offers button (quick refresh)

Signed-in users can press **Refresh offers** on Find offers. It calls the Supabase Edge Function `supabase/functions/refresh-offers/`, which reads the Doctor of Credit and Fat Stacks lists, merges new offers and changed amounts into the latest full list, and saves it to the `site_data` table, in about 10-20 seconds. The site loads both the daily `data/offers.json` and that saved copy and shows whichever is newer. One quick refresh every 5 minutes, site-wide.

The slow work (reading articles, federal lookups, bank-page checks, the crawler) still runs in the daily GitHub refresh at 11:17 UTC. Offers a quick refresh adds say so on their card until then.

`roundups.ts` is a TypeScript copy of the roundup parsers in `scripts/scrape.py`. `npm run parity` (also run on every push) checks both read the same pages identically; if you change one, change the other.

Setup, once, in the Supabase dashboard:
1. **SQL Editor:** run `supabase/setup.sql` (it's safe to run again; it creates the `site_data` table).
2. **Edge Functions → Deploy a new function → Via editor:** name it `refresh-offers`, add the files `index.ts` and `roundups.ts` from `supabase/functions/refresh-offers/`, and deploy.
3. **In the function's settings:** turn off JWT verification. The function checks the signed-in user itself.

## Tests

Every push runs `.github/workflows/tests.yml` on GitHub (free for public repos):

- `tests/test_scrape.py` checks the scraper against saved sample pages.
- `tests/e2e/` holds browser tests for setup, offer statuses, the planner's limits, Start over and Undo, free accounts, and phone and desktop layouts. Accounts are tested against an in-memory stand-in for Supabase (`tests/e2e/mock-supabase.js`), so the tests never touch real user data.

To run the browser tests yourself: `npm install`, `npx playwright install chromium`, then `npm test`. Add a filter to run some, e.g. `npm test -- planner`.

## Maintenance

- **Run it now:** Actions tab → *Refresh bonus offers* → *Run workflow*.
- **A source keeps failing:** the site probably changed its layout. Check the run log, then update the matching `parse_doc` / `parse_fs` function and the sample pages in `tests/test_scrape.py`.
- **Improve details for an offer:** edit `data/curated.json` (states, keep-open days `keep`, churn months `cd`, etc.). Curated details always win over scraped ones.
- GitHub pauses scheduled workflows after 60 days without commits; the workflow makes a tiny keep-alive commit on the 1st of each month to prevent that.

Offer data comes from public roundup pages and may be incomplete or out of date — always confirm terms on the bank's own offer page.
