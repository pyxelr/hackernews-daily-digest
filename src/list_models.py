"""List the Gemini models your API key can use for text generation.

Run it to discover a valid value for GEMINI_MODEL (handy when a model gets
deprecated or restricted):

    GEMINI_API_KEY=your-key python -m src.list_models
"""

from __future__ import annotations

from google import genai

from .config import config


def main() -> int:
    if not config.gemini_api_key:
        raise SystemExit("Set GEMINI_API_KEY (e.g. in .env) before running.")

    client = genai.Client(api_key=config.gemini_api_key)
    print("Models supporting generateContent:\n")
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if "generateContent" in actions:
            # model.name looks like "models/gemini-2.0-flash"; strip the prefix.
            name = model.name.split("/", 1)[-1]
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
