# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/pyxelr/hackernews-daily-digest/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/pyxelr/hackernews-daily-digest/releases/tag/v1.0.0
