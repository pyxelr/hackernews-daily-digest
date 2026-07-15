"""Generate brief digest summaries for stories using Google Gemini.

Uses the current unified `google-genai` SDK. To stay well under the free-tier
per-minute request limits, stories are summarized in *batches*: one request
returns summaries for several stories at once (structured JSON output), so 30
stories cost ~4 requests instead of 30.

The prompt blends each article's text (when available) with its top HN comments
so the summary captures both what the piece says and how the community reacted --
mirroring the reference newsletter.
"""

from __future__ import annotations

import json
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .hn_client import Story

_SYSTEM_INSTRUCTION = """\
You write very short summaries for a "Hacker News Daily" email digest.

For each story, write 1-2 sentences (about 45 words, up to two lines). First say \
what the story is about, then briefly note the mood of the discussion. Refer to \
the community only as "HN" or "Commenters" (e.g. "HN is split", "Commenters \
praise X but warn Y"); never write "Hacker News readers" or "Hacker News \
commenters". Be concrete and neutral. Do NOT start with the title, do NOT use \
markdown, and do NOT add a preamble like "This article"; just the summary text.

Return one summary per input story, matched by its index.
"""

# Structured-output schema: a JSON array of {index, summary}.
_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "index": types.Schema(type=types.Type.INTEGER),
            "summary": types.Schema(type=types.Type.STRING),
        },
        required=["index", "summary"],
    ),
)


def _fallback_summary(story: Story) -> str:
    return "(summary unavailable)"


class Summarizer:
    def __init__(
        self,
        api_key: str,
        model: str,
        delay: float,
        max_retries: int,
        batch_size: int = 8,
    ):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._delay = delay
        self._max_retries = max_retries
        self._batch_size = max(1, batch_size)

    def _build_batch_prompt(self, batch: list[tuple[int, Story, str, list[str]]]) -> str:
        parts: list[str] = ["Summarize each of the following stories.\n"]
        for index, story, article_text, comments in batch:
            comment_block = "\n".join(f"  - {c[:500]}" for c in comments) or "  (none)"
            parts.append(
                f"=== STORY index={index} ===\n"
                f"TITLE: {story.title}\n"
                f"ARTICLE CONTENT (may be empty/truncated):\n{article_text[:5000] or '(none)'}\n"
                f"TOP HN COMMENTS:\n{comment_block}\n"
            )
        return "\n".join(parts)

    def _generate_batch(self, prompt: str) -> list[dict]:
        last_error: Exception | None = None
        config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        )
        for attempt in range(self._max_retries):
            try:
                resp = self._client.models.generate_content(
                    model=self._model, contents=prompt, config=config
                )
                data = json.loads(resp.text or "[]")
                if isinstance(data, list):
                    return data
                last_error = RuntimeError("response was not a JSON array")
            except genai_errors.APIError as exc:
                last_error = exc
                status = getattr(exc, "code", None)
                if status not in (429, 500, 502, 503, 504):
                    break  # 404 (bad model) etc. -> no point retrying
            except Exception as exc:
                last_error = exc

            backoff = max(self._delay, 4) * (2**attempt)
            print(f"    Gemini retry {attempt + 1}/{self._max_retries} in {backoff:.0f}s ({last_error})")
            time.sleep(backoff)

        raise RuntimeError(f"Gemini batch failed after {self._max_retries} attempts: {last_error}")

    def summarize_all(self, jobs: list[tuple[Story, str, list[str]]]) -> dict[int, str]:
        """Summarize every story in batches. Returns {story_id: summary}.

        A failed batch falls back to minimal per-story summaries so one bad batch
        never breaks the whole digest.
        """
        summaries: dict[int, str] = {}
        indexed = list(enumerate(jobs))  # global index -> (story, text, comments)
        batches = [
            indexed[i : i + self._batch_size] for i in range(0, len(indexed), self._batch_size)
        ]

        for batch_no, chunk in enumerate(batches, start=1):
            batch = [(idx, s, t, c) for idx, (s, t, c) in chunk]
            titles = ", ".join(s.title[:30] for _, s, _, _ in batch[:2])
            print(f"  Batch {batch_no}/{len(batches)} ({len(batch)} stories): {titles}...")

            try:
                results = self._generate_batch(self._build_batch_prompt(batch))
                by_index = {
                    int(r["index"]): str(r["summary"]).strip()
                    for r in results
                    if isinstance(r, dict) and "index" in r and r.get("summary")
                }
            except Exception as exc:
                print(f"    ! Batch {batch_no} failed, using fallbacks: {exc}")
                by_index = {}

            for index, story, _, _ in batch:
                summary = by_index.get(index)
                summaries[story.id] = summary if summary else _fallback_summary(story)

            if batch_no < len(batches) and self._delay > 0:
                time.sleep(self._delay)

        return summaries
