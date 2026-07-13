"""Generate a brief digest summary for each story using Google Gemini.

Uses the current unified `google-genai` SDK. The prompt blends the article text
(when available) with the top HN comments so the summary captures both what the
piece says and how the community reacted -- mirroring the reference newsletter.
"""

from __future__ import annotations

import time

from google import genai
from google.genai import errors as genai_errors

from .hn_client import Story

_PROMPT_TEMPLATE = """\
You write one-paragraph summaries for a "Hacker News Daily" email digest.

Write a single, information-dense paragraph (2-3 sentences, max ~60 words) about \
the story below. First convey what the article/story is about, then briefly note \
the tone or split of the Hacker News discussion (e.g. "commenters are split", \
"HN praises X but warns Y"). Be concrete and neutral. Do NOT start with the \
title, do NOT use markdown, do NOT add a preamble like "This article" -- just the \
summary text.

TITLE: {title}

ARTICLE CONTENT (may be empty or truncated):
{article}

TOP HACKER NEWS COMMENTS (may be empty):
{comments}
"""


class Summarizer:
    def __init__(self, api_key: str, model: str, delay: float, max_retries: int):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._delay = delay
        self._max_retries = max_retries

    def _generate(self, prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = self._client.models.generate_content(model=self._model, contents=prompt)
                text = (resp.text or "").strip()
                if text:
                    return text
                last_error = RuntimeError("empty response")
            except genai_errors.APIError as exc:
                last_error = exc
                # 429 (rate limit) / 5xx -> back off and retry.
                status = getattr(exc, "code", None)
                if status not in (429, 500, 502, 503, 504):
                    break
            except Exception as exc:  # network hiccup, etc.
                last_error = exc

            backoff = self._delay * (2**attempt)
            print(f"    Gemini retry {attempt + 1}/{self._max_retries} in {backoff:.0f}s ({last_error})")
            time.sleep(backoff)

        raise RuntimeError(f"Gemini failed after {self._max_retries} attempts: {last_error}")

    def summarize(self, story: Story, article_text: str, comments: list[str]) -> str:
        comment_block = "\n\n".join(f"- {c[:600]}" for c in comments) or "(none)"
        prompt = _PROMPT_TEMPLATE.format(
            title=story.title,
            article=article_text or "(could not fetch article content)",
            comments=comment_block,
        )
        return self._generate(prompt)

    def summarize_all(self, jobs: list[tuple[Story, str, list[str]]]) -> dict[int, str]:
        """Summarize every story sequentially, pacing calls for the free tier.

        Returns {story_id: summary}. On failure for a single story, falls back to
        a minimal summary so one bad story never breaks the whole digest.
        """
        summaries: dict[int, str] = {}
        total = len(jobs)
        for index, (story, article_text, comments) in enumerate(jobs, start=1):
            print(f"  [{index}/{total}] Summarizing: {story.title[:70]}")
            try:
                summaries[story.id] = self.summarize(story, article_text, comments)
            except Exception as exc:
                print(f"    ! Falling back for story {story.id}: {exc}")
                summaries[story.id] = (
                    f"{story.title} — {story.score} points, {story.descendants} comments on "
                    "Hacker News. (AI summary unavailable.)"
                )
            if index < total and self._delay > 0:
                time.sleep(self._delay)
        return summaries
