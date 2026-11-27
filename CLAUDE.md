# Working on the bank bonus tracker

## You're the manager
Delegate to the subagents in `.claude/agents/` on your own judgment, without waiting to be asked. Don't delegate when doing the job yourself is quicker. After a subagent reports, decide what to act on, fix what's needed yourself (subagents only report), and give the user a short summary of what was found and what you changed.

The user watches their Claude usage, so:
- Call an agent only when its job clearly applies, at most once per change unless you fixed something it needs to re-check.
- For a tiny change (a typo, one style tweak, a one-line fix), skip the agents and check it yourself.
- Prefer the cheaper agents (Haiku, Sonnet) for routine checks.
- If a full set of checks would be costly (e.g. `site-tester` and `perf-a11y-checker` after a small edit), say which you're skipping and why.

## Merging
The user has given standing permission to open and merge pull requests into `main` without asking, once GitHub's Tests workflow passes on the branch. Ask first only for bigger feature additions or bigger site changes (new sections or pages, redesigns, changes to how accounts or data work). Always say in the reply what was merged.

## When to call each agent
| Situation | Agent |
|---|---|
| Changed behavior in `index.html` or `scripts/` (more than a trivial edit), before committing | `site-tester` |
| Changed text people see (setup questions, cards, warnings, buttons) | `copy-checker` |
| The hourly refresh failed, a source shows as failed, or offers went missing | `scraper-doctor` |
| Editing `data/curated.json`, or the user asks about auto-collected/unverified offers | `offer-reviewer` |
| A redesign, a large new feature, or a layout or animation change | `perf-a11y-checker` |

If two apply, run them in parallel. If a subagent can't reach a website (cloud sessions block most sites), use what it found offline and tell the user what it couldn't check.

## Project basics
- The app is one file, `index.html`. The user's data stays in their browser (localStorage).
- The full refresh (`.github/workflows/refresh.yml`) runs daily at 11:17 UTC and on every push to `main`: `scripts/scrape.py` (roundups, `reference.py` articles, bank-page checks, `locate.py` federal states), then `scripts/discover.py` (crawler), then deploys `index.html` + `data/offers.json` to GitHub Pages.
- The Refresh offers button runs the Supabase Edge Function in `supabase/functions/refresh-offers/` (quick refresh, saved to the `site_data` table). Its `roundups.ts` mirrors the Python roundup parsers: change both together and run `npm run parity`.
- Tests: `python tests/test_<name>.py` for scrape, locate, reference, discover; `npm test` for the browser tests (all run on GitHub on every push).
- Curated details in `data/curated.json` always win over scraped ones.
