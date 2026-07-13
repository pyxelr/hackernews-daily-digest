"""Entry point: build and send the Hacker News Daily digest.

Run locally:
    python main.py            # sends the email (needs Gmail config)
    DRY_RUN=true python main.py   # writes output/digest.html, sends nothing
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src import hn_client, schedule
from src.article_fetcher import fetch_many
from src.config import config
from src.email_renderer import render_html, render_subject
from src.mailer import send_email
from src.summarizer import Summarizer


def should_skip_this_run() -> bool:
    """For scheduled runs, skip unless it's the target local hour.

    The workflow schedules two UTC times so one always lands on the target local
    hour regardless of daylight saving; this lets only that one proceed. Manual
    (workflow_dispatch) runs and local runs always proceed.
    """
    target = config.run_only_at_local_hour.strip()
    if not target or not target.isdigit():
        return False
    # Only guard actual cron runs; always allow manual (workflow_dispatch) and
    # local runs (where GITHUB_EVENT_NAME is unset).
    if os.getenv("GITHUB_EVENT_NAME", "") != "schedule":
        return False
    try:
        tz = ZoneInfo(config.display_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    local_hour = datetime.now(tz=tz).hour
    if local_hour != int(target):
        print(
            f"Skipping: local hour is {local_hour:02d} in {config.display_timezone}, "
            f"target is {int(target):02d} (DST guard)."
        )
        return True
    return False


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
        batch_size=config.batch_size,
    )
    summaries = summarizer.summarize_all(jobs)

    return stories, summaries, now


def main() -> int:
    if should_skip_this_run():
        return 0

    config.validate(require_email=not config.dry_run)

    stories, summaries, now = build_digest()
    next_run = schedule.next_run_utc(schedule.read_cron(), now)
    html_body = render_html(
        stories,
        summaries,
        now,
        next_run=next_run,
        tz_name=config.display_timezone,
        tz_label=config.display_tz_label,
    )
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
