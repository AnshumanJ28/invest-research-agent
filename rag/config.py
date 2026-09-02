"""Configuration helpers for the Role 3 RAG pipeline."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .embeddings import DEFAULT_MODEL_NAME
from .llm_client import DEFAULT_GEMINI_MODEL, load_local_env

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAG_DB_PATH = PROJECT_ROOT / "cpp_pipeline" / "invest.sqlite"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "rag" / "output"


class ConfigError(ValueError):
    """Raised for invalid runtime configuration."""


@dataclass(frozen=True)
class RAGConfig:
    ticker: str
    db_path: Path
    output_root: Path
    embedding_model: str
    gemini_model: str
    top_k: int
    enable_verification: bool
    verify_batch_size: int

    @property
    def ticker_output_dir(self) -> Path:
        return self.output_root / self.ticker


def load_config(ticker: str) -> RAGConfig:
    load_local_env(PROJECT_ROOT / ".env")
    normalized = normalize_ticker(ticker)
    return RAGConfig(
        ticker=normalized,
        db_path=_resolve_project_path(os.environ.get("RAG_DB_PATH"), DEFAULT_RAG_DB_PATH),
        output_root=_resolve_project_path(os.environ.get("RAG_OUTPUT_DIR"), DEFAULT_OUTPUT_ROOT),
        embedding_model=os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL_NAME),
        gemini_model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        top_k=_env_int("RAG_TOP_K", 5),
        enable_verification=_env_bool("ENABLE_VERIFICATION", True),
        verify_batch_size=_env_int("VERIFY_BATCH_SIZE", 1),
    )


def normalize_ticker(ticker: str) -> str:
    value = (ticker or "").strip().upper()
    if not value:
        raise ConfigError("Ticker is required.")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,24}", value):
        raise ConfigError(f"Invalid ticker: {ticker!r}")
    return value


def validate_db_path(db_path: Path) -> None:
    if not db_path.exists():
        raise ConfigError(
            f"invest.sqlite was not found at {db_path}. Run the C++ ingestion/analysis pipeline first."
        )


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def _resolve_project_path(raw: str | None, default: Path) -> Path:
    path = Path(raw) if raw else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
