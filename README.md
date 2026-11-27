# Bank Bonus Tracker

A checking-account bonus tracker that refreshes its offer list every hour.

**Live app:** https://lukeonopa.github.io/bank-bonus-tracking/

- Finds the checking bonuses you qualify for (state, direct deposit, cash on hand), with requirements, safe-to-close dates and churn rules.
- Tracks the accounts you've applied for, opened, been paid on, closed or been denied for.
- Shows which transfers count as direct deposits at each bank and your approval odds from your ChexSystems inquiries (you can upload your ChexSystems PDF).
- Your data stays in your own browser, or sign in with a free account (email and password) to sync it across devices. **Add & back up → Copy backup** still works without an account.

## How the hourly refresh works

`.github/workflows/refresh.yml` runs every hour:

1. `scripts/scrape.py` reads Doctor of Credit's "Best Bank Account Bonuses" page and Fat Stacks Academy's checking-bonus list.
2. It merges them with the hand-researched list in `data/curated.json`: updates bonus amounts, fills in missing churn rules and expiry dates, records when each offer was last listed, and adds offers it hasn't seen before (marked "Auto-collected — verify details").
3. It deploys the app (`index.html`) plus a fresh `data/offers.json` to GitHub Pages. Nothing is committed, so the repo history stays clean.

If a site is down or changes its layout, that source is skipped for the run and the last good data is kept. The app's header shows when offers were last checked and whether any source failed. Offers that drop off both sites for 7 days are hidden as possibly ended.

## Accounts (Supabase)

Free accounts use Supabase for sign-in and storage. The site talks to Supabase's web API directly, with no extra library.

- `SB_URL` and `SB_KEY` near the top of the account code in `index.html` hold the project URL and the publishable key. The publishable key is meant to be public. If `SB_URL` is blank, the Sign in button stays hidden and the site works as before.
- `supabase/setup.sql` creates the `user_data` table (one row per user) with row-level security, so each user can only read and write their own data.
- In Supabase under **Authentication → URL Configuration**, the Site URL and redirect URLs must include the live app address, or confirmation and password-reset emails will link to the wrong place.
- Sync merges by timestamp per entry, so two devices editing at once don't overwrite each other's newer changes.

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
