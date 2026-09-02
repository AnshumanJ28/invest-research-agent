import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.config import ConfigError, PROJECT_ROOT, load_config, normalize_ticker, validate_db_path  # noqa: E402


def test_normalize_ticker_uppercases_valid_ticker():
    assert normalize_ticker("reliance.ns") == "RELIANCE.NS"


def test_normalize_ticker_rejects_shell_punctuation():
    try:
        normalize_ticker("RELIANCE.NS && bad")
    except ConfigError as exc:
        assert "Invalid ticker" in str(exc)
    else:
        raise AssertionError("Expected ConfigError")


def test_relative_env_paths_resolve_from_project_root(monkeypatch):
    monkeypatch.setenv("RAG_DB_PATH", "cpp_pipeline/invest.sqlite")
    monkeypatch.setenv("RAG_OUTPUT_DIR", "rag/output")

    config = load_config("RELIANCE.NS")

    assert config.db_path == (PROJECT_ROOT / "cpp_pipeline" / "invest.sqlite").resolve()
    assert config.output_root == (PROJECT_ROOT / "rag" / "output").resolve()


def test_validate_db_path_reports_missing_file(tmp_path):
    missing = tmp_path / "missing.sqlite"

    try:
        validate_db_path(missing)
    except ConfigError as exc:
        assert "invest.sqlite was not found" in str(exc)
    else:
        raise AssertionError("Expected ConfigError")
