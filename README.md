# Hacker News Daily digest 📰

A **completely free**, self-hosted email newsletter that sends you the top
[Hacker News](https://news.ycombinator.com/) stories every morning — each with a
short AI summary (article + community reaction) and links to both the article and
its HN discussion.

No servers, no paid services, no n8n. Just a **GitHub Action** on a cron schedule.

<p align="center">
  <em>Top-N stories · AI summaries by Google Gemini · delivered over Gmail SMTP</em>
</p>

---

## Why it's free

| Piece | Service | Cost |
|-------|---------|------|
| Scheduling / compute | **GitHub Actions** | Free, *unlimited minutes* for public repos |
| Story data | **Hacker News Firebase API** | Free, no auth, no rate limits |
| AI summaries | **Google Gemini API** (free tier) | Free — ~1500 req/day, well above 30/day |
| Email delivery | **Gmail SMTP** (app password) | Free |

> The consumer **Google AI Pro** subscription is *not* required — the Gemini API
> has its own free tier available to any Google account.

## How it works

```
GitHub Actions (cron, ~08:00)
        │
        ▼
  main.py  ──▶  Hacker News API      (top 30 stories + top comments)
        │  ──▶  fetch article pages   (best-effort text extraction)
        │  ──▶  Google Gemini         (one summary per story)
        │  ──▶  render HTML email
        ▼
   Gmail SMTP  ──▶  your inbox 📬
```

Each story in the email shows its **score**, **title** (→ article), source
domain, **N replies** (→ HN discussion), author, age, and a 2–3 sentence summary.

---

## Setup (≈ 10 minutes)

### 1. Fork / use this repo
Fork it (or click **Use this template**) into your own account so the Action runs
under your quota. Keep it **public** for free unlimited Actions minutes.

### 2. Get a free Gemini API key
Go to **[aistudio.google.com/apikey](https://aistudio.google.com/apikey)** → *Create API key*. Copy it.

### 3. Create a Gmail App Password
1. Enable **2-Step Verification** on your Google account.
2. Go to **[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)**.
3. Create a password (name it e.g. "HN digest"). Copy the 16-character value.

### 4. Add repository secrets
In your repo: **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | your Gemini key |
| `GMAIL_USERNAME` | `you@gmail.com` |
| `GMAIL_APP_PASSWORD` | the 16-char app password |
| `RECIPIENTS` | *(optional)* comma-separated recipients; defaults to `GMAIL_USERNAME` |

Optional **Variables** (same page, *Variables* tab) to tweak without editing code:
`NUM_STORIES` (default `30`), `GEMINI_MODEL` (default `gemini-2.5-flash`).

### 5. Test it
Go to **Actions → Daily HN Digest → Run workflow**.
- Tick **Dry run** to build the email as a downloadable artifact without sending.
- Leave it unticked to send a real email.

### 6. Done
It now runs automatically every day. Adjust the time by editing the `cron` line
in [`.github/workflows/daily-digest.yml`](.github/workflows/daily-digest.yml)
(times are **UTC** — use [crontab.guru](https://crontab.guru)).

---

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your keys

# Preview without sending — writes output/digest.html
DRY_RUN=true python main.py

# Send for real
python main.py
```

## Configuration

All settings are environment variables (see [`.env.example`](.env.example)):

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Gemini API key (required) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used for summaries |
| `GMAIL_USERNAME` | — | Sender Gmail address |
| `GMAIL_APP_PASSWORD` | — | Gmail app password |
| `RECIPIENTS` | sender | Comma-separated recipients |
| `NUM_STORIES` | `30` | Stories per email |
| `MIN_SCORE` | `0` | Skip stories below this score |
| `MAX_COMMENTS` | `6` | Top comments fed to the summarizer |
| `FETCH_ARTICLES` | `true` | Also fetch article bodies for context |
| `REQUEST_DELAY_SECONDS` | `6` | Pause between Gemini calls (free-tier pacing) |
| `DRY_RUN` | `false` | Write HTML file instead of emailing |

## Project layout

```
main.py                     Orchestrator
src/config.py               Env-based configuration
src/hn_client.py            Hacker News API client
src/article_fetcher.py      Best-effort article text extraction
src/summarizer.py           Gemini summaries (paced + retried)
src/email_renderer.py       HTML email template
src/mailer.py               Gmail SMTP sender
.github/workflows/          Daily cron workflow
```

## Notes & troubleshooting

- **Gemini free-tier rate limits** are per-minute. 30 stories are paced ~6s apart
  by default; raise `REQUEST_DELAY_SECONDS` if you see `429` retries.
- **Some articles won't be fetched** (paywalls, JS-only, PDFs, videos). The
  summary then falls back to the title + HN comments — which is usually enough.
- **Email in spam?** Mark it "not spam" once; sending to yourself is very reliable.
- **Scheduled runs can be delayed** a few minutes by GitHub during peak load — a
  known GitHub Actions behaviour, not a bug here.

## License

[MIT](LICENSE) © 2026 pyxelr
