# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.3] - 2026-07-22

### Changed

- Default Gemini model bumped to `gemini-3.6-flash`.
- Dependencies are now managed with [uv](https://docs.astral.sh/uv/) via
  `pyproject.toml` + `uv.lock` (replacing `requirements.txt`), giving reproducible
  pinned installs. CI uses `uv sync --frozen` and `uv run`, and lets uv manage the
  Python interpreter (the separate setup-python step is gone).
- README now recommends using a dedicated Gmail account as the sender (keeps your
  personal Sent folder clean).

## [1.0.2] - 2026-07-15

### Added

- Grey `#N` rank (`#1`, `#2`, …) shown under each story's score badge, so the
  top-to-bottom order by points is explicit. Refreshed the sample digest and
  README screenshot to show it.

## [1.0.1] - 2026-07-15

Layout refresh for better inbox readability.

### Changed

- Redesigned the email to a left-aligned, wider (960px) layout that reads well in
  most mail clients.
- Summaries are now more concise (1-2 lines, about 45 words) and refer to the
  community as "HN" or "Commenters" instead of "Hacker News readers".
- Dropped user-profile links from the per-story meta line.
- Email subject now shows the date (e.g. "15 Jul") instead of the story count.
- When a story's AI summary is unavailable, the fallback text is now just
  "(summary unavailable)" instead of restating the points and comment counts.
- Refreshed the sample digest (`docs/example-digest.html`, 30 stories) and the
  README screenshot to the new layout.
- Documented running the digest locally, without GitHub Actions.
- Sample digest is served via GitHub Pages (`docs/`) and linked from the README
  for a reliable in-browser preview; Pages redeploys only when `docs/` changes.

## [1.0.0] - 2026-07-14

Initial release: a completely free, self-hosted daily Hacker News email digest.

### Added

- Daily email digest of the top Hacker News stories, powered entirely by GitHub
  Actions (no servers, no paid services).
- Stories sorted by points (highest first), each with a short AI summary that
  blends the article with the tone of the HN discussion.
- Links to both the article and its Hacker News discussion for every story.
- AI summaries via the Google Gemini free tier (default `gemini-3.5-flash`),
  batched into a few requests so the whole digest stays within free-tier limits.
- Best-effort article text extraction (requests + BeautifulSoup); falls back to
  the title and top comments when a page cannot be fetched.
- HTML email styled after the reference newsletter: score badge, source domain,
  reply count, author, and relative age per story.
- Header shows the edition day and coverage window; footer shows the generation
  time and the next scheduled run, with a DST-aware timezone label.
- Email delivery over Gmail SMTP using an app password.
- Daily schedule at about 05:17 Poland time, year-round. GitHub cron is UTC-only
  and ignores daylight saving, so two UTC crons are scheduled and a guard keyed
  on the triggering cron lets only the correct one run (robust to GitHub's run
  delays).
- Manual runs via `workflow_dispatch`, including a dry-run mode that uploads the
  rendered HTML as a downloadable artifact instead of sending an email.
- Fast CI dependency installs with uv, and collapsible per-phase log groups
  (fetch, summarize, render and send).
- Configuration via environment variables and repository variables (number of
  stories, model, timezone, batch size, and more).
- `src/list_models.py` helper to list the Gemini models available to your API key.
- Sample rendered digest and a screenshot in `docs/`.

[Unreleased]: https://github.com/pyxelr/hackernews-daily-digest/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/pyxelr/hackernews-daily-digest/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/pyxelr/hackernews-daily-digest/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/pyxelr/hackernews-daily-digest/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/pyxelr/hackernews-daily-digest/releases/tag/v1.0.0
