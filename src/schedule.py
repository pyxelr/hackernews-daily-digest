"""Work out when the next scheduled run will happen.

To avoid drift, the cron expression is read straight from the workflow file
(the single source of truth) rather than duplicated in config. Only a small,
common subset of cron is supported (enough for a daily/weekly digest); anything
fancier just yields ``None`` and the "next run" line is omitted.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _PROJECT_ROOT / ".github" / "workflows" / "daily-digest.yml"

_CRON_RE = re.compile(r"^\s*-?\s*cron:\s*['\"]?([^'\"#\n]+?)['\"]?\s*$", re.MULTILINE)

# (min, max) inclusive ranges for each cron field.
_FIELD_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def read_crons(path: Path | None = None) -> list[str]:
    """Return every ``cron:`` expression from the workflow file."""
    wf = path or _WORKFLOW
    try:
        text = wf.read_text(encoding="utf-8")
    except OSError:
        return []
    return [m.strip() for m in _CRON_RE.findall(text)]


def read_cron(path: Path | None = None) -> str | None:
    """Return the first ``cron:`` expression from the workflow file, if any."""
    crons = read_crons(path)
    return crons[0] if crons else None


def _parse_field(field: str, lo: int, hi: int) -> set[int] | None:
    """Parse one cron field into the set of matching integers."""
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, _, step_s = part.partition("/")
            if not step_s.isdigit():
                return None
            step = int(step_s)
        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part:
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                return None
            start, end = int(a), int(b)
        elif part.isdigit():
            start = end = int(part)
        else:
            return None
        values.update(v for v in range(start, end + 1, step) if lo <= v <= hi)
    return values or None


def next_run_utc(cron: str | None, after: datetime) -> datetime | None:
    """Return the next UTC datetime matching ``cron`` strictly after ``after``.

    Supports ``*``, single values, ranges (``a-b``), lists (``a,b``) and steps
    (``*/n``). Returns ``None`` for unsupported expressions.
    """
    if not cron:
        return None
    fields = cron.split()
    if len(fields) != 5:
        return None

    parsed: list[set[int]] = []
    for raw, (lo, hi) in zip(fields, _FIELD_RANGES):
        vals = _parse_field(raw, lo, hi)
        if vals is None:
            return None
        parsed.append(vals)
    minutes, hours, doms, months, dows = parsed
    # Cron treats both 0 and 7 as Sunday.
    if 7 in dows:
        dows = (dows - {7}) | {0}

    # Restrict the search space: candidate minutes/hours are small sets.
    cursor = after.astimezone(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(367):  # at most ~a year of days
        day = cursor.date()
        cron_dow = day.isoweekday() % 7  # Mon=1..Sun=7 -> Sun=0..Sat=6
        if day.day in doms and day.month in months and cron_dow in dows:
            for hour in sorted(hours):
                for minute in sorted(minutes):
                    candidate = datetime(
                        day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc
                    )
                    if candidate > after:
                        return candidate
        # Advance to the start of the next day.
        cursor = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
    return None


def next_effective_run(
    after: datetime,
    tz_name: str = "UTC",
    guard_local_hour: int | None = None,
    path: Path | None = None,
) -> datetime | None:
    """Next run that will actually send, across all workflow crons.

    With the DST guard, several UTC crons are scheduled but only the one landing
    on ``guard_local_hour`` in ``tz_name`` proceeds. This returns the earliest
    upcoming run that passes that guard (or just the earliest run if no guard).
    """
    candidates = [
        run for cron in read_crons(path) if (run := next_run_utc(cron, after)) is not None
    ]
    if not candidates:
        return None

    if guard_local_hour is not None:
        try:
            tz = ZoneInfo(tz_name)
            matching = [c for c in candidates if c.astimezone(tz).hour == guard_local_hour]
            if matching:
                candidates = matching
        except (ZoneInfoNotFoundError, ValueError):
            pass

    return min(candidates)
