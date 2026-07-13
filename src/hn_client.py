"""Client for the official Hacker News Firebase API.

Docs: https://github.com/HackerNews/API  (no auth, no rate limits, free forever).
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"

_session = requests.Session()
_session.headers.update({"User-Agent": "hackernews-daily-digest (+https://github.com/pyxelr)"})

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Story:
    id: int
    title: str
    score: int
    by: str
    time: int
    descendants: int  # total comment count
    url: str | None  # external article URL (None for Ask/Show self-posts)
    kids: list[int] = field(default_factory=list)

    @property
    def hn_url(self) -> str:
        return HN_ITEM_URL.format(id=self.id)

    @property
    def article_url(self) -> str:
        # Self-posts (Ask HN, etc.) have no external URL -> point at the thread.
        return self.url or self.hn_url

    @property
    def domain(self) -> str:
        source = self.url or self.hn_url
        netloc = urlparse(source).netloc
        return netloc[4:] if netloc.startswith("www.") else netloc


def _get_json(path: str, timeout: int = 15):
    resp = _session.get(f"{API_BASE}/{path}", timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_top_story_ids(limit: int) -> list[int]:
    """Return the top `limit` story IDs, already ranked by HN."""
    ids = _get_json("topstories.json") or []
    return ids[:limit]


def get_item(item_id: int) -> dict | None:
    try:
        return _get_json(f"item/{item_id}.json")
    except requests.RequestException:
        return None


def get_stories(limit: int, min_score: int = 0) -> list[Story]:
    """Fetch and hydrate the top stories, filtered by score and ranked."""
    ids = get_top_story_ids(limit * 2 if min_score else limit)

    with ThreadPoolExecutor(max_workers=12) as pool:
        items = list(pool.map(get_item, ids))

    stories: list[Story] = []
    for item in items:
        if not item or item.get("type") != "story" or item.get("dead") or item.get("deleted"):
            continue
        score = item.get("score", 0)
        if score < min_score:
            continue
        stories.append(
            Story(
                id=item["id"],
                title=item.get("title", "(untitled)"),
                score=score,
                by=item.get("by", "unknown"),
                time=item.get("time", 0),
                descendants=item.get("descendants", 0),
                url=item.get("url"),
                kids=item.get("kids", []),
            )
        )
        if len(stories) >= limit:
            break

    return stories


def _clean_comment(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("<p>", "\n")
    text = _TAG_RE.sub("", text)
    return text.strip()


def get_top_comments(story: Story, max_comments: int) -> list[str]:
    """Return cleaned text of the top-level comments (best-effort)."""
    if not story.kids or max_comments <= 0:
        return []

    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(get_item, story.kids[: max_comments * 2]))

    comments: list[str] = []
    for item in items:
        if not item or item.get("deleted") or item.get("dead"):
            continue
        raw = item.get("text")
        if not raw:
            continue
        cleaned = _clean_comment(raw)
        if cleaned:
            comments.append(cleaned)
        if len(comments) >= max_comments:
            break
    return comments
