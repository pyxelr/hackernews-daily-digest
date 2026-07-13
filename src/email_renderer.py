"""Render the digest as an HTML email styled after the reference newsletter.

Uses inline styles + a table layout because that is the only thing that renders
reliably across email clients (Gmail, Outlook, Apple Mail).
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
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
    meta_bits = [
        f'<a href="{_e(story.article_url)}" style="color:{_HN_ORANGE};text-decoration:none;">{_e(story.domain)}</a>',
        f'<a href="{_e(story.hn_url)}" style="color:{_HN_ORANGE};text-decoration:none;">{_e(replies)}</a>',
        _e(story.by),
        _time_ago(story.time, now),
    ]
    meta_line = ' <span style="color:#c0c0c0;">&bull;</span> '.join(bit for bit in meta_bits if bit)

    return f"""\
        <tr>
          <td style="padding:16px 20px;border-bottom:1px solid #ececec;background:{'#ffffff' if rank % 2 else '#fbfbf9'};">
            <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td valign="top" width="52" style="padding-right:14px;">
                  <div style="background:#fce9d6;color:#8a4b1a;font-weight:700;font-size:13px;text-align:center;border-radius:6px;padding:6px 0;">{story.score}</div>
                </td>
                <td valign="top">
                  <a href="{_e(story.article_url)}" style="color:#1a1a1a;font-size:16px;font-weight:700;text-decoration:none;line-height:1.35;">{_e(story.title)}</a>
                  <div style="margin-top:5px;font-size:12px;color:#828282;">{meta_line}</div>
                  <div style="margin-top:9px;font-size:14px;color:#3a3a3a;line-height:1.55;">{_e(summary)}</div>
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
    date_label = local_now.strftime("%a, %-d %b %Y")
    time_label = f"{local_now.strftime('%H:%M')} {tz_label or local_now.strftime('%Z')}".rstrip()

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
<body style="margin:0;padding:0;background:#f2f2f2;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#f2f2f2;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" width="640" style="max-width:640px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
          <tr>
            <td style="background:{_HN_ORANGE};padding:14px 20px;">
              <span style="color:#ffffff;font-size:18px;font-weight:800;letter-spacing:.2px;">Hacker News Daily</span>
              <span style="color:#ffe9d6;font-size:13px;float:right;padding-top:4px;">{date_label} &middot; {time_label}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 20px 4px;">
              <span style="font-size:15px;font-weight:700;color:#333;">{len(stories)} Top Stories</span>
            </td>
          </tr>
          {rows}
          <tr>
            <td style="padding:18px 20px;background:#fafafa;border-top:1px solid #ececec;">
              <div style="font-size:12px;color:#9a9a9a;line-height:1.6;">
                Generated {_e(_fmt_dt(now, tz, tz_label))} from the
                <a href="https://news.ycombinator.com/news" style="color:{_HN_ORANGE};text-decoration:none;">Hacker News</a>
                top-stories API, with summaries by Google Gemini.
                Ages like &ldquo;3h ago&rdquo; are relative to that time.{next_run_html}<br>
                Source: <a href="https://github.com/pyxelr/hackernews-daily-digest" style="color:{_HN_ORANGE};text-decoration:none;">github.com/pyxelr/hackernews-daily-digest</a>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_subject(stories: list[Story], now: datetime | None = None) -> str:
    now = now or datetime.now(tz=timezone.utc)
    top = stories[0].title if stories else "Top Stories"
    return f"HN Daily · {len(stories)} stories · {top[:60]}"
