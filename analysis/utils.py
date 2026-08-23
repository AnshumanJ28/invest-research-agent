"""Shared helpers for the Analysis layer: safe math, missing-data handling,
and the adapter from ingestion's real CitationMetadata to analysis's SourceRef."""

from __future__ import annotations

from typing import Any, Optional

from .schemas import SourceRef


def safe_divide(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """Returns None (never raises, never returns inf/nan) when either input
    is missing or the denominator is zero. Callers use this result to decide
    `computable=False` rather than propagating a crash or a silent 0.0."""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    try:
        result = numerator / denominator
    except (TypeError, ZeroDivisionError):
        return None
    if result != result:  # NaN
        return None
    return result


def line_item_value(line_items: list[Any], name: str) -> Optional[float]:
    """Look up a FinancialLineItem-like object's value by name from a list.
    Works against both real ingestion.schemas.FinancialLineItem objects and
    plain dicts (used in tests), so analysis code doesn't hard-depend on the
    exact ingestion class."""
    for item in line_items:
        item_name = item.name if hasattr(item, "name") else item.get("name")
        if item_name == name:
            return item.value if hasattr(item, "value") else item.get("value")
    return None


def to_source_ref(metadata: Any) -> SourceRef:
    """Adapt ingestion.schemas.CitationMetadata (or an equivalent dict/object)
    into analysis.schemas.SourceRef. This is the one place that needs to
    change if/when Role 1's real schema shape shifts -- ratios.py, sentiment.py,
    and competitors.py never touch ingestion metadata directly."""
    if hasattr(metadata, "model_dump"):
        data = metadata.model_dump()
    elif isinstance(metadata, dict):
        data = metadata
    elif hasattr(metadata, "__dict__"):
        # Covers SimpleNamespace and other plain attribute-holders used in
        # tests/smoke scripts that don't want a full pydantic dependency.
        data = vars(metadata)
    else:
        raise TypeError(f"Cannot adapt metadata of type {type(metadata)} to SourceRef")

    document_type = data.get("document_type")
    if hasattr(document_type, "value"):
        document_type = document_type.value

    return SourceRef(
        ticker=data["ticker"],
        document_type=str(document_type),
        source_url=data.get("source_url"),
        section_id=data.get("section_id"),
        as_of_date=data.get("as_of_date"),
    )
