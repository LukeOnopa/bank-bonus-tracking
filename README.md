# Bank Bonus Tracker

A checking-account bonus tracker that refreshes its offer list every hour.

**Live app:** https://lukeonopa.github.io/bank-bonus-tracking/

- Finds the checking bonuses you qualify for (state, direct deposit, cash on hand), with requirements, safe-to-close dates and churn rules.
- Tracks the accounts you've applied for, opened, been paid on, closed or been denied for.
- Shows which transfers count as direct deposits at each bank and your approval odds from your ChexSystems inquiries (you can upload your ChexSystems PDF).
- Your data stays in your own browser. Use **Add offer & data → Copy backup** to move it to another device.

## How the hourly refresh works

`.github/workflows/refresh.yml` runs every hour:

1. `scripts/scrape.py` reads Doctor of Credit's "Best Bank Account Bonuses" page and Fat Stacks Academy's checking-bonus list.
2. It merges them with the hand-researched list in `data/curated.json`: updates bonus amounts, fills in missing churn rules and expiry dates, records when each offer was last listed, and adds offers it hasn't seen before (marked "Auto-collected — verify details").
3. It deploys the app (`index.html`) plus a fresh `data/offers.json` to GitHub Pages. Nothing is committed, so the repo history stays clean.

If a site is down or changes its layout, that source is skipped for the run and the last good data is kept. The app's header shows when offers were last checked and whether any source failed. Offers that drop off both sites for 7 days are hidden as possibly ended.

## Maintenance

- **Run it now:** Actions tab → *Refresh bonus offers* → *Run workflow*.
- **A source keeps failing:** the site probably changed its layout. Check the run log, then update the matching `parse_doc` / `parse_fs` function and the sample pages in `tests/test_scrape.py`.
- **Improve details for an offer:** edit `data/curated.json` (states, keep-open days `keep`, churn months `cd`, etc.). Curated details always win over scraped ones.
- GitHub pauses scheduled workflows after 60 days without commits; the workflow makes a tiny keep-alive commit on the 1st of each month to prevent that.

Offer data comes from public roundup pages and may be incomplete or out of date — always confirm terms on the bank's own offer page.
