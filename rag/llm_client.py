"""Gemini client wrapper for memo generation.

The wrapper keeps provider details out of RAG orchestration and makes tests easy
to run with a mock client. It never prints or returns the API key.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_MAX_OUTPUT_TOKENS = 8192


class GeminiClientError(RuntimeError):
    """Raised when Gemini generation cannot complete."""


class MissingGeminiAPIKey(GeminiClientError):
    """Raised when GEMINI_API_KEY is not configured."""


def load_local_env(env_path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE pairs without requiring python-dotenv."""

    path = Path(env_path)
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class GeminiLLMClient:
    """Minimal Gemini text/JSON generation client."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_output_tokens: int | None = None,
    ):
        load_local_env()
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.max_output_tokens = int(
            max_output_tokens
            or os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)
        )
        self._client = None

    @property
    def client(self):
        if not self.api_key:
            raise MissingGeminiAPIKey("GEMINI_API_KEY is not set.")
        if self._client is None:
            _add_local_dependency_path()
            try:
                from google import genai
            except ImportError as exc:
                raise GeminiClientError(
                    "google-genai is required. Install with: py -3.10 -m pip install google-genai"
                ) from exc
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate_json(self, prompt: str, *, response_schema=None) -> str:
        """Generate JSON text from Gemini."""

        _add_local_dependency_path()
        try:
            from google.genai import types
        except ImportError as exc:
            raise GeminiClientError(
                "google-genai is required. Install with: py -3.10 -m pip install google-genai"
            ) from exc

        try:
            config_kwargs = {
                "response_mime_type": "application/json",
                "max_output_tokens": self.max_output_tokens,
            }
            if response_schema is not None:
                config_kwargs["response_schema"] = response_schema
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except MissingGeminiAPIKey:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GeminiClientError(f"Gemini generation failed: {exc}") from exc

        if not getattr(response, "text", None):
            raise GeminiClientError("Gemini returned an empty response.")
        return response.text


def _add_local_dependency_path() -> None:
    dep_path = Path(__file__).resolve().parent / ".deps"
    if dep_path.exists():
        dep_str = str(dep_path)
        if dep_str not in sys.path:
            sys.path.insert(0, dep_str)
