"""Entry point: build and send the Hacker News Daily digest.

Run locally:
    python main.py            # sends the email (needs Gmail config)
    DRY_RUN=true python main.py   # writes output/digest.html, sends nothing
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from src import hn_client
from src.article_fetcher import fetch_many
from src.config import config
from src.email_renderer import render_html, render_subject
from src.mailer import send_email
from src.summarizer import Summarizer


def build_digest() -> tuple[list[hn_client.Story], dict[int, str], datetime]:
    now = datetime.now(tz=timezone.utc)

    print(f"Fetching top {config.num_stories} stories from Hacker News...")
    stories = hn_client.get_stories(config.num_stories, config.min_score)
    print(f"Got {len(stories)} stories.")
    if not stories:
        raise SystemExit("No stories returned from Hacker News; aborting.")

    # Fetch article bodies concurrently (best-effort).
    article_text: dict[str, str] = {}
    if config.fetch_articles:
        urls = [s.url for s in stories if s.url]
        print(f"Fetching {len(urls)} article bodies...")
        article_text = fetch_many(
            urls, config.article_timeout, config.article_char_limit, config.fetch_workers
        )

    # Gather top comments per story for sentiment context.
    print("Fetching top comments...")
    jobs: list[tuple[hn_client.Story, str, list[str]]] = []
    for story in stories:
        comments = hn_client.get_top_comments(story, config.max_comments)
        text = article_text.get(story.url or "", "")
        jobs.append((story, text, comments))

    print(f"Generating summaries with {config.gemini_model}...")
    summarizer = Summarizer(
        api_key=config.gemini_api_key,
        model=config.gemini_model,
        delay=config.request_delay_seconds,
        max_retries=config.max_retries,
    )
    summaries = summarizer.summarize_all(jobs)

    return stories, summaries, now


def main() -> int:
    config.validate(require_email=not config.dry_run)

    stories, summaries, now = build_digest()
    html_body = render_html(stories, summaries, now)
    subject = render_subject(stories, now)

    if config.dry_run:
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / "digest.html"
        out_file.write_text(html_body, encoding="utf-8")
        print(f"\nDRY RUN — wrote {out_file.resolve()}")
        print(f"Subject would be: {subject}")
        return 0

    print(f"\nSending digest to {', '.join(config.recipients)}...")
    send_email(
        username=config.gmail_username,
        app_password=config.gmail_app_password,
        recipients=config.recipients,
        subject=subject,
        html_body=html_body,
    )
    print("Sent successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
