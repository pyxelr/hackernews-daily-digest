"""Central configuration, loaded from environment variables.

All secrets (Gemini key, Gmail credentials) come from the environment so the
same code runs locally (via a .env file) and in GitHub Actions (via secrets).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Load a local .env when present. In GitHub Actions there is no .env file and
# the values come from repository secrets, so a missing file is not an error.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is a dev convenience only; not required in CI.
    pass


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # --- AI (Google Gemini) ---
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

    # --- Email (Gmail SMTP) ---
    gmail_username: str = field(default_factory=lambda: os.getenv("GMAIL_USERNAME", ""))
    gmail_app_password: str = field(default_factory=lambda: os.getenv("GMAIL_APP_PASSWORD", ""))
    # Comma-separated list of recipients. Defaults to sending to yourself.
    recipients_raw: str = field(default_factory=lambda: os.getenv("RECIPIENTS", ""))

    # --- Digest behaviour ---
    num_stories: int = field(default_factory=lambda: _get_int("NUM_STORIES", 30))
    # Only include stories with at least this score (0 = no filter).
    min_score: int = field(default_factory=lambda: _get_int("MIN_SCORE", 0))
    # How many top comments to feed the summarizer for sentiment context.
    max_comments: int = field(default_factory=lambda: _get_int("MAX_COMMENTS", 6))

    # --- Article fetching ---
    fetch_articles: bool = field(default_factory=lambda: _get_bool("FETCH_ARTICLES", True))
    article_timeout: int = field(default_factory=lambda: _get_int("ARTICLE_TIMEOUT", 12))
    article_char_limit: int = field(default_factory=lambda: _get_int("ARTICLE_CHAR_LIMIT", 6000))
    fetch_workers: int = field(default_factory=lambda: _get_int("FETCH_WORKERS", 8))

    # --- Gemini rate limiting (free tier is a few requests/minute) ---
    request_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_DELAY_SECONDS", "6"))
    )
    max_retries: int = field(default_factory=lambda: _get_int("MAX_RETRIES", 4))

    # --- Run mode ---
    # When true, write the rendered email to output/ instead of sending it.
    dry_run: bool = field(default_factory=lambda: _get_bool("DRY_RUN", False))

    @property
    def recipients(self) -> list[str]:
        raw = self.recipients_raw.strip()
        if not raw:
            # Default: email yourself.
            return [self.gmail_username] if self.gmail_username else []
        return [addr.strip() for addr in raw.split(",") if addr.strip()]

    def validate(self, *, require_email: bool = True) -> None:
        """Raise a clear error if required settings are missing."""
        missing: list[str] = []
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if require_email:
            if not self.gmail_username:
                missing.append("GMAIL_USERNAME")
            if not self.gmail_app_password:
                missing.append("GMAIL_APP_PASSWORD")
            if not self.recipients:
                missing.append("RECIPIENTS (or GMAIL_USERNAME as fallback)")
        if missing:
            raise SystemExit(
                "Missing required configuration: "
                + ", ".join(missing)
                + "\nSet them as environment variables (or in a local .env file). "
                "See .env.example."
            )


config = Config()
