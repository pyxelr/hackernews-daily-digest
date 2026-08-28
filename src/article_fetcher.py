"""Best-effort extraction of readable text from an article URL.

This is intentionally lightweight (requests + BeautifulSoup). Many pages will be
paywalled, JS-only, PDFs, or videos; when extraction fails we simply return an
empty string and the summarizer falls back to the title + HN comments.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

_STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]

# requests' `timeout` bounds each individual socket operation, not the call as a
# whole: a server that dribbles out a byte just inside the limit keeps a worker
# alive forever. Streaming the body under a hard wall-clock deadline and a size
# cap makes every fetch genuinely bounded, which in turn bounds `fetch_many`.
_DEADLINE_FACTOR = 3  # hard per-URL cap = timeout * this
_MAX_BODY_BYTES = 2_000_000  # no article needs more; stops accidental huge downloads
_CHUNK_BYTES = 16_384


def fetch_article_text(url: str, timeout: int, char_limit: int) -> str:
    if not url:
        return ""

    deadline = time.monotonic() + timeout * _DEADLINE_FACTOR
    try:
        resp = requests.get(
            url, headers=_HEADERS, timeout=timeout, allow_redirects=True, stream=True
        )
        resp.raise_for_status()
    except requests.RequestException:
        return ""

    with resp:
        content_type = resp.headers.get("Content-Type", "").lower()
        if "html" not in content_type:
            # PDFs, images, video pages, etc. -> nothing useful to parse.
            return ""

        chunks: list[bytes] = []
        size = 0
        try:
            for chunk in resp.iter_content(_CHUNK_BYTES):
                chunks.append(chunk)
                size += len(chunk)
                if size >= _MAX_BODY_BYTES or time.monotonic() >= deadline:
                    break
        except requests.RequestException:
            return ""

    try:
        # Passing bytes lets BeautifulSoup sniff the encoding from the <meta>
        # charset, which is more accurate than requests' header-only guess.
        soup = BeautifulSoup(b"".join(chunks), "html.parser")
    except Exception:
        return ""

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    # Prefer the semantic <article>/<main> region when present.
    region = soup.find("article") or soup.find("main") or soup.body or soup
    text = region.get_text(separator=" ", strip=True)
    text = " ".join(text.split())
    return text[:char_limit]


def fetch_many(urls: list[str], timeout: int, char_limit: int, workers: int) -> dict[str, str]:
    """Fetch several URLs concurrently. Returns {url: extracted_text}."""

    def _fetch(url: str) -> tuple[str, str]:
        return url, fetch_article_text(url, timeout, char_limit)

    results: dict[str, str] = {}
    unique = [u for u in dict.fromkeys(urls) if u]
    if not unique:
        return results
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for url, text in pool.map(_fetch, unique):
            results[url] = text
    return results
