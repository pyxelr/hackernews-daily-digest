"""Render the digest as an HTML email styled after the reference newsletter.

Uses inline styles + a table layout because that is the only thing that renders
reliably across email clients (Gmail, Outlook, Apple Mail).
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .hn_client import Story

_HN_ORANGE = "#ff6600"


def _resolve_tz(tz_name: str):
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def _fmt_dt(dt: datetime, tz, tz_label: str = "") -> str:
    """Full human timestamp, e.g. 'Mon, 13 Jul 2026, 08:17 CET'.

    When ``tz_label`` is given it overrides the automatic abbreviation (which
    would otherwise switch between e.g. CET/CEST across daylight saving).
    """
    local = dt.astimezone(tz)
    label = tz_label or local.strftime("%Z")
    # %-d (no leading zero) is supported on Linux/macOS; the CI runner is Linux.
    return f"{local.strftime('%a, %-d %b %Y, %H:%M')} {label}".rstrip()


def _time_ago(unix_ts: int, now: datetime) -> str:
    if not unix_ts:
        return ""
    delta = now - datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        minutes = max(1, int(delta.total_seconds() // 60))
        return f"{minutes}m ago"
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _story_block(rank: int, story: Story, summary: str, now: datetime) -> str:
    replies = f"{story.descendants} replies" if story.descendants else "discuss"
    link = f"color:{_HN_ORANGE};text-decoration:none;"
    meta_bits = [
        # Domain links to the article, reply count links to the HN discussion.
        f'<a href="{_e(story.article_url)}" style="{link}">{_e(story.domain)}</a>',
        f'<a href="{_e(story.hn_url)}" style="{link}">{_e(replies)}</a>',
        _e(story.by),  # author name as plain text (no profile link)
        _time_ago(story.time, now),
    ]
    sep = ' <span style="color:#c9c9c9;">&bull;</span> '
    meta_line = sep.join(bit for bit in meta_bits if bit)

    return f"""\
        <tr>
          <td style="padding:9px 16px;border-bottom:1px solid #eeece7;background:#f7f6f1;">
            <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td valign="top" width="46" style="padding-right:12px;">
                  <div style="background:#fce4cf;color:#8a4b1a;font-weight:700;font-size:12px;text-align:center;border-radius:5px;padding:4px 0;">{story.score}</div>
                  <div style="margin-top:3px;color:#8a8a8a;font-size:11px;font-weight:600;text-align:center;">#{rank}</div>
                </td>
                <td valign="top" align="left">
                  <a href="{_e(story.article_url)}" style="color:#141414;font-size:15px;font-weight:700;text-decoration:none;line-height:1.3;">{_e(story.title)}</a>
                  <div style="margin-top:3px;font-size:12px;color:#8a8a8a;">{meta_line}</div>
                  <div style="margin-top:7px;background:#ffffff;border:1px solid #ebe9e3;border-radius:6px;padding:7px 11px;font-size:13px;color:#3f3f3f;line-height:1.5;">{_e(summary)}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""


def render_html(
    stories: list[Story],
    summaries: dict[int, str],
    generated_at: datetime | None = None,
    next_run: datetime | None = None,
    tz_name: str = "UTC",
    tz_label: str = "",
) -> str:
    now = generated_at or datetime.now(tz=timezone.utc)
    tz = _resolve_tz(tz_name)
    local_now = now.astimezone(tz)
    abbrev = tz_label or local_now.strftime("%Z")
    # The digest is a daily edition; it covers roughly the 24h up to now.
    window_start = (now - timedelta(hours=24)).astimezone(tz)
    edition_day = local_now.strftime("%A, %-d %b %Y")  # e.g. "Tuesday, 14 Jul 2026"
    coverage = (
        f"{window_start.strftime('%-d %b, %H:%M')} &ndash; "
        f"{local_now.strftime('%-d %b, %H:%M')} {abbrev}"
    ).strip()

    rows = "\n".join(
        _story_block(rank, story, summaries.get(story.id, ""), now)
        for rank, story in enumerate(stories, start=1)
    )

    next_run_html = ""
    if next_run is not None:
        next_run_html = (
            f'<br>Next scheduled run &asymp; {_e(_fmt_dt(next_run, tz, tz_label))} '
            f'<span style="color:#bbb;">(GitHub may delay it a few minutes)</span>'
        )

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#ffffff;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0" align="left" width="100%" style="max-width:960px;background:#ffffff;">
    <tr>
      <td style="background:{_HN_ORANGE};padding:11px 16px;">
        <span style="color:#141414;font-size:17px;font-weight:800;letter-spacing:.2px;">Hacker News Daily</span>
        <span style="color:#5a2a00;font-size:12px;font-weight:600;float:right;padding-top:4px;">{_e(edition_day)}</span>
      </td>
    </tr>
    <tr>
      <td style="padding:10px 16px 8px;border-bottom:1px solid #eeece7;">
        <span style="font-size:14px;font-weight:700;color:#333;">Top {len(stories)} stories</span>
        <span style="font-size:12px;color:#9a9a9a;float:right;padding-top:2px;">Covering {coverage}</span>
      </td>
    </tr>
    {rows}
    <tr>
      <td style="padding:14px 16px;background:#fafafa;border-top:1px solid #eeece7;">
        <div style="font-size:11px;color:#9a9a9a;line-height:1.6;">
          Generated {_e(_fmt_dt(now, tz, tz_label))} from the
          <a href="https://news.ycombinator.com/news" style="color:{_HN_ORANGE};text-decoration:none;">Hacker News</a>
          top-stories API, with summaries by Google Gemini.
          Ages like &ldquo;3h ago&rdquo; are relative to that time.{next_run_html}<br>
          Source: <a href="https://github.com/pyxelr/hackernews-daily-digest" style="color:{_HN_ORANGE};text-decoration:none;">github.com/pyxelr/hackernews-daily-digest</a>
        </div>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_subject(stories: list[Story], now: datetime | None = None, tz_name: str = "UTC") -> str:
    now = now or datetime.now(tz=timezone.utc)
    date_label = now.astimezone(_resolve_tz(tz_name)).strftime("%-d %b")  # e.g. "15 Jul"
    top = stories[0].title if stories else "Top Stories"
    return f"HN Daily · {date_label} · {top[:60]}"
