# Working on the bank bonus tracker

## You're the manager
Delegate to the subagents in `.claude/agents/` on your own judgment, without waiting to be asked. Don't delegate when doing the job yourself is quicker. After a subagent reports, decide what to act on, fix what's needed yourself (subagents only report), and give the user a short summary of what was found and what you changed.

The user watches their Claude usage, so:
- Call an agent only when its job clearly applies, at most once per change unless you fixed something it needs to re-check.
- For a tiny change (a typo, one style tweak, a one-line fix), skip the agents and check it yourself.
- Prefer the cheaper agents (Haiku, Sonnet) for routine checks.
- If a full set of checks would be costly (e.g. `site-tester` and `perf-a11y-checker` after a small edit), say which you're skipping and why.

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
- `scripts/scrape.py` runs hourly on GitHub Actions (`.github/workflows/refresh.yml`) and deploys `index.html` plus a fresh `data/offers.json` to GitHub Pages. Every push to `main` also deploys.
- Run `python -m pytest tests/` after changing the scraper.
- Curated details in `data/curated.json` always win over scraped ones.
