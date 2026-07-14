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
    """For scheduled runs, let only the cron whose *scheduled* local time matches
    the target hour proceed.

    The workflow schedules two UTC times so one always maps to the target local
    hour regardless of daylight saving. We must NOT decide from the wall-clock at
    execution time: GitHub often delays scheduled runs by a long time (we have
    seen ~2h), which would make every run miss the target hour. Instead we read
    which cron entry triggered this run (github.event.schedule, passed in as
    TRIGGER_CRON) and compute the local hour it was scheduled for -- stable no
    matter how late GitHub actually starts the job.

    Manual (workflow_dispatch) runs and local runs always proceed.
    """
    target = config.run_only_at_local_hour.strip()
    if not target or not target.isdigit():
        return False
    # Only guard scheduled runs; manual and local runs proceed.
    if os.getenv("GITHUB_EVENT_NAME", "") != "schedule":
        return False
    try:
        tz = ZoneInfo(config.display_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return False

    trigger = os.getenv("TRIGGER_CRON", "").strip()  # e.g. "17 3 * * *"
    fields = trigger.split()
    if len(fields) == 5 and fields[0].isdigit() and fields[1].isdigit():
        # Local hour this cron entry maps to today. Uses the current UTC offset,
        # which is stable around our early-morning run times (DST switches happen
        # at 01:00 UTC, before either cron fires).
        scheduled_utc = datetime.now(tz=timezone.utc).replace(
            hour=int(fields[1]), minute=int(fields[0]), second=0, microsecond=0
        )
        scheduled_local_hour = scheduled_utc.astimezone(tz).hour
        if scheduled_local_hour != int(target):
            print(
                f"Skipping: cron '{trigger}' maps to {scheduled_local_hour:02d}:00 "
                f"in {config.display_timezone}, target is {int(target):02d}:00 (DST guard)."
            )
            return True
        return False

    # Fallback (no cron info): best-effort execution-time hour check.
    local_hour = datetime.now(tz=tz).hour
    if local_hour != int(target):
        print(
            f"Skipping: local hour is {local_hour:02d} in {config.display_timezone}, "
            f"target is {int(target):02d} (DST guard, no cron info)."
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
    guard_hour = (
        int(config.run_only_at_local_hour)
        if config.run_only_at_local_hour.strip().isdigit()
        else None
    )
    next_run = schedule.next_effective_run(now, config.display_timezone, guard_hour)
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
