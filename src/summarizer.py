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
        request_timeout: int = 90,
        deadline_seconds: int = 600,
    ):
        # HttpOptions.timeout is in *milliseconds*. It must be set explicitly:
        # the SDK's default of None means httpx never gives up on a stalled
        # response, which is how a single bad request can burn a whole CI job.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=max(1, request_timeout) * 1000),
        )
        self._model = model
        self._delay = delay
        self._max_retries = max(1, max_retries)
        self._batch_size = max(1, batch_size)
        self._deadline_seconds = max(1, deadline_seconds)
        self._logged_version = False

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

    def _generate_batch(self, prompt: str, deadline: float) -> list[dict]:
        """Summarize one batch, retrying transient errors until ``deadline``.

        ``deadline`` is a ``time.monotonic()`` reading shared by every batch, so
        a slow Gemini eats into the retry budget of later batches rather than
        multiplying it: total time here is bounded no matter how badly the API
        misbehaves.
        """
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
                # A model ID can be an alias (e.g. "-latest") that resolves to a
                # dated build, so log what actually served the first request --
                # the only reliable record of which model wrote the summaries.
                if not self._logged_version:
                    self._logged_version = True
                    served = getattr(resp, "model_version", None)
                    print(f"    Requested '{self._model}', served by '{served or 'unknown'}'")
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

            # Sleeping after the final attempt just burns time -- nothing will
            # consume the result.
            if attempt == self._max_retries - 1:
                break

            backoff = max(self._delay, 4) * (2**attempt)
            remaining = deadline - time.monotonic()
            if backoff >= remaining:
                raise RuntimeError(
                    f"Gemini batch abandoned after {attempt + 1} attempt(s): next retry needs "
                    f"{backoff:.0f}s but only {max(remaining, 0):.0f}s of budget is left "
                    f"(last error: {last_error})"
                )
            print(
                f"    Gemini retry {attempt + 1}/{self._max_retries - 1} in {backoff:.0f}s ({last_error})"
            )
            time.sleep(backoff)

        raise RuntimeError(f"Gemini batch failed after {self._max_retries} attempts: {last_error}")

    def summarize_all(self, jobs: list[tuple[Story, str, list[str]]]) -> dict[int, str]:
        """Summarize every story in batches. Returns {story_id: summary}.

        A failed batch falls back to minimal per-story summaries so one bad batch
        never breaks the whole digest. The phase as a whole is bounded by
        ``deadline_seconds``: once that budget is gone the remaining batches skip
        Gemini entirely and take the fallback, because a digest with some
        placeholder summaries beats no digest at all.
        """
        summaries: dict[int, str] = {}
        indexed = list(enumerate(jobs))  # global index -> (story, text, comments)
        batches = [
            indexed[i : i + self._batch_size] for i in range(0, len(indexed), self._batch_size)
        ]
        deadline = time.monotonic() + self._deadline_seconds

        for batch_no, chunk in enumerate(batches, start=1):
            batch = [(idx, s, t, c) for idx, (s, t, c) in chunk]

            if time.monotonic() >= deadline:
                skipped = batches[batch_no - 1 :]
                print(
                    f"  ! Out of time after {self._deadline_seconds}s; falling back on the "
                    f"last {len(skipped)} of {len(batches)} batches"
                )
                for rest in skipped:
                    for _, (story, _, _) in rest:
                        summaries[story.id] = _fallback_summary(story)
                break

            titles = ", ".join(s.title[:30] for _, s, _, _ in batch[:2])
            print(f"  Batch {batch_no}/{len(batches)} ({len(batch)} stories): {titles}...")

            try:
                results = self._generate_batch(self._build_batch_prompt(batch), deadline)
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
                # Never let the free-tier pacing sleep push us past the budget.
                time.sleep(min(self._delay, max(deadline - time.monotonic(), 0)))

        return summaries
